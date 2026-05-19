# app/core/metrics.py
from prometheus_client import Counter, Gauge, Histogram
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# 定义指标
REQUEST_COUNT = Counter(
    "alert_api_requests_total",
    "Total number of API requests",
    ["method", "endpoint", "status_code"]
)
REQUEST_LATENCY = Histogram(
    "alert_api_request_latency_seconds",
    "API request latency",
    ["endpoint"]
)
ALERT_METRICS = Gauge(
    "alert_core_metrics",
    "Core alert analysis metrics",
    ["metric_name"]
)

# 中间件：采集请求指标
class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 记录请求开始时间
        import time
        start_time = time.time()
        # 处理请求
        response = await call_next(request)
        # 计算耗时
        latency = time.time() - start_time
        # 记录指标
        endpoint = request.url.path
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=endpoint,
            status_code=response.status_code
        ).inc()
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(latency)
        return response

# 注册指标到FastAPI
def register_metrics(app):
    app.add_middleware(PrometheusMiddleware)
    # 暴露metrics接口
    from prometheus_client import generate_latest
    @app.get("/metrics")
    async def metrics():
        return Response(
            content=generate_latest(),
            media_type="text/plain; version=0.0.4; charset=utf-8"
        )