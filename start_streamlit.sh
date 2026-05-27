#!/bin/bash

echo "🚀 正在启动告警日志流式分析系统..."
echo ""

cd "$(dirname "$0")"

if ! command -v streamlit &> /dev/null; then
    echo "⚠️  Streamlit 未安装，正在安装..."
    pip install -r requirements.txt
fi

echo "✅ 依赖检查完成"
echo ""
echo "🌐 正在打开浏览器..."
echo "📍 应用地址: http://localhost:8502"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

streamlit run streamlit_app.py --server.port 8502 --server.address localhost
