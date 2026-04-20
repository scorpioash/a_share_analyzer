import streamlit as st
import os
import sys

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
    st.success("恢复上次诊断报告：")
    st.markdown(f"### 【{res['name']} - {res['code']}】")
    st.markdown(res['result'])
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
                    
                    st.write("2. 正在实时拉取 K 线与基本面数据...")
                    _, _, data_ctx = fetcher.get_full_analysis_context(code)
                    
                    # 追加用户临时输入的经验
                    if extra_stock_notes.strip():
                        data_ctx += f"\n\n## 11. 用户附加的个人判断与经验\n{extra_stock_notes.strip()}\n"
                    
                    st.write(f"3. 数据获取成功，正在呼叫 {analyzer.provider.upper()} 根据经验进行深度推演...")
                    analysis_result = analyzer.analyze(data_ctx)
                    
                    # Save result to session state for persistence
                    st.session_state['last_analysis'] = {
                        'name': name,
                        'code': code,
                        'result': analysis_result
                    }
                    
                    status.update(label="诊断完成！", state="complete")
                    st.rerun() # Trigger fresh rerun to update UI with cached state
        except Exception as e:
            st.error(f"⚠️ 诊断中断或出错: {str(e)}")
