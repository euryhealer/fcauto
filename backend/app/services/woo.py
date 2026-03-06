import time
import requests
from typing import Dict, Any

DEFAULT_TIMEOUT = 15


def _delay(cfg):
    return getattr(cfg, "woo_rate_delay_ms", 200) / 1000.0


def woo_request(cfg, method: str, path: str, params=None, json=None):
    url = f"{cfg.woo_base_url}/wp-json/wc/v3{path}"
    auth = (cfg.woo_key, cfg.woo_secret)
    resp = requests.request(
        method, url, auth=auth, params=params, json=json, timeout=DEFAULT_TIMEOUT
    )
    return resp


def get_product_by_sku(cfg, sku: str):
    resp = woo_request(cfg, "GET", "/products", params={"sku": sku})
    if resp.status_code == 200 and resp.json():
        return resp.json()[0]
    return None


def create_parent(cfg, payload: Dict[str, Any]):
    resp = woo_request(cfg, "POST", "/products", json=payload)
    resp.raise_for_status()
    time.sleep(_delay(cfg))
    return resp.json()


def update_parent(cfg, product_id: int, payload: Dict[str, Any]):
    resp = woo_request(cfg, "PUT", f"/products/{product_id}", json=payload)
    resp.raise_for_status()
    time.sleep(_delay(cfg))
    return resp.json()


def list_variations(cfg, product_id: int, page: int = 1, per_page: int = 100):
    resp = woo_request(
        cfg,
        "GET",
        f"/products/{product_id}/variations",
        params={"page": page, "per_page": per_page},
    )
    resp.raise_for_status()
    return resp.json()


def create_variation(cfg, product_id: int, payload: Dict[str, Any]):
    resp = woo_request(cfg, "POST", f"/products/{product_id}/variations", json=payload)
    resp.raise_for_status()
    time.sleep(_delay(cfg))
    return resp.json()


def update_variation(cfg, product_id: int, variation_id: int, payload: Dict[str, Any]):
    resp = woo_request(
        cfg,
        "PUT",
        f"/products/{product_id}/variations/{variation_id}",
        json=payload,
    )
    resp.raise_for_status()
    time.sleep(_delay(cfg))
    return resp.json()
