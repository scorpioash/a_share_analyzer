import streamlit as st
# Force Reload: v2.0 - Updated with manual PDF/MD export support
import os
import sys
from datetime import datetime
# Force reload trigger: normalize_datetime_imports_v3

# 注入根目录路径，确保子页面能正确找到视觉组件
sys.path.append(os.path.abspath("."))

from data_fetcher import AShareDataFetcher
from llm_analyzer import LLMAnalyzer
from visual_style import inject_premium_style, show_error_clean
from market_monitor import render_market_monitor
from report_exporter import ReportExporter

# --- 注入视觉与监控 ---
inject_premium_style()

# 初始化组件
if 'fetcher' not in st.session_state:
    st.session_state['fetcher'] = AShareDataFetcher()

fetcher = st.session_state['fetcher']
analyzer = LLMAnalyzer() 
exporter = ReportExporter()

# 渲染侧边栏市场心跳仪表盘
render_market_monitor(fetcher)

st.title("🔍 智能诊股")
st.markdown("通过名字或代码输入，结合您的个性化铁律进行深度诊股。如需调整分析准则，请前往左侧 **[📋 策略配置]** 界面。")

query = st.text_input("🔍 请输入 A 股代码或名称 (例如：贵州茅台，或 600519)", "", key="stock_query")

# --- State Preservation Logic ---
if 'last_analysis' not in st.session_state:
    st.session_state['last_analysis'] = None

# 展示诊断结果
if st.session_state['last_analysis']:
    res = st.session_state['last_analysis']
    st.markdown(f"### 🎯 【{res['name']} - {res['code']}】诊断报告")
    st.caption(f"🕒 本报告生成于: {res.get('timestamp', '未知时间')}")
    
    # 渲染持久化的分时图和盘口数据
    spot = res.get('spot')
    plot_df = res.get('plot_df')
    if spot:
        st.subheader(f"📈 {res['name']} 实盘分时脉搏 (1分钟线)")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("当前价", f"{spot['price']:.2f}", f"{spot['change_pct']:.2f}%", delta_color="inverse")
        col2.metric("今日最高", f"{spot['high']:.2f}")
        col3.metric("今日最低", f"{spot['low']:.2f}")
        col4.metric("成交量", f"{int(spot['volume'])}")
        
        if plot_df is not None and not plot_df.empty:
            try:
                import plotly.graph_objects as go
                from plotly.subplots import make_subplots
                
                # 1. 计算基准价 (昨收)
                pre_close = spot['price'] / (1 + spot['change_pct'] / 100)
                
                # 2. 确定主副Y轴绝对对称范围
                max_diff = max(abs(plot_df['Price'].max() - pre_close), abs(plot_df['Price'].min() - pre_close))
                if max_diff == 0: max_diff = pre_close * 0.02
                max_diff = max_diff * 1.05  # 5% 边距
                
                y_min, y_max = pre_close - max_diff, pre_close + max_diff
                pct_min, pct_max = -max_diff / pre_close * 100, max_diff / pre_close * 100
                
                # 3. 创建专业双轴子图
                fig = make_subplots(
                    rows=2, cols=1, shared_xaxes=True,
                    row_heights=[0.75, 0.25], vertical_spacing=0.03,
                    specs=[[{"secondary_y": True}], [{"secondary_y": False}]]
                )
                
                # --- 上半部分：价格与均价 ---
                # 现价线 (经典黑色)
                fig.add_trace(
                    go.Scatter(x=plot_df['Time'], y=plot_df['Price'], mode='lines',
                               name='现价', line=dict(color='#111111', width=1.5)),
                    row=1, col=1, secondary_y=False
                )
                
                # 均价线 (同花顺经典橙黄色)
                if 'AvgPrice' in plot_df.columns:
                    fig.add_trace(
                        go.Scatter(x=plot_df['Time'], y=plot_df['AvgPrice'], mode='lines',
                                   name='均价', line=dict(color='#f0a30a', width=1.2)),
                        row=1, col=1, secondary_y=False
                    )
                
                # 昨收基准线 (中间红色虚线)
                fig.add_hline(y=pre_close, line_dash="dash", line_color="#ff4b4b", line_width=1, row=1, col=1, secondary_y=False)
                
                # --- 下半部分：成交量柱状图 ---
                if 'Volume' in plot_df.columns:
                    colors = ['#ff3333' if (i == 0 or plot_df['Price'].iloc[i] >= plot_df['Price'].iloc[i-1]) else '#00cc66' 
                              for i in range(len(plot_df))]
                    fig.add_trace(
                        go.Bar(x=plot_df['Time'], y=plot_df['Volume'], name='成交量', marker_color=colors, opacity=0.8),
                        row=2, col=1, secondary_y=False
                    )
                
                # --- 坐标轴与全局样式优化 ---
                # 主价格 Y轴
                fig.update_yaxes(range=[y_min, y_max], showgrid=True, gridcolor='rgba(0,0,0,0.05)', zeroline=False, row=1, col=1, secondary_y=False)
                # 副涨跌幅 Y轴
                fig.update_yaxes(range=[pct_min, pct_max], tickformat=".2f", ticksuffix="%", showgrid=False, zeroline=False, row=1, col=1, secondary_y=True)
                # X轴 (分类轴自动无缝对接上午下午，消除休市空挡)
                fig.update_xaxes(type='category', nticks=7, showgrid=True, gridcolor='rgba(0,0,0,0.05)')
                # 隐藏成交量 Y轴标签以保持清爽
                fig.update_yaxes(showticklabels=False, row=2, col=1)
                
                fig.update_layout(
                    height=400, margin=dict(l=5, r=5, t=10, b=5),
                    showlegend=False, hovermode='x unified',
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
                )
                
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                st.caption("注：已开启【同花顺专业视角】（黑色现价、橙色均价、双向对称基准轴）。")
            except Exception as e:
                # 降级处理
                st.line_chart(plot_df.set_index('Time')['Price'])
                st.caption(f"图表渲染回退至基础模式。({str(e)})")
        st.divider()
    
    # 修正 Markdown 渲染（确保加粗成功）
    cleaned_result = res['result'].replace('**"', ' **"').replace('"**', '"** ')
    st.markdown(cleaned_result)
    
    # --- 导出功能区域 (手动) ---
    st.markdown("#### 📥 导出与保存")
    exp_col1, exp_col2, exp_col3 = st.columns([1, 1, 2])
    
    # 实时生成内容，不写盘
    md_content = exporter.generate_markdown(res['name'], res['code'], res['result'])
    pdf_bytes = exporter.generate_pdf(res['name'], res['code'], res['result'])
    filename_base = f"Report_{res['name']}_{res['code']}"
    
    if md_content:
        exp_col1.download_button("下载 Markdown", md_content, f"{filename_base}.md", "text/markdown", key="dl_md")
    if pdf_bytes:
        exp_col2.download_button("下载 PDF 报告", pdf_bytes, f"{filename_base}.pdf", "application/pdf", key="dl_pdf")

    if st.button("扫清结果，重新诊断", key="btn_clear_stock"):
        st.session_state['last_analysis'] = None
        st.rerun()
    st.divider()

