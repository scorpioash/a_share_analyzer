import streamlit as st
import os
import sys

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
try:
    render_market_monitor(fetcher)
except Exception as e:
    show_error_clean("市场监控组件加载失败", e)

st.title("🌡️ 市场情绪与热度")
st.markdown("监控全市场散户关注度与赚钱效应，判断大盘冰点与高潮。")

tab_hot, tab_sentiment = st.tabs(["🔥 股票关注度排行", "💰 赚钱效应分析"])

with tab_hot:
    st.info("拉取东方财富全市场股票热度排名榜单。散户关注度极高往往意味着加速或见顶。")
    if st.button("刷新股票热度榜", key="btn_hot"):
        with st.spinner("数据加载中..."):
            try:
                df_hot = fetcher.get_stock_heat_rank()
            except Exception as e:
                df_hot = None
                st.error(f"❌ 抓取异常: {type(e).__name__}: {e}")

        if df_hot is not None and not df_hot.empty:
            st.success(f"📌 共收录当前热度前 {len(df_hot)} 名的股票。")

            if '排名' in df_hot.columns:
                df_hot = df_hot.sort_values(by='排名')

            render_styled_dataframe(df_hot, width='stretch', hide_index=True)
        else:
            st.warning("获取股票热度榜失败，可能接口被限流或非交易时段。")

with tab_sentiment:
    st.info("大盘情绪温度计：展示全市场赚钱效应、涨跌停家数比、封板率等核心情绪指标。")
    if st.button("刷新赚钱效应", key="btn_sentiment"):
        with st.spinner("数据加载中..."):
            try:
                df_sent = fetcher.get_market_sentiment()
            except Exception as e:
                df_sent = None
                st.error(f"❌ 抓取异常: {type(e).__name__}: {e}")

        if df_sent is not None and not df_sent.empty:
            st.success("📌 最新市场真实温度")

            # 提取前几项显示为指标卡片
            st.markdown("### 核心情绪指标")
            try:
                # df_sent 格式: 指标/数值/占比
                row_map = {r['指标']: r for _, r in df_sent.iterrows()}
                cols = st.columns(4)

                def _metric(col, key, label=None, delta_color="off"):
                    if key in row_map:
                        r = row_map[key]
                        col.metric(label or key, r['数值'], r.get('占比', ''),
                                   delta_color=delta_color)

                _metric(cols[0], '上涨家数', '🔴 上涨家数', 'inverse')
                _metric(cols[1], '下跌家数', '🟢 下跌家数', 'normal')
                _metric(cols[2], '涨停家数', '🚀 涨停家数', 'inverse')
                _metric(cols[3], '全市场情绪', '🌡️ 情绪', 'off')
            except Exception:
                pass

            st.markdown("### 详细指标表")
            render_styled_dataframe(df_sent, width='stretch', hide_index=True)
        else:
            st.warning("获取赚钱效应数据失败，可能非交易时段或全市场快照接口受限。")
            diags = fetcher.get_last_diagnostics() if hasattr(fetcher, 'get_last_diagnostics') else []
            if diags:
                with st.expander("🔍 查看诊断日志"):
                    for line in diags[-15:]:
                        st.text(line)