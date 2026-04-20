import streamlit as st
import pandas as pd
from data_fetcher import AShareDataFetcher

if 'fetcher' not in st.session_state:
    st.session_state['fetcher'] = AShareDataFetcher()

fetcher = st.session_state['fetcher']

st.title("🌡️ 市场情绪与热度")
st.markdown("监控全市场散户关注度与赚钱效应，判断大盘冰点与高潮。")

tab_hot, tab_sentiment = st.tabs(["🔥 股票关注度排行", "💰 赚钱效应分析"])

with tab_hot:
    st.info("拉取东方财富全市场股票热度排名榜单。散户关注度极高往往意味着加速或见顶。")
    if st.button("刷新股票热度榜", key="btn_hot"):
        with st.spinner("数据加载中..."):
            try:
                import akshare as ak
                from data_fetcher import bypass_proxy
                with bypass_proxy():
                    df_hot = ak.stock_hot_rank_em()
                if not df_hot.empty:
                    st.success(f"📌 共收录当前热度前 {len(df_hot)} 名的股票。")
                    
                    # 简单清洗列名
                    if '排名' in df_hot.columns:
                        df_hot = df_hot.sort_values(by='排名')
                        
                    st.dataframe(df_hot, width='stretch', hide_index=True)
                else:
                    st.error("获取股票热度榜失败，数据为空。")
            except Exception as e:
                st.error(f"接口调用失败: {e}")

with tab_sentiment:
    st.info("大盘情绪温度计：展示全市场赚钱效应、涨跌停家数比、封板率等核心情绪指标。")
    if st.button("刷新赚钱效应", key="btn_sentiment"):
        with st.spinner("数据加载中..."):
            df_sent = fetcher.get_market_sentiment()
            if df_sent is not None and not df_sent.empty:
                st.success("📌 最新市场真实温度")
                
                # 提取前几项显示为指标卡片
                st.markdown("### 核心情绪指标")
                cols = st.columns(4)
                
                # 显示表格
                st.dataframe(df_sent, width='stretch', hide_index=True)
            else:
                st.error("获取赚钱效应数据失败，可能非交易时段。")
