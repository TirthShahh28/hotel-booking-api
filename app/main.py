from fastapi import FastAPI

from app.api import auth, health, hotels, hotels_admin
from app.core.config import settings

app = FastAPI(
    title="Hotel Booking API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(hotels.router)
app.include_router(hotels_admin.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "hotel-booking-api", "env": settings.env}
