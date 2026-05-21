


# 大模型告警分析方案完整实现代码
# 包含全流程核心模块 + 简单Web可视化界面
# 运行前请安装依赖：pip install pandas flask scikit-learn sentence-transformers requests

import pandas as pd
from flask import Flask, render_template, jsonify
from datetime import datetime
from sklearn.cluster import DBSCAN
from sentence_transformers import SentenceTransformer
from zhipuai import ZhipuAI

import json
# ===================== 配置项（可根据实际情况修改）=====================
# 大模型API配置（预留，可替换为自己的API地址和密钥）

LLM_API_KEY = "aaa16e53a2cf92220d4fd3d9282a9fa7.A8zR3KN6eI1uKwZM"
LLM_MODEL = "glm-4-long"
# 初始化客户端
client = ZhipuAI(api_key=LLM_API_KEY)
# 服务依赖关系图谱（根据方案定义）
SERVICE_DEPENDENCY = {
    "frontend": ["mobservice1", "mobservice2", "webservice1", "webservice2"],
    "middleware": ["redisservice1", "redisservice2"],
    "database": ["dbservice1", "dbservice2"],
    "log": ["logservice1", "logservice2"],
    "dependency_chain": ["frontend", "middleware", "database"]
}

# 告警优先级定义
PRIORITY_LEVELS = {
    "P0": "必须立即处理",
    "P1": "1小时内处理",
    "P2": "当天处理",
    "P3": "低优先级，可忽略"
}

# 时间窗口配置（根因分析用）
TIME_WINDOW_MINUTES = 10

# 数据集路径
DATASET_PATH = "../GAIA-DataSet-main/sample/run_0801.xlsx"
# ============================================================================

# 初始化Flask应用
app = Flask(__name__)

# 全局变量（存储处理后的数据）
processed_data = {}
alert_events = []
risk_warnings = []
core_metrics = {}

# ===================== 核心功能模块实现 =====================

