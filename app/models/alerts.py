# app/models/alert.py
from sqlalchemy import Column, Integer, String, DateTime, JSON, Float
from app.models.base import Base

class AlertRecord(Base):
    """告警记录模型"""
    __tablename__ = "alert_records"

    id = Column(Integer, primary_key=True, index=True)
    log_time = Column(DateTime, index=True)
    log_level = Column(String(20))
    source_ip = Column(String(50))
    content = Column(String(2000))
    alert_level = Column(String(20))
    affected_service = Column(String(100))
    error_type = Column(String(100))
    root_cause_keywords = Column(JSON)
    affected_scope = Column(String(200))
    is_known_issue = Column(String(10))
    create_time = Column(DateTime, default=datetime.utcnow)

class AlertDenoiseResult(Base):
    """告警降噪结果模型"""
    __tablename__ = "alert_denoise_results"

    id = Column(Integer, primary_key=True, index=True)
    message = Column(String(2000), index=True)
    service = Column(String(100), index=True)
    alert_count = Column(Integer)
    first_time = Column(DateTime)
    last_time = Column(DateTime)
    is_valid = Column(String(10))
    priority = Column(String(10))
    judge_reason = Column(String(1000))
    handle_suggestion = Column(String(1000))