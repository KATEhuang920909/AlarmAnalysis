import pandas as pd
import numpy as np
import json
import re
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from sklearn.cluster import DBSCAN
import networkx as nx
from prophet import Prophet
import warnings
warnings.filterwarnings('ignore')

# --------------------------
# 大模型/智能体基础配置
# --------------------------
from openai import OpenAI

class AIOpsAgent:
    """智能体基类：所有模块共用"""
    def __init__(self, name="AIOps智能体"):
        self.name = name
        self.client = OpenAI(
            api_key="你的API_KEY",  # 可换成本地大模型
            base_url="https://api.chatanywhere.tech/v1"  # 国内中转地址
        )

    def llm_chat(self, prompt):
        """调用大模型"""
        response = self.client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return response.choices[0].message.content.strip()

# 全局智能体
ai_agent = AIOpsAgent(name="GAIA-AIOps-Engine")


class DataStructurer:
    """GAIA数据统一结构化"""

    def __init__(self, data_path="./MicroSS"):
        self.path = data_path

    def load_metric(self, file):
        """加载指标数据并结构化"""
        df = pd.read_csv(file)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['node'] = file.split('/')[-1].split('-')[0]
        df['metric_type'] = file.split('/')[-1].split('-')[2]
        return df

    def load_trace(self, file):
        """加载调用链结构化"""
        df = pd.read_csv(file)
        df['start_time'] = pd.to_datetime(df['start_time'])
        df['is_error'] = df['status_code'].apply(lambda x: 0 if x == 200 else 1)
        return df

    def load_run_anomaly(self, file):
        """加载异常注入（真实根因标签）"""
        df = pd.read_csv(file)
        df['datetime'] = pd.to_datetime(df['datetime'])
        return df

    def build_alarm_table(self, metric_df, trace_df):
        """构建统一告警表"""
        alarms = []

        # 指标异常告警
        for idx, row in metric_df.iterrows():
            if np.abs(row['value'] - row['value'].mean()) > 3 * row['value'].std():
                alarms.append({
                    'time': row['timestamp'],
                    'node': row['node'],
                    'type': 'metric',
                    'content': f"{row['metric_type']} 异常波动",
                    'level': 'critical' if row['value'] > 1.5 else 'warning'
                })

        # 调用链异常告警
        for idx, row in trace_df[trace_df['is_error'] == 1].iterrows():
            alarms.append({
                'time': row['start_time'],
                'node': row['service_name'],
                'type': 'trace',
                'content': f"接口调用失败 {row['status_code']}",
                'level': 'critical'
            })

        return pd.DataFrame(alarms)

# 使用示例
# struct = DataStructurer()
# metric_df = struct.load_metric("metric.csv")
class AlarmDenoiseAgent(AIOpsAgent):
    """告警降噪智能体"""
    def __init__(self):
        super().__init__("告警降噪智能体")

    def deduplicate(self, alarm_df):
        """去重：5分钟内相同告警只保留1条"""
        alarm_df = alarm_df.sort_values('time')
        alarm_df['time_gap'] = alarm_df['time'].diff().dt.total_seconds().fillna(0)
        alarm_df['is_duplicate'] = alarm_df.apply(
            lambda x: 1 if x['time_gap'] < 300 else 0, axis=1
        )
        return alarm_df[alarm_df['is_duplicate'] == 0]

    def cluster_denoise(self, alarm_df):
        """聚类合并相似告警"""
        feat = pd.get_dummies(alarm_df[['node', 'type']])
        cluster = DBSCAN(eps=1.5, min_samples=2).fit(feat)
        alarm_df['cluster'] = cluster.labels_
        return alarm_df

    def llm_denoise(self, alarm_list):
        """大模型智能降噪：识别风暴、冗余、无效告警"""
        prompt = f"""
你是智能告警降噪专家，请对以下告警做降噪处理：
1. 删除重复告警
2. 合并同类告警
3. 压制风暴告警
4. 只保留关键根因告警

告警列表：
{alarm_list}

输出格式：
{{
    "denoised_alarms": [精简后的告警],
    "reason": "降噪说明"
}}
"""
        return self.llm_chat(prompt)

