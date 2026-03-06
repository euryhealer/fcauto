import typing as _t

# Patch ForwardRef for Python 3.12 + pydantic v1 compatibility
if hasattr(_t, "ForwardRef") and hasattr(_t.ForwardRef, "_evaluate"):
    _orig_fr_eval = _t.ForwardRef._evaluate

    def _patched_fr_eval(self, globalns, localns, type_params=None, recursive_guard=None):
        return _orig_fr_eval(
            self,
            globalns,
            localns,
            type_params,
            recursive_guard=recursive_guard or set(),
        )

    _t.ForwardRef._evaluate = _patched_fr_eval

from fastapi import (
    FastAPI,
    BackgroundTasks,
    UploadFile,
    File,
    Depends,
    HTTPException,
    Form,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import io
import pandas as pd
from sqlalchemy import delete, inspect, text, func
import re
from pathlib import Path
from uuid import uuid4
from typing import Optional

from app import db
from app import models, schemas
from app.services.sync_runner import SyncRunner, get_sync_runner
from app.services import drive

app = FastAPI(title="Woo Sync MVP")
LOCAL_SUBGROUP_UPLOADS = (
    Path(__file__).resolve().parent.parent / "uploads" / "subgroups"
)
LOCAL_UPLOADS_ROOT = Path(__file__).resolve().parent.parent / "uploads"
LOCAL_ASSETS_IMG_ROOT = LOCAL_UPLOADS_ROOT / "assets" / "img"
LOCAL_UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)
LOCAL_ASSETS_IMG_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=LOCAL_UPLOADS_ROOT), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@app.on_event("startup")
def startup():
    db.Base.metadata.create_all(bind=db.engine)
    # Backward-compatible column add for existing DBs.
    insp = inspect(db.engine)
    var_cols = {c["name"] for c in insp.get_columns("products_variation")}
    if "group_name" not in var_cols:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE products_variation ADD COLUMN group_name VARCHAR"))
    if "additional_price" not in var_cols:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE products_variation ADD COLUMN additional_price VARCHAR"))
    parent_cols = {c["name"] for c in insp.get_columns("products_parent")}
    if "brand" not in parent_cols:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE products_parent ADD COLUMN brand VARCHAR"))


@app.get("/")
def root():
    return {"ok": True, "service": "Woo Sync API", "docs": "/docs", "base": "/api"}


@app.get("/api/config", response_model=schemas.AppConfigOut)
def get_config(session: Session = Depends(get_db)):
    cfg = session.query(models.AppConfig).first()
    if not cfg:
        cfg = models.AppConfig()
        session.add(cfg)
        session.commit()
        session.refresh(cfg)
    return schemas.AppConfigOut.from_orm(cfg)


@app.post("/api/config", response_model=schemas.AppConfigOut)
def save_config(payload: schemas.AppConfigIn, session: Session = Depends(get_db)):
    cfg = session.query(models.AppConfig).first()
    if not cfg:
        cfg = models.AppConfig()
        session.add(cfg)
    for field, value in payload.dict().items():
        setattr(cfg, field, value)
    session.commit()
    session.refresh(cfg)
    return schemas.AppConfigOut.from_orm(cfg)


@app.post("/api/test/drive")
def test_drive(session: Session = Depends(get_db)):
    cfg = session.query(models.AppConfig).first()
    if not cfg or not cfg.drive_folder_id:
        raise HTTPException(status_code=400, detail="drive_folder_id missing")
    client = drive.get_drive_client()
    files = drive.list_folder_files(client, cfg.drive_folder_id, page_size=5)
    return {"ok": True, "count": len(files)}


@app.post("/api/test/woo")
def test_woo():
    return {"ok": True}


@app.post("/api/test/wp")
def test_wp():
    return {"ok": True}


