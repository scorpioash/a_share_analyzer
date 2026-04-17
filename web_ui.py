import streamlit as st
import os
import dotenv
from data_fetcher import AShareDataFetcher
from llm_analyzer import LLMAnalyzer

dotenv.load_dotenv()

st.set_page_config(page_title="极简 A 股智能分析器", layout="centered", page_icon="📈")

st.title("📈 极简 A 股智能分析器")
st.markdown("通过名字或代码输入，结合本地 `my_strategy.md` 经验，让大模型为你深度诊股。")

# 初始化组件
@st.cache_resource
def get_fetcher():
    return AShareDataFetcher()

fetcher = get_fetcher()

# ============== 左侧栏：全局配置面板 ==============
st.sidebar.header("⚙️ 引擎配置面板")
env_path = os.path.join(os.path.dirname(__file__), ".env")

with st.sidebar.expander("🔑 快捷配置 API"):
    st.info("在此处的修改将实时保存并生效。")
    # 读取当前装载的环境变量
    current_provider = os.getenv("LLM_PROVIDER", "openai").lower()
    provider_options = ["openai", "deepseek", "anthropic", "gemini"]
    try:
        provider_idx = provider_options.index(current_provider)
    except ValueError:
        provider_idx = 0
        
    new_provider = st.selectbox("选择驱动引擎", provider_options, index=provider_idx)
    
    # 动态显示对应平台的必填字段
    if new_provider in ["openai", "deepseek"]:
        new_api_key = st.text_input("API KEY:", value=os.getenv("OPENAI_API_KEY", ""), type="password")
        new_base_url = st.text_input("Base URL (可选):", value=os.getenv("OPENAI_BASE_URL", ""))
        new_model = st.text_input("模型名:", value=os.getenv("OPENAI_MODEL", "gpt-4o"))
    elif new_provider == "anthropic":
        new_api_key = st.text_input("API KEY:", value=os.getenv("ANTHROPIC_API_KEY", ""), type="password")
        new_base_url = ""
        new_model = st.text_input("模型名:", value=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"))
    else:
        new_api_key = st.text_input("API KEY:", value=os.getenv("GEMINI_API_KEY", ""), type="password")
        new_base_url = ""
        new_model = st.text_input("模型名:", value=os.getenv("GEMINI_MODEL", "gemini-1.5-pro"))

    if st.button("保存配置并重载"):
        if not os.path.exists(env_path):
            open(env_path, 'w').close()
            
        dotenv.set_key(env_path, "LLM_PROVIDER", new_provider)
        
        if new_provider in ["openai", "deepseek"]:
            dotenv.set_key(env_path, "OPENAI_API_KEY", new_api_key)
            dotenv.set_key(env_path, "OPENAI_BASE_URL", new_base_url)
            dotenv.set_key(env_path, "OPENAI_MODEL", new_model)
        elif new_provider == "anthropic":
            dotenv.set_key(env_path, "ANTHROPIC_API_KEY", new_api_key)
            dotenv.set_key(env_path, "ANTHROPIC_MODEL", new_model)
        else:
            dotenv.set_key(env_path, "GEMINI_API_KEY", new_api_key)
            dotenv.set_key(env_path, "GEMINI_MODEL", new_model)
            
        # 强制重载环境变量
        dotenv.load_dotenv(override=True)
        st.success("配置已更新！")
        st.rerun()

# 加载分析器 (会在每次重载环境变量后使用最新的配置)
analyzer = LLMAnalyzer()

st.sidebar.info(f"当前启用的底层模型: **{analyzer.provider.upper()}**")

current_strategy = analyzer._load_strategy()
with st.sidebar.expander("👀 查看当前注入的经验/策略"):
    st.markdown(current_strategy)

# ============== 主界面：诊股交互 ==============
query = st.text_input("🔍 请输入 A 股代码或名称 (例如：贵州茅台，或 600519)", "")

if st.button("开始诊断"):
    if not query.strip():
        st.warning("请输入有效的股票代码或名称！")
    else:
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
                
                st.write(f"3. 数据获取成功，正在呼叫 {analyzer.provider.upper()} 根据经验进行深度推演...")
                analysis_result = analyzer.analyze(data_ctx)
                
                status.update(label="诊断完成！", state="complete")
        
        st.success("分析报告已生成：")
        st.markdown(f"### 【{name} - {code}】")
        st.markdown(analysis_result)
