import sys
from loguru import logger

LOG_LEVEL = "INFO"
LOG_FILE = "logs/app_{time:YYYY-MM-DD}.log"
LOG_ROTATION = "1 day"
LOG_RETENTION = "7 days"
LOG_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"

# Remove default handler to prevent duplicate console logs if configured below
logger.remove()

logger.add(
    sys.stdout,
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    colorize=True
)

logger.add(
    LOG_FILE,
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    rotation=LOG_ROTATION,
    retention=LOG_RETENTION,
    enqueue=True,
    backtrace=True,
    diagnose=True
)

log = logger