import os
import io
import json
import pandas as pd
from datetime import datetime
from typing import Generator, Dict, Any
import sys

sys.path.insert(0, os.path.dirname(__file__))

from alert_analysis_system import DataPreprocessor, AlertDenoise, core_metrics, processed_data

class StreamAlertParser:
    def __init__(self):
        self.total_alerts = 0
        self.structured_df = None
        self.denoised_df = None
        self.alert_clusters = []
        self.report_content = ""

    def parse_file(self, file_content: bytes, filename: str) -> Generator[Dict[str, Any], None, None]:
        try:
            yield {
                "step": "接收文件",
                "progress": 5,
                "message": "正在接收文件...",
                "status": "processing"
            }

            if filename.endswith('.xlsx'):
                df = pd.read_excel(io.BytesIO(file_content))
            elif filename.endswith('.csv'):
                df = pd.read_csv(io.BytesIO(file_content))
            elif filename.endswith('.txt'):
                content = file_content.decode('utf-8')
                lines = content.split('\n')
                df = pd.DataFrame({'message': [line.strip() for line in lines if line.strip()]})
            else:
                yield {
                    "step": "错误",
                    "progress": 0,
                    "message": "不支持的文件格式",
                    "status": "error"
                }
                return

            self.total_alerts = len(df)
            core_metrics['total_alerts'] = self.total_alerts

            yield {
                "step": "文件加载",
                "progress": 10,
                "message": f"成功加载 {self.total_alerts} 条日志",
                "status": "processing"
            }

            yield {
                "step": "数据预处理",
                "progress": 15,
                "message": "开始解析日志内容",
                "status": "processing"
            }

            preprocessor = DataPreprocessor(df, None)
            self.structured_df = preprocessor.process()
            self.structured_df = self.structured_df.dropna(subset=['timestamp_raw'])

            yield {
                "step": "数据预处理",
                "progress": 50,
                "message": f"日志解析完成，共解析 {len(self.structured_df)} 条记录",
                "status": "processing",
                "data": {
                    "parsed_count": len(self.structured_df),
                    "columns": list(self.structured_df.columns)
                }
            }

            processed_data['structured_df'] = self.structured_df

            yield {
                "step": "智能降噪",
                "progress": 55,
                "message": "开始智能降噪处理",
                "status": "processing"
            }

            denoiser = AlertDenoise(self.structured_df, None)
            self.report_content, self.denoised_df = denoiser.process()

            denoised_count = len(self.denoised_df)
            core_metrics['denoised_count'] = denoised_count
            noise_reduction_rate = ((self.total_alerts - denoised_count) / self.total_alerts * 100) if self.total_alerts > 0 else 0
            core_metrics['noise_reduction_rate'] = round(noise_reduction_rate, 2)
            core_metrics['alert_clusters'] = len(denoiser.alert_clusters)

            self.alert_clusters = denoiser.alert_clusters

            yield {
                "step": "智能降噪",
                "progress": 85,
                "message": f"智能降噪完成，降噪率 {core_metrics['noise_reduction_rate']}%",
                "status": "processing",
                "data": {
                    "denoised_count": denoised_count,
                    "noise_reduction_rate": core_metrics['noise_reduction_rate']
                }
            }

            processed_data['denoised_df'] = self.denoised_df
            processed_data['alert_clusters'] = self.alert_clusters
            processed_data['alert_report'] = self.report_content

            yield {
                "step": "事件抽取",
                "progress": 90,
                "message": f"发现 {core_metrics['alert_clusters']} 个告警事件",
                "status": "processing",
                "data": {
                    "event_count": len(self.alert_clusters)
                }
            }

            yield {
                "step": "报告生成",
                "progress": 95,
                "message": "生成分析报告",
                "status": "processing"
            }

            final_metrics = {
                'total_alerts': self.total_alerts,
                'denoised_count': denoised_count,
                'noise_reduction_rate': core_metrics['noise_reduction_rate'],
                'alert_clusters': core_metrics['alert_clusters']
            }

            yield {
                "step": "完成",
                "progress": 100,
                "message": "分析完成",
                "status": "completed",
                "metrics": final_metrics,
                "data": {
                    "report": self.report_content,
                    "event_summary": {
                        "total_events": len(self.alert_clusters),
                        "events": self.alert_clusters[:5]
                    }
                }
            }

        except Exception as e:
            import traceback
            yield {
                "step": "错误",
                "progress": 0,
                "message": f"分析失败: {str(e)}",
                "status": "error",
                "error_detail": traceback.format_exc()
            }

    def get_structured_data(self) -> pd.DataFrame:
        return self.structured_df

    def get_denoised_data(self) -> pd.DataFrame:
        return self.denoised_df

    def get_events(self) -> list:
        return self.alert_clusters

    def get_report(self) -> str:
        return self.report_content

    def get_metrics(self) -> Dict[str, Any]:
        return {
            'total_alerts': self.total_alerts,
            'denoised_count': len(self.denoised_df) if self.denoised_df is not None else 0,
            'noise_reduction_rate': core_metrics.get('noise_reduction_rate', 0),
            'alert_clusters': len(self.alert_clusters)
        }

    def save_results(self, output_dir: str = "."):
        if self.structured_df is not None:
            self.structured_df.to_excel(os.path.join(output_dir, "结构化数据.xlsx"), index=False)
            self.structured_df.to_csv(os.path.join(output_dir, "结构化数据.csv"), index=False)

        if self.denoised_df is not None:
            self.denoised_df.to_excel(os.path.join(output_dir, "降噪数据.xlsx"), index=False)
            self.denoised_df.to_csv(os.path.join(output_dir, "降噪数据.csv"), index=False)

        if self.alert_clusters:
            events_df = pd.DataFrame(self.alert_clusters)
            events_df.to_excel(os.path.join(output_dir, "事件聚类.xlsx"), index=False)
            events_df.to_csv(os.path.join(output_dir, "事件聚类.csv"), index=False)

        if self.report_content:
            with open(os.path.join(output_dir, "分析报告.md"), "w", encoding="utf-8") as f:
                f.write(self.report_content)

def stream_log_file(filepath: str) -> Generator[Dict[str, Any], None, None]:
    parser = StreamAlertParser()
    with open(filepath, 'rb') as f:
        file_content = f.read()
    yield from parser.parse_file(file_content, os.path.basename(filepath))

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("使用方法: python stream_parser_api.py <日志文件路径>")
        print("示例: python stream_parser_api.py sample/run_0801.xlsx")
        sys.exit(1)
    
    filepath = sys.argv[1]
    
    if not os.path.exists(filepath):
        print(f"错误: 文件不存在 - {filepath}")
        sys.exit(1)
    
    print(f"开始流式解析文件: {filepath}")
    print("-" * 60)
    
    parser = StreamAlertParser()
    with open(filepath, 'rb') as f:
        file_content = f.read()
    
    for progress in parser.parse_file(file_content, os.path.basename(filepath)):
        print(f"[{progress['step']}] 进度: {progress['progress']}% - {progress['message']}")
        if progress.get('data'):
            import json
            print(f"  数据: {json.dumps(progress['data'], ensure_ascii=False)}")
    
    print("-" * 60)
    print("分析完成！")
    print(f"\n统计指标:")
    for key, value in parser.get_metrics().items():
        print(f"  {key}: {value}")
    
    print("\n保存结果文件:")
    parser.save_results(".")
    print("  ✓ 结构化数据.xlsx")
    print("  ✓ 降噪数据.xlsx")
    print("  ✓ 事件聚类.xlsx")
    print("  ✓ 分析报告.md")