@app.post("/api/import")
def import_excel(file: UploadFile = File(...), session: Session = Depends(get_db)):
    try:
        content = file.file.read()
        df = pd.read_excel(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error leyendo Excel: {exc}")
    try:
        summary = SyncRunner.import_rows(df, session)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error importando filas: {exc}")
    return summary


@app.post("/api/sync")
def start_sync(
    background: BackgroundTasks,
    session: Session = Depends(get_db),
    runner: SyncRunner = Depends(get_sync_runner),
):
    sync_run = runner.start(session)
    background.add_task(runner.run, sync_run.id)
    return {"run_id": sync_run.id}


@app.get("/api/sync/{run_id}/status")
def sync_status(
    run_id: int,
    session: Session = Depends(get_db),
    runner: SyncRunner = Depends(get_sync_runner),
):
    run = session.query(models.SyncRun).get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return runner.status(run)


@app.get("/api/sync/{run_id}/logs")
def sync_logs(run_id: int, session: Session = Depends(get_db), limit: int = 100):
    logs = (
        session.query(models.Log)
        .filter(models.Log.sync_run_id == run_id)
        .order_by(models.Log.id.desc())
        .limit(limit)
        .all()
    )
    return [schemas.LogOut.from_orm(l) for l in logs]


@app.get("/api/sync/{run_id}/events")
def sync_events(run_id: int, runner: SyncRunner = Depends(get_sync_runner)):
    return StreamingResponse(
        runner.event_stream(run_id), media_type="text/event-stream"
    )


@app.get("/api/catalog/groups", response_model=schemas.GroupListOut)
def list_groups(session: Session = Depends(get_db)):
    vals = (
        session.query(models.ProductVariation.group_name)
        .filter(models.ProductVariation.group_name.isnot(None))
        .distinct()
        .all()
    )
    groups = sorted([v[0] for v in vals if v and v[0]])
    return schemas.GroupListOut(groups=groups)


@app.get("/api/catalog/parents")
def list_parents(group: str = None, session: Session = Depends(get_db)):
    q = session.query(models.ProductParent)
    if group:
        q = q.join(
            models.ProductVariation,
            models.ProductVariation.parent_sku == models.ProductParent.parent_sku,
        ).filter(models.ProductVariation.group_name == group)
    parents = q.distinct().all()
    count_q = session.query(
        models.ProductVariation.parent_sku,
        func.count(models.ProductVariation.variation_sku),
    )
    if group:
        count_q = count_q.filter(models.ProductVariation.group_name == group)
    counts = {
        sku: total
        for sku, total in count_q.group_by(models.ProductVariation.parent_sku).all()
    }
    return [
        schemas.ParentOut(
            parent_sku=p.parent_sku,
            base_name=p.base_name,
            brand=p.brand,
            woo_product_id=p.woo_product_id,
            sync_status=p.sync_status,
            last_error=p.last_error,
            variations_count=counts.get(p.parent_sku, 0),
            product_kind=(
                "variable product"
                if counts.get(p.parent_sku, 0) > 1
                else "single product"
            ),
        )
        for p in parents
    ]


@app.get("/api/catalog/parents/{parent_sku:path}/variations")
def list_variations(parent_sku: str, group: str = None, session: Session = Depends(get_db)):
    parent = session.query(models.ProductParent).get(parent_sku)
    vars = (
        session.query(models.ProductVariation)
        .filter(models.ProductVariation.parent_sku == parent_sku)
    )
    if group:
        vars = vars.filter(models.ProductVariation.group_name == group)
    vars = vars.all()
    owner_skus = [v.variation_sku for v in vars]
    images = (
        session.query(models.Image)
        .filter(models.Image.owner_sku.in_(owner_skus))
        .all()
        if owner_skus
        else []
    )
    image_map = {img.owner_sku: img.file_name for img in images}
    return [
        schemas.VariationOut(
            variation_sku=v.variation_sku,
            parent_sku=v.parent_sku,
            brand=parent.brand if parent else None,
            group_name=v.group_name,
            color_code=v.color_code,
            size_code=v.size_code,
            name_full=v.name_full,
            price=v.price,
            additional_price=v.additional_price,
            stock_qty=v.stock_qty,
            woo_variation_id=v.woo_variation_id,
            image_file_name=image_map.get(v.variation_sku),
            image_preview_url=resolve_image_preview_url(
                image_map.get(v.variation_sku), parent.brand if parent else None
            ),
            sync_status=v.sync_status,
            last_error=v.last_error,
        )
        for v in vars
    ]


def resolve_image_preview_url(file_name: str, brand: Optional[str]) -> Optional[str]:
    raw = (file_name or "").strip()
    if not raw:
        return None

    if raw.startswith("local://"):
        local_name = Path(raw[len("local://") :]).name
        if not local_name:
            return None
        return f"/uploads/subgroups/{local_name}"

    img_name = Path(raw.replace("\\", "/").split("?", 1)[0]).name
    if not img_name:
        return None

    brand_raw = (brand or "").strip()
    brand_norm = re.sub(r"[^A-Za-z0-9_-]", "_", brand_raw).upper()
    brand_candidates = [b for b in {brand_raw, brand_raw.upper(), brand_norm} if b]
    for candidate_brand in brand_candidates:
        brand_dir = LOCAL_ASSETS_IMG_ROOT / candidate_brand
        if not brand_dir.exists() or not brand_dir.is_dir():
            continue
        exact = brand_dir / img_name
        if exact.exists():
            return f"/uploads/assets/img/{candidate_brand}/{exact.name}"
        lower_target = img_name.lower()
        for entry in brand_dir.iterdir():
            if entry.is_file() and entry.name.lower() == lower_target:
                return f"/uploads/assets/img/{candidate_brand}/{entry.name}"
    return None


def subgroup_key_from_variation_sku(variation_sku: str) -> str:
    sku = (variation_sku or "").strip()
    upper = sku.upper()

    # JJ350-2.0-P special rule:
    # variants are organized by color, not by size.
    # Examples:
    #   JJ350-2.0-P/A0         -> JJ350-2.0-P-WHITE
    #   JJ350-2.0-P/A1-BLK     -> JJ350-2.0-P-BLK
    #   JJ350-2.0-P/A1-BLK/GLD -> JJ350-2.0-P-BLK/GLD
    m_jj350 = re.match(r"^(JJ350-2\.0-P)/[^/-]+(?:-(.+))?$", upper)
    if m_jj350:
        color_token = (m_jj350.group(2) or "WHITE").strip()
        return f"{m_jj350.group(1)}-{color_token}"

    # VENUM special rule:
    # Parent: VENUM-<4|5 digits>
    # Subgroup: VENUM-<4|5 digits>-<3 digits> (color code)
    m_venum = re.match(r"^(VENUM-\d{4,5}-\d{3})(?:[/\-].*)?$", upper)
    if m_venum:
        return m_venum.group(1)

    # EU-VENUM equivalent subgroup shape when present.
    m_eu_venum = re.match(r"^(EU-VENUM-\d{3,4}-\d{3})(?:[/\-].*)?$", upper)
    if m_eu_venum:
        return m_eu_venum.group(1)

    # EU-VENUM black special case: EU-VENUM-0003/<TALLA>
    m_eu_venum_black = re.match(r"^(EU-VENUM-\d{3,4})/[^/]+$", upper)
    if m_eu_venum_black:
        return f"{m_eu_venum_black.group(1)}-NEGRO"

    cut = sku.rfind("-")
    if cut <= 0:
        return sku
    tail = sku[cut + 1 :]
    if re.fullmatch(r"[A-Za-z0-9]+", tail):
        return sku[:cut]
    return sku


@app.post("/api/catalog/subgroup-image", response_model=schemas.SubgroupImageOut)
def set_subgroup_image(
    payload: schemas.SubgroupImageIn, session: Session = Depends(get_db)
):
    file_name = (payload.file_name or "").strip()
    if not file_name:
        raise HTTPException(status_code=400, detail="file_name required")

    vars_for_parent = (
        session.query(models.ProductVariation)
        .filter(models.ProductVariation.parent_sku == payload.parent_sku)
        .all()
    )
    targets = [
        v
        for v in vars_for_parent
        if subgroup_key_from_variation_sku(v.variation_sku) == payload.subgroup_key
    ]
    if not targets:
        raise HTTPException(status_code=404, detail="subgroup not found")

    updated = 0
    for var in targets:
        img = (
            session.query(models.Image)
            .filter(models.Image.owner_sku == var.variation_sku)
            .first()
        )
        if not img:
            img = models.Image(owner_type="variation", owner_sku=var.variation_sku)
            session.add(img)
        img.file_name = file_name
        img.status = "pending"
        img.last_error = None
        img.wp_media_id = None
        img.file_hash = None
        updated += 1

    session.commit()
    return schemas.SubgroupImageOut(ok=True, updated=updated)


@app.post("/api/catalog/subgroup-image/upload", response_model=schemas.SubgroupImageOut)
def upload_subgroup_image(
    parent_sku: str = Form(...),
    subgroup_key: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
):
    original_name = (file.filename or "").strip()
    if not original_name:
        raise HTTPException(status_code=400, detail="file required")

    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", original_name)
    stored_name = f"{uuid4().hex}_{safe_name}"

    LOCAL_SUBGROUP_UPLOADS.mkdir(parents=True, exist_ok=True)
    out_path = LOCAL_SUBGROUP_UPLOADS / stored_name
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    out_path.write_bytes(data)

    vars_for_parent = (
        session.query(models.ProductVariation)
        .filter(models.ProductVariation.parent_sku == parent_sku)
        .all()
    )
    targets = [
        v
        for v in vars_for_parent
        if subgroup_key_from_variation_sku(v.variation_sku) == subgroup_key
    ]
    if not targets:
        raise HTTPException(status_code=404, detail="subgroup not found")

    updated = 0
    for var in targets:
        img = (
            session.query(models.Image)
            .filter(models.Image.owner_sku == var.variation_sku)
            .first()
        )
        if not img:
            img = models.Image(owner_type="variation", owner_sku=var.variation_sku)
            session.add(img)
        img.file_name = f"local://{stored_name}"
        img.status = "pending"
        img.last_error = None
        img.wp_media_id = None
        img.file_hash = None
        updated += 1

    session.commit()
    return schemas.SubgroupImageOut(ok=True, updated=updated)


@app.post("/api/catalog/variation-image/upload", response_model=schemas.SubgroupImageOut)
def upload_variation_image(
    variation_sku: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
):
    original_name = (file.filename or "").strip()
    if not original_name:
        raise HTTPException(status_code=400, detail="file required")

    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", original_name)
    stored_name = f"{uuid4().hex}_{safe_name}"

    LOCAL_SUBGROUP_UPLOADS.mkdir(parents=True, exist_ok=True)
    out_path = LOCAL_SUBGROUP_UPLOADS / stored_name
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    out_path.write_bytes(data)

    var = (
        session.query(models.ProductVariation)
        .filter(models.ProductVariation.variation_sku == variation_sku)
        .first()
    )
    if not var:
        raise HTTPException(status_code=404, detail="variation not found")

    img = (
        session.query(models.Image)
        .filter(models.Image.owner_sku == variation_sku)
        .first()
    )
    if not img:
        img = models.Image(owner_type="variation", owner_sku=variation_sku)
        session.add(img)

    img.file_name = f"local://{stored_name}"
    img.status = "pending"
    img.last_error = None
    img.wp_media_id = None
    img.file_hash = None

    session.commit()
    return schemas.SubgroupImageOut(ok=True, updated=1)


@app.delete("/api/catalog/clear")
def clear_catalog(session: Session = Depends(get_db)):
    # Order matters due to FK
    session.execute(delete(models.Log))
    session.execute(delete(models.SyncRun))
    session.execute(delete(models.Image))
    session.execute(delete(models.MediaHash))
    session.execute(delete(models.ProductVariation))
    session.execute(delete(models.ProductParent))
    session.commit()
    return {"ok": True}
