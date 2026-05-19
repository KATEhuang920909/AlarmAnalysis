# app/schemas/alert.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional, Dict

# 请求Schema
class AlertAnalysisRequest(BaseModel):
    """告警分析请求体"""
    dataset_path: Optional[str] = Field(None, description="本地数据集路径")
    raw_logs: Optional[List[str]] = Field(None, description="原始告警日志列表（优先级高于dataset_path）")
    time_window_minutes: Optional[int] = Field(None, description="时间窗口（覆盖全局配置）")

# 响应Schema
class AlertStructuredData(BaseModel):
    """结构化告警数据"""
    log_time: str
    log_level: str
    source_ip: str
    content: str
    alert_level: str
    affected_service: str
    error_type: str
    root_cause_keywords: List[str]
    affected_scope: str
    is_known_issue: str

class AlertDenoiseResult(BaseModel):
    """告警降噪结果"""
    message: str
    service: str
    alert_count: int
    first_time: datetime
    last_time: datetime
    is_valid: str = Field(alias="是否有效")
    priority: str = Field(alias="优先级")
    judge_reason: str = Field(alias="判断依据")
    handle_suggestion: str = Field(alias="建议处理动作")

class AlertAnalysisResponse(BaseModel):
    """告警分析总响应"""
    code: int = 200
    msg: str = "success"
    data: Dict[str, any] = Field(
        description="分析结果，包含结构化数据、降噪结果、根因分析、风险预警"
    )