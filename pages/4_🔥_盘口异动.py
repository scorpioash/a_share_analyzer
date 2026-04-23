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

st.title("🔥 盘口异动与特征股池")
st.markdown("监控全市场涨跌停、强势股及盘口异动情况，捕捉情绪拐点。")

tab_pools, tab_changes, tab_board_changes = st.tabs(["📊 特征股池", "⚡ 盘中异动", "💥 板块异动详情"])

with tab_pools:
    pool_type = st.radio("选择特征股池",
                         ["涨停", "跌停", "昨日涨停", "强势股", "次新股", "炸板"],
                         horizontal=True)

    st.info("盘中极限异动数据频繁变动，为避免接口耗流请手动获取。")
    if st.button(f"获取 {pool_type} 池最新数据"):
        with st.spinner("数据加载中..."):
            try:
                df_pool = fetcher.get_limit_pool(pool_type)
            except Exception as e:
                df_pool = None
                st.error(f"❌ 抓取异常: {type(e).__name__}: {e}")

        if df_pool is not None and not df_pool.empty:
            st.success(f"📌 共收录 {len(df_pool)} 只股票。")
            df_clean = df_pool.copy()
            sort_col = '涨跌幅' if '涨跌幅' in df_clean.columns else (
                '最新价' if '最新价' in df_clean.columns else None
            )
            if sort_col:
                df_clean[sort_col] = pd.to_numeric(df_clean[sort_col], errors='coerce')
                df_clean = df_clean.sort_values(by=sort_col, ascending=False, na_position='last')
            st.dataframe(df_clean, width='stretch', hide_index=True)
        else:
            st.warning(f"暂无 {pool_type} 数据。可能原因：\n"
                       f"- 盘后/节假日数据未更新\n"
                       f"- 该股池今日无股票入围\n"
                       f"- 接口暂时受限")
            diags = fetcher.get_last_diagnostics() if hasattr(fetcher, 'get_last_diagnostics') else []
            if diags:
                with st.expander("🔍 查看诊断日志"):
                    for line in diags[-15:]:
                        st.text(line)

with tab_changes:
    st.markdown("盘中实时异动信号捕捉。")
    change_types = ["大笔买入", "火箭发射", "快速反弹", "封涨停板", "打开跌停板", "有大买盘",
                    "竞价上涨", "高开5日线", "向上缺口", "60日新高",
                    "大笔卖出", "加速下跌", "高台跳水", "封跌停板", "打开涨停板",
                    "有大卖盘", "竞价下跌", "低开5日线", "向下缺口", "60日新低"]
    change_symbol = st.selectbox("选择异动类型", change_types)
    if st.button("刷新异动数据"):
        with st.spinner("拉取盘中异动..."):
            try:
                df_changes = fetcher.get_market_changes(symbol=change_symbol)
            except Exception as e:
                df_changes = None
                st.error(f"❌ 抓取异常: {type(e).__name__}: {e}")

        if df_changes is not None and not df_changes.empty:
            st.dataframe(df_changes, width='stretch', hide_index=True)
        else:
            st.warning("今日该类型暂无异动数据（盘后/节假日常见）。")

with tab_board_changes:
    st.markdown("监控全市场行业/概念板块的日内异动详情。")
    if st.button("刷新板块异动"):
        with st.spinner("拉取板块异动..."):
            try:
                from data_fetcher import bypass_proxy
                import akshare as ak
                with bypass_proxy():
                    if hasattr(ak, 'stock_board_change_em'):
                        df_bc = ak.stock_board_change_em()
                    else:
                        df_bc = None
                if df_bc is not None and not df_bc.empty:
                    st.dataframe(df_bc, width='stretch', hide_index=True)
                else:
                    st.warning("今日暂无板块异动数据。")
            except Exception as e:
                st.error(f"获取板块异动失败: {type(e).__name__}: {e}")