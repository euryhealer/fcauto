from pydantic import BaseSettings

class Settings(BaseSettings):
    database_url: str = 'sqlite:///./local.db'
    log_level: str = 'INFO'
    woo_rate_delay_ms: int = 200

    class Config:
        env_file = '.env'

settings = Settings()