if st.button("开始诊断", key="btn_stock"):
    if not query.strip():
        st.warning("请输入有效的股票代码或名称！")
    else:
        try:
            st.session_state['last_analysis'] = None
            with st.status(f"正在诊断: {query}...", expanded=True) as status:
                st.write("1. 正在检索股票代码...")
                code, name = fetcher.get_stock_name_or_code(query)
                
                if not code:
                    status.update(label="未找到该股票", state="error")
                    st.error(f"未找到与 '{query}' 相关的股票，请检查输入。")
                else:
                    st.write(f"已锁定股票: **{name} ({code})**")
                    st.write("2. 正在启动『三级防线』实时抓取引擎...")
                    plot_df = fetcher.get_intraday_plot_data(code)
                    spot = fetcher._get_bulletproof_spot(code)
                    
                    if spot:
                        st.subheader(f"📈 {name} 实盘分时脉搏 (1分钟线)")
                        col1, col2, col3, col4 = st.columns(4)
                        # delta_color="inverse" 实现红涨绿跌 (A股标准)
                        col1.metric("当前价", f"{spot['price']:.2f}", f"{spot['change_pct']:.2f}%", delta_color="inverse")
                        col2.metric("今日最高", f"{spot['high']:.2f}")
                        col3.metric("今日最低", f"{spot['low']:.2f}")
                        col4.metric("成交量", f"{int(spot['volume'])}")
                        
                        if not plot_df.empty:
                            st.line_chart(plot_df.set_index('Time')['Price'], color="#ff4b4b" if spot['change_pct'] > 0 else "#28a745")
                            st.caption("注：分时图由 1 分钟 OHLC 聚合生成，颜色随涨跌实时切换（红涨绿跌）。")
                    
                    st.write("3. 正在生成深度分析上下文...")
                    _, _, data_ctx = fetcher.get_full_analysis_context(code)
                    
                    st.write(f"4. 正在呼叫 {analyzer.provider.upper()} 进行多维度『实战级』推演...")
                    analysis_result = analyzer.analyze(data_ctx)
                    
                    # Save result to session state for persistence
                    st.session_state['last_analysis'] = {
                        'name': name,
                        'code': code,
                        'result': analysis_result,
                        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'spot': spot,
                        'plot_df': plot_df
                    }
                    
                    status.update(label="诊断完成！", state="complete")
                    st.rerun() # Refresh to show result from persisted state
        except Exception as e:
            st.error(f"⚠️ 诊断中断或出错: {str(e)}")
