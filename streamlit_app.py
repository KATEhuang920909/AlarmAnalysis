import streamlit as st
import pandas as pd
import io
import time
from datetime import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from alert_analysis_system import (
    DataPreprocessor, 
    AlertDenoise, 
    core_metrics,
    processed_data
)

st.set_page_config(
    page_title="告警日志分析系统",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1.5rem;
    }
    .section-header {
        font-size: 1.3rem;
        font-weight: bold;
        color: #2c3e50;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
    }
    .step-box {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        border-left: 4px solid #1f77b4;
    }
    .download-section {
        background: #e8f4f8;
        padding: 1rem;
        border-radius: 8px;
        margin-top: 1rem;
    }
</style>
""", unsafe_allow_html=True)

if 'page' not in st.session_state:
    st.session_state.page = 'home'

def set_page(page_name):
    st.session_state.page = page_name

def init_session_state():
    if 'task1_complete' not in st.session_state:
        st.session_state.task1_complete = False
        st.session_state.task1_structured_df = None
        st.session_state.task1_raw_df = None
    
    if 'task2_complete' not in st.session_state:
        st.session_state.task2_complete = False
        st.session_state.task2_denoised_df = None
        st.session_state.task2_structured_df = None
    
    if 'task3_complete' not in st.session_state:
        st.session_state.task3_complete = False
        st.session_state.task3_clusters = []
        st.session_state.task3_structured_df = None
    
    if 'task4_complete' not in st.session_state:
        st.session_state.task4_complete = False
        st.session_state.task4_report = ""
        st.session_state.task4_clusters = []
        st.session_state.task4_structured_df = None
        st.session_state.task4_progress = []

def load_file(uploaded_file):
    if uploaded_file is None:
        return None
    
    try:
        file_content = uploaded_file.read()
        filename = uploaded_file.name
        
        if filename.endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(file_content))
        elif filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content))
        elif filename.endswith('.txt'):
            content = file_content.decode('utf-8')
            lines = content.split('\n')
            df = pd.DataFrame({'message': [line.strip() for line in lines if line.strip()]})
        else:
            st.error("❌ 不支持的文件格式")
            return None

        return df
    except Exception as e:
        st.error(f"❌ 加载文件失败: {str(e)}")
        return None

def download_df(df, filename_prefix, filetype='csv'):
    if df is None:
        st.warning("暂无数据可下载")
        return
    
    if filetype == 'csv':
        csv = df.to_csv(index=False)
        st.download_button(
            label=f"📥 下载 {filename_prefix} (CSV)",
            data=csv,
            file_name=f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    elif filetype == 'excel':
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name=filename_prefix)
        st.download_button(
            label=f"📥 下载 {filename_prefix} (Excel)",
            data=buffer.getvalue(),
            file_name=f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

def home_page():
    st.title("📊 告警日志分析系统")
    st.markdown("---")
    
    st.markdown("""
    <div style="text-align: center; padding: 2rem;">
        <h2>欢迎使用告警日志分析系统</h2>
        <p style="font-size: 1.2rem; color: #666; margin-top: 1rem;">
            请从左侧菜单栏选择要执行的分析任务
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        <div style="background: #e8f4f8; padding: 1.5rem; border-radius: 10px; text-align: center;">
            <h3>📋</h3>
            <p><strong>日志解析</strong></p>
            <p style="font-size: 0.9rem; color: #666;">
                将原始日志解析为结构化数据
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style="background: #fce4ec; padding: 1.5rem; border-radius: 10px; text-align: center;">
            <h3>🔇</h3>
            <p><strong>智能降噪</strong></p>
            <p style="font-size: 0.9rem; color: #666;">
                去除重复告警，降低告警噪音
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div style="background: #fff3e0; padding: 1.5rem; border-radius: 10px; text-align: center;">
            <h3>🎯</h3>
            <p><strong>事件抽取</strong></p>
            <p style="font-size: 0.9rem; color: #666;">
                语义聚类，发现告警事件模式
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown("""
        <div style="background: #e8f5e9; padding: 1.5rem; border-radius: 10px; text-align: center;">
            <h3>📝</h3>
            <p><strong>分析报告</strong></p>
            <p style="font-size: 0.9rem; color: #666;">
                生成完整的告警分析报告（流式输出）
            </p>
        </div>
        """, unsafe_allow_html=True)

