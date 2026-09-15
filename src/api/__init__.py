from .categories import router as categories_router
from .auth import router as auth_router
from .changes import router as changes_router
from .feedback import router as feedback_router
from .i18n import router as i18n_router
from .logs import router as logs_router
from .moysklad import router as moysklad_router
from .payments import router as payments_router
from .products import router as products_router
from .purchases import router as purchases_router
from .static import router as static_router
from .settings import router as settings_router
from .yookassa import router as yookassa_router
from .stock import router as stock_router

routers = (
  auth_router,
  categories_router,
  changes_router,
  feedback_router,
  i18n_router,
  logs_router,
  moysklad_router,
  payments_router,
  products_router,
  static_router,
  purchases_router,
  settings_router,
  yookassa_router,
  stock_router,
)

# BEGIN DEV-ONLY PURCHASE DELETION: remove this block and dev_purchases.py to exclude it.
from src.core.config import settings

if settings.STAGE == 'DEV' and settings.DEV_PURCHASE_DELETE_ENABLED:
  from .dev_purchases import router as dev_purchases_router
  routers += (dev_purchases_router,)
# END DEV-ONLY PURCHASE DELETION
