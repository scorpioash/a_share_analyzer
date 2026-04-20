import streamlit as st
from data_fetcher import AShareDataFetcher

if 'fetcher' not in st.session_state:
    st.session_state['fetcher'] = AShareDataFetcher()

fetcher = st.session_state['fetcher']

st.title("👥 股东研究")
st.markdown("穿透筹码分布，追踪散户集中度与主力控盘情况。")

query = st.text_input("请输入股票名称或代码查询", "贵州茅台", key="shareholder_query")

if st.button("查询股东数据"):
    code, name = fetcher.get_stock_name_or_code(query)
    if not code:
        st.error("未能识别股票")
    else:
        st.write(f"### {name} ({code}) 股东结构解析")
        
        cola, colb = st.columns(2)
        
        with cola:
            with st.spinner("拉取十大股东..."):
                top_holders_df = fetcher.get_top_shareholders(code)
            if top_holders_df is not None:
                st.dataframe(top_holders_df, width='stretch', hide_index=True)
            else:
                st.warning("近期暂无该股的十大股东变动记录。")
            
        with colb:
            st.markdown("#### 股东户数变化")
            with st.spinner("拉取户数趋势..."):
                holders_count_md = fetcher.get_shareholder_count(code)
            
            # 由于 get_shareholder_count 返回的是换行字符串，我们直接渲染
            st.markdown(holders_count_md)
        
        st.info("提示：结合个股阶段走势。如果股价在底部但股东户数持续下降，通常是主力吸筹；如果是股价高位且股东户数大幅增加，需警惕主力派发筹码。")
