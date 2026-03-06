import json
import time
import re
import unicodedata
from datetime import datetime
from typing import Dict, Any, Iterable, Optional
from pathlib import Path
import pandas as pd
from sqlalchemy.orm import Session

from app import models
from app.db import SessionLocal
from app.services import drive, wp_media, woo

LOCAL_SUBGROUP_UPLOADS = (
    Path(__file__).resolve().parent.parent.parent / "uploads" / "subgroups"
)
LOCAL_ASSETS_IMG_UPLOADS = (
    Path(__file__).resolve().parent.parent.parent / "uploads" / "assets" / "img"
)

# Central registry for import-time exceptions by parent SKU.
PARENT_SKU_IMPORT_EXCEPTIONS = {
    "ADIRHP01": {
        "pattern": r"^(ADIRHP01)-(.+)-([A-Za-z0-9]+)$",
        "lock_color_size_from_sku": True,
        "expand_size_slash_variants": True,
    },
    "ADIH25": {
        "pattern": r"^(ADIH25)-([^/]+)/(.+)$",
        "subgroup_rule": "color_before_slash",
    },
    "ADIHBWG01": {
        "pattern": r"^(ADIHBWG01)-(.+)$",
        "lock_color_from_sku": True,
        "expand_size_slash_variants": True,
    },
    "ADISBG175": {
        "pattern": r"^(ADISBG175-3\.0)/([^-]+)-(.+)$",
        "lock_color_size_from_sku": True,
    },
}


