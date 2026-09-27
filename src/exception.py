from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging

app = FastAPI()
logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log the error to your monitoring system
    logger.error(f"Unhandled error on {request.url.path}: {exc}")
    
    # Return a custom formatted 500 response
    return JSONResponse(
        status_code=500,
        content={"message": "Oops! Something went wrong on our end."}
    )