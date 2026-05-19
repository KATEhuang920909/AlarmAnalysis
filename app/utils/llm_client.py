# app/utils/llm_client.py
import httpx
from app.core.config import settings
from app.core.logger import logger

class LLMClient:
    def __init__(self):
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.api_url = settings.llm_api_url
        self.client = httpx.AsyncClient(timeout=30.0)

    async def structured_extract(self, message_content: str) -> dict:
        """异步调用LLM进行结构化提取，支持降级"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        prompt = self._build_extract_prompt(message_content)
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        try:
            response = await self.client.post(
                self.api_url, headers=headers, json=data
            )
            response.raise_for_status()
            result = response.json()["choices"][0]["message"]["content"]
            return json.loads(result)
        except Exception as e:
            logger.error(f"LLM调用失败: {str(e)}", exc_info=True)
            # 降级返回模拟结果
            return self._get_fallback_result(message_content)

    def _build_extract_prompt(self, content: str) -> str:
        """构建提取提示词"""
        prompt = """你是运维日志结构化专家，基于以下告警日志，提取核心要素，输出JSON格式：
- 告警级别：ERROR/WARNING/INFO
- 影响服务：从日志中提取，无则填无
- 错误类型：从日志中提取核心错误分类
- 根因关键词：3-5个核心根因相关的关键词
- 影响范围：从日志中提取，无则填无
- 是否已知问题：是/否
告警日志：{content}""".format(content=content)
        return prompt

    def _get_fallback_result(self, content: str) -> dict:
        """降级模拟结果"""
        return {
            "告警级别": "WARNING",
            "影响服务": "UNKNOWN",
            "错误类型": "未知错误",
            "根因关键词": ["未知", "日志解析失败"],
            "影响范围": "未知",
            "是否已知问题": "否"
        }