class SyncRunner:
    def __init__(self):
        self._info_cache = {}

    # Import Excel into staging tables
    @staticmethod
    def import_rows(df: pd.DataFrame, session: Session):
        original_cols = list(df.columns)
        df.columns = [normalize_col_name(c) for c in df.columns]
        # Header aliases for partner/vendor files.
        if "SKU" not in df.columns and "REFERENCIA" in df.columns:
            df["SKU"] = df["REFERENCIA"]
        if "NOMBRE" not in df.columns and "DESCRIPCION" in df.columns:
            df["NOMBRE"] = df["DESCRIPCION"]
        if "PRECIO" not in df.columns and "PVTAPUBPTY" in df.columns:
            df["PRECIO"] = df["PVTAPUBPTY"]
        if "PRECIO_ADICIONAL" not in df.columns and "POFERTA" in df.columns:
            df["PRECIO_ADICIONAL"] = df["POFERTA"]
        if "PRECIO_ADICIONAL" not in df.columns and "PRECIO ADICIONAL" in df.columns:
            df["PRECIO_ADICIONAL"] = df["PRECIO ADICIONAL"]
        required = ["SKU", "NOMBRE", "FOTO"]
        missing_cols = [c for c in required if c not in df.columns]
        if missing_cols:
            return {"error": f"Missing columns {missing_cols}"}
        group_col = "GRUPO" if "GRUPO" in df.columns else None
        group_idx_f = 5 if len(original_cols) > 5 else None
        df = df.drop_duplicates(subset=["SKU"], keep="last")
        skus = [str(v).strip() for v in df["SKU"].tolist()]
        sku_group_map = compute_group_keys_from_skus(skus)
        parents_seen = {}
        parents_cache = {}
        parent_colors: Dict[str, set] = {}
        parent_sizes: Dict[str, set] = {}
        parent_names: Dict[str, list] = {}
        parent_brands: Dict[str, Dict[str, int]] = {}
        for _, row in df.iterrows():
            sku = str(row["SKU"]).strip()
            parsed_parent, color_code, size_code = parse_sku(sku)
            exception = resolve_import_exception(sku)
            if exception and exception.get("parent_sku") == "ADIRHP01":
                parsed_parent = exception["parent_sku"]
                size_code = exception["size_code"]
                color_code = exception["color_code"]
            if exception and exception.get("parent_sku") == "ADIHBWG01":
                parsed_parent = exception["parent_sku"]
                if not color_code:
                    color_code = exception["color_code"]
            if exception and exception.get("parent_sku") == "ADISBG175":
                parsed_parent = exception["parent_sku"]
                color_code = exception.get("color_code") or color_code
                size_code = exception.get("size_code") or size_code
            if "COLOR" in df.columns and not pd.isna(row["COLOR"]):
                color_from_col = str(row["COLOR"]).strip()
                if color_from_col and not (
                    exception
                    and (
                        exception.get("lock_color_size_from_sku")
                        or exception.get("lock_color_from_sku")
                    )
                ):
                    color_code = color_from_col
            if "TALLA" in df.columns and not pd.isna(row["TALLA"]):
                size_from_col = str(row["TALLA"]).strip()
                if size_from_col and not (exception and exception.get("lock_color_size_from_sku")):
                    size_code = size_from_col
            parent_sku = sku_group_map.get(sku) or parsed_parent
            if exception and exception.get("parent_sku") in {"ADIRHP01", "ADIHBWG01", "ADISBG175"}:
                parent_sku = exception["parent_sku"]
            group_name = None
            if group_col and not pd.isna(row[group_col]):
                group_name = str(row[group_col]).strip()
            elif group_idx_f is not None:
                raw_f = row.iloc[group_idx_f]
                if not pd.isna(raw_f):
                    group_name = str(raw_f).strip()
            if not group_name:
                group_name = None
            brand_name = None
            if "MARCA" in df.columns and not pd.isna(row["MARCA"]):
                brand_name = str(row["MARCA"]).strip()
            if not brand_name:
                brand_name = None
            name_full = str(row["NOMBRE"]) if not pd.isna(row["NOMBRE"]) else ""
            price = (
                row["PRECIO"]
                if "PRECIO" in df.columns and not pd.isna(row["PRECIO"])
                else None
            )
            additional_price = (
                row["PRECIO_ADICIONAL"]
                if "PRECIO_ADICIONAL" in df.columns and not pd.isna(row["PRECIO_ADICIONAL"])
                else None
            )
            stock = (
                int(row["STOCK"])
                if "STOCK" in df.columns and not pd.isna(row["STOCK"])
                else None
            )

            expanded = [(sku, color_code, size_code, stock)]
            if (
                exception
                and exception.get("expand_size_slash_variants")
                and size_code
                and "/" in size_code
            ):
                split_sizes = [s.strip() for s in size_code.split("/") if s.strip()]
                if split_sizes:
                    per_size_stocks = [None] * len(split_sizes)
                    if stock is not None:
                        base = stock // len(split_sizes)
                        rem = stock % len(split_sizes)
                        per_size_stocks = [base + (1 if i < rem else 0) for i in range(len(split_sizes))]
                    if exception.get("parent_sku") == "ADIRHP01":
                        expanded = [
                            (
                                f"{exception['parent_sku']}-{sz}-{exception['color_code']}",
                                color_code,
                                sz,
                                per_size_stocks[i],
                            )
                            for i, sz in enumerate(split_sizes)
                        ]
                    elif exception.get("parent_sku") == "ADIHBWG01":
                        m_color = re.match(r"^ADIHBWG01-([^/]+/[^-]+)", sku.upper())
                        color_token = (
                            (m_color.group(1).strip() if m_color else "")
                            or (color_code or "").strip()
                            or (exception.get("color_code") or "").strip()
                        )
                        expanded = [
                            (
                                f"{exception['parent_sku']}-{color_token}-{sz}",
                                color_token,
                                sz,
                                per_size_stocks[i],
                            )
                            for i, sz in enumerate(split_sizes)
                        ]
                    # Remove previously imported combined SKU rows so re-imports
                    # keep one-size-per-variant exceptions normalized.
                    old_combined = session.query(models.ProductVariation).get(sku)
                    if old_combined is not None:
                        session.delete(old_combined)

            parent = parents_cache.get(parent_sku)
            if parent is None:
                parent = session.query(models.ProductParent).get(parent_sku)
                if parent is not None:
                    parents_cache[parent_sku] = parent
            if parent is None:
                parent = models.ProductParent(
                    parent_sku=parent_sku,
                    base_name=name_full.strip(),
                )
                session.add(parent)
                parents_cache[parent_sku] = parent

            parent_names.setdefault(parent_sku, []).append(name_full.strip())
            if brand_name:
                brand_bucket = parent_brands.setdefault(parent_sku, {})
                brand_bucket[brand_name] = brand_bucket.get(brand_name, 0) + 1

            for expanded_sku, expanded_color, expanded_size, expanded_stock in expanded:
                var = session.query(models.ProductVariation).get(expanded_sku)
                if not var:
                    var = models.ProductVariation(
                        variation_sku=expanded_sku, parent_sku=parent_sku
                    )
                    session.add(var)
                else:
                    # Keep grouping consistent across re-imports if parent logic changes.
                    var.parent_sku = parent_sku
                var.color_code = expanded_color
                var.size_code = expanded_size
                var.group_name = group_name
                var.name_full = name_full
                var.price = str(price) if price is not None else None
                var.additional_price = (
                    str(additional_price) if additional_price is not None else None
                )
                var.stock_qty = expanded_stock
                parent_colors.setdefault(parent_sku, set())
                parent_sizes.setdefault(parent_sku, set())
                if expanded_color:
                    parent_colors[parent_sku].add(expanded_color)
                if expanded_size:
                    parent_sizes[parent_sku].add(expanded_size)
                img = (
                    session.query(models.Image)
                    .filter(models.Image.owner_sku == expanded_sku)
                    .first()
                )
                if not img:
                    img = models.Image(
                        owner_type="variation",
                        owner_sku=expanded_sku,
                        file_name=str(row["FOTO"]).strip(),
                    )
                    session.add(img)
                else:
                    img.file_name = str(row["FOTO"]).strip()
            parents_seen[parent_sku] = True
        # normalize parent names based on collected colors/sizes
        for parent_sku, parent in parents_cache.items():
            colors = sorted(parent_colors.get(parent_sku, []))
            sizes = sorted(parent_sizes.get(parent_sku, []))
            names = parent_names.get(parent_sku, [parent.base_name or parent.parent_sku])
            parent.base_name = longest_common_prefix_name(names)
            parent.base_name = normalize_base_name(parent.base_name, colors, sizes)
            brands = parent_brands.get(parent_sku, {})
            if brands:
                parent.brand = max(brands.items(), key=lambda item: item[1])[0]
        # ADIHBWG01 exception safety: never keep combined size rows (S/M, L/XL, X/XL).
        # Import may receive them, but catalog must only retain split sizes (S,M,L,XL).
        adihbwg01_vars = (
            session.query(models.ProductVariation)
            .filter(models.ProductVariation.parent_sku == "ADIHBWG01")
            .all()
        )
        for var in adihbwg01_vars:
            raw_size = (var.size_code or "").strip()
            raw_sku = (var.variation_sku or "").upper()
            if (
                "/" in raw_size
                or "-S/M-" in raw_sku
                or "-L/XL-" in raw_sku
                or "-X/XL-" in raw_sku
                or "/S/M-" in raw_sku
                or "/L/XL-" in raw_sku
                or "/X/XL-" in raw_sku
            ):
                session.query(models.Image).filter(
                    models.Image.owner_sku == var.variation_sku
                ).delete(synchronize_session=False)
                session.delete(var)
        session.commit()
        return {"rows": len(df), "parents": len(parents_seen)}

    def start(self, session: Session):
        run = models.SyncRun()
        session.add(run)
        session.commit()
        session.refresh(run)
        return run

    def run(self, run_id: int):
        session = SessionLocal()
        try:
            run = session.query(models.SyncRun).get(run_id)
            self._log(session, run, "INFO", None, "Sync started")
            cfg = session.query(models.AppConfig).first()
            if not cfg:
                raise RuntimeError("Config missing")
            stages = [
                self.build_drive_index,
                self.upload_images,
                self.sync_parents,
                self.sync_variations,
            ]
            summary = {"stage": None}
            for stage in stages:
                summary["stage"] = stage.__name__
                self._update_summary(session, run, summary)
                stage(session, cfg, run)
            run.status = "done"
            run.finished_at = datetime.utcnow()
            session.commit()
        except Exception as e:
            run = session.query(models.SyncRun).get(run_id)
            if run:
                run.status = "error"
                run.finished_at = datetime.utcnow()
                run.summary_json = {"error": str(e)}
                session.commit()
        finally:
            session.close()

    def event_stream(self, run_id: int) -> Iterable[str]:
        while True:
            session = SessionLocal()
            run = session.query(models.SyncRun).get(run_id)
            if not run:
                yield "event: error\ndata: run not found\n\n"
                session.close()
                break
            data = run.summary_json or {}
            yield f"data: {json.dumps(data)}\n\n"
            status = run.status
            session.close()
            if status in ("done", "error"):
                break
            time.sleep(1)

    def status(self, run: models.SyncRun):
        return run.summary_json or {"status": run.status}

    def build_drive_index(self, session: Session, cfg: models.AppConfig, run: models.SyncRun):
        client = drive.get_drive_client()
        index = drive.list_folder_files(client, cfg.drive_folder_id)
        run.summary_json = {"stage": "build_drive_index", "files": len(index)}
        session.commit()
        self._info_cache["drive_index"] = index
        self._log(session, run, "INFO", None, f"Indexed {len(index)} files")

    def upload_images(self, session: Session, cfg: models.AppConfig, run: models.SyncRun):
        client = None
        index = None
        variations = session.query(models.ProductVariation).all()
        total = len(variations)
        done = 0
        for var in variations:
            parent = session.query(models.ProductParent).get(var.parent_sku)
            parent_brand = (parent.brand or "").strip() if parent else ""
            img = (
                session.query(models.Image)
                .filter(models.Image.owner_sku == var.variation_sku)
                .first()
            )
            if not img:
                continue
            data = None
            if img.file_name and img.file_name.startswith("local://"):
                local_name = Path(img.file_name[len("local://") :]).name
                local_path = LOCAL_SUBGROUP_UPLOADS / local_name
                if not local_path.exists():
                    img.status = "missing"
                    img.last_error = "local file not found"
                    session.commit()
                    self._log(
                        session,
                        run,
                        "WARN",
                        var.variation_sku,
                        f"Local image {local_name} missing",
                    )
                    done += 1
                    continue
                data = local_path.read_bytes()
            else:
                local_asset_path = resolve_asset_image_path(parent_brand, img.file_name)
                if local_asset_path and local_asset_path.exists():
                    data = local_asset_path.read_bytes()
                else:
                    if client is None:
                        client = drive.get_drive_client()
                    if index is None:
                        index = self._info_cache.get("drive_index") or drive.list_folder_files(
                            client, cfg.drive_folder_id
                        )
                    file = index.get(img.file_name)
                    if not file:
                        img.status = "missing"
                        img.last_error = "file not found in local brand assets or drive index"
                        session.commit()
                        self._log(
                            session,
                            run,
                            "WARN",
                            var.variation_sku,
                            f"Image {img.file_name} missing for brand {parent_brand or '-'}",
                        )
                        done += 1
                        continue
                    data = drive.download_file(client, file["id"])
            wp_id = wp_media.upload_or_reuse(
                session,
                cfg,
                img.file_name,
                data,
                lambda lvl, sku, msg: self._log(session, run, lvl, sku, msg),
            )
            if wp_id:
                img.wp_media_id = wp_id
                img.file_hash = wp_media.file_sha1(data)
                img.status = "uploaded"
                session.commit()
            done += 1
            run.summary_json = {"stage": "upload_images", "done": done, "total": total}
            session.commit()

    def sync_parents(self, session: Session, cfg: models.AppConfig, run: models.SyncRun):
        parents = session.query(models.ProductParent).all()
        for p in parents:
            vars_for_parent = (
                session.query(models.ProductVariation)
                .filter(models.ProductVariation.parent_sku == p.parent_sku)
                .all()
            )
            colors = sorted({v.color_code for v in vars_for_parent if v.color_code})
            sizes = sorted({v.size_code for v in vars_for_parent if v.size_code})
            clean_name = normalize_base_name(p.base_name or p.parent_sku, colors, sizes)
            p.base_name = clean_name
            attrs = [
                {
                    "name": cfg.attr_color_name,
                    "variation": True,
                    "visible": True,
                    "options": colors,
                },
                {
                    "name": cfg.attr_size_name,
                    "variation": True,
                    "visible": True,
                    "options": sizes,
                },
            ]
            if p.brand:
                attrs.append(
                    {
                        "name": "Marca",
                        "variation": False,
                        "visible": True,
                        "options": [p.brand],
                    }
                )
            payload = {
                "name": clean_name,
                "sku": p.parent_sku,
                "type": "variable",
                "attributes": attrs,
            }
            existing = woo.get_product_by_sku(cfg, p.parent_sku)
            if existing:
                woo.update_parent(cfg, existing["id"], payload)
                p.woo_product_id = existing["id"]
            else:
                res = woo.create_parent(cfg, payload)
                p.woo_product_id = res["id"]
            p.sync_status = "synced"
            p.last_sync_at = datetime.utcnow()
            session.commit()
            self._log(session, run, "INFO", p.parent_sku, "Parent synced")

    def sync_variations(self, session: Session, cfg: models.AppConfig, run: models.SyncRun):
        vars = session.query(models.ProductVariation).all()
        for var in vars:
            parent = session.query(models.ProductParent).get(var.parent_sku)
            if not parent or not parent.woo_product_id:
                continue
            attr = [
                {"name": cfg.attr_color_name, "option": var.color_code},
                {"name": cfg.attr_size_name, "option": var.size_code},
            ]
            payload = {
                "sku": var.variation_sku,
                "regular_price": var.price or "0",
                "manage_stock": True,
                "stock_quantity": var.stock_qty or 0,
                "attributes": attr,
            }
            if var.additional_price not in (None, "", "0", "0.0"):
                payload["sale_price"] = var.additional_price
            img = (
                session.query(models.Image)
                .filter(models.Image.owner_sku == var.variation_sku)
                .first()
            )
            if img and img.wp_media_id:
                payload["image"] = {"id": img.wp_media_id}
            var_id = var.woo_variation_id
            if not var_id:
                page = 1
                found = None
                while True:
                    items = woo.list_variations(cfg, parent.woo_product_id, page=page)
                    if not items:
                        break
                    for it in items:
                        if it.get("sku") == var.variation_sku:
                            found = it
                            break
                    if found or len(items) < 100:
                        break
                    page += 1
                if found:
                    var_id = found["id"]
                    var.woo_variation_id = var_id
            if var_id:
                woo.update_variation(cfg, parent.woo_product_id, var_id, payload)
            else:
                res = woo.create_variation(cfg, parent.woo_product_id, payload)
                var.woo_variation_id = res["id"]
            var.sync_status = "synced"
            var.last_sync_at = datetime.utcnow()
            session.commit()
            self._log(session, run, "INFO", var.variation_sku, "Variation synced")

    def _log(self, session: Session, run: models.SyncRun, level: str, sku: str, message: str):
        entry = models.Log(sync_run_id=run.id, level=level, sku=sku, message=message)
        session.add(entry)
        session.commit()

    def _update_summary(self, session: Session, run: models.SyncRun, data: Dict[str, Any]):
        run.summary_json = data
        session.commit()


