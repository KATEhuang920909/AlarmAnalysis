import os
import io
import json
from datetime import datetime
from flask import Flask, render_template, jsonify, request, Response, stream_with_context
import pandas as pd
from sklearn.cluster import DBSCAN
from sentence_transformers import SentenceTransformer
from zhipuai import ZhipuAI

LLM_API_KEY = "aaa16e53a2cf92220d4fd3d9282a9fa7.A8zR3KN6eI1uKwZM"
LLM_MODEL = "glm-4-long"
client = ZhipuAI(api_key=LLM_API_KEY)

SERVICE_DEPENDENCY = {
    "frontend": ["mobservice1", "mobservice2", "webservice1", "webservice2"],
    "middleware": ["redisservice1", "redisservice2"],
    "database": ["dbservice1", "dbservice2"],
    "log": ["logservice1", "logservice2"],
    "dependency_chain": ["frontend", "middleware", "database"]
}

PRIORITY_LEVELS = {
    "P0": "必须立即处理",
    "P1": "1小时内处理",
    "P2": "当天处理",
    "P3": "低优先级，可忽略"
}

TIME_WINDOW_MINUTES = 10

app = Flask(__name__)

processed_data = {}
alert_events = []
risk_warnings = []
analysis_tasks = {}

core_metrics = {
    'total_alerts': 0,
    'noise_reduction_rate': 0,
    'alert_clusters': 0,
    'high_risk_warnings': 0,
    'medium_risk_warnings': 0,
    'low_risk_warnings': 0,
    'fault_events': 0
}

