import streamlit as st
import pandas as pd
from data_fetcher import AShareDataFetcher

if 'fetcher' not in st.session_state:
    st.session_state['fetcher'] = AShareDataFetcher()

fetcher = st.session_state['fetcher']

st.title("🏷️ 全局板块大盘")
st.markdown("同花顺/东方财富全量行业、概念板块实时排名，把握市场绝对主线。")

tab_industry, tab_concept = st.tabs(["🏭 行业板块排行", "💡 概念板块排行"])

with tab_industry:
    st.info("拉取同花顺行业板块排名榜单。")
    if st.button("刷新行业板块库", key="btn_industry"):
        with st.spinner("拉取行业大盘..."):
            df_ind = fetcher.get_board_list(board_type="行业")
            if df_ind is not None and not df_ind.empty:
                st.success(f"📌 共收录 {len(df_ind)} 个行业板块。")
                
                # 清洗转数字方便排序
                sort_col = '涨跌幅' if '涨跌幅' in df_ind.columns else '最新价'
                if sort_col in df_ind.columns:
                    df_ind[sort_col] = pd.to_numeric(df_ind[sort_col], errors='coerce')
                    df_ind = df_ind.sort_values(by=sort_col, ascending=False)
                    
                st.dataframe(df_ind, width='stretch', hide_index=True)
            else:
                st.error("获取行业列表失败。")

with tab_concept:
    st.info("拉取同花顺数百个短线热点概念板块一览。")
    if st.button("刷新概念板块库", key="btn_concept"):
        with st.spinner("拉取概念大盘..."):
            df_con = fetcher.get_board_list(board_type="概念")
            if df_con is not None and not df_con.empty:
                st.success(f"📌 共收录 {len(df_con)} 个概念板块。")
                
                # 清洗转数字方便排序
                sort_col = '涨跌幅' if '涨跌幅' in df_con.columns else '最新价'
                if sort_col in df_con.columns:
                    df_con[sort_col] = pd.to_numeric(df_con[sort_col], errors='coerce')
                    df_con = df_con.sort_values(by=sort_col, ascending=False)
                    
                st.dataframe(df_con, width='stretch', hide_index=True)
            else:
                st.error("获取概念列表失败。")
