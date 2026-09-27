from fastapi import FastAPI
from src.config import settings
from src.payments.router import router as payments_router

app = FastAPI(
    title=settings.APP_NAME,
    description="Setu Test Payment API",
    version="1.0.0",
)

# Register the payments router
app.include_router(payments_router,prefix="/api/v1/payments")
