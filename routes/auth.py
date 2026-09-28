# backend/routes/auth.py
"""
JWT Authentication — login + token verification
"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import bcrypt
from jose import JWTError, jwt
import os

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── Config ────────────────────────────────────────────────────────
SECRET_KEY  = os.getenv("JWT_SECRET", "bfi-credit-secret-key-change-in-production")
ALGORITHM   = "HS256"
TOKEN_HOURS = 24


bearer      = HTTPBearer()

# ── Schemas ───────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    username:     str
    role:         str

# ── Helpers ───────────────────────────────────────────────────────
def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def _verify(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

def _create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=TOKEN_HOURS)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")

# ── User DB (PostgreSQL) ──────────────────────────────────────────
def _get_user(username: str) -> Optional[dict]:
    import pg8000
    from dotenv import load_dotenv
    load_dotenv()
    conn = pg8000.connect(
        host=os.getenv("PG_HOST","localhost"),
        port=int(os.getenv("PG_PORT","5432")),
        database=os.getenv("PG_DB","tunisie_industrie"),
        user=os.getenv("PG_USER","postgres"),
        password=os.getenv("PG_PASSWORD","")
    )
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT username, password_hash, role, is_active FROM users WHERE username = %s",
            (username,)
        )
        row = cur.fetchone()
        if row:
            return {"username": row[0], "password_hash": row[1],
                    "role": row[2], "is_active": row[3]}
        return None
    finally:
        cur.close()
        conn.close()

# ── Dependency — require valid JWT ────────────────────────────────
def require_auth(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    payload = _decode_token(credentials.credentials)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Token invalide")
    user = _get_user(username)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Utilisateur inactif ou introuvable")
    return user

# ── Endpoints ─────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    user = _get_user(req.username)
    if not user or not _verify(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Identifiants incorrects")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Compte désactivé")
    token = _create_token({"sub": user["username"], "role": user["role"]})
    return TokenResponse(access_token=token, username=user["username"], role=user["role"])

@router.get("/me")
def me(user: dict = Depends(require_auth)):
    return {"username": user["username"], "role": user["role"]}

@router.post("/logout")
def logout():
    # JWT is stateless — client just deletes the token
    return {"message": "Déconnecté avec succès"}