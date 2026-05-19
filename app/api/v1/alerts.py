# app/api/v1/alerts.py
from fastapi import APIRouter, Depends, BackgroundTasks
from app.schemas.alert import AlertAnalysisRequest, AlertAnalysisResponse
from app.services.data_preprocess import DataPreprocessService
from app.services.alert_denoise import AlertDenoiseService
from app.services.root_cause import RootCauseAnalysisService
from app.services.risk_warning import RiskWarningService
from app.tasks.alert_tasks import async_alert_analysis

router = APIRouter(prefix="/alerts", tags=["告警分析"])

@router.post("/analysis", response_model=AlertAnalysisResponse)
async def alert_analysis(
    req: AlertAnalysisRequest,
    background_tasks: BackgroundTasks,
    preprocess_service: DataPreprocessService = Depends(),
    denoise_service: AlertDenoiseService = Depends()
):
    """
    告警分析接口（同步/异步）
    - 同步：返回基础分析结果
    - 异步：提交后台任务，返回任务ID，供后续查询结果
    """
    # 1. 预处理数据
    structured_data = await preprocess_service.process(
        dataset_path=req.dataset_path, raw_logs=req.raw_logs
    )
    # 2. 同步执行基础降噪（耗时短的操作）
    denoise_result = await denoise_service.process(structured_data)
    # 3. 耗时操作（根因分析、风险预警）提交异步任务
    task_id = await async_alert_analysis.delay(
        structured_data=structured_data,
        time_window_minutes=req.time_window_minutes
    )
    # 4. 返回响应
    return AlertAnalysisResponse(
        data={
            "structured_data": structured_data,
            "denoise_result": denoise_result,
            "task_id": task_id,
            "tips": "根因分析和风险预警已提交异步任务，可通过/tasks/{task_id}查询结果"
        }
    )

@router.get("/metrics")
async def get_alert_metrics():
    """获取告警分析核心指标"""
    from app.core.metrics import alert_metrics
    return {
        "total_alerts": alert_metrics["total_alerts"],
        "valid_alerts": alert_metrics["valid_alerts"],
        "noise_reduction_rate": alert_metrics["noise_reduction_rate"],
        "fault_events": alert_metrics["fault_events"]
    }