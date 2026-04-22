from fastapi import FastAPI

from contextlib import asynccontextmanager

from app.api import auth, bookings, health, hotels, hotels_admin
from app.core.config import settings
from app.services.reaper import start_reaper


@asynccontextmanager
async def lifespan(_app: FastAPI):
    scheduler = start_reaper() if settings.env != "test" else None
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)

app = FastAPI(
    title="Hotel Booking API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(hotels.router)
app.include_router(hotels_admin.router)
app.include_router(bookings.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "hotel-booking-api", "env": settings.env}
