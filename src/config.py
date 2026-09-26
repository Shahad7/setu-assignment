from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "Setu Test Service"
    APP_ENV: str = "prod"

    # Database configuration with defaults for local IDE runs
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "payments_db"

    # The async connection string defaults to localhost
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/payments_db"

settings = Settings()