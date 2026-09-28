"""
main.py — FastAPI entry point
Run with: uvicorn main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.config import API_TITLE, API_VERSION, API_DESCRIPTION
from core.logger import logger
from routes.main_routes import router as main_router
from routes.research import router as research_router
from routes.jobes import router as jobs_router
from routes.pdf import router as pdf_router
from routes import refinement
from routes import stress_test
from routes import forecast
from routes.auth import router as auth_router
from routes.dashboard import router as dashboard_router
app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.include_router(dashboard_router)

from fastapi import Request
from fastapi.responses import JSONResponse

# Laminar observability
try:
    from lmnr import Laminar
    import os
    _lmnr_key = os.getenv("LAMINAR_API_KEY")
    if _lmnr_key:
        Laminar.initialize(project_api_key=_lmnr_key)
        print("Laminar tracing enabled")
except Exception as _e:
    print(f"Laminar not available: {_e}")


PUBLIC_ROUTES = {"/health", "/api/auth/login", "/api/auth/logout", "/docs", "/openapi.json", "/redoc"}

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path in PUBLIC_ROUTES or request.method == "OPTIONS":
        return await call_next(request)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Non authentifie"})
    token = auth.split(" ")[1]
    try:
        from jose import jwt
        import os
        jwt.decode(token, os.getenv("JWT_SECRET", "bfi-credit-secret-key"), algorithms=["HS256"])
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Token invalide ou expire"})
    return await call_next(request)
# ?????????????????????????????????????????????????????????????????

app.include_router(stress_test.router)
app.include_router(auth_router)

app.include_router(forecast.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(main_router)
app.include_router(research_router)
app.include_router(jobs_router)
app.include_router(pdf_router)
app.include_router(refinement.router)  # ✅ Only here, AFTER app is defined

@app.on_event("startup")
async def on_startup():
    logger.info("Deep Research API started.")

@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Deep Research API shutting down.")


