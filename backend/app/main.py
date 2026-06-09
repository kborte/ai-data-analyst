from fastapi import FastAPI

from app.api.routes.analytics import router as analytics_router
from app.api.routes.cleaning import router as cleaning_router
from app.api.routes.saved_views import router as saved_views_router
from app.api.routes.saved_visuals import router as saved_visuals_router
from app.api.routes.features import router as features_router
from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.profiles import router as profiles_router
from app.api.routes.uploads import router as uploads_router
from app.api.routes.visualization import router as visualization_router
from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title=settings.APP_NAME, version="0.1.0")

app.include_router(health_router)
app.include_router(uploads_router)
app.include_router(profiles_router)
app.include_router(cleaning_router)
app.include_router(features_router)
app.include_router(visualization_router)
app.include_router(jobs_router)
app.include_router(saved_views_router)
app.include_router(saved_visuals_router)
app.include_router(analytics_router)