def task1_log_parsing():
    st.title("📋 任务一：日志解析")
    st.markdown("---")
    
    st.markdown('<div class="section-header">1️⃣ 上传原始日志文件</div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader(
        "选择日志文件",
        type=['txt', 'csv', 'xlsx'],
        help="支持 TXT、CSV、Excel 格式的日志文件"
    )
    
    if uploaded_file is not None:
        st.success(f"✅ 已选择文件: {uploaded_file.name}")
        
        # 立即加载并保存原始数据，确保数据不被修改
        raw_df = load_file(uploaded_file)
        if raw_df is not None:
            st.session_state.task1_raw_df = raw_df.copy(deep=True)
        
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("🔧 开始解析", type="primary", use_container_width=True):
                with st.spinner("正在解析日志..."):
                    try:
                        if raw_df is not None:
                            st.markdown('<div class="section-header">2️⃣ 解析进度</div>', unsafe_allow_html=True)
                            progress_bar = st.progress(0)
                            status_text = st.empty()
                            
                            status_text.text("正在加载数据...")
                            progress_bar.progress(10)
                            time.sleep(0.3)
                            
                            status_text.text("正在解析日志内容...")
                            progress_bar.progress(30)
                            time.sleep(0.3)
                            
                            # 使用副本进行处理
                            preprocessor = DataPreprocessor(raw_df.copy(deep=True), None)
                            status_text.text("正在进行数据预处理...")
                            progress_bar.progress(60)
                            time.sleep(0.3)
                            
                            structured_df = preprocessor.process()
                            
                            # 统计有多少记录无法解析（timestamp_raw 为 NaN）
                            parsed_count = len(structured_df[structured_df['timestamp_raw'].notna()])
                            unparsed_count = len(structured_df) - parsed_count
                            
                            # 删除无法解析的记录
                            structured_df = structured_df.dropna(subset=['timestamp_raw'])
                            
                            st.session_state.task1_structured_df = structured_df
                            processed_data['structured_df'] = structured_df
                            
                            status_text.text("解析完成！")
                            progress_bar.progress(100)
                            time.sleep(0.5)
                            
                            st.session_state.task1_complete = True
                            
                            # 显示详细解析统计
                            if unparsed_count > 0:
                                st.warning(f"⚠️ 共处理 {len(raw_df)} 条日志，成功解析 {parsed_count} 条，删除 {unparsed_count} 条格式无法识别的日志")
                            else:
                                st.success(f"✅ 解析完成！共处理 {len(raw_df)} 条日志，全部成功解析")
                    
                    except Exception as e:
                        st.error(f"❌ 解析失败: {str(e)}")
                        import traceback
                        with st.expander("查看错误详情"):
                            st.code(traceback.format_exc())
    
    if st.session_state.task1_complete:
        st.markdown('<div class="section-header">3️⃣ 结果展示</div>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📄 原始数据")
            if st.session_state.task1_raw_df is not None:
                st.dataframe(st.session_state.task1_raw_df, use_container_width=True)
                st.info(f"共 {len(st.session_state.task1_raw_df)} 条原始记录")
        
        with col2:
            st.subheader("🔧 结构化数据")
            if st.session_state.task1_structured_df is not None:
                st.dataframe(st.session_state.task1_structured_df, use_container_width=True)
                st.info(f"共 {len(st.session_state.task1_structured_df)} 条结构化记录")
        
        st.markdown('<div class="download-section">', unsafe_allow_html=True)
        st.subheader("💾 下载结果")
        
        download_col1, download_col2, download_col3, download_col4 = st.columns(4)
        
        with download_col1:
            if st.session_state.task1_raw_df is not None:
                download_df(st.session_state.task1_raw_df, "原始数据", "csv")
        
        with download_col2:
            if st.session_state.task1_raw_df is not None:
                download_df(st.session_state.task1_raw_df, "原始数据", "excel")
        
        with download_col3:
            if st.session_state.task1_structured_df is not None:
                download_df(st.session_state.task1_structured_df, "结构化数据", "csv")
        
        with download_col4:
            if st.session_state.task1_structured_df is not None:
                download_df(st.session_state.task1_structured_df, "结构化数据", "excel")
        
        st.markdown('</div>', unsafe_allow_html=True)

def task2_denoising():
    st.title("🔇 任务二：智能降噪")
    st.markdown("---")
    
    st.markdown('<div class="section-header">1️⃣ 上传结构化数据</div>', unsafe_allow_html=True)
    
    data_source = st.radio(
        "数据来源",
        ["使用任务一的结果", "上传新文件"],
        horizontal=True
    )
    
    uploaded_file = None
    input_df = None
    
    if data_source == "上传新文件":
        uploaded_file = st.file_uploader(
            "选择结构化数据文件",
            type=['csv', 'xlsx'],
            help="支持 CSV、Excel 格式的结构化数据"
        )
    else:
        if st.session_state.task1_structured_df is not None:
            st.success("✅ 已加载任务一的结构化数据")
            input_df = st.session_state.task1_structured_df
        else:
            st.warning("⚠️ 请先完成任务一，或选择上传新文件")
    
    if data_source == "上传新文件" and uploaded_file is not None:
        st.success(f"✅ 已选择文件: {uploaded_file.name}")
        input_df = load_file(uploaded_file)
    
    if input_df is not None:
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("🔇 开始降噪", type="primary", use_container_width=True):
                with st.spinner("正在进行智能降噪..."):
                    try:
                        st.session_state.task2_structured_df = input_df
                        denoiser = AlertDenoise(input_df, None)
                        st.markdown('<div class="section-header">2️⃣ 降噪进度</div>', unsafe_allow_html=True)
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        status_text.text("正在进行基础降噪...")
                        progress_bar.progress(20)
                        time.sleep(0.3)
                        denoised_df = denoiser.base_duplicate_removal()

                        status_text.text("正在生成降噪统计...")
                        progress_bar.progress(50)
                        time.sleep(0.3)
                        

                        status_text.text("正在保存结果...")
                        progress_bar.progress(80)
                        time.sleep(0.3)
                        
                        st.session_state.task2_denoised_df = denoised_df
                        processed_data['denoised_df'] = denoised_df
                        
                        status_text.text("降噪完成！")
                        progress_bar.progress(100)
                        time.sleep(0.5)
                        
                        st.session_state.task2_complete = True
                        
                        noise_reduction = ((len(input_df) - len(denoised_df)) / len(input_df) * 100)
                        st.success(f"✅ 降噪完成！原始: {len(input_df)} → 降噪后: {len(denoised_df)} → 降噪率: {noise_reduction:.2f}%")
                    
                    except Exception as e:
                        st.error(f"❌ 降噪失败: {str(e)}")
                        import traceback
                        with st.expander("查看错误详情"):
                            st.code(traceback.format_exc())
    
    if st.session_state.task2_complete:
        st.markdown('<div class="section-header">3️⃣ 结果展示</div>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📄 结构化数据")
            if st.session_state.task2_structured_df is not None:
                st.dataframe(st.session_state.task2_structured_df, use_container_width=True)
                st.info(f"共 {len(st.session_state.task2_structured_df)} 条记录")
        
        with col2:
            st.subheader("🔇 降噪后数据")
            if st.session_state.task2_denoised_df is not None:
                st.dataframe(st.session_state.task2_denoised_df, use_container_width=True)
                st.info(f"共 {len(st.session_state.task2_denoised_df)} 条记录")
        
        st.markdown('<div class="download-section">', unsafe_allow_html=True)
        st.subheader("💾 下载结果")
        
        download_col1, download_col2 = st.columns(2)
        
        with download_col1:
            if st.session_state.task2_denoised_df is not None:
                download_df(st.session_state.task2_denoised_df, "降噪数据", "csv")
        
        with download_col2:
            if st.session_state.task2_denoised_df is not None:
                download_df(st.session_state.task2_denoised_df, "降噪数据", "excel")
        
        st.markdown('</div>', unsafe_allow_html=True)

def task3_event_extraction():
    st.title("🎯 任务三：事件抽取")
    st.markdown("---")
    
    st.markdown('<div class="section-header">1️⃣ 上传结构化数据</div>', unsafe_allow_html=True)
    
    data_source = st.radio(
        "数据来源",
        ["使用任务二的结果", "上传新文件"],
        horizontal=True
    )
    
    uploaded_file = None
    input_df = None
    
    if data_source == "上传新文件":
        uploaded_file = st.file_uploader(
            "选择结构化数据文件",
            type=['csv', 'xlsx'],
            help="支持 CSV、Excel 格式的结构化数据"
        )
    else:
        if st.session_state.task2_denoised_df is not None:
            st.success("✅ 已加载任务二的结构化数据")
            input_df = st.session_state.task2_denoised_df
        else:
            st.warning("⚠️ 请先完成任务二，或选择上传新文件")
    
    if data_source == "上传新文件" and uploaded_file is not None:
        st.success(f"✅ 已选择文件: {uploaded_file.name}")
        input_df = load_file(uploaded_file)
    
    if input_df is not None:
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("🎯 开始事件抽取", type="primary", use_container_width=True):
                with st.spinner("正在进行事件抽取..."):
                    try:
                        st.session_state.task3_structured_df = input_df
                        
                        st.markdown('<div class="section-header">2️⃣ 事件抽取进度</div>', unsafe_allow_html=True)
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        status_text.text("正在加载语义模型...")
                        progress_bar.progress(15)
                        time.sleep(0.5)
                        
                        denoiser = AlertDenoise(input_df, None)
                        
                        status_text.text("正在生成向量嵌入...")
                        progress_bar.progress(30)
                        time.sleep(0.5)
                        
                        alert_clusters = denoiser.semantic_clustering()
                        
                        status_text.text("正在进行聚类分析...")
                        progress_bar.progress(60)
                        time.sleep(0.5)
                        
                        st.session_state.task3_clusters = alert_clusters
                        processed_data['alert_clusters'] = alert_clusters
                        
                        status_text.text("事件抽取完成！")
                        progress_bar.progress(100)
                        time.sleep(0.5)
                        
                        st.session_state.task3_complete = True
                        
                        st.success(f"✅ 事件抽取完成！共发现 {len(alert_clusters)} 个告警事件")
                    
                    except Exception as e:
                        st.error(f"❌ 事件抽取失败: {str(e)}")
                        import traceback
                        with st.expander("查看错误详情"):
                            st.code(traceback.format_exc())
    
    if st.session_state.task3_complete:
        st.markdown('<div class="section-header">3️⃣ 结果展示</div>', unsafe_allow_html=True)
        
        if st.session_state.task3_clusters:
            clusters_df = pd.DataFrame(st.session_state.task3_clusters)
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("📊 事件聚类数据")
                st.dataframe(clusters_df, use_container_width=True)
                st.info(f"共发现 {len(clusters_df)} 个告警事件")
            
            with col2:
                st.subheader("📈 事件统计")
                if 'level' in clusters_df.columns:
                    st.bar_chart(clusters_df['level'].value_counts())
            
            st.subheader("🔍 事件详情")
            for idx, cluster in enumerate(st.session_state.task3_clusters):
                with st.expander(f"事件 {cluster.get('cluster_id', idx)} - {cluster.get('service', '未知服务')} ({cluster.get('level', '未知级别')}) - {cluster.get('alert_count', 0)}条"):
                    st.write(f"**服务:** {cluster.get('service', 'N/A')}")
                    st.write(f"**级别:** {cluster.get('level', 'N/A')}")
                    st.write(f"**告警数量:** {cluster.get('alert_count', 0)}")
                    st.write(f"**首次发生:** {cluster.get('first_time', 'N/A')}")
                    st.write(f"**最后发生:** {cluster.get('last_time', 'N/A')}")
                    st.write("**示例内容:**")
                    sample_content = cluster.get('sample_content', [])
                    for content in sample_content[:3]:
                        st.text(f"  - {content}")
            
            st.markdown('<div class="download-section">', unsafe_allow_html=True)
            st.subheader("💾 下载结果")
            
            download_col1, download_col2 = st.columns(2)
            
            with download_col1:
                download_df(clusters_df, "事件聚类", "csv")
            
            with download_col2:
                download_df(clusters_df, "事件聚类", "excel")
            
            st.markdown('</div>', unsafe_allow_html=True)

def task4_report_generation():
    st.title("📝 任务四：分析报告生成（流式输出）")
    st.markdown("---")
    
    st.markdown('<div class="section-header">1️⃣ 上传结构化数据</div>', unsafe_allow_html=True)
    
    data_source = st.radio(
        "数据来源",
        ["使用任务三的结果", "上传新文件"],
        horizontal=True
    )
    
    uploaded_file = None
    input_df = None
    input_clusters = None
    
    if data_source == "上传新文件":
        uploaded_file = st.file_uploader(
            "选择结构化数据文件",
            type=['csv', 'xlsx'],
            help="支持 CSV、Excel 格式的结构化数据"
        )
    elif data_source == "使用任务三的结果":
        if st.session_state.task3_clusters and st.session_state.task3_structured_df is not None:
            st.success("✅ 已加载任务三的数据")
            input_df = pd.DataFrame(st.session_state.task3_clusters)
        else:
            st.warning("⚠️ 请先完成任务三，或选择其他数据来源")
    
    if data_source == "上传新文件" and uploaded_file is not None:
        st.success(f"✅ 已选择文件: {uploaded_file.name}")
        input_df = load_file(uploaded_file)
    
    if input_df is not None:
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("📝 开始生成报告", type="primary", use_container_width=True):
                with st.spinner("正在生成分析报告..."):
                    try:
                        st.session_state.task4_structured_df = input_df
                        st.session_state.task4_progress = []
                        
                        st.markdown('<div class="section-header">2️⃣ 报告生成进度</div>', unsafe_allow_html=True)
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        status_text.text("正在初始化分析...")
                        progress_bar.progress(10)
                        time.sleep(0.3)
                        
                        st.session_state.task4_progress.append("## 📊 告警分析报告\n")
                        st.session_state.task4_progress.append("\n---\n")
                        st.session_state.task4_progress.append("\n### 📈 分析概述\n")
                        st.session_state.task4_progress.append(f"\n- 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        st.session_state.task4_progress.append(f"- 日志总数: {len(input_df)}\n")
                        st.session_state.task4_progress.append(f"- 事件总数: {len(st.session_state.task3_clusters)}\n")


                        
                        denoiser = AlertDenoise(input_df, None)
                        
                        status_text.text("正在进行告警分析...")
                        progress_bar.progress(35)
                        time.sleep(0.3)
                        # print("st.session_state.task4_structured_df",st.session_state.task4_structured_df)
                        # exit()
                        report= denoiser.llm_alert_validity_check(st.session_state.task4_structured_df.head(1))
                        
                        # st.session_state.task4_clusters = denoiser.alert_clusters
                        # st.session_state.task4_progress.append(f"- 降噪后: {len(denoised_df)}\n")
                        # noise_reduction = ((len(input_df) - len(denoised_df)) / len(input_df) * 100)
                        # st.session_state.task4_progress.append(f"- 降噪率: {noise_reduction:.2f}%\n")
                        # st.session_state.task4_progress.append(f"- 发现事件: {len(denoiser.alert_clusters)} 个\n")
                        #
                        print("report...",report)
                        # exit()
                        status_text.text("正在生成事件分析...")
                        progress_bar.progress(50)
                        time.sleep(0.3)
                        
                        st.session_state.task4_progress.append("\n---\n")
                        st.session_state.task4_progress.append("\n### 🎯 事件分析\n")
                        alert_clusters_dict = st.session_state.task4_structured_df.head(1).T.to_dict()
                        for idx, cluster in enumerate( alert_clusters_dict):
                            print(cluster)
                            cluster= alert_clusters_dict[cluster]
                            # exit()
                            st.session_state.task4_progress.append(f"\n#### 事件 {cluster.get('cluster_id', idx)}\n")
                            st.session_state.task4_progress.append(f"- **服务**: {cluster.get('service', 'N/A')}\n")
                            st.session_state.task4_progress.append(f"- **级别**: {cluster.get('level', 'N/A')}\n")
                            st.session_state.task4_progress.append(f"- **告警数量**: {cluster.get('alert_count', 0)}\n")
                            st.session_state.task4_progress.append(f"- **首次发生**: {cluster.get('first_time', 'N/A')}\n")
                            st.session_state.task4_progress.append(f"- **最后发生**: {cluster.get('last_time', 'N/A')}\n")
                            
                            sample_content = cluster.get('sample_content', [])
                            if sample_content:
                                st.session_state.task4_progress.append("\n**示例内容**:\n")
                                for content in sample_content[:2]:
                                    st.session_state.task4_progress.append(f"- {content}\n")
                            
                            progress_bar.progress(50 + (idx + 1) * (40 // len(alert_clusters_dict)))
                            status_text.text(f"正在分析事件 {idx + 1}/{len(alert_clusters_dict)}...")
                            time.sleep(0.2)

                        st.session_state.task4_report = "".join(st.session_state.task4_progress)+report
                        processed_data['alert_report'] = st.session_state.task4_report
                        
                        status_text.text("报告生成完成！")
                        progress_bar.progress(100)
                        time.sleep(0.5)
                        
                        st.session_state.task4_complete = True
                        
                        st.success(f"✅ 报告生成完成！")
                    
                    except Exception as e:
                        st.error(f"❌ 报告生成失败: {str(e)}")
                        import traceback
                        with st.expander("查看错误详情"):
                            st.code(traceback.format_exc())
    
    if st.session_state.task4_complete:
        st.markdown('<div class="section-header">3️⃣ 报告展示（流式输出）</div>', unsafe_allow_html=True)
        
        report_container = st.empty()
        
        report_text = st.session_state.task4_report
        
        with st.spinner("正在流式输出报告..."):
            display_text = ""
            for char in report_text:
                display_text += char
                report_container.markdown(display_text)
                time.sleep(0.005)
        
        st.markdown('<div class="download-section">', unsafe_allow_html=True)
        st.subheader("💾 下载报告")
        
        st.download_button(
            label="📥 下载完整报告 (Markdown)",
            data=st.session_state.task4_report,
            file_name=f"告警分析报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown"
        )
        
        st.markdown('</div>', unsafe_allow_html=True)

def main():
    init_session_state()
    
    with st.sidebar:
        st.title("📋 任务菜单")
        st.markdown("---")
        
        st.button("🏠 首页", on_click=set_page, args=('home',), use_container_width=True)
        st.button("📋 任务一：日志解析", on_click=set_page, args=('task1',), use_container_width=True)
        st.button("🔇 任务二：智能降噪", on_click=set_page, args=('task2',), use_container_width=True)
        st.button("🎯 任务三：事件抽取", on_click=set_page, args=('task3',), use_container_width=True)
        st.button("📝 任务四：分析报告", on_click=set_page, args=('task4',), use_container_width=True)
        
        st.markdown("---")
        st.markdown("### 📊 任务状态")
        
        status_colors = {
            'home': 'blue',
            'task1': 'green' if st.session_state.task1_complete else 'gray',
            'task2': 'green' if st.session_state.task2_complete else 'gray',
            'task3': 'green' if st.session_state.task3_complete else 'gray',
            'task4': 'green' if st.session_state.task4_complete else 'gray',
        }
        
        st.markdown(f"- 🏠 首页: :blue[当前]" if st.session_state.page == 'home' else "- 🏠 首页")
        st.markdown(f"- 📋 日志解析: :{status_colors['task1']}[{'✓ 已完成' if st.session_state.task1_complete else '未完成'}]")
        st.markdown(f"- 🔇 智能降噪: :{status_colors['task2']}[{'✓ 已完成' if st.session_state.task2_complete else '未完成'}]")
        st.markdown(f"- 🎯 事件抽取: :{status_colors['task3']}[{'✓ 已完成' if st.session_state.task3_complete else '未完成'}]")
        st.markdown(f"- 📝 分析报告: :{status_colors['task4']}[{'✓ 已完成' if st.session_state.task4_complete else '未完成'}]")
    
    if st.session_state.page == 'home':
        home_page()
    elif st.session_state.page == 'task1':
        task1_log_parsing()
    elif st.session_state.page == 'task2':
        task2_denoising()
    elif st.session_state.page == 'task3':
        task3_event_extraction()
    elif st.session_state.page == 'task4':
        task4_report_generation()

if __name__ == "__main__":
    main()
