import streamlit as st
import os
import sys
import datetime

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

st.title("🐉 龙虎榜与资金流")
st.markdown("跟踪市场最敏锐的活跃资金、机构席位异动以及主力资金排名。")

tab_lhb, tab_flow = st.tabs(["🔥 每日龙虎榜全量数据", "💰 资金流向排行"])

with tab_lhb:
    st.info("查询个股因异动被交易所公布的买卖席位数据。")
    default_date = datetime.datetime.now().strftime("%Y%m%d")
    lhb_date = st.text_input("请输入交易日 (格式 YYYYMMDD)", value=default_date)

    if st.button("查询龙虎榜"):
        with st.spinner("拉取数据中..."):
            try:
                df_lhb = fetcher.get_daily_dragon_tiger(lhb_date)
            except Exception as e:
                df_lhb = None
                st.error(f"❌ 抓取异常: {type(e).__name__}: {e}")

        if df_lhb is not None and not df_lhb.empty:
            st.success(f"📌 {lhb_date} 共上榜 {len(df_lhb)} 次。")
            render_styled_dataframe(df_lhb, width='stretch', hide_index=True)
        else:
            st.warning("暂无数据，可能是周末/节假日，或者当日龙虎榜尚未公布（一般晚上 17:00 后更新）。")

with tab_flow:
    st.info("展示全市场个股资金流向排行，洞察主力资金进攻方向。")
    indicator = st.selectbox("选择统计周期", ["今日", "3日", "5日", "10日"])

    if st.button("查询资金流向"):
        with st.spinner("拉取资金流向中..."):
            try:
                df_flow = fetcher.get_fund_flow_rank(indicator)
            except Exception as e:
                df_flow = None
                st.error(f"❌ 抓取异常: {type(e).__name__}: {e}")

        if df_flow is not None and not df_flow.empty:
            st.success(f"📌 共获取 {len(df_flow)} 只个股资金数据。")
            render_styled_dataframe(df_flow, width='stretch', hide_index=True)
        else:
            st.warning("获取资金流向排名失败。可能非交易时段或接口限流。")