def parse_sku(sku: str):
    # SPECIAL RULE: VENUM / EU-VENUM
    # Parent:
    #   - VENUM-<4|5 digits>
    #   - EU-VENUM-<3|4 digits>
    # Color:
    #   - next 3 digits after parent (e.g. ...-001)
    # Size:
    #   - token after '-' or '/' following the color token
    m_venum = re.match(r"^(VENUM-\d{4,5})-(\d{3})(?:[-/](.+))?$", sku.upper())
    if m_venum:
        parent_sku = m_venum.group(1)
        color_code = m_venum.group(2)
        size_code = m_venum.group(3) if m_venum.group(3) else None
        return parent_sku, color_code, size_code

    m_eu_venum = re.match(r"^(EU-VENUM-\d{3,4})-(\d{3})(?:[-/](.+))?$", sku.upper())
    if m_eu_venum:
        parent_sku = m_eu_venum.group(1)
        color_code = m_eu_venum.group(2)
        size_code = m_eu_venum.group(3) if m_eu_venum.group(3) else None
        return parent_sku, color_code, size_code

    # EU-VENUM black special case:
    # EU-VENUM-0003/<TALLA> -> color fixed as NEGRO, size after '/'
    m_eu_venum_black = re.match(r"^(EU-VENUM-\d{3,4})/([^/]+)$", sku.upper())
    if m_eu_venum_black:
        parent_sku = m_eu_venum_black.group(1)
        color_code = "NEGRO"
        size_code = m_eu_venum_black.group(2)
        return parent_sku, color_code, size_code

    # FORMATO MIXTO: FAMILIA-BLOQUE/TALLA (ej: JJ250-R/M0)
    if "-" in sku and "/" in sku and sku.count("-") == 1 and sku.count("/") == 1:
        try:
            familia, tail = sku.split("-", 1)
            bloque2, talla = tail.split("/", 1)
            parent_sku = familia
            color_code = bloque2
            size_code = talla
            return parent_sku, color_code, size_code
        except Exception:
            pass

    # FORMATO NUEVO: FAMILIA/COLOR-TALLA (ej: ADICLHD25JJS/BLU-S)
    if "/" in sku and sku.count("-") == 1 and sku.count("/") == 1:
        try:
            familia, rest = sku.split("/", 1)
            if "-" not in rest:
                raise ValueError("new-format SKU missing '-' after '/'")
            color, talla = rest.split("-", 1)
            parent_sku = familia
            return parent_sku, color, talla
        except Exception:
            # fallback to generic parsing
            return sku, None, None

    # FORMATO ANTERIOR: FAMILIA-BLOQUE2-TALLA
    parts = sku.split("-", 2)
    if len(parts) >= 3:
        familia, bloque2, talla = parts[0], parts[1], parts[2]
        if "/" in bloque2:
            left, right = bloque2.split("/", 1)
        else:
            left, right = bloque2, None
        if right and len(left) <= 2:
            # subtipo
            parent_sku = f"{familia}-{left}"
            color_code = right
        else:
            parent_sku = familia
            color_code = bloque2
        return parent_sku, color_code, talla

    # fallback: SKU desconocido -> tratar como simple
    return sku, None, None