class DataPreprocessor:
    def __init__(self, df, progress_callback=None):
        # 对原始数据进行深拷贝，避免修改原始数据
        self.df = df.copy(deep=True)
        self.structured_df = None
        self.progress_callback = progress_callback

    def update_progress(self, step, progress, message=""):
        if self.progress_callback:
            self.progress_callback({
                "step": step,
                "progress": progress,
                "message": message,
                "timestamp": datetime.now().isoformat()
            })

    def split_datetime(self):
        self.update_progress("数据预处理", 10, "开始拆分时间字段")
        self.df['datetime'] = pd.to_datetime(self.df['timestamp_raw'], errors='coerce')
        self.df['year'] = self.df['datetime'].dt.year
        self.df['month'] = self.df['datetime'].dt.month
        self.df['day'] = self.df['datetime'].dt.day
        self.df['hour'] = self.df['datetime'].dt.hour
        self.df['minute'] = self.df['datetime'].dt.minute
        self.df['second'] = self.df['datetime'].dt.second
        self.update_progress("数据预处理", 15, "时间字段拆分完成")
        return self.df

    def parse_log_line(self, line: str) -> dict:
        line = line.rstrip('\n')
        parts = line.split(" | ")
        
        if len(parts) not in (6, 7):
            return {
                "level": "NONE",
                "message": line
            }

        timestamp_str = parts[0].strip()
        level = parts[1].strip()
        src_ip = parts[2].strip()
        svc_ip = parts[3].strip()
        service = parts[4].strip()

        if len(parts) == 6:
            track_id = None
            content = parts[5].strip()
        else:
            track_id = parts[5].strip()
            content = parts[6].strip()

        parsed_ts = None
        try:
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
            "service": service,
            "content": content,
        }
        if track_id:
            result["track_id"] = track_id

        return result

    def regex_split_message(self):
        self.update_progress("日志解析", 20, "开始解析日志内容")
        total_rows = len(self.df)
        split_result = []
        for idx, row in self.df.iterrows():
            split_result.append(self.parse_log_line(row['message']))
            if idx % max(1, total_rows // 10) == 0:
                progress = 20 + int((idx / total_rows) * 20)
                self.update_progress("日志解析", progress, f"已解析 {idx}/{total_rows} 条日志")
        
        result_df = pd.DataFrame(split_result)
        for col in result_df.columns:
            if col in self.df.columns:
                self.df.drop(col, axis=1, inplace=True)
        
        self.df = pd.concat([self.df, result_df], axis=1)
        self.update_progress("日志解析", 40, "日志解析完成")
        return self.df

    def process(self):
        self.update_progress("数据预处理", 5, "开始数据预处理")
        self.regex_split_message()
        self.split_datetime()
        self.update_progress("数据预处理", 50, "数据预处理完成")
        return self.df

class AlertDenoise:
    def __init__(self, structured_df, progress_callback=None):
        self.df = structured_df
        self.denoised_df = None
        self.alert_clusters = []
        self.progress_callback = progress_callback

    def update_progress(self, step, progress, message=""):
        if self.progress_callback:
            self.progress_callback({
                "step": step,
                "progress": progress,
                "message": message,
                "timestamp": datetime.now().isoformat()
            })

    def base_duplicate_removal(self):
        self.update_progress("智能降噪", 55, "开始基础去重")
        self.df['timestamp_dt'] = pd.to_datetime(self.df['timestamp_raw'])
        self.df['time_window'] = self.df['timestamp_dt'].dt.floor('30min')

        trace_id_col = "track_id" if 'track_id' in self.df.columns else "service"

        duplicate_stats = self.df.groupby(
            ['level', 'src_ip', 'service_ip', 'service', 'time_window']
        ).agg(
            first_time=('timestamp_dt', 'min'),
            last_time=('timestamp_dt', 'max'),
            alert_count=('timestamp_dt', 'count'),
            content=('content', lambda x: list(dict.fromkeys([i for i in x if pd.notna(i)]))),
            trace_id_list=(trace_id_col, list),
        ).reset_index()

        self.update_progress("智能降噪", 65, "基础去重完成")
        return duplicate_stats

    def semantic_clustering(self):
        self.update_progress("事件抽取", 70, "开始语义聚类")
        model = SentenceTransformer('all-MiniLM-L6-v2')
        # 确保输入是字符串列表，而不是列表的列表
        sentences = [c[0] if isinstance(c, list) and c else "" for c in self.df['content']]
        self.update_progress("事件抽取", 72, "正在编码日志内容")
        embeddings = model.encode(sentences, show_progress_bar=False)
        self.update_progress("事件抽取", 80, "编码完成，开始聚类")
        
        clustering = DBSCAN(eps=0.4, min_samples=1, metric='cosine').fit(embeddings)
        labels = clustering.labels_
        self.df['cluster_id'] = [int(k) for k in labels]

        for cluster_id in set(labels):
            if cluster_id == -1:
                continue
            cluster_data = self.df[self.df['cluster_id'] == cluster_id]
            self.alert_clusters.append({
                "cluster_id": int(cluster_id),
                "alert_count": cluster_data['alert_count'].sum(),
                "service": cluster_data['service'].unique().tolist(),
                "level": cluster_data['level'].iloc[0],
                "first_time": cluster_data['first_time'].min(),
                "last_time": cluster_data['last_time'].max(),
                "sample_content": cluster_data['content'].iloc[0],
                "track_id_sample": cluster_data['trace_id_list'].iloc[0][0] if 'trace_id_list' in cluster_data.columns and len(cluster_data['trace_id_list'].iloc[0]) > 0 else None,
            })

        self.update_progress("事件抽取", 85, f"聚类完成，发现 {len(self.alert_clusters)} 个事件")
        return self.alert_clusters
    def llm_alert_validity_check(self, alert_clusters_df, output_file="告警分析报告"):
        self.update_progress("报告生成", 88, "开始生成分析报告")
        report = ""
        
        if alert_clusters_df.empty:
            self.update_progress("报告生成", 95, "没有可分析的事件，跳过报告生成")
            return ""

        alert_clusters_dict = alert_clusters_df.T.to_dict()
        num_clusters = len(alert_clusters_dict)

        for i, unit_key in enumerate(alert_clusters_dict):
            unit = alert_clusters_dict[unit_key]
            cluster_id = unit['cluster_id']
            
            prompt = f"""请作为SRE专家，分析以下属于同一聚类ID的日志统计信息。以markdown的格式返回分析报告。
            聚类ID: {cluster_id}
            日志统计信息：{unit}
            请输出分析报告，只包含如下内容：
            事件ID: {cluster_id}
            1. 聚类概要：告警类型、日志模板（动态变量用{{}}标注）
            2. 关键特征：涉及的主要服务、日志级别、核心关键词（多个关键词用逗号分隔）、时间/频率模式、相关ID/参数规律
            3. 建议与行动：监控指标、告警优化（是否需升降级）、处理建议（正常流程可降级DEBUG，异常流程给出排查步骤）、还需哪些数据确认根因"""
            
            full_content = ""
            try:
                response = client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    stream=True,
                    max_tokens=4000
                )
                
                for chunk in response:
                    content = chunk.choices[0].delta.content
                    if content:
                        full_content += content
                        print(content, end="", flush=True)
                        self.update_progress("报告流", 90, content)
            except Exception as e:
                error_message = f"调用LLM为事件 {cluster_id} 生成报告时出错: {str(e)}"
                self.update_progress("错误", 90, error_message)
                full_content = error_message
                
            report += full_content + "\n\n"
            progress = 88 + int(((i + 1) / num_clusters) * 7)
            self.update_progress("报告生成", progress, f"事件 {cluster_id} 报告生成完毕")

        self.update_progress("报告生成", 95, "报告生成完成")
        return report

    def process(self):
        self.update_progress("智能降噪", 52, "开始告警智能降噪")
        duplicate_stats = self.base_duplicate_removal()
        duplicate_stats.to_excel("降噪数据.xlsx", index=False)
        
        self.semantic_clustering()
        alert_clusters_df = pd.DataFrame(self.alert_clusters)
        alert_clusters_df.to_excel('事件挖掘.xlsx', index=False)

        noise_reduction_rate = (self.df.shape[0] - duplicate_stats.shape[0]) / self.df.shape[0] * 100 if self.df.shape[0] > 0 else 0
        core_metrics['noise_reduction_rate'] = round(noise_reduction_rate, 2)
        core_metrics['alert_clusters'] = len(self.alert_clusters)

        report = self.llm_alert_validity_check(alert_clusters_df, "告警分析报告")
        return report, duplicate_stats

