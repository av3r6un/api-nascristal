import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOGS_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_FILE_PATH = LOGS_DIR / "actions.log"
LOGGER_NAME = "nascrystal.actions"


class WebhookAccessFilter(logging.Filter):
  def filter(self, record: logging.LogRecord) -> bool:
    if not isinstance(record.args, tuple) or len(record.args) != 5:
      return True
    client, method, url, protocol, status = record.args
    if isinstance(url, str):
      path = url.split('?', 1)[0]
      if path == '/webhooks' or path.startswith('/webhooks/'):
        record.args = client, method, path, protocol, status
    return True


def get_actions_logger() -> logging.Logger:
  LOGS_DIR.mkdir(parents=True, exist_ok=True)

  logger = logging.getLogger(LOGGER_NAME)
  if logger.handlers:
    return logger

  logger.setLevel(logging.INFO)
  logger.propagate = False

  filepath = str(LOG_FILE_PATH)
  handler = RotatingFileHandler(filepath, maxBytes=3 * 1024 * 1024, backupCount=5, encoding="utf-8")
  handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")
  )
  logger.addHandler(handler)
  return logger
