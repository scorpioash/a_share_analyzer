import streamlit as st
import os
import sys
from datetime import datetime

# 注入根目录路径
sys.path.append(os.path.abspath("."))

from visual_style import inject_premium_style, render_styled_dataframe, show_error_clean
from market_monitor import render_market_monitor

# --- 注入视觉与监控 ---
inject_premium_style()

if 'fetcher' not in st.session_state:
    from data_fetcher import AShareDataFetcher
    st.session_state['fetcher'] = AShareDataFetcher()

fetcher = st.session_state['fetcher']

# 渲染侧边栏市场心跳仪表盘
render_market_monitor(fetcher)

st.title("📋 财务与年报季报")
st.markdown("跟踪上市公司业绩披露、财务报表、机构调研等基本面信息。")

tab_report, tab_research = st.tabs(["💰 业绩快报/预告", "🏢 机构调研详细"])

def _default_report_date():
    """根据当前时间推断最近的合理报告期"""
    now = datetime.now()
    y = now.year
    m = now.month
    # 5 月后通常 Q1 已披露,10 月后 Q3 披露
    if m >= 10:
        return f"{y}0930"
    if m >= 8:
        return f"{y}0630"
    if m >= 5:
        return f"{y}0331"
    # 1-4 月看上一年年报
    return f"{y-1}1231"

with tab_report:
    st.info("查询上市公司的业绩快报与预告，在财报披露季寻找超预期机会或规避业绩雷。")
    cola, colb = st.columns(2)
    with cola:
        report_type = st.selectbox("报告类型", ["业绩快报", "业绩预告", "业绩报表"])
    with colb:
        default_date = _default_report_date()
        report_date = st.text_input("报告期 (YYYYMMDD,只支持 0331/0630/0930/1231)",
                                     default_date,
                                     help="必须是季度末日期。示例:20251231 (年报) / 20250930 (三季报)")

    if st.button("查询业绩数据"):
        with st.spinner("拉取中..."):
            try:
                df_report = fetcher.get_earnings_summary(report_date, report_type)
            except Exception as e:
                df_report = None
                st.error(f"❌ 抓取异常: {type(e).__name__}: {e}")

        if df_report is not None and not df_report.empty:
            st.success(f"📌 共拉取到 {len(df_report)} 条企业披露记录。")
            render_styled_dataframe(df_report, width='stretch', hide_index=True)
        else:
            st.warning(f"未获取到 {report_date} 的 {report_type} 数据。可能原因：\n"
                       f"- 该报告期尚未到披露窗口\n"
                       f"- 日期格式不对（必须是季度末日期）\n"
                       f"- 接口限流")

with tab_research:
    st.markdown("跟踪全市场最新鲜的机构调研记录。**（默认展示近期最新记录）**")
    if st.button("刷新机构调研记录"):
        with st.spinner("由于信息量较大，拉取需要数秒钟..."):
            try:
                df_research = fetcher.get_institutional_research()
            except Exception as e:
                df_research = None
                st.error(f"❌ 抓取异常: {type(e).__name__}: {e}")

        if df_research is not None and not df_research.empty:
            st.success(f"📌 共拉取到 {len(df_research)} 条调研记录。")
            render_styled_dataframe(df_research, width='stretch', hide_index=True)
        else:
            st.warning("机构调研数据获取失败或今日暂无新记录。")