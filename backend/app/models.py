from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db import Base

class AppConfig(Base):
    __tablename__ = 'app_config'
    id = Column(Integer, primary_key=True, default=1)
    woo_base_url = Column(String)
    woo_key = Column(String)
    woo_secret = Column(String)
    wp_base_url = Column(String)
    wp_username = Column(String)
    wp_app_password = Column(String)
    drive_folder_id = Column(String)
    attr_color_name = Column(String, default='Color')
    attr_size_name = Column(String, default='Talla')
    dry_run_default = Column(Boolean, default=False)

class ProductParent(Base):
    __tablename__ = 'products_parent'
    parent_sku = Column(String, primary_key=True)
    base_name = Column(String)
    brand = Column(String)
    woo_product_id = Column(Integer)
    sync_status = Column(String, default='pending')
    last_error = Column(String)
    last_sync_at = Column(DateTime)
    variations = relationship('ProductVariation', back_populates='parent')

class ProductVariation(Base):
    __tablename__ = 'products_variation'
    variation_sku = Column(String, primary_key=True)
    parent_sku = Column(String, ForeignKey('products_parent.parent_sku'))
    group_name = Column(String)
    color_code = Column(String)
    size_code = Column(String)
    name_full = Column(String)
    price = Column(String)
    additional_price = Column(String)
    stock_qty = Column(Integer)
    woo_variation_id = Column(Integer)
    sync_status = Column(String, default='pending')
    last_error = Column(String)
    last_sync_at = Column(DateTime)
    parent = relationship('ProductParent', back_populates='variations')
    images = relationship('Image', back_populates='variation')

class Image(Base):
    __tablename__ = 'images'
    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_type = Column(String)
    owner_sku = Column(String, ForeignKey('products_variation.variation_sku'))
    file_name = Column(String)
    role = Column(String, default='main')
    status = Column(String, default='pending')
    wp_media_id = Column(Integer)
    file_hash = Column(String)
    last_error = Column(String)
    variation = relationship('ProductVariation', back_populates='images')

class MediaHash(Base):
    __tablename__ = 'media_hashes'
    file_hash = Column(String, primary_key=True)
    wp_media_id = Column(Integer)

class SyncRun(Base):
    __tablename__ = 'sync_runs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    status = Column(String, default='running')
    summary_json = Column(JSON)
    logs = relationship('Log', back_populates='sync_run')

class Log(Base):
    __tablename__ = 'logs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_run_id = Column(Integer, ForeignKey('sync_runs.id'))
    ts = Column(DateTime, default=datetime.utcnow)
    level = Column(String)
    sku = Column(String)
    message = Column(String)
    sync_run = relationship('SyncRun', back_populates='logs')
