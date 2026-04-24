import streamlit as st
import os
import dotenv
from data_fetcher import AShareDataFetcher
from llm_analyzer import LLMAnalyzer
from visual_style import inject_premium_style, show_error_clean
from market_monitor import render_market_monitor

dotenv.load_dotenv()

st.set_page_config(page_title="A 股智能助手", layout="centered", page_icon="📈")

# 注入 Premium 视觉与报错降噪
inject_premium_style()

# ============== 顶部 Header 区域：极致对称布局 ==============
# 使用 [1.5, 7, 1.5] 布局实现标题绝对居中，同时两翼对等
spacer_l, col_main, col_opt = st.columns([1.5, 7, 1.5])

with col_main:
    # 强制标题与下方的介绍文字在视觉中轴线上对齐 - 极致压缩版
    st.markdown("""
        <div style="text-align: center; margin-bottom: 0.5rem;">
            <h1 style="margin-bottom: 0px; font-size: 2.6rem;">A 股智能助手</h1>
            <p style="color: rgba(0,0,0,0.7); font-size: 1rem; margin-top: 5px; line-height: 1.4;">
                覆盖 <b>行情 · 资金 · 板块 · 基本面 · 资讯 · 情绪</b> 六大维度，<br>
                辅助 AI 深度推演，打造一站式投研决策中枢。
            </p>
        </div>
    """, unsafe_allow_html=True)

with col_opt:
    # API 配置按钮 - 配合 CSS 锁定为横向长宽
    with st.popover("⚙️ API 配置"):
        st.markdown("### 🔑 AI 驱动核心配置")
        st.caption("在此处的修改将实时保存并生效。")
        
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        current_provider = os.getenv("LLM_PROVIDER", "openai").lower()
        
        provider_options = {
            "openai": "ChatGPT (OpenAI)",
            "anthropic": "Claude (Anthropic)",
            "gemini": "Gemini (Google)",
            "custom": "自定义 (OpenAI 协议)"
        }
        
        provider_keys = list(provider_options.keys())
        provider_idx = provider_keys.index(current_provider) if current_provider in provider_keys else 0
            
        new_provider = st.selectbox("选择驱动引擎", provider_keys, index=provider_idx, format_func=lambda x: provider_options[x])
        
        if new_provider == "openai":
            new_api_key = st.text_input("OpenAI API KEY:", value=os.getenv("OPENAI_API_KEY", ""), type="password")
            new_base_url = st.text_input("API Base URL:", value=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
            new_model = st.text_input("模型名:", value=os.getenv("OPENAI_MODEL", "gpt-4o"))
        elif new_provider == "anthropic":
            new_api_key = st.text_input("Anthropic API KEY:", value=os.getenv("ANTHROPIC_API_KEY", ""), type="password")
            new_model = st.text_input("模型名:", value=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"))
        elif new_provider == "gemini":
            new_api_key = st.text_input("Gemini API KEY:", value=os.getenv("GEMINI_API_KEY", ""), type="password")
            new_model = st.text_input("模型名:", value=os.getenv("GEMINI_MODEL", "gemini-1.5-pro"))
        else: # custom
            new_api_key = st.text_input("API KEY:", value=os.getenv("OPENAI_API_KEY", ""), type="password")
            new_base_url = st.text_input("自定义 API URL:", value=os.getenv("OPENAI_BASE_URL", ""))
            new_model = st.text_input("模型名:", value=os.getenv("OPENAI_MODEL", ""))

        if st.button("💾 保存配置并重载", use_container_width=True):
            if not os.path.exists(env_path):
                with open(env_path, 'w') as f: f.write("")
            dotenv.set_key(env_path, "LLM_PROVIDER", new_provider)
            if new_provider in ["openai", "custom"]:
                dotenv.set_key(env_path, "OPENAI_API_KEY", new_api_key)
                dotenv.set_key(env_path, "OPENAI_BASE_URL", new_base_url if new_provider == "custom" else "https://api.openai.com/v1")
                dotenv.set_key(env_path, "OPENAI_MODEL", new_model)
            elif new_provider == "anthropic":
                dotenv.set_key(env_path, "ANTHROPIC_API_KEY", new_api_key)
                dotenv.set_key(env_path, "ANTHROPIC_MODEL", new_model)
            elif new_provider == "gemini":
                dotenv.set_key(env_path, "GEMINI_API_KEY", new_api_key)
                dotenv.set_key(env_path, "GEMINI_MODEL", new_model)
            
            dotenv.load_dotenv(override=True)
            st.session_state['api_saved'] = True
            st.rerun()

# 处理刚刚保存配置的 Toast 提示
if st.session_state.get('api_saved', False):
    st.toast("✅ API 配置已保存", icon="💾")
    st.session_state['api_saved'] = False

# ============== 初始化业务组件 ==============
st.sidebar.header("🧭 功能导航")

analyzer = LLMAnalyzer()

st.sidebar.markdown(f'<div class="model-status-box">当前启用的底层模型: {analyzer.provider.upper()}</div>', unsafe_allow_html=True)

# ============== 主界面：首页功能矩阵 ==============
st.markdown("---")

# ============== 功能导航：一体化卡片化矩阵 ==============
st.markdown('<div class="card-grid">', unsafe_allow_html=True)

# 第一排
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("##### 🔍 智能诊股")
    st.markdown("<p class='card-desc'>输入股票代码或名称，AI 结合策略研判，输出全维度诊断报告。</p>", unsafe_allow_html=True)
    st.page_link("pages/1_🔍_智能诊股.py", label="进入诊股", icon="🔍")

with col2:
    st.markdown("##### 📊 板块分析")
    st.markdown("<p class='card-desc'>挖掘行业与概念板块轮动机会，深度拆解细分领头羊与资金逻辑。</p>", unsafe_allow_html=True)
    st.page_link("pages/2_📊_板块分析.py", label="进入板块", icon="📊")

with col3:
    st.markdown("##### 📈 行情中心")
    st.markdown("<p class='card-desc'>沪深主板/创业板/科创板/北交所全市场实时行情，自适应排序。</p>", unsafe_allow_html=True)
    st.page_link("pages/3_📈_行情中心.py", label="查看行情", icon="📈")

st.markdown("<div style='margin-bottom: 30px;'></div>", unsafe_allow_html=True)

# 第二排
col4, col5, col6 = st.columns(3)
with col4:
    st.markdown("##### 🔥 盘口异动")
    st.markdown("<p class='card-desc'>监控涨跌停股池、盘中火箭发射、大笔成交等极端异常信号。</p>", unsafe_allow_html=True)
    st.page_link("pages/4_🔥_盘口异动.py", label="捕捉异动", icon="🔥")

with col5:
    st.markdown("##### 🐉 龙虎榜")
    st.markdown("<p class='card-desc'>深度跟踪游资席位席位、机构资金净买入及其持续性动向。</p>", unsafe_allow_html=True)
    st.page_link("pages/7_🐉_龙虎榜与资金流.py", label="查看龙虎榜", icon="🐉")

with col6:
    st.markdown("##### 🌡️ 市场情绪")
    st.markdown("<p class='card-desc'>整合赚钱效应、散户关注度与多空温度计，判断大盘冰点。</p>", unsafe_allow_html=True)
    st.page_link("pages/10_🌡️_市场情绪与热度.py", label="感知情绪", icon="🌡️")

st.markdown('</div>', unsafe_allow_html=True) # 关闭 card-grid

st.markdown("---")
st.caption("⚠️ 免责声明：本系统所有的行情推演及 AI 回复仅作为技术测试与个人逻辑复盘，不构成任何投资建议。股市有风险，交易需谨慎！")
