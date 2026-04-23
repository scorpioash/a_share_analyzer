import streamlit as st
import os
import sys
import pandas as pd

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

st.title("🏷️ 板块大盘")
st.markdown("同花顺/东方财富全量行业、概念板块实时排名，把握市场绝对主线。")

tab_industry, tab_concept = st.tabs(["🏭 行业板块排行", "💡 概念板块排行"])

def _display_board(df, name):
    """通用板块展示逻辑"""
    if df is None or df.empty:
        st.error(f"获取{name}列表失败。")
        return
    st.success(f"📌 共收录 {len(df)} 个{name}。")

    # 智能选择排序列
    sort_candidates = ['涨跌幅', '最新价', '板块涨跌幅']
    sort_col = None
    for c in sort_candidates:
        if c in df.columns:
            sort_col = c
            break

    df_sorted = df.copy()
    if sort_col:
        df_sorted[sort_col] = pd.to_numeric(df_sorted[sort_col], errors='coerce')
        df_sorted = df_sorted.sort_values(by=sort_col, ascending=False, na_position='last')

    st.dataframe(df_sorted, width='stretch', hide_index=True)

with tab_industry:
    st.info("拉取东方财富/同花顺行业板块排名榜单。")
    if st.button("刷新行业板块库", key="btn_industry"):
        with st.spinner("拉取行业大盘..."):
            try:
                df_ind = fetcher.get_board_list(board_type="行业")
            except Exception as e:
                df_ind = None
                st.error(f"❌ 抓取异常: {type(e).__name__}: {e}")
        _display_board(df_ind, "行业板块")

with tab_concept:
    st.info("拉取东方财富/同花顺数百个短线热点概念板块一览。")
    if st.button("刷新概念板块库", key="btn_concept"):
        with st.spinner("拉取概念大盘..."):
            try:
                df_con = fetcher.get_board_list(board_type="概念")
            except Exception as e:
                df_con = None
                st.error(f"❌ 抓取异常: {type(e).__name__}: {e}")
        _display_board(df_con, "概念板块")