# class RootCauseAnalysis:
#     def __init__(self, structured_df, progress_callback=None):
#         self.df = structured_df
#         self.fault_events = []
#         self.progress_callback = progress_callback
#
#     def update_progress(self, step, progress, message=""):
#         if self.progress_callback:
#             self.progress_callback({
#                 "step": step,
#                 "progress": progress,
#                 "message": message,
#                 "timestamp": datetime.now().isoformat()
#             })
#
#     def time_window_correlation(self):
#         self.update_progress("根因分析", 96, "开始根因分析")
#         sorted_df = self.df.sort_values('timestamp_raw').reset_index(drop=True)
#         sorted_df['time_window'] = sorted_df['timestamp_raw'].dt.floor(f'{TIME_WINDOW_MINUTES}min')
#         window_groups = sorted_df.groupby('time_window')
#         return window_groups
#
#     def llm_root_cause_inference(self, alert_list):
#         return {
#             "根因告警": alert_list[0],
#             "衍生告警列表": alert_list[1:],
#             "根因分析": "根据服务依赖关系，数据库层服务为上游依赖，该告警先于其他服务告警出现，因此判定为根因告警，后续其他服务的告警均为该根因导致的衍生告警",
#             "故障影响范围": "数据库服务、中间件服务、前端服务，全链路业务受影响",
#             "修复建议": "1. 立即检查数据库主库磁盘IO情况，优化慢查询；2. 调整数据库连接池配置，增加可用连接数；3. 优化主从同步策略，降低同步延迟"
#         }
#
#     def process(self):
#         window_groups = self.time_window_correlation()
#
#         for window_time, group in window_groups:
#             if len(group) < 2:
#                 continue
#
#             alert_list = []
#             for idx, row in group.iterrows():
#                 alert_list.append({
#                     "service": row['service'],
#                     "message": row['message'],
#                     "datetime": row['timestamp_raw'].strftime('%Y-%m-%d %H:%M:%S')
#                 })
#
#             root_cause_result = self.llm_root_cause_inference(alert_list)
#             self.fault_events.append({
#                 "event_time": window_time.strftime('%Y-%m-%d %H:%M:%S'),
#                 "alert_count": len(group),
#                 "services": group['service'].unique().tolist(),
#                 **root_cause_result
#             })
#
#         core_metrics['fault_events'] = len(self.fault_events)
#         self.update_progress("根因分析", 98, f"根因分析完成，识别 {len(self.fault_events)} 个故障事件")
#         return self.fault_events
#
# class RiskWarning:
#     def __init__(self, structured_df, progress_callback=None):
#         self.df = structured_df
#         self.warnings = []
#         self.progress_callback = progress_callback
#
#     def update_progress(self, step, progress, message=""):
#         if self.progress_callback:
#             self.progress_callback({
#                 "step": step,
#                 "progress": progress,
#                 "message": message,
#                 "timestamp": datetime.now().isoformat()
#             })
#
#     def time_series_trend_analysis(self):
#         daily_stats = self.df.groupby(['day', 'service']).agg({
#             'message': 'count'
#         }).reset_index()
#         daily_stats.columns = ['day', 'service', 'alert_count']
#         daily_stats['growth_rate'] = daily_stats.groupby('service')['alert_count'].pct_change()
#         return daily_stats
#
#     def llm_risk_warning(self, service_name, alert_features, current_alert):
#         if alert_features.get('growth_rate', 0) >= 0.2:
#             return {
#                 "风险等级": "高",
#                 "预测故障时间": "未来24小时内",
#                 "风险类型": "数据库性能瓶颈",
#                 "预警依据": "该服务过去3天告警数量持续增长，日增长率超过20%，符合历史故障发生前的特征，存在较高的故障风险",
#                 "预防措施": "1. 提前检查数据库性能指标，优化慢查询；2. 增加数据库资源配额，提升处理能力；3. 提前做好故障应急预案"
#             }
#         else:
#             return {
#                 "风险等级": "低",
#                 "预测故障时间": "无明确预测时间",
#                 "风险类型": "无明显风险",
#                 "预警依据": "该服务告警数量无明显增长趋势，无异常波动，当前无明显故障风险",
#                 "预防措施": "持续观察告警趋势，定期巡检服务状态"
#             }
#
#     def process(self):
#         self.update_progress("风险预警", 99, "开始风险预警分析")
#         daily_stats = self.time_series_trend_analysis()
#
#         for service in self.df['service'].unique():
#             service_stats = daily_stats[daily_stats['service'] == service].sort_values('day')
#             if len(service_stats) < 3:
#                 continue
#
#             latest_stats = service_stats.iloc[-1]
#             alert_features = {
#                 "latest_alert_count": latest_stats['alert_count'],
#                 "growth_rate": latest_stats['growth_rate'],
#                 "avg_alert_count": service_stats['alert_count'].mean(),
#                 "max_alert_count": service_stats['alert_count'].max()
#             }
#
#             current_alert = self.df[self.df['service'] == service].iloc[-1]['message']
#             warning_result = self.llm_risk_warning(service, alert_features, current_alert)
#             self.warnings.append({
#                 "service": service,
#                 "stats_time": f"2021-07-{int(latest_stats['day'])}",
#                 **warning_result
#             })
#
#         core_metrics['high_risk_warnings'] = len([w for w in self.warnings if w['风险等级'] == '高'])
#         core_metrics['medium_risk_warnings'] = len([w for w in self.warnings if w['风险等级'] == '中'])
#         core_metrics['low_risk_warnings'] = len([w for w in self.warnings if w['风险等级'] == '低'])
#
#         self.update_progress("风险预警", 100, f"风险预警完成，生成 {len(self.warnings)} 条预警")
#         return self.warnings

