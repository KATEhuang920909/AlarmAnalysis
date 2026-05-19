# app/tasks/__init__.py
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "alert_analysis_tasks",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.alert_tasks",
        "app.tasks.cron_tasks"
    ]
)

# 配置
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_retry_policy={
        "max_retries": 3,
        "interval_start": 1,
        "interval_step": 2,
        "interval_max": 5,
    }
)