def resolve_import_exception(sku: str) -> Optional[Dict[str, Any]]:
    upper = (sku or "").strip().upper()
    if not upper:
        return None

    cfg_adirhp01 = PARENT_SKU_IMPORT_EXCEPTIONS.get("ADIRHP01", {})
    m_adirhp01 = re.match(cfg_adirhp01.get("pattern", r"^$"), upper)
    if m_adirhp01:
        return {
            "parent_sku": "ADIRHP01",
            "size_code": m_adirhp01.group(2).strip(),
            "color_code": m_adirhp01.group(3).strip(),
            "lock_color_size_from_sku": bool(cfg_adirhp01.get("lock_color_size_from_sku")),
            "expand_size_slash_variants": bool(cfg_adirhp01.get("expand_size_slash_variants")),
        }

    cfg_adih25 = PARENT_SKU_IMPORT_EXCEPTIONS.get("ADIH25", {})
    m_adih25 = re.match(cfg_adih25.get("pattern", r"^$"), upper)
    if m_adih25:
        return {
            "parent_sku": "ADIH25",
            "color_token": m_adih25.group(2).strip(),
            "size_token": m_adih25.group(3).strip(),
            "subgroup_rule": cfg_adih25.get("subgroup_rule"),
        }

    cfg_adihbwg01 = PARENT_SKU_IMPORT_EXCEPTIONS.get("ADIHBWG01", {})
    m_adihbwg01 = re.match(cfg_adihbwg01.get("pattern", r"^$"), upper)
    if m_adihbwg01:
        # ADIHBWG01-BLK/PNK-S/M -> color token must stay BLK/PNK
        m_color = re.match(r"^ADIHBWG01-([^/]+/[^-]+)(?:-.+)?$", upper)
        return {
            "parent_sku": "ADIHBWG01",
            "color_code": (m_color.group(1).strip() if m_color else m_adihbwg01.group(2).strip()),
            "lock_color_from_sku": bool(cfg_adihbwg01.get("lock_color_from_sku")),
            "expand_size_slash_variants": bool(
                cfg_adihbwg01.get("expand_size_slash_variants")
            ),
        }

    cfg_adisbg175 = PARENT_SKU_IMPORT_EXCEPTIONS.get("ADISBG175", {})
    m_adisbg175 = re.match(cfg_adisbg175.get("pattern", r"^$"), upper)
    if m_adisbg175:
        return {
            "parent_sku": m_adisbg175.group(1).strip(),
            "color_code": m_adisbg175.group(2).strip(),
            "size_code": m_adisbg175.group(3).strip(),
            "lock_color_size_from_sku": bool(
                cfg_adisbg175.get("lock_color_size_from_sku")
            ),
        }

    return None


