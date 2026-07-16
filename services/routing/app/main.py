"""Routing Service - FastAPI entrypoint."""
import logging
import os
from typing import List

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from .osrm_client import map_match, route, nearest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MapNet Routing Service", version="1.0.0")

SERVICE_NAME = os.environ.get("SERVICE_NAME", "routing")


class Point(BaseModel):
    latitude: float
    longitude: float


class MapMatchRequest(BaseModel):
    points: List[Point]


class RouteRequest(BaseModel):
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float


class HealthResponse(BaseModel):
    status: str
    service: str


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", service=SERVICE_NAME)


@app.post("/api/v1/routing/map-match")
def map_match_route(req: MapMatchRequest):
    if len(req.points) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Need at least 2 points")
    try:
        data = map_match([p.model_dump() for p in req.points])
    except Exception as exc:
        logger.error("Map matching failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"status": "ok", "matchings": data.get("matchings", []), "tracepoints": data.get("tracepoints", [])}


@app.post("/api/v1/routing/route")
def calculate_route(req: RouteRequest):
    try:
        data = route(req.from_lat, req.from_lon, req.to_lat, req.to_lon)
    except Exception as exc:
        logger.error("Routing failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"status": "ok", "routes": data.get("routes", [])}


@app.get("/api/v1/routing/nearest")
def nearest_point(lat: float, lon: float):
    try:
        data = nearest(lat, lon)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"status": "ok", "result": data}
