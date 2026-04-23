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

st.title("📰 资讯中心")
st.markdown("全球财经快讯及个股负面/利好消息监控。")

tab_global, tab_individual = st.tabs(["🌐 7×24 全球财经", "🔎 个股新闻查询"])

with tab_global:
    st.info("展示东财 7×24 小时全球财经直播与重要快讯。")
    if st.button("拉取最新快讯"):
        with st.spinner("获取中..."):
            try:
                df_global = fetcher.get_global_news()
            except Exception as e:
                df_global = None
                st.error(f"❌ 抓取异常: {type(e).__name__}: {e}")

        if df_global is not None and not df_global.empty:
            # 智能列配置: 如有 url 列则做链接
            col_config = {}
            if 'url' in df_global.columns:
                col_config['url'] = st.column_config.LinkColumn(
                    "文章链接", help="点击跳转到原文", display_text="点击阅读"
                )
            if '发布时间' in df_global.columns:
                col_config['发布时间'] = st.column_config.TextColumn("发布时间", width="medium")

            st.dataframe(df_global, width='stretch', hide_index=True,
                         column_config=col_config if col_config else None)
        else:
            st.warning("拉取财经快讯失败，请重试或检查网络。")

with tab_individual:
    query = st.text_input("请输入股票名称或代码查询相关新闻", "贵州茅台")
    if st.button("查询个股新闻"):
        code, name = fetcher.get_stock_name_or_code(query)
        if not code:
            st.error("未能识别股票")
        else:
            with st.spinner(f"正在拉取 {name} ({code}) 的新闻..."):
                try:
                    # 使用 get_stock_news_detail 返回 DataFrame (资讯中心专用)
                    df_news = fetcher.get_stock_news_detail(code)
                except Exception as e:
                    df_news = None
                    st.error(f"❌ 抓取异常: {type(e).__name__}: {e}")

            if df_news is not None and not df_news.empty:
                st.success(f"📌 共获取 {len(df_news)} 条新闻。")
                # 智能识别 URL 列
                col_config = {}
                for c in df_news.columns:
                    if '链接' in str(c) or 'url' in str(c).lower() or 'link' in str(c).lower():
                        col_config[c] = st.column_config.LinkColumn(
                            str(c), display_text="查看原文"
                        )
                st.dataframe(df_news, width='stretch', hide_index=True,
                             column_config=col_config if col_config else None)
            else:
                # 回退到 str 版 get_news
                news_txt = fetcher.get_news(code)
                st.markdown(news_txt)