def normalize_brand_folder_name(brand: str) -> str:
    raw = (brand or "").strip()
    return re.sub(r"[^A-Za-z0-9_-]", "_", raw).upper()


def extract_image_file_name(file_name: str) -> str:
    raw = (file_name or "").strip().replace("\\", "/")
    raw = raw.split("?", 1)[0]
    return Path(raw).name


def resolve_asset_image_path(brand: str, file_name: str) -> Optional[Path]:
    img_name = extract_image_file_name(file_name)
    if not img_name:
        return None

    normalized_brand = normalize_brand_folder_name(brand)
    brand_candidates = [b for b in {brand, brand.upper(), normalized_brand} if b]

    for brand_folder in brand_candidates:
        folder_path = LOCAL_ASSETS_IMG_UPLOADS / brand_folder
        if not folder_path.exists() or not folder_path.is_dir():
            continue
        exact = folder_path / img_name
        if exact.exists():
            return exact
        lower_target = img_name.lower()
        for candidate in folder_path.iterdir():
            if candidate.is_file() and candidate.name.lower() == lower_target:
                return candidate

    return None


def get_sync_runner():
    return SyncRunner()


def sku_family_hint(sku: str) -> str:
    raw = (sku or "").strip()
    upper = raw.upper()

    # EXCEPTION 1: VENUM groups by VENUM-<4 or 5 digits>-
    m_venum = re.match(r"^(VENUM)-(\d{4,5})(?:-|/)", upper)
    if m_venum:
        return f"{m_venum.group(1)}-{m_venum.group(2)}"

    # EXCEPTION 2: EU-VENUM groups by EU-VENUM-<3 or 4 digits>-
    m_eu_venum = re.match(r"^(EU-VENUM)-(\d{3,4})(?:-|/)", upper)
    if m_eu_venum:
        return f"{m_eu_venum.group(1)}-{m_eu_venum.group(2)}"

    token = re.split(r"[-/_\s]", raw, maxsplit=1)[0]
    return token or raw


