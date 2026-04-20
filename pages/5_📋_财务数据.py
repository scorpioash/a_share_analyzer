import streamlit as st
import os
import sys

# 注入根目录路径
sys.path.append(os.path.abspath("."))

from visual_style import inject_premium_style, show_error_clean
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

with tab_report:
    st.info("查询上市公司的业绩快报与预告，在财报披露季寻找超预期机会或规避业绩雷。")
    cola, colb = st.columns(2)
    with cola:
        report_type = st.selectbox("报告类型", ["业绩快报", "业绩预告"])
    with colb:
        report_date = st.text_input("报告期 (例如20241231、20250331)", "20241231")
    
    if st.button("查询业绩数据"):
        with st.spinner("拉取中..."):
            df_report = fetcher.get_earnings_summary(report_date, report_type)
        if df_report is not None and not df_report.empty:
            st.success(f"📌 共拉取到 {len(df_report)} 条企业披露记录。")
            st.dataframe(df_report, width='stretch', hide_index=True)
        else:
            st.error("数据拉取失败，请检查报告期格式是否正确，或该报告期暂无数据。")

with tab_research:
    st.markdown("跟踪全市场最新鲜的机构调研记录。**（默认展示近期最新记录）**")
    if st.button("刷新机构调研记录"):
        with st.spinner("由于信息量较大，拉取需要数秒钟..."):
            df_research = fetcher.get_institutional_research()
        if df_research is not None and not df_research.empty:
            st.dataframe(df_research, width='stretch', hide_index=True)
        else:
            st.error("机构调研数据获取失败。")