@app.route('/')
def index():
    return render_template('index.html', metrics=core_metrics)

@app.route('/parse')
def parse_page():
    return render_template('parse.html')

@app.route('/denoise')
def denoise_page():
    return render_template('denoise.html')

@app.route('/events')
def events_page():
    return render_template('events.html')

@app.route('/report')
def report_page():
    return render_template('report.html')

@app.route('/api/metrics')
def get_metrics():
    return jsonify(core_metrics)

@app.route('/alerts')
def alerts_page():
    denoised_alerts = processed_data.get('denoised_df', pd.DataFrame()).to_dict('records')
    return render_template('alerts.html', alerts=denoised_alerts, priorities=PRIORITY_LEVELS)

@app.route('/api/alerts')
def get_alerts():
    denoised_alerts = processed_data.get('denoised_df', pd.DataFrame()).to_dict('records')
    return jsonify(alerts=denoised_alerts)

@app.route('/api/alerts/structured')
def get_structured_alerts():
    structured_df = processed_data.get('structured_df', pd.DataFrame())
    data = structured_df.to_dict('records')
    return jsonify(data=data)

@app.route('/api/alerts/denoised')
def get_denoised_alerts():
    denoised_df = processed_data.get('denoised_df', pd.DataFrame())
    data = denoised_df.to_dict('records')
    return jsonify(data=data)

@app.route('/api/events')
def get_events():
    events = processed_data.get('alert_clusters', [])
    return jsonify(data=events)

@app.route('/api/report')
def get_report():
    report = processed_data.get('alert_report', '')
    return jsonify(content=report, timestamp=datetime.now().isoformat())

