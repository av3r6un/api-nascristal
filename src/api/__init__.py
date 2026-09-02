from .auth import router as auth_router
from .feedback import router as feedback_router
from .i18n import router as i18n_router
from .logs import router as logs_router
from .moysklad import router as moysklad_router
from .payments import router as payments_router
from .products import router as products_router
from .static import router as static_router
from .settings import router as settings_router
from .yookassa import router as yookassa_router
from .stock import router as stock_router

routers = (
  auth_router,
  feedback_router,
  i18n_router,
  logs_router,
  moysklad_router,
  payments_router,
  products_router,
  static_router,
  settings_router,
  yookassa_router,
  stock_router,
)