# 1. 数据预处理与结构化解析模块
class DataPreprocessor:
    def __init__(self, df):
        self.df = df
        self.structured_df = None

    def split_datetime(self):
        """拆分datetime字段为年、月、日、时、分、秒"""
        self.df['datetime'] = pd.to_datetime(self.df['timestamp_raw'], errors='coerce')
        self.df['year'] = self.df['datetime'].dt.year
        self.df['month'] = self.df['datetime'].dt.month
        self.df['day'] = self.df['datetime'].dt.day
        self.df['hour'] = self.df['datetime'].dt.hour
        self.df['minute'] = self.df['datetime'].dt.minute
        self.df['second'] = self.df['datetime'].dt.second
        return self.df

    def parse_log_line(self,line: str) -> dict:
        """
        解析单行日志，返回结构化字典。
        支持三种格式：
          1) 标准6字段：timestamp | level | src_ip | svc_ip | service | message
          2) 标准7字段：timestamp | level | src_ip | svc_ip | service | track_id | message
          3) 无结构文本（如 SQLAlchemy 错误提示）
        """
        # print(line)
        line = line.rstrip('\n')

        # 尝试按 " | " 分割（注意空格）
        parts = line.split(" | ")
        # 常见的无结构错误消息（第三种格式）
        if len(parts) not in (6, 7):
            # 如果是纯文本（如以 "(Background on this error" 开头）
            return {
                "level": "NONE",  # 默认级别，可调整
                "message": line
            }

        # 有结构日志：至少6个部分
        timestamp_str = parts[0].strip()
        level = parts[1].strip()
        src_ip = parts[2].strip()
        svc_ip = parts[3].strip()
        service = parts[4].strip()

        # 区分6字段还是7字段
        if len(parts) == 6:
            track_id = None
            content = parts[5].strip()
        else:  # len == 7
            track_id = parts[5].strip()
            content = parts[6].strip()

        # 转换时间戳（可选，保留原始字符串和解析后的ISO格式）
        parsed_ts = None
        try:
            # 格式：2021-07-01 15:10:23,517 -> 替换逗号为小数点
            normalized = timestamp_str.replace(',', '.')
            dt = datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S.%f")
            parsed_ts = dt.isoformat()
        except ValueError:
            parsed_ts = None

        result = {
            "timestamp_raw": timestamp_str,
            "timestamp_iso": parsed_ts,
            "level": level,
            "src_ip": src_ip,
            "service_ip": svc_ip,
            "content": content,
        }
        if track_id:
            result["track_id"] = track_id

        return result

    def regex_split_message(self):
        """用正则拆分message字段为基础结构化字段"""
        # 正则匹配日志格式：时间 | 级别 | IP | 内容
        split_result = self.df['message'].apply(lambda x: self.parse_log_line(x))
        self.df = pd.concat([self.df, pd.DataFrame(split_result.values.tolist())], axis=1)
        return self.df

    def llm_structured_extract(self, message_content):
        """大模型零样本结构化提取（预留真实API接口，默认返回模拟结果）"""
        # prompt = "你是运维日志结构化专家，基于以下告警日志，提取核心要素，输出JSON格式：\n"
        # # prompt += "- 告警级别：ERROR/WARNING/INFO\n"
        # prompt += "- 影响服务：从日志中提取，无则填无\n"
        # prompt += "- 错误类型：从日志中提取核心错误分类，如数据库连接超时、缓存内存溢出等\n"
        # prompt += "- 根因关键词：3-5个核心根因相关的关键词\n"
        # prompt += "- 影响范围：从日志中提取，无则填无\n"
        # prompt += "- 是否已知问题：是/否，基于通用运维知识判断\n"
        # prompt += f"告警日志：{message_content}"
        # try:
        #
        #     # 创建聊天完成请求
        #     response = client.chat.completions.create(
        #         model=LLM_MODEL,
        #         messages=[
        #             {"role": "user",
        #              "content": prompt}
        #         ]
        #     )
        #     # 获取回复
        #     result=response.choices[0].message.content
        #
        #     return json.loads(result)
        # except Exception as e:
        #     print(f"大模型API调用失败：{e}，返回模拟结果")


        # 模拟返回结果（用于演示）
        return {
            "影响服务": "dbservice1",
            "错误类型": "数据库连接超时",
            "根因关键词": ["数据库", "连接超时", "IO过高", "主从同步"],
            "影响范围": "数据库服务",
            "是否已知问题": "否"
        }

    def process(self):
        """全量数据预处理主流程"""
        print("开始数据预处理...")

        self.regex_split_message()

        self.split_datetime()
        # 对每条日志进行大模型结构化提取（演示用，仅处理前100条，全量处理可取消注释）
        """
        print("开始大模型结构化提取...")
        extract_results = []
        for idx, row in self.df.head(1000).iterrows():
            result = self.llm_structured_extract(row['message'])
            extract_results.append(result)
        # 合并提取结果到DataFrame
        extract_df = pd.DataFrame(extract_results)
        self.structured_df = pd.concat([self.df.head(1000).reset_index(drop=True), extract_df], axis=1)
        print("数据预处理完成！")
        return self.structured_df
        """
        return self.df


