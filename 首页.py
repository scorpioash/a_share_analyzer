import streamlit as st
import os
import dotenv
from data_fetcher import AShareDataFetcher
from llm_analyzer import LLMAnalyzer

dotenv.load_dotenv()

st.set_page_config(page_title="A股智能数据终端", layout="centered", page_icon="📈")

# 隐藏 Streamlit 报错信息下方的 "Copy / Ask Google / Ask ChatGPT" 链接
st.markdown("""
<style>
    .stException [data-testid="stMarkdownContainer"] a,
    .stAlert [data-testid="stMarkdownContainer"] a[href*="google"],
    .stAlert [data-testid="stMarkdownContainer"] a[href*="chatgpt"],
    div[class*="stException"] div[data-testid="stNotificationContentInfo"] ~ div,
    button[kind="minimal"][data-testid="stBaseButton-minimal"] {
        display: none !important;
    }
    /* 隐藏错误弹窗底部的操作栏 */
    .stException > div:last-child {
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏠 A 股智能数据终端 · 首页")

# 初始化组件
def get_fetcher():
    return AShareDataFetcher()

fetcher = get_fetcher()

# ============== 左侧栏：全局配置面板 ==============
st.sidebar.header("⚙️ 引擎配置面板")
env_path = os.path.join(os.path.dirname(__file__), ".env")

with st.sidebar.expander("🔑 快捷配置 API"):
    st.info("在此处的修改将实时保存并生效。")
    current_provider = os.getenv("LLM_PROVIDER", "openai").lower()
    
    # 用户要求：内置 Gemini, ChatGPT, Claude，其他改为自定义
    provider_options = {
        "openai": "ChatGPT (OpenAI)",
        "anthropic": "Claude (Anthropic)",
        "gemini": "Gemini (Google)",
        "custom": "自定义 (OpenAI 协议)"
    }
    
    provider_keys = list(provider_options.keys())
    try:
        provider_idx = provider_keys.index(current_provider) if current_provider in provider_keys else 0
    except ValueError:
        provider_idx = 0
        
    new_provider = st.selectbox("选择驱动引擎", provider_keys, index=provider_idx, format_func=lambda x: provider_options[x])
    
    # 根据不同厂商显示不同的输入框
    if new_provider == "openai":
        new_api_key = st.text_input("OpenAI API KEY:", value=os.getenv("OPENAI_API_KEY", ""), type="password")
        new_base_url = st.text_input("API Base URL:", value=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
        new_model = st.text_input("模型名:", value=os.getenv("OPENAI_MODEL", "gpt-4o"))
    elif new_provider == "anthropic":
        new_api_key = st.text_input("Anthropic API KEY:", value=os.getenv("ANTHROPIC_API_KEY", ""), type="password")
        new_base_url = "" # Anthropic 通常不自定义 URL
        new_model = st.text_input("模型名:", value=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"))
    elif new_provider == "gemini":
        new_api_key = st.text_input("Gemini API KEY:", value=os.getenv("GEMINI_API_KEY", ""), type="password")
        new_base_url = ""
        new_model = st.text_input("模型名:", value=os.getenv("GEMINI_MODEL", "gemini-1.5-pro"))
    else: # custom
        # 自定义模型强制要求输入 URL
        new_api_key = st.text_input("API KEY:", value=os.getenv("OPENAI_API_KEY", ""), type="password")
        new_base_url = st.text_input("自定义 API URL (例如: https://api.deepseek.com/v1):", value=os.getenv("OPENAI_BASE_URL", ""))
        new_model = st.text_input("模型名:", value=os.getenv("OPENAI_MODEL", ""))

    if st.button("保存配置并重载"):
        if not os.path.exists(env_path):
            with open(env_path, 'w') as f: f.write("")
            
        dotenv.set_key(env_path, "LLM_PROVIDER", new_provider)
        
        # 统一存储逻辑
        if new_provider in ["openai", "custom"]:
            dotenv.set_key(env_path, "OPENAI_API_KEY", new_api_key)
            dotenv.set_key(env_path, "OPENAI_BASE_URL", new_base_url)
            dotenv.set_key(env_path, "OPENAI_MODEL", new_model)
        elif new_provider == "anthropic":
            dotenv.set_key(env_path, "ANTHROPIC_API_KEY", new_api_key)
            dotenv.set_key(env_path, "ANTHROPIC_MODEL", new_model)
        elif new_provider == "gemini":
            dotenv.set_key(env_path, "GEMINI_API_KEY", new_api_key)
            dotenv.set_key(env_path, "GEMINI_MODEL", new_model)
            
        dotenv.load_dotenv(override=True)
        st.success("配置已更新！")
        st.rerun()

analyzer = LLMAnalyzer()

st.sidebar.info(f"当前启用的底层模型: **{analyzer.provider.upper()}**")

# ============== 主界面：首页 ==============
st.markdown("### 欢迎来到极简 A 股数据终端大本营")
st.markdown("通过左侧边栏导航，畅享从大盘行情到个股深度拆解的全套数据体系。")

st.info("👈 请点击左侧边栏的页面进行浏览。目前支持：\n- **智能诊股**：结合AI的个股级深度剖析\n- **板块分析**：结合AI的子板块拆解预判\n- 更多行情与基本面数据模块正在陆续开放...")

st.markdown("---")
st.markdown("#### 🚀 快速开始")
cola, colb = st.columns(2)
with cola:
    st.page_link("pages/1_🔍_智能诊股.py", label="体验智能诊股", icon="🔍")
with colb:
    st.page_link("pages/2_📊_板块分析.py", label="体验板块分析", icon="📊")
