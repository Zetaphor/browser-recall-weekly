import sys
from loguru import logger

# --- Configuration ---
LOG_LEVEL = "INFO"  # Loguru uses string levels (TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL)
LOG_FILE = "logs/app_{time:YYYY-MM-DD}.log" # File path for logs, with date-based rotation
LOG_ROTATION = "1 day" # Rotate logs daily
LOG_RETENTION = "7 days" # Keep logs for 7 days
LOG_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
# ---------------------

# Remove default handler to prevent duplicate console logs if configured below
logger.remove()

# Configure console logging
logger.add(
    sys.stdout,
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    colorize=True # Enable colorized output for the console
)

# Configure file logging with rotation and retention
logger.add(
    LOG_FILE,
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    rotation=LOG_ROTATION,
    retention=LOG_RETENTION,
    enqueue=True, # Make logging asynchronous (good for performance)
    backtrace=True, # Better tracebacks
    diagnose=True   # Extra details on errors
)

# Export the configured logger instance
# Loguru's logger is already a singleton, so we just export it.
log = logger