# 2. 告警智能降噪与优先级分级模块
class AlertDenoise:
    def __init__(self, structured_df):
        self.df = structured_df
        self.denoised_df = None
        self.alert_clusters = []

    # def base_duplicate_removal(self):
    #     """基础完全重复告警去重"""
    #     # 按message完全去重，统计出现次数
    #     duplicate_stats = self.df.groupby('content').agg({
    #         'timestamp_raw': ['min', 'max', 'count'],
    #         'service': 'first'
    #     }).reset_index()
    #     duplicate_stats.columns = ['content', 'first_time', 'last_time', 'alert_count', 'service']
    #     return duplicate_stats

    def base_duplicate_removal(self):
        """基础完全重复告警去重（5分钟窗口）"""
        # 将时间戳转为 datetime 类型
        self.df['timestamp_dt'] = pd.to_datetime(self.df['timestamp_raw'])

        # 按 content 和 5分钟时间窗口分组
        # 计算每个告警所属的时间窗口（向下取整到5分钟）
        self.df['time_window'] = self.df['timestamp_dt'].dt.floor('30min')

        # 按 content + 5分钟窗口 去重，统计出现次数
        duplicate_stats = self.df.groupby(['level','src_ip','service_ip','content','time_window']).agg({
            'timestamp_dt': ['min', 'max', 'count'],
            'service': 'first'
        }).reset_index()

        # 扁平化多级列名
        duplicate_stats.columns = ['level','src_ip','service_ip','content', 'time_window', 'first_time', 'last_time', 'alert_count', 'service']

        # 可选：删除辅助列
        # duplicate_stats = duplicate_stats.drop(columns=['time_window'])

        return duplicate_stats

    def semantic_clustering(self):
        """语义聚类：Sentence-BERT编码 + DBSCAN聚类"""
        print("开始告警语义聚类...")
        # 加载预训练模型
        model = SentenceTransformer('all-MiniLM-L6-v2')
        # 对告警内容进行编码
        sentences = self.df['content'].tolist()
        embeddings = model.encode(sentences, show_progress_bar=True)
        # DBSCAN聚类
        clustering = DBSCAN(eps=0.4, min_samples=1, metric='cosine').fit(embeddings)
        labels = clustering.labels_
        # 合并聚类结果
        self.df['cluster_id'] = [int(k) for k in labels]
        # 统计每个聚类的信息
        for cluster_id in set(labels):
            if cluster_id == -1:
                continue
            cluster_data = self.df[self.df['cluster_id'] == cluster_id]
            self.alert_clusters.append({
                "cluster_id": int(cluster_id),
                "alert_count": len(cluster_data),
                "service": cluster_data['service'].iloc[0],
                "level": cluster_data['level'].iloc[0],
                "first_time": cluster_data['timestamp_raw'].min(),
                "last_time": cluster_data['timestamp_raw'].max(),
                "sample_content": cluster_data['content'].values.unique().tolist(),
            })
        # print(self.alert_clusters)
        print(f"语义聚类完成，共生成{len(self.alert_clusters)}个告警聚类")
        self.df.to_excel('clustered.xlsx', index=False)
        return self.df

    def llm_alert_validity_check(self, output_file):
        """大模型告警有效性判断与优先级分级（预留真实API接口，默认返回模拟结果）"""
        # 真实API调用代码（取消注释即可使用）
        report = ""
        with open(output_file, "w", encoding="utf-8") as f:
            for unit in self.alert_clusters:
                cluster_id = unit['cluster_id']
                values = unit.values()
                prompt = f"请作为SRE专家，分析以下属于同一聚类ID的日志统计信息。\
                聚类ID: [替换为具体ID，如0、1、2]\
                日志统计信息：\
                [{values}]\
                请输出结构化分析报告，只包含如下内容：\
                事件ID: [替换为具体ID，如0、1、2]\
                1. 聚类概要：告警类型、严重程度（高/中/低）、典型日志模板（动态变量用{{}}标注）\
                2. 关键特征：涉及的主要服务、日志级别、核心关键词、时间/频率模式、相关ID/参数规律\
                3. 建议与行动：监控指标、告警优化（是否需升降级）、处理建议（正常流程可降级DEBUG，异常流程给出排查步骤）、还需哪些数据确认根因"
                prompt = prompt.replace("[替换为具体ID，如0、1、2]", str(cluster_id))

                full_content = ""
                response = client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    thinking={
                        "type": "disabled",  # 启用深度思考模式
                    },
                    stream=True,
                    max_tokens=4000
                )

                for chunk in response:
                    content = chunk.choices[0].delta.content
                    if content:
                        full_content += content
                        print(content, end="", flush=True)  # 实时打印
                        f.write(content)
                        f.flush()  # 实时刷新，不缓存
                report +=""
                report += full_content + "\n"
        print(f"\n\n✅ 报告已生成：{output_file}")
        return report

    def process(self):
        """智能降噪主流程"""
        print("开始告警智能降噪...")
        # 基础去重
        duplicate_stats = self.base_duplicate_removal()
        duplicate_stats.to_excel("去重数据.xlsx")
        # exit()
        # 语义聚类
        self.semantic_clustering()


        # 计算核心指标

        noise_reduction_rate = (self.df.shape[0] - duplicate_stats.shape[0]) / self.df.shape[0] * 100
        core_metrics['noise_reduction_rate'] = round(noise_reduction_rate, 2)
        core_metrics['alert_clusters'] = len(self.alert_clusters)
        print(f"智能降噪完成，总告警数：{self.df.shape[0]}，降噪告警数：{duplicate_stats.shape[0]}，告警事件数：{len(self.alert_clusters)}，降噪率：{noise_reduction_rate:.2f}%")
        print("生成告警分析报告...")
        report = self.llm_alert_validity_check("告警分析报告.md")
        return report

