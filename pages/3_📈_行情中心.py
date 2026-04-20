import streamlit as st
from data_fetcher import AShareDataFetcher

if 'fetcher' not in st.session_state:
    st.session_state['fetcher'] = AShareDataFetcher()

fetcher = st.session_state['fetcher']

st.title("📈 行情中心")
st.markdown("全市场实时行情数据大盘点。")

market_type = st.selectbox("🎯 选择市场", ["主板", "创业板", "科创板", "北交所"])

st.info("因数据量较大，为避免接口耗流，请手动点击获取行情。")

if st.button(f"获取 {market_type} 最新行情"):
    with st.spinner("数据加载中..."):
        df = fetcher.get_realtime_quotes(market_type)
    
    if df is not None and not df.empty:
        st.success(f"成功获取 {len(df)} 只股票数据。")
        # 格式化展示一些核心列
        display_cols = ['代码', '名称', '最新价', '涨跌幅', '涨跌额', '成交量', '成交额', '换手率', '市盈率-动态']
        available_cols = [c for c in display_cols if c in df.columns]
        
        # 支持按涨跌幅等排序
        sort_by = st.selectbox("排序依据", available_cols[2:], index=1)
        
        # 清洗数据：将非数字转为 NaN，便于排序
        import pandas as pd
        df_clean = df.copy()
        if sort_by in df_clean.columns:
            df_clean[sort_by] = pd.to_numeric(df_clean[sort_by], errors='coerce')
            df_clean = df_clean.sort_values(by=sort_by, ascending=False)
            
        st.dataframe(df_clean[available_cols], width='stretch', hide_index=True)
    else:
        st.error("数据拉取失败，请检查网络或接口是否因频繁访问被限制。")