# 使用
# denoise_agent = AlarmDenoiseAgent()
# clean_alarms = denoise_agent.deduplicate(alarms)
class RootCauseAgent(AIOpsAgent):
    """根因定位智能体：大模型+调用链图+异常注入"""
    def __init__(self):
        super().__init__("根因定位智能体")

    def build_service_graph(self, trace_df):
        """构建服务依赖图"""
        G = nx.DiGraph()
        for _, row in trace_df.iterrows():
            G.add_edge(row['service_name'], row['parent_service'], weight=row['duration'])
        return G

    def time_window_analyze(self, alarm_df, run_df, window=3):
        """时间窗口对齐：告警前后3分钟"""
        alarm_time = alarm_df['time'].iloc[0]
        start = alarm_time - timedelta(minutes=window)
        end = alarm_time + timedelta(minutes=window)
        return run_df[(run_df['datetime'] >= start) & (run_df['datetime'] <= end)]

    def llm_root_cause(self, alarm, metric_data, trace_data, run_data):
        """大模型推理根因"""
        prompt = f"""
你是AIOps根因定位专家，基于以下数据定位故障根因：

告警：{alarm}
指标异常：{metric_data.describe().to_string()}
调用链异常：{trace_data[trace_data['is_error']==1].to_string()}
真实异常注入：{run_data.to_string()}

请输出：
1. 根因服务/节点
2. 异常类型（内存/CPU/网络/接口）
3. 故障传播路径
4. 置信度
"""
        return self.llm_chat(prompt)

# 使用
# rca_agent = RootCauseAgent()
# rca_result = rca_agent.llm_root_cause(alarm, m, t, r)
class RiskForecastAgent(AIOpsAgent):
    """风险预警智能体：预测未来15分钟风险"""
    def forecast(self, metric_df):
        """Prophet预测指标趋势"""
        df = metric_df[['timestamp', 'value']].rename(
            columns={'timestamp':'ds', 'value':'y'}
        )
        model = Prophet()
        model.fit(df)
        future = model.make_future_dataframe(periods=15, freq='min')
        forecast = model.predict(future)
        return forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']]

    def llm_risk_warn(self, forecast_data):
        """大模型判断风险等级"""
        prompt = f"""
根据指标预测结果，判断未来15分钟风险等级（低/中/高）：
{forecast_data.tail(15).to_string()}
输出风险等级 + 原因
"""
        return self.llm_chat(prompt)

class ReportAgent(AIOpsAgent):
    """趋势分析 + 自动报告生成"""
    def statics(self, alarm_df):
        return {
            "total_alarms": len(alarm_df),
            "critical_count": len(alarm_df[alarm_df['level']=='critical']),
            "top_nodes": alarm_df['node'].value_counts().head(5).to_dict()
        }

    def llm_generate_report(self, stats, rca_result, warn_result):
        """大模型生成专业运维报告"""
        prompt = f"""
生成一份GAIA数据集AIOps分析报告：
统计：{stats}
根因定位结果：{rca_result}
风险预警：{warn_result}
要求：专业、简洁、可直接用于汇报
"""
        return self.llm_chat(prompt)

if __name__ == "__main__":
    # ======================
    # 1. 加载并结构化数据
    # ======================
    struct = DataStructurer()
    metric = struct.load_metric("metric.csv")
    trace = struct.load_trace("trace.csv")
    run = struct.load_run_anomaly("run.csv")
    alarms = struct.build_alarm_table(metric, trace)
    print("✅ 数据结构化完成")

    # ======================
    # 2. 告警降噪智能体
    # ======================
    denoise = AlarmDenoiseAgent()
    clean_alarms = denoise.deduplicate(alarms)
    denoise_result = denoise.llm_denoise(clean_alarms.to_dict('records'))
    print("✅ 告警降噪完成")
    print(denoise_result)

    # ======================
    # 3. 根因定位智能体
    # ======================
    rca = RootCauseAgent()
    rca_result = rca.llm_root_cause(clean_alarms.iloc[0], metric, trace, run)
    print("✅ 根因定位完成")
    print(rca_result)

    # ======================
    # 4. 风险预警智能体
    # ======================
    forecast = RiskForecastAgent()
    pred = forecast.forecast(metric)
    warn = forecast.llm_risk_warn(pred)
    print("✅ 风险预警完成")
    print(warn)

    # ======================
    # 5. 趋势分析 + 报告
    # ======================
    report = ReportAgent()
    stats = report.statics(clean_alarms)
    final_report = report.llm_generate_report(stats, rca_result, warn)
    print("\n===== 📊 最终AIOps分析报告 =====")
    print(final_report)