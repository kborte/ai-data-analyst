import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.analytics import router as analytics_router
from app.api.routes.auth import router as auth_router
from app.api.routes.cleaning import router as cleaning_router
from app.api.routes.datasets import router as datasets_router
from app.api.routes.saved_views import router as saved_views_router
from app.api.routes.saved_visuals import router as saved_visuals_router
from app.api.routes.features import router as features_router
from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.profiles import router as profiles_router
from app.api.routes.uploads import router as uploads_router
from app.api.routes.visualization import router as visualization_router
from app.api.routes.workspaces import router as workspaces_router
from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()

_logger = logging.getLogger(__name__)

origins = [
    "http://localhost:3000",
    "https://your-frontend.vercel.app",
]

app = FastAPI(title=settings.APP_NAME, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}: {exc}"},
    )

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(workspaces_router)
app.include_router(uploads_router)
app.include_router(profiles_router)
app.include_router(cleaning_router)
app.include_router(features_router)
app.include_router(visualization_router)
app.include_router(jobs_router)
app.include_router(saved_views_router)
app.include_router(saved_visuals_router)
app.include_router(analytics_router)
app.include_router(datasets_router)
