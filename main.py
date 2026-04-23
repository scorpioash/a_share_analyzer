"""极简 A 股智能分析引擎 - CLI 入口

支持场景:
    1. 本地命令行: python main.py --stocks 600519,000001
    2. GitHub Actions 定时任务
    3. 配合飞书机器人 Webhook 推送结果
"""

import os
import sys
import argparse
import traceback
from datetime import datetime

import httpx
from dotenv import load_dotenv

load_dotenv()


# ===========================================================================
# 飞书推送
# ===========================================================================
def send_to_feishu(webhook_url: str, title: str, content: str) -> bool:
    """发送富文本到飞书机器人。成功返回 True。"""
    if not webhook_url:
        print("⚠️  未配置 FEISHU_WEBHOOK_URL，跳过推送")
        return False

    # 飞书富文本需要把长文按段落拆分,每段一个 text 元素
    # 单条消息不建议超过 30KB,这里粗暴截断 25KB 内保平安
    max_len = 25000
    if len(content) > max_len:
        content = content[:max_len] + "\n\n...[内容过长已截断]"

    # 按双换行分段,每段作为一行文本
    paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
    rich_content = [[{"tag": "text", "text": p}] for p in paragraphs]

    payload = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": rich_content,
                }
            }
        },
    }

    try:
        resp = httpx.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0 or data.get("StatusCode") == 0:
                print("✅ 飞书消息推送成功")
                return True
            else:
                print(f"❌ 飞书推送失败(业务错误): {data}")
                return False
        else:
            print(f"❌ 飞书推送失败: HTTP {resp.status_code} - {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ 飞书推送异常: {type(e).__name__}: {e}")
        return False


# ===========================================================================
# 股票池解析
# ===========================================================================
def resolve_stock_list(cli_arg: str) -> list:
    """按优先级解析要分析的股票代码:
       1. 命令行 --stocks 参数
       2. 环境变量 STOCK_LIST
       3. 交互式输入 (仅本地,CI 环境直接 sys.exit)
    """
    stocks_input = (cli_arg or "").strip()

    if not stocks_input:
        stocks_input = os.getenv("STOCK_LIST", "").strip()

    if not stocks_input:
        # CI 环境下拒绝交互,直接退出并提示
        if os.getenv("GITHUB_ACTIONS") or os.getenv("IN_GITHUB_ACTIONS"):
            print("\n" + "!" * 60)
            print("🚨 [GITHUB ACTIONS 配置错误] 未检测到 STOCK_LIST")
            print("!" * 60)
            print("请按以下步骤配置:")
            print("  1. 前往 GitHub 仓库 → Settings → Secrets and variables → Actions")
            print("  2. 点击 'New repository secret'")
            print("  3. 名称填: STOCK_LIST")
            print("  4. 值填想跟踪的股票代码,逗号分隔,如: 600519,000001,sz002594")
            print("\n或者通过 Actions 页面手动运行时,在输入框里直接填入股票代码。")
            print("!" * 60 + "\n")
            sys.exit(1)

        # 本地环境,引导用户输入
        print("\n[提示] 未在命令行参数或 .env 中检测到 STOCK_LIST。")
        stocks_input = input(
            "👉 请手动输入你想要分析的 A 股代码 (逗号分隔,如 600519,sz002594): "
        ).strip()

    if not stocks_input:
        print("❌ 未提供有效的股票代码,程序退出。")
        sys.exit(1)

    codes = [s.strip() for s in stocks_input.split(",") if s.strip()]
    if not codes:
        print("❌ 股票代码解析后为空,程序退出。")
        sys.exit(1)

    return codes


# ===========================================================================
# 主逻辑
# ===========================================================================
def main():
    print("=" * 60)
    print("📈 极简 A 股智能分析引擎")
    print(f"⏰ 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🌐 运行环境: {'GitHub Actions' if os.getenv('IN_GITHUB_ACTIONS') else '本地'}")
    print("=" * 60)

    # 1. 解析参数
    parser = argparse.ArgumentParser(description="极简 A 股智能分析器")
    parser.add_argument(
        "--stocks",
        type=str,
        default="",
        help="要分析的股票代码,逗号分隔,如 600519,000001",
    )
    args = parser.parse_args()

    stock_codes = resolve_stock_list(args.stocks)
    print(f"\n📋 本次任务: 共 {len(stock_codes)} 只股票 → {', '.join(stock_codes)}\n")

    # 2. 初始化引擎 (延迟 import,让错误定位更清晰)
    print("🔧 正在初始化数据抓取引擎...")
    try:
        from data_fetcher import AShareDataFetcher
        fetcher = AShareDataFetcher()
    except Exception as e:
        print(f"❌ 数据引擎初始化失败: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)

    print("🤖 正在初始化 AI 分析引擎...")
    try:
        from llm_analyzer import LLMAnalyzer
        analyzer = LLMAnalyzer()
        print(f"   当前 Provider: {analyzer.provider}")
    except Exception as e:
        print(f"❌ AI 引擎初始化失败: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)

    # 3. 依次分析
    feishu_webhook = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
    overall_report = []
    success_count = 0
    fail_count = 0

    for idx, raw_query in enumerate(stock_codes, 1):
        print(f"\n{'─' * 60}")
        print(f"[{idx}/{len(stock_codes)}] 正在分析: {raw_query}")
        print(f"{'─' * 60}")

        # 3.1 抓取数据
        try:
            code, name, data_ctx = fetcher.get_full_analysis_context(raw_query)
        except Exception as e:
            print(f"❌ 数据抓取异常: {type(e).__name__}: {e}")
            traceback.print_exc()
            fail_count += 1
            continue

        if not code:
            print(f"❌ 股票解析失败: {data_ctx}")
            fail_count += 1
            continue

        print(f"✅ 已锁定: {name} ({code})")
        print(f"📊 数据包大小: {len(data_ctx)} 字符")

        # 3.2 调用 AI
        print(f"🤖 调用 {analyzer.provider.upper()} 进行分析...")
        try:
            analysis_result = analyzer.analyze(data_ctx)
        except Exception as e:
            print(f"❌ AI 分析异常: {type(e).__name__}: {e}")
            traceback.print_exc()
            fail_count += 1
            continue

        if not analysis_result or analysis_result.startswith("❌"):
            print(f"⚠️  AI 返回异常结果: {analysis_result[:200]}")
            fail_count += 1
            continue

        # 3.3 组装结果
        report_block = f"【{name} - {code}】\n{analysis_result}\n" + "─" * 30
        overall_report.append(report_block)
        success_count += 1

        print(f"✅ 分析完成")
        print(f"\n{report_block}\n")

    # 4. 汇总与推送
    print("\n" + "=" * 60)
    print(f"📊 执行总结: 成功 {success_count} / 失败 {fail_count} / 共 {len(stock_codes)}")
    print("=" * 60)

    if overall_report:
        full_text = "\n\n".join(overall_report)
        title = f"📈 A 股盘后研报 · {datetime.now().strftime('%Y-%m-%d')}"

        if feishu_webhook:
            print("\n📤 正在推送到飞书...")
            send_to_feishu(feishu_webhook, title, full_text)
        else:
            print("\n💡 未配置飞书 Webhook,仅输出到日志")
    else:
        print("\n⚠️  没有任何成功的分析结果,跳过推送")
        # 全部失败时退出码设为 1,让 CI 标红
        if fail_count > 0:
            sys.exit(1)

    print("\n🎉 所有任务已结束")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断,程序退出")
        sys.exit(130)
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ 主程序致命错误: {type(e).__name__}: {e}")
        print("=" * 60)
        traceback.print_exc()
        sys.exit(1)