@app.route('/api/report/stream')
def stream_report():
    def generate():
        report = processed_data.get('alert_report', '')
        if not report:
            report = """## 告警日志分析报告

**报告概述:**
本次分析共处理了告警日志数据，以下是详细分析结果。

### 一、数据概览
- 原始告警总数: 0
- 降噪后告警数: 0
- 降噪率: 0%
- 发现事件数: 0

### 二、告警级别分布
- ERROR级别: 0条
- WARNING级别: 0条
- INFO级别: 0条

### 三、智能降噪分析
系统基于时间窗口和语义相似度进行了告警去重处理，有效降低了告警噪音。

### 四、事件发现
通过语义聚类分析，发现了0个告警事件模式。

### 五、处理建议
1. 建议定期监控告警趋势变化
2. 关注高优先级告警的处理时效
3. 建立告警阈值动态调整机制

### 六、总结
本次分析完成了告警日志的全面处理，为运维团队提供了清晰的告警视图。
"""
        for i in range(0, len(report), 50):
            yield report[i:i+50]
            import time
            time.sleep(0.1)
    
    return Response(generate(), content_type='text/plain')

@app.route('/faults')
def faults_page():
    return render_template('faults.html', events=alert_events)

@app.route('/api/faults')
def get_faults():
    return jsonify(events=alert_events)

@app.route('/warnings')
def warnings_page():
    high_count = len([w for w in risk_warnings if w.get('风险等级') == '高'])
    medium_count = len([w for w in risk_warnings if w.get('风险等级') == '中'])
    low_count = len([w for w in risk_warnings if w.get('风险等级') == '低'])
    return render_template('warnings.html', warnings=risk_warnings, 
                           high_count=high_count, medium_count=medium_count, low_count=low_count)

@app.route('/api/warnings')
def get_warnings():
    return jsonify(warnings=risk_warnings)

def generate_progress(task_id):
    import time
    while task_id in analysis_tasks:
        if analysis_tasks[task_id]['progress']:
            progress = analysis_tasks[task_id]['progress'].pop(0)
            yield f"data: {json.dumps(progress)}\n\n"
        time.sleep(0.1)
    
    while analysis_tasks[task_id]['done']:
        if analysis_tasks[task_id]['progress']:
            progress = analysis_tasks[task_id]['progress'].pop(0)
            yield f"data: {json.dumps(progress)}\n\n"
        else:
            break
        time.sleep(0.1)

@app.route('/api/analysis/progress/<task_id>')
def stream_progress(task_id):
    if task_id not in analysis_tasks:
        return jsonify({"error": "任务不存在"}), 404
    
    return Response(
        stream_with_context(generate_progress(task_id)),
        mimetype='text/event-stream'
    )

@app.route('/api/analyze/upload', methods=['POST'])
def upload_and_analyze():
    global alert_events, risk_warnings
    
    if 'file' not in request.files:
        return jsonify({'error': '未选择文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '文件名不能为空'}), 400
    
    task_id = f"task_{datetime.now().timestamp()}"
    analysis_tasks[task_id] = {
        'progress': [],
        'done': False
    }

    def progress_callback(progress_data):
        analysis_tasks[task_id]['progress'].append(progress_data)

    try:
        file_content = file.read()
        
        if file.filename.endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(file_content))
        elif file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content))
        elif file.filename.endswith('.txt'):
            content = file_content.decode('utf-8')
            lines = content.split('\n')
            df = pd.DataFrame({'message': [line.strip() for line in lines if line.strip()]})
        else:
            return jsonify({'error': '不支持的文件格式'}), 400
        
        core_metrics['total_alerts'] = len(df)
        
        preprocessor = DataPreprocessor(df, progress_callback)
        structured_df = preprocessor.process()
        structured_df = structured_df.dropna(subset=['timestamp_raw'])
        processed_data['structured_df'] = structured_df
        structured_df.to_excel("结构化数据.xlsx", index=False)

        denoiser = AlertDenoise(structured_df, progress_callback)
        alert_report, denoised_df = denoiser.process()
        processed_data['alert_report'] = alert_report
        processed_data['alert_clusters'] = denoiser.alert_clusters
        processed_data['denoised_df'] = denoised_df

        # rca = RootCauseAnalysis(structured_df, progress_callback)
        # alert_events = rca.process()
        #
        # warning = RiskWarning(structured_df, progress_callback)
        # risk_warnings = warning.process()

        analysis_tasks[task_id]['done'] = True
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'metrics': core_metrics
        })
    
    except Exception as e:
        analysis_tasks[task_id]['done'] = True
        analysis_tasks[task_id]['progress'].append({
            "step": "错误",
            "progress": 0,
            "message": f"分析失败: {str(e)}",
            "timestamp": datetime.now().isoformat()
        })
        return jsonify({'error': str(e)}), 500

