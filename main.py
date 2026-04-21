import os
import httpx
import json
from dotenv import load_dotenv
from data_fetcher import AShareDataFetcher
from llm_analyzer import LLMAnalyzer

load_dotenv()

def send_to_feishu(webhook_url: str, title: str, content: str):
    """发送富文本到飞书机器人的简单实现"""
    if not webhook_url:
        print("未配置 FEISHU_WEBHOOK_URL，跳过推送")
        return
        
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": [
                        [{"tag": "text", "text": content}]
                    ]
                }
            }
        }
    }
    
    try:
        response = httpx.post(webhook_url, json=payload, headers=headers, timeout=10.0)
        if response.status_code == 200:
            print("飞书消息推送成功")
        else:
            print(f"飞书消息推送失败: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"飞书消息推送异常: {e}")

import argparse

def main():
    print("="*50)
    print("极简 A 股智能分析引擎启动")
    print("="*50)
    
    # 1. 载入环境与参数
    parser = argparse.ArgumentParser(description="极简 A 股智能分析器")
    parser.add_argument("--stocks", type=str, help="要分析的股票代码，逗号分隔，如 600519,000001", default="")
    args = parser.parse_args()

    feishu_webhook = os.getenv("FEISHU_WEBHOOK_URL", "")
    
    # 获取股票池顺序：1. 命令行参数 -> 2. .env变量 -> 3. 阻塞式交互输入
    stocks_input = args.stocks.strip()
    if not stocks_input:
        stocks_input = os.getenv("STOCK_LIST", "").strip()
        
    if not stocks_input:
        if os.getenv("GITHUB_ACTIONS"):
            print("\n" + "!"*60)
            print("🚨 [GITHUB ACTIONS 配置错误] 未检测到 STOCK_LIST！")
            print("请按以下步骤操作：")
            print("1. 前往 GitHub 仓库 -> Settings -> Secrets and variables -> Actions")
            print("2. 点击 'New repository secret'，名称设为 STOCK_LIST")
            print("3. 内容通过逗号分隔，如: 600519,000001,sz002594")
            print("!"*60 + "\n")
            import sys
            sys.exit(1)
            
        print("\n[环境提示] 未在命令或 .env 中检测到指定目标。")
        stocks_input = input("👉 请手动输入你想要分析的 A 股代码 (逗号分隔，例如 600519,sz002594): ").strip()
        
    if not stocks_input:
        print("未提供有效的股票代码，程序退出。")
        return
        
    stock_codes = [s.strip() for s in stocks_input.split(",") if s.strip()]
    
    fetcher = AShareDataFetcher()
    analyzer = LLMAnalyzer()
    
    # 2. 依次遍历
    overall_report = []
    
    for raw_query in stock_codes:
        print(f"\n[+] 正在解析查询: {raw_query} ...")
        code, name, data_ctx = fetcher.get_full_analysis_context(raw_query)
        
        if not code:
            print(f"[-] 错误: {data_ctx}")
            continue
            
        print(f"[*] 正在调用 {analyzer.provider.upper()} 进行 AI 分析...")
        analysis_result = analyzer.analyze(data_ctx)
        
        report_block = f"【{name} - {code}】\n{analysis_result}\n" + "-"*30
        overall_report.append(report_block)
        
        print(f"[✓] {raw_query} 分析完成。")
        print("\n" + report_block)
        
    # 3. 合并推送
    if feishu_webhook and overall_report:
        full_text = "\n\n".join(overall_report)
        send_to_feishu(feishu_webhook, "📈 A 股极简盘后研报", full_text)
        
    print("\n所有任务已结束。")

if __name__ == "__main__":
    main()
