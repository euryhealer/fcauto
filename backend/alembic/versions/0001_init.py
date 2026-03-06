from alembic import op
import sqlalchemy as sa

revision = '0001_init'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('app_config',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('woo_base_url', sa.String()),
        sa.Column('woo_key', sa.String()),
        sa.Column('woo_secret', sa.String()),
        sa.Column('wp_base_url', sa.String()),
        sa.Column('wp_username', sa.String()),
        sa.Column('wp_app_password', sa.String()),
        sa.Column('drive_folder_id', sa.String()),
        sa.Column('attr_color_name', sa.String(), default='Color'),
        sa.Column('attr_size_name', sa.String(), default='Talla'),
        sa.Column('dry_run_default', sa.Boolean(), default=False),
    )
    op.create_table('products_parent',
        sa.Column('parent_sku', sa.String(), primary_key=True),
        sa.Column('base_name', sa.String()),
        sa.Column('woo_product_id', sa.Integer()),
        sa.Column('sync_status', sa.String(), default='pending'),
        sa.Column('last_error', sa.String()),
        sa.Column('last_sync_at', sa.DateTime()),
    )
    op.create_table('products_variation',
        sa.Column('variation_sku', sa.String(), primary_key=True),
        sa.Column('parent_sku', sa.String(), sa.ForeignKey('products_parent.parent_sku')),
        sa.Column('color_code', sa.String()),
        sa.Column('size_code', sa.String()),
        sa.Column('name_full', sa.String()),
        sa.Column('price', sa.String()),
        sa.Column('stock_qty', sa.Integer()),
        sa.Column('woo_variation_id', sa.Integer()),
        sa.Column('sync_status', sa.String(), default='pending'),
        sa.Column('last_error', sa.String()),
        sa.Column('last_sync_at', sa.DateTime()),
    )
    op.create_table('images',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('owner_type', sa.String()),
        sa.Column('owner_sku', sa.String(), sa.ForeignKey('products_variation.variation_sku')),
        sa.Column('file_name', sa.String()),
        sa.Column('role', sa.String(), default='main'),
        sa.Column('status', sa.String(), default='pending'),
        sa.Column('wp_media_id', sa.Integer()),
        sa.Column('file_hash', sa.String()),
        sa.Column('last_error', sa.String()),
    )
    op.create_table('media_hashes',
        sa.Column('file_hash', sa.String(), primary_key=True),
        sa.Column('wp_media_id', sa.Integer()),
    )
    op.create_table('sync_runs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('started_at', sa.DateTime()),
        sa.Column('finished_at', sa.DateTime()),
        sa.Column('status', sa.String(), default='running'),
        sa.Column('summary_json', sa.JSON()),
    )
    op.create_table('logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('sync_run_id', sa.Integer(), sa.ForeignKey('sync_runs.id')),
        sa.Column('ts', sa.DateTime()),
        sa.Column('level', sa.String()),
        sa.Column('sku', sa.String()),
        sa.Column('message', sa.String()),
    )

def downgrade():
    op.drop_table('logs')
    op.drop_table('sync_runs')
    op.drop_table('media_hashes')
    op.drop_table('images')
    op.drop_table('products_variation')
    op.drop_table('products_parent')
    op.drop_table('app_config')