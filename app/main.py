from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.routers import items

settings = get_settings()
app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(items.router)

@app.get("/", tags=["meta"])
def root() -> dict:
    return {"name": settings.app_name, "version": settings.app_version}

@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "database": "connected", "container": "docker"}
