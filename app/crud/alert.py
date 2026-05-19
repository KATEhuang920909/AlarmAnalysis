# app/crud/alert.py
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.alert import AlertRecord
from app.schemas.alert import AlertStructuredData

async def create_alert_record(db: AsyncSession, alert_data: AlertStructuredData):
    """创建告警记录"""
    db_alert = AlertRecord(
        log_time=datetime.strptime(alert_data.log_time, "%Y-%m-%d %H:%M:%S"),
        log_level=alert_data.log_level,
        source_ip=alert_data.source_ip,
        content=alert_data.content,
        alert_level=alert_data.alert_level,
        affected_service=alert_data.affected_service,
        error_type=alert_data.error_type,
        root_cause_keywords=alert_data.root_cause_keywords,
        affected_scope=alert_data.affected_scope,
        is_known_issue=alert_data.is_known_issue
    )
    db.add(db_alert)
    await db.commit()
    await db.refresh(db_alert)
    return db_alert

async def get_alert_records_by_service(
    db: AsyncSession, service: str, skip: int = 0, limit: int = 100
):
    """按服务查询告警记录"""
    return await db.query(AlertRecord).filter(
        AlertRecord.affected_service == service
    ).offset(skip).limit(limit).all()