@app.route('/api/analyze/stream', methods=['POST'])
def analyze_stream():
    global alert_events, risk_warnings
    
    if 'file' not in request.files:
        return jsonify({'error': '未选择文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '文件名不能为空'}), 400
    
    file_content = file.read()
    filename = file.filename

    def generate():
        global alert_events, risk_warnings
        
        yield json.dumps({"step": "开始", "progress": 0, "message": "接收文件..."}) + "\n"
        
        try:
            if filename.endswith('.xlsx'):
                df = pd.read_excel(io.BytesIO(file_content))
            elif filename.endswith('.csv'):
                df = pd.read_csv(io.BytesIO(file_content))
            elif filename.endswith('.txt'):
                content = file_content.decode('utf-8')
                lines = content.split('\n')
                df = pd.DataFrame({'message': [line.strip() for line in lines if line.strip()]})
            else:
                yield json.dumps({"step": "错误", "progress": 0, "message": "不支持的文件格式"}) + "\n"
                return
            
            total_alerts = len(df)
            core_metrics['total_alerts'] = total_alerts
            yield json.dumps({"step": "文件加载", "progress": 5, "message": f"成功加载 {total_alerts} 条日志"}) + "\n"

            def streaming_callback(step, progress, message):
                yield json.dumps({"step": step, "progress": progress, "message": message}) + "\n"

            preprocessor = DataPreprocessor(df, None)
            
            yield json.dumps({"step": "数据预处理", "progress": 10, "message": "开始解析日志内容"}) + "\n"
            structured_df = preprocessor.process()
            structured_df = structured_df.dropna(subset=['timestamp_raw'])
            processed_data['structured_df'] = structured_df
            
            yield json.dumps({"step": "数据预处理", "progress": 50, "message": "日志解析完成，共解析 " + str(len(structured_df)) + " 条记录"}) + "\n"

            denoiser = AlertDenoise(structured_df, None)
            
            yield json.dumps({"step": "智能降噪", "progress": 55, "message": "开始智能降噪处理"}) + "\n"
            alert_report, denoised_df = denoiser.process()
            processed_data['alert_report'] = alert_report
            processed_data['alert_clusters'] = denoiser.alert_clusters
            processed_data['denoised_df'] = denoised_df
            
            denoised_count = len(denoised_df)
            core_metrics['denoised_count'] = denoised_count
            noise_reduction_rate = ((total_alerts - denoised_count) / total_alerts * 100) if total_alerts > 0 else 0
            core_metrics['noise_reduction_rate'] = round(noise_reduction_rate, 2)
            core_metrics['alert_clusters'] = len(denoiser.alert_clusters)
            
            yield json.dumps({"step": "智能降噪", "progress": 85, "message": f"智能降噪完成，降噪率 {core_metrics['noise_reduction_rate']}%"}) + "\n"

            yield json.dumps({"step": "事件抽取", "progress": 90, "message": f"发现 {core_metrics['alert_clusters']} 个告警事件"}) + "\n"

            yield json.dumps({"step": "报告生成", "progress": 95, "message": "生成分析报告"}) + "\n"

            final_metrics = {
                'total_alerts': total_alerts,
                'denoised_count': denoised_count,
                'noise_reduction_rate': core_metrics['noise_reduction_rate'],
                'alert_clusters': core_metrics['alert_clusters'],
                'high_risk_warnings': 0,
                'fault_events': 0
            }
            
            yield json.dumps({
                "step": "完成", 
                "progress": 100, 
                "message": "分析完成",
                "metrics": final_metrics
            }) + "\n"
            
        except Exception as e:
            import traceback
            yield json.dumps({"step": "错误", "progress": 0, "message": f"分析失败: {str(e)}\n{traceback.format_exc()}"}) + "\n"

    return Response(generate(), mimetype='application/json')

# def run_web_server():
#     print("\n===== 启动Web服务 =====")
#     print("服务器将在 http://localhost:5002 运行")
#     print("按 Ctrl+C 停止服务")
#     app.run(host='0.0.0.0', port=5002, debug=True, threaded=True)
#
# if __name__ == "__main__":
#     run_web_server()