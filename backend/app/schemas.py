from typing import Optional, List
from pydantic import BaseModel

class AppConfigIn(BaseModel):
    woo_base_url: Optional[str] = None
    woo_key: Optional[str] = None
    woo_secret: Optional[str] = None
    wp_base_url: Optional[str] = None
    wp_username: Optional[str] = None
    wp_app_password: Optional[str] = None
    drive_folder_id: Optional[str] = None
    attr_color_name: str = 'Color'
    attr_size_name: str = 'Talla'
    dry_run_default: bool = False

class AppConfigOut(AppConfigIn):
    class Config:
        orm_mode = True

class ParentOut(BaseModel):
    parent_sku: str
    base_name: Optional[str]
    brand: Optional[str]
    woo_product_id: Optional[int]
    sync_status: Optional[str]
    last_error: Optional[str]
    variations_count: Optional[int]
    product_kind: Optional[str]
    class Config:
        orm_mode = True

class VariationOut(BaseModel):
    variation_sku: str
    parent_sku: str
    brand: Optional[str]
    group_name: Optional[str]
    color_code: Optional[str]
    size_code: Optional[str]
    name_full: Optional[str]
    price: Optional[str]
    additional_price: Optional[str]
    stock_qty: Optional[int]
    woo_variation_id: Optional[int]
    image_file_name: Optional[str]
    image_preview_url: Optional[str]
    sync_status: Optional[str]
    last_error: Optional[str]
    class Config:
        orm_mode = True

class LogOut(BaseModel):
    id: int
    ts: str
    level: str
    sku: Optional[str]
    message: str
    class Config:
        orm_mode = True


class SubgroupImageIn(BaseModel):
    parent_sku: str
    subgroup_key: str
    file_name: str


class SubgroupImageOut(BaseModel):
    ok: bool
    updated: int


class GroupListOut(BaseModel):
    groups: List[str]