# 3. 告警根因定位与关联分析模块
class RootCauseAnalysis:
    def __init__(self, structured_df):
        self.df = structured_df
        self.fault_events = []

    def time_window_correlation(self):
        """时间窗口内的告警关联分析"""
        # 按时间排序
        sorted_df = self.df.sort_values('timestamp_raw').reset_index(drop=True)
        # 按时间窗口分组
        sorted_df['time_window'] = sorted_df['timestamp_raw'].dt.floor(f'{TIME_WINDOW_MINUTES}min')
        # 统计每个时间窗口的告警
        window_groups = sorted_df.groupby('time_window')
        return window_groups

    def llm_root_cause_inference(self, alert_list):
        """大模型根因因果推理（预留真实API接口，默认返回模拟结果）"""
        # 真实API调用代码（取消注释即可使用）
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}"
        }
        prompt = "你是运维根因定位专家，基于以下信息，完成根因分析，输出JSON格式：\n"
        prompt += "1. 根因告警：明确指出哪条告警是根因\n"
        prompt += "2. 衍生告警列表：列出所有由根因导致的衍生告警\n"
        prompt += "3. 根因分析：详细说明根因定位的推理过程，结合服务依赖、告警时序、运维知识\n"
        prompt += "4. 故障影响范围：说明本次故障影响的服务、业务范围\n"
        prompt += "5. 修复建议：给出具体的、可落地的根因修复方案\n"
        prompt += "输入信息：\n"
        prompt += f"- 服务依赖关系图：{SERVICE_DEPENDENCY}\n"
        prompt += f"- 告警时序列表：按时间排序的告警列表，包含服务名称、告警内容、发生时间\n"
        data = {
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        try:
            response = requests.post(LLM_API_URL, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()['choices'][0]['message']['content']
            return json.loads(result)
        except Exception as e:
            print(f"大模型API调用失败：{e}，返回模拟结果")
        """

        # 模拟返回结果（用于演示）
        return {
            "根因告警": alert_list[0],
            "衍生告警列表": alert_list[1:],
            "根因分析": "根据服务依赖关系，数据库层服务为上游依赖，该告警先于其他服务告警出现，因此判定为根因告警，后续其他服务的告警均为该根因导致的衍生告警",
            "故障影响范围": "数据库服务、中间件服务、前端服务，全链路业务受影响",
            "修复建议": "1. 立即检查数据库主库磁盘IO情况，优化慢查询；2. 调整数据库连接池配置，增加可用连接数；3. 优化主从同步策略，降低同步延迟"
        }

    def process(self):
        """根因定位主流程"""
        print("开始告警根因定位...")
        window_groups = self.time_window_correlation()
        # 对每个时间窗口的告警进行根因分析
        for window_time, group in window_groups:
            if len(group) < 2:
                continue
            # 构建告警时序列表
            alert_list = []
            for idx, row in group.iterrows():
                alert_list.append({
                    "service": row['service'],
                    "message": row['message'],
                    "datetime": row['timestamp_raw'].strftime('%Y-%m-%d %H:%M:%S')
                })
            # 根因推理
            root_cause_result = self.llm_root_cause_inference(alert_list)
            self.fault_events.append({
                "event_time": window_time.strftime('%Y-%m-%d %H:%M:%S'),
                "alert_count": len(group),
                "services": group['service'].unique().tolist(),
                **root_cause_result
            })
        core_metrics['fault_events'] = len(self.fault_events)
        print(self.fault_events)
        print(f"根因定位完成，共识别出{len(self.fault_events)}个故障事件")
        return self.fault_events

# 4. 告警风险预警与趋势分析模块
class RiskWarning:
    def __init__(self, structured_df):
        self.df = structured_df
        self.warnings = []

    def time_series_trend_analysis(self):
        """时序趋势分析，按天统计告警数量"""
        # 按天统计每个服务的告警数量
        daily_stats = self.df.groupby(['day', 'service']).agg({
            'message': 'count'
        }).reset_index()
        daily_stats.columns = ['day', 'service', 'alert_count']
        # 计算增长率
        daily_stats['growth_rate'] = daily_stats.groupby('service')['alert_count'].pct_change()
        return daily_stats

    def llm_risk_warning(self, service_name, alert_features, current_alert):
        """大模型风险预警（预留真实API接口，默认返回模拟结果）"""
        # 真实API调用代码（取消注释即可使用）
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}"
        }
        prompt = "你是运维风险预警专家，基于以下信息，完成故障风险预警，输出JSON格式：\n"
        prompt += "1. 风险等级：高/中/低\n"
        prompt += "2. 预测故障时间：未来X小时/天内\n"
        prompt += "3. 风险类型：比如数据库性能瓶颈、缓存内存溢出、服务可用性风险等\n"
        prompt += "4. 预警依据：详细说明预警的推理逻辑，结合历史趋势、运维知识、类似故障案例\n"
        prompt += "5. 预防措施：给出具体的、可落地的风险预防建议\n"
        prompt += "输入信息：\n"
        prompt += f"- 服务名称：{service_name}\n"
        prompt += f"- 过去7天告警特征：{alert_features}\n"
        prompt += f"- 当前告警内容：{current_alert}\n"
        prompt += f"- 服务依赖关系：{SERVICE_DEPENDENCY}\n"
        prompt += "- 历史故障案例：[]"
        data = {
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        try:
            response = requests.post(LLM_API_URL, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()['choices'][0]['message']['content']
            return json.loads(result)
        except Exception as e:
            print(f"大模型API调用失败：{e}，返回模拟结果")
        """

        # 模拟返回结果（用于演示）
        if alert_features.get('growth_rate', 0) >= 0.2:
            return {
                "风险等级": "高",
                "预测故障时间": "未来24小时内",
                "风险类型": "数据库性能瓶颈",
                "预警依据": "该服务过去3天告警数量持续增长，日增长率超过20%，符合历史故障发生前的特征，存在较高的故障风险",
                "预防措施": "1. 提前检查数据库性能指标，优化慢查询；2. 增加数据库资源配额，提升处理能力；3. 提前做好故障应急预案"
            }
        else:
            return {
                "风险等级": "低",
                "预测故障时间": "无明确预测时间",
                "风险类型": "无明显风险",
                "预警依据": "该服务告警数量无明显增长趋势，无异常波动，当前无明显故障风险",
                "预防措施": "持续观察告警趋势，定期巡检服务状态"
            }

    def process(self):
        """风险预警主流程"""
        print("开始告警风险预警...")
        daily_stats = self.time_series_trend_analysis()
        # 对每个服务进行风险预警
        for service in self.df['service'].unique():
            service_stats = daily_stats[daily_stats['service'] == service].sort_values('day')
            if len(service_stats) < 3:
                continue
            # 构建告警特征
            latest_stats = service_stats.iloc[-1]
            alert_features = {
                "latest_alert_count": latest_stats['alert_count'],
                "growth_rate": latest_stats['growth_rate'],
                "avg_alert_count": service_stats['alert_count'].mean(),
                "max_alert_count": service_stats['alert_count'].max()
            }
            # 获取当前告警样例
            current_alert = self.df[self.df['service'] == service].iloc[-1]['message']
            # 风险预警
            warning_result = self.llm_risk_warning(service, alert_features, current_alert)
            self.warnings.append({
                "service": service,
                "stats_time": f"2021-07-{int(latest_stats['day'])}",
                **warning_result
            })
        print(self.warnings)
        core_metrics['high_risk_warnings'] = len([w for w in self.warnings if w['风险等级'] == '高'])
        core_metrics['medium_risk_warnings'] = len([w for w in self.warnings if w['风险等级'] == '中'])
        core_metrics['low_risk_warnings'] = len([w for w in self.warnings if w['风险等级'] == '低'])
        print(f"风险预警完成，共生成{len(self.warnings)}条风险预警，其中高风险{core_metrics['high_risk_warnings']}条")
        return self.warnings

# ===================== Web界面路由 =====================

@app.route('/')
def index():
    """首页：核心指标看板"""
    return render_template('index.html', metrics=core_metrics)

@app.route('/api/metrics')
def get_metrics():
    """获取核心指标API"""
    return jsonify(core_metrics)

@app.route('/alerts')
def alerts_page():
    """告警列表页"""
    denoised_alerts = processed_data['denoised_df'].to_dict('records')
    return render_template('alerts.html', alerts=denoised_alerts, priorities=PRIORITY_LEVELS)

@app.route('/api/alerts')
def get_alerts():
    """获取告警列表API"""
    denoised_alerts = processed_data['denoised_df'].to_dict('records')
    return jsonify(alerts=denoised_alerts)

@app.route('/faults')
def faults_page():
    """故障事件页"""
    return render_template('faults.html', events=alert_events)

@app.route('/api/faults')
def get_faults():
    """获取故障事件API"""
    return jsonify(events=alert_events)

@app.route('/warnings')
def warnings_page():
    """风险预警页"""
    return render_template('warnings.html', warnings=risk_warnings)

@app.route('/api/warnings')
def get_warnings():
    """获取风险预警API"""
    return jsonify(warnings=risk_warnings)

# ===================== 主流程执行 =====================

def main():
    # 1. 加载原始数据
    print("加载原始数据集...")
    df = pd.read_excel(DATASET_PATH,)

    print(f"原始数据集加载完成，共{len(df)}条数据")

    # 2. 数据预处理与结构化解析
    preprocessor = DataPreprocessor(df)
    structured_df = preprocessor.process()
    processed_data['structured_df'] = structured_df
    print(processed_data['structured_df'].head())
    processed_data['structured_df'].to_excel("结构化数据.xlsx")
    # 3. 告警分析
    denoiser = AlertDenoise(structured_df)
    alert_report = denoiser.process()
    processed_data['alert_report'] = alert_report
    processed_data['alert_clusters'] = denoiser.alert_clusters
    exit()
    # 4. 告警根因定位与关联分析
    rca = RootCauseAnalysis(structured_df)
    global alert_events
    alert_events = rca.process()

    # 5. 告警风险预警与趋势分析
    warning = RiskWarning(structured_df)
    global risk_warnings
    risk_warnings = warning.process()

    # 6. 输出核心指标
    print("\n===== 核心指标汇总 =====")
    for k, v in core_metrics.items():
        print(f"{k}: {v}")



if __name__ == "__main__":
    main()