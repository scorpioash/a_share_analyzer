import streamlit as st
import os
import sys
import pandas as pd

# 注入根目录路径
sys.path.append(os.path.abspath("."))

from visual_style import inject_premium_style, show_error_clean, render_styled_dataframe
from market_monitor import render_market_monitor

# --- 注入视觉与监控 ---
inject_premium_style()

if 'fetcher' not in st.session_state:
    from data_fetcher import AShareDataFetcher
    st.session_state['fetcher'] = AShareDataFetcher()

fetcher = st.session_state['fetcher']

# 渲染侧边栏市场心跳仪表盘
render_market_monitor(fetcher)

st.title("📈 行情中心")
st.markdown("全市场实时行情数据大盘点。")

market_type = st.selectbox("🎯 选择市场", ["沪深主板", "创业板", "科创板", "北交所"])

st.info("因数据量较大，为避免接口耗流，请手动点击获取行情。")

if st.button(f"获取 {market_type} 最新行情"):
    with st.spinner("数据加载中..."):
        try:
            df = fetcher.get_realtime_quotes(market_type)
        except Exception as e:
            df = None
            st.error(f"❌ 抓取异常: {type(e).__name__}: {e}")

    if df is not None and not df.empty:
        st.success(f"成功获取 {len(df)} 只股票数据。")

        # 只显示存在的核心列 (不同数据源列名可能不同)
        preferred_cols = ['代码', '名称', '最新价', '涨跌幅', '涨跌额',
                          '成交量', '成交额', '今开', '最高', '最低',
                          '昨收', '换手率', '市盈率-动态', '市盈率', '市净率']
        available_cols = [c for c in preferred_cols if c in df.columns]
        if not available_cols:
            # 如果预设列全不存在,直接把原表展示
            available_cols = list(df.columns)

        # 排序:只选可能是数值的列
        numeric_candidates = [c for c in ['涨跌幅', '最新价', '换手率', '成交额', '成交量']
                              if c in df.columns]
        sort_by = None
        if numeric_candidates:
            sort_by = st.selectbox("排序依据", numeric_candidates, index=0)

        df_clean = df.copy()
        if sort_by:
            df_clean[sort_by] = pd.to_numeric(df_clean[sort_by], errors='coerce')
            df_clean = df_clean.sort_values(by=sort_by, ascending=False, na_position='last')

        render_styled_dataframe(df_clean[available_cols], width='stretch', hide_index=True)
    else:
        st.error("数据拉取失败，请检查网络或接口是否因频繁访问被限制。")
        # 显示诊断日志便于排查
        diags = fetcher.get_last_diagnostics() if hasattr(fetcher, 'get_last_diagnostics') else []
        if diags:
            with st.expander("🔍 查看抓取诊断日志"):
                for line in diags[-20:]:
                    st.text(line)