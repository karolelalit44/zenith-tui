"""Minimal FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="FastAPI App", version="0.1.0")


class HealthResponse(BaseModel):
    status: str = "ok"


class EchoRequest(BaseModel):
    message: str


class EchoResponse(BaseModel):
    echo: str


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@app.post("/echo", response_model=EchoResponse)
async def echo(req: EchoRequest) -> EchoResponse:
    return EchoResponse(echo=req.message)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
