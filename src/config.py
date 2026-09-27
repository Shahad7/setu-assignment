from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "Setu Test Service"
    APP_ENV: str = "prod"

    # fallback for local terminal
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/payments_db"

settings = Settings()