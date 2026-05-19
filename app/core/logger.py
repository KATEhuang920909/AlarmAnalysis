# app/core/logger.py
from loguru import logger
import sys
from app.core.config import settings

# 移除默认日志
logger.remove()
# 添加控制台输出
logger.add(
    sys.stdout,
    level="DEBUG" if settings.debug else "INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{line} | {message}",
    enqueue=True
)
# 添加文件输出（按天轮转）
logger.add(
    "logs/alert_analysis_{time:YYYY-MM-DD}.log",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{line} | {message}",
    rotation="00:00",
    retention="7 days",
    compression="zip",
    enqueue=True
)
# 添加错误日志单独输出
logger.add(
    "logs/error_{time:YYYY-MM-DD}.log",
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{line} | {message}\n{exception}",
    rotation="00:00",
    retention="30 days",
    compression="zip",
    enqueue=True
)