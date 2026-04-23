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
            st.markdown("#### 🏦 十大流通股东")
            with st.spinner("拉取十大股东..."):
                try:
                    top_holders_df = fetcher.get_top_shareholders(code)
                except Exception as e:
                    top_holders_df = None
                    st.error(f"❌ 抓取异常: {type(e).__name__}: {e}")

            if top_holders_df is not None and not top_holders_df.empty:
                st.dataframe(top_holders_df, width='stretch', hide_index=True)
            else:
                st.warning("近期暂无该股的十大股东变动记录。")

        with colb:
            st.markdown("#### 📉 股东户数变化")
            with st.spinner("拉取户数趋势..."):
                try:
                    # 使用 DataFrame 版本 (get_shareholder_count_detail)
                    holders_count_df = fetcher.get_shareholder_count_detail(code)
                except Exception as e:
                    holders_count_df = None
                    st.error(f"❌ 抓取异常: {type(e).__name__}: {e}")

            if holders_count_df is not None and not holders_count_df.empty:
                st.dataframe(holders_count_df, width='stretch', hide_index=True)
            else:
                st.warning("该股股东户数数据获取失败。")

        st.info("💡 **筹码解读提示**：如果股价在底部但股东户数持续下降，通常是主力吸筹；"
                "如果是股价高位且股东户数大幅增加，需警惕主力派发筹码。")