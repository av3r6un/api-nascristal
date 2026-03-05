import os

from .auth import router as auth_router
from .feedback import router as feedback_router
from .i18n import router as i18n_router
from .catalog import router as catalog_router
from .static import router as static_router
from .settings import router as settings_router

routers = (
  auth_router,
  feedback_router,
  i18n_router,
  catalog_router,
  static_router,
  settings_router,
)

ONEC_ENABLED = os.getenv("ONEC_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
if ONEC_ENABLED:
  from .onec import router as onec_router
  routers = (*routers, onec_router)
