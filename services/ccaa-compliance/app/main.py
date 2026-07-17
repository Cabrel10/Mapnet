"""CCAA Compliance Service - FastAPI entrypoint."""
import json
import logging
import os
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from shapely.geometry import shape, Polygon
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .geofencer import check_flight_plan

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MapNet CCAA Compliance Service", version="1.0.0")

SERVICE_NAME = os.environ.get("SERVICE_NAME", "ccaa-compliance")
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:secure_password@postgis:5432/quamtechs_db"
)
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, future=True)


class HealthResponse(BaseModel):
    status: str
    service: str


class DroneValidationRequest(BaseModel):
    drone_id: str
    operator_id: str
    flight_polygon: dict
    altitude_m: int = Field(..., gt=0, le=500)
    planned_start: datetime
    planned_end: datetime


class FlightPlanResponse(BaseModel):
    status: str
    reason: str
    conflicts: List[dict]


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", service=SERVICE_NAME)


@app.post("/api/v1/drone/validate", response_model=FlightPlanResponse)
def validate_flight(req: DroneValidationRequest):
    try:
        polygon = shape(req.flight_polygon)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid polygon: {exc}") from exc

    result = check_flight_plan(polygon, req.altitude_m)
    db_status = "pending" if result["status"] == "approved" else "rejected"

    try:
        with SessionLocal() as session:
            session.execute(
                text(
                    """
                    INSERT INTO drone_flight_plans (drone_id, operator_id, flight_polygon, altitude_m,
                                                    planned_start, planned_end, status)
                    VALUES (:drone_id, :operator_id, ST_SetSRID(ST_GeomFromGeoJSON(:polygon), 4326),
                            :altitude, :start, :end, :status)
                    """
                ),
                {
                    "drone_id": req.drone_id,
                    "operator_id": req.operator_id,
                    "polygon": json.dumps(req.flight_polygon),
                    "altitude": req.altitude_m,
                    "start": req.planned_start,
                    "end": req.planned_end,
                    "status": db_status,
                },
            )
            session.commit()
    except Exception as exc:
        # Likely intersects no-fly zone at DB level
        logger.warning("Flight plan DB insertion failed: %s", exc)
        return FlightPlanResponse(
            status="rejected",
            reason=f"Flight plan intersects with a no-fly zone: {exc}",
            conflicts=[],
        )

    return FlightPlanResponse(status=result["status"], reason=result["reason"], conflicts=result.get("conflicts", []))


@app.get("/api/v1/drone/plans")
def list_plans(drone_id: Optional[str] = None, limit: int = 100):
    with SessionLocal() as session:
        sql = "SELECT id, drone_id, operator_id, altitude_m, planned_start, planned_end, status FROM drone_flight_plans"
        params = {}
        if drone_id:
            sql += " WHERE drone_id = :drone_id"
            params["drone_id"] = drone_id
        sql += " ORDER BY id DESC LIMIT :limit"
        params["limit"] = limit
        rows = session.execute(text(sql), params).mappings().all()
    return {"status": "ok", "count": len(rows), "plans": [dict(row) for row in rows]}