def is_fixed_family_hint(hint: str) -> bool:
    upper = (hint or "").upper()
    return bool(
        re.match(r"^VENUM-\d{4,5}$", upper)
        or re.match(r"^EU-VENUM-\d{3,4}$", upper)
    )


def compute_group_keys_from_skus(skus: list) -> Dict[str, str]:
    buckets: Dict[str, list] = {}
    for raw in skus:
        sku = (raw or "").strip()
        if not sku:
            continue
        hint = sku_family_hint(sku)
        buckets.setdefault(hint, []).append(sku)

    result: Dict[str, str] = {}
    for hint, items in buckets.items():
        if is_fixed_family_hint(hint):
            # Brand-specific exception: do not apply longest common prefix.
            group_key = hint
        elif len(items) == 1:
            group_key = hint
        else:
            group_key = longest_common_prefix_name(items).strip(" -_/")
        if not group_key:
            group_key = hint
        for sku in items:
            result[sku] = group_key
    return result


def longest_common_prefix_name(names: list) -> str:
    """Devuelve el prefijo común carácter a carácter entre todas las variantes, limpiando separadores."""
    if not names:
        return ""
    # trabajar en mayúsculas para comparar pero devolver con formato original del primero
    upper = [n.strip() for n in names if n]
    if not upper:
        return ""
    first = upper[0]
    min_len = min(len(n) for n in upper)
    i = 0
    while i < min_len:
        ch = upper[0][i]
        if any(n[i] != ch for n in upper):
            break
        i += 1

    # If the prefix split happens inside an alphanumeric token (e.g. A1/A2),
    # rewind to the last separator instead of keeping a partial token.
    if i < min_len and i > 0:
        prev_is_alnum = first[i - 1].isalnum()
        next_chars = [n[i] for n in upper if len(n) > i]
        next_all_alnum = bool(next_chars) and all(ch.isalnum() for ch in next_chars)
        if prev_is_alnum and next_all_alnum:
            while i > 0 and first[i - 1].isalnum():
                i -= 1

    prefix = first[:i].rstrip(" -_/")
    return prefix


def normalize_base_name(name: str, colors: list, sizes: list) -> str:
    """
    Limpia espacios y separadores del nombre base (ya calculado por prefijo común).
    No elimina color ni talla aquí; esa decisión la toma longest_common_prefix_name.
    """
    working = (name or "").strip()
    working = re.sub(r"\s*\([^)]*\)\s*$", " ", working)
    working = re.sub(r"[\-_/]+", " ", working)
    working = re.sub(r"\s{2,}", " ", working).strip()
    return working


def normalize_col_name(name: str) -> str:
    text = str(name or "").strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.upper()
