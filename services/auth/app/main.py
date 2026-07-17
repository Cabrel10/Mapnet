"""Auth Service - FastAPI entrypoint."""
import logging
import os
from datetime import timedelta

from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .security import create_access_token, decode_token, get_password_hash, verify_password

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MapNet Auth Service", version="1.0.0")

SERVICE_NAME = os.environ.get("SERVICE_NAME", "auth")
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:secure_password@postgis:5432/quamtechs_db"
)
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, future=True)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


class HealthResponse(BaseModel):
    status: str
    service: str


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: str = "driver"


class Token(BaseModel):
    access_token: str
    token_type: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str


def get_user_by_username(username: str):
    with SessionLocal() as session:
        row = session.execute(
            text("SELECT id, username, email, hashed_password, role FROM users WHERE username = :username"),
            {"username": username},
        ).mappings().first()
    return dict(row) if row else None


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", service=SERVICE_NAME)


@app.post("/api/v1/auth/register", response_model=UserOut)
def register(user: UserCreate):
    with SessionLocal() as session:
        existing = session.execute(
            text("SELECT id FROM users WHERE username = :username OR email = :email"),
            {"username": user.username, "email": user.email},
        ).fetchone()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

        hashed = get_password_hash(user.password)
        row = session.execute(
            text(
                """
                INSERT INTO users (username, email, hashed_password, role)
                VALUES (:username, :email, :hashed_password, :role)
                RETURNING id, username, email, role
                """
            ),
            {
                "username": user.username,
                "email": user.email,
                "hashed_password": hashed,
                "role": user.role,
            },
        ).mappings().first()
        session.commit()
    return UserOut(**dict(row))


@app.post("/api/v1/auth/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = get_user_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token({"sub": user["username"], "role": user["role"]})
    return Token(access_token=token, token_type="bearer")


@app.get("/api/v1/auth/me", response_model=UserOut)
def me(token: str = Depends(oauth2_scheme)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    username = payload.get("sub")
    user = get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserOut(id=user["id"], username=user["username"], email=user["email"], role=user["role"])
