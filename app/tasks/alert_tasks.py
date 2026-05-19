# app/tasks/alert_tasks.py
from app.tasks import celery_app
from app.services.root_cause import RootCauseAnalysisService
from app.services.risk_warning import RiskWarningService
from app.core.logger import logger

@celery_app.task(bind=True, name="async_alert_analysis")
async def async_alert_analysis(self, structured_data, time_window_minutes=None):
    """异步执行根因分析和风险预警"""
    try:
        # 根因分析
        rca_service = RootCauseAnalysisService(time_window_minutes=time_window_minutes)
        root_cause_result = await rca_service.process(structured_data)
        # 风险预警
        warning_service = RiskWarningService()
        risk_warning_result = await warning_service.process(structured_data)
        # 结果存储（数据库/缓存）
        from app.crud.fault import create_fault_events
        from app.crud.warning import create_risk_warnings
        await create_fault_events(root_cause_result)
        await create_risk_warnings(risk_warning_result)
        return {
            "root_cause_result": root_cause_result,
            "risk_warning_result": risk_warning_result
        }
    except Exception as e:
        logger.error(f"异步任务执行失败: {str(e)}", exc_info=True)
        self.retry(exc=e)