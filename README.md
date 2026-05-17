e-commerce automation app

# Woo Sync MVP

Monorepo (backend FastAPI + frontend Vite React) para importar Excel y sincronizar productos variables en WooCommerce con imágenes de Google Drive y subida a WordPress Media.

## Estructura
- ackend/ FastAPI, SQLAlchemy, Alembic
- rontend/ React + Vite + Tailwind
- docker-compose.yml Postgres

## Requisitos
- Python 3.11+
- Node 18+
- Postgres (o SQLite para dev)
- Credenciales:
  - WooCommerce REST (consumer key/secret)
  - WordPress usuario + Application Password (para /wp-json/wp/v2/media)
  - Google Service Account JSON con acceso al folder de Drive

## Backend
`
cd backend
python -m venv .venv
. .venv/Scripts/activate  # Windows
pip install -r requirements.txt
cp .env.example .env
# edita DATABASE_URL y GOOGLE_APPLICATION_CREDENTIALS
alembic upgrade head
uvicorn app.main:app --reload
`

### Variables .env
- DATABASE_URL e.g. postgresql+psycopg2://woo_sync:woo_sync@localhost:5432/woo_sync o sqlite:///./local.db
- GOOGLE_APPLICATION_CREDENTIALS ruta al JSON del service account

## Frontend
`
cd frontend
npm install
cp .env.example .env
npm run dev
`

## Docker
`
docker-compose up -d db
`
(El servicio backend en docker-compose usa Postgres; puedes extender para frontend si quieres.)

## Endpoints clave
- POST /api/import subir Excel (SKU, NOMBRE, PRECIO, STOCK, FOTO)
- POST /api/sync inicia sincronización
- GET /api/sync/{run_id}/status progreso
- GET /api/sync/{run_id}/events SSE
- GET /api/catalog/parents y /variations

## Notas de seguridad
- No registres secretos en logs.
- WP upload usa Basic Auth (usuario + application password).
- Rate limit configurable en pp/config.py (woo_rate_delay_ms).

## Flujo de sincronización
1) Indexa carpeta de Drive
2) Sube imágenes a WP con deduplicación por hash
3) Crea/actualiza padres en Woo (variable)
4) Crea/actualiza variaciones con atributos Color/Talla
