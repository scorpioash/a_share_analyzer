import streamlit as st
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

# --- 注入视觉与监控 ---
inject_premium_style()

# 初始化组件（Analyzer 不进入 session_state 以便实时响应首页 API 修改）
if 'fetcher' not in st.session_state:
    st.session_state['fetcher'] = AShareDataFetcher()

fetcher = st.session_state['fetcher']
analyzer = LLMAnalyzer() # 实时读取最新配置

# 渲染侧边栏市场心跳仪表盘
render_market_monitor(fetcher)

st.title("🔍 智能诊股")
st.markdown("通过名字或代码输入，结合本地 `my_strategy.md` 经验，让大模型为你深度诊股。")

query = st.text_input("🔍 请输入 A 股代码或名称 (例如：贵州茅台，或 600519)", "", key="stock_query")
extra_stock_notes = st.text_area("💡 附加经验/想法（可选）", placeholder="例如：我觉得这只票最近放量滞涨，主力可能在出货...", height=80, key="stock_notes")

# --- State Preservation Logic ---
if 'last_analysis' not in st.session_state:
    st.session_state['last_analysis'] = None

# If we have a stored analysis, display it immediately
if st.session_state['last_analysis']:
    res = st.session_state['last_analysis']
    # Removed the success message as requested
    st.markdown(f"### 🎯 【{res['name']} - {res['code']}】诊断报告")
    st.caption(f"🕒 本报告生成于: {res.get('timestamp', '未知时间')}")
    st.markdown(res['result'])
    if st.button("🧹 清除报告并重新诊断", key="btn_clear_stock"):
        st.session_state['last_analysis'] = None
        st.rerun()
    st.divider()

if st.button("开始诊断", key="btn_stock"):
    if not query.strip():
        st.warning("请输入有效的股票代码或名称！")
    else:
        try:
            # Clear previous result while running
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
                    # 1. 抓取分时绘图数据
                    plot_df = fetcher.get_intraday_plot_data(code)
                    # 2. 抓取实盘核心指标 (用于 UI 展示)
                    spot = fetcher._get_bulletproof_spot(code)
                    
                    if spot:
                        # 在状态栏内展示实时仪表盘，增加可见性
                        st.subheader(f"📈 {name} 实盘分时脉搏 (1分钟线)")
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("当前价", f"{spot['price']:.2f}", f"{spot['change_pct']:.2f}%")
                        col2.metric("今日最高", f"{spot['high']:.2f}")
                        col3.metric("今日最低", f"{spot['low']:.2f}")
                        col4.metric("成交量", f"{int(spot['volume'])}")
                        
                        if not plot_df.empty:
                            st.line_chart(plot_df.set_index('Time')['Price'], color="#00ffcc")
                            st.caption("注：分时图由 1 分钟 OHLC 聚合生成，确保捕捉日内极致脉冲。")
                    
                    st.write("3. 正在生成深度分析上下文...")
                    _, _, data_ctx = fetcher.get_full_analysis_context(code)
                    
                    # 追加用户临时输入的经验
                    if extra_stock_notes.strip():
                        data_ctx += f"\n\n## 11. 用户附加的个人判断与经验\n{extra_stock_notes.strip()}\n"
                    
                    st.write(f"4. 正在呼叫 {analyzer.provider.upper()} 进行多维度『实战级』推演...")
                    analysis_result = analyzer.analyze(data_ctx)
                    
                    # Save result to session state for persistence
                    st.session_state['last_analysis'] = {
                        'name': name,
                        'code': code,
                        'result': analysis_result,
                        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    status.update(label="诊断完成！", state="complete")
                    st.rerun() # Refresh to show result from persisted state
        except Exception as e:
            st.error(f"⚠️ 诊断中断或出错: {str(e)}")
