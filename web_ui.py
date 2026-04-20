import streamlit as st
import os
import dotenv
from data_fetcher import AShareDataFetcher
from llm_analyzer import LLMAnalyzer

dotenv.load_dotenv()

st.set_page_config(page_title="极简 A 股智能分析器", layout="centered", page_icon="📈")

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

st.title("📈 极简 A 股智能分析器")
st.markdown("通过名字或代码输入，结合本地 `my_strategy.md` 经验，让大模型为你深度诊股。")

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
    provider_options = ["openai", "deepseek", "anthropic", "gemini"]
    try:
        provider_idx = provider_options.index(current_provider)
    except ValueError:
        provider_idx = 0
        
    new_provider = st.selectbox("选择驱动引擎", provider_options, index=provider_idx)
    
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
            
        dotenv.load_dotenv(override=True)
        st.success("配置已更新！")
        st.rerun()

analyzer = LLMAnalyzer()

st.sidebar.info(f"当前启用的底层模型: **{analyzer.provider.upper()}**")

current_strategy = analyzer._load_strategy()
with st.sidebar.expander("👀 查看个股分析策略 (my_strategy.md)"):
    st.markdown(current_strategy)

board_strategy = analyzer._load_board_strategy()
with st.sidebar.expander("👀 查看板块分析策略 (my_board_strategy.md)"):
    st.markdown(board_strategy)

# ============== 主界面：Tab 切换 ==============
tab_stock, tab_board = st.tabs(["🔍 个股诊断", "📊 板块分析"])

# ============== Tab 1: 个股诊断 ==============
with tab_stock:
    query = st.text_input("🔍 请输入 A 股代码或名称 (例如：贵州茅台，或 600519)", "", key="stock_query")
    extra_stock_notes = st.text_area("💡 附加经验/想法（可选）", placeholder="例如：我觉得这只票最近放量滞涨，主力可能在出货...", height=80, key="stock_notes")

    if st.button("开始诊断", key="btn_stock"):
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
                    
                    # 追加用户临时输入的经验
                    if extra_stock_notes.strip():
                        data_ctx += f"\n\n## 4. 用户附加的个人判断与经验\n{extra_stock_notes.strip()}\n"
                    
                    st.write(f"3. 数据获取成功，正在呼叫 {analyzer.provider.upper()} 根据经验进行深度推演...")
                    analysis_result = analyzer.analyze(data_ctx)
                    
                    status.update(label="诊断完成！", state="complete")
            
            st.success("分析报告已生成：")
            st.markdown(f"### 【{name} - {code}】")
            st.markdown(analysis_result)

# ============== Tab 2: 板块分析（含子板块拆解推理） ==============
with tab_board:
    st.markdown("输入板块关键词（如：**半导体**、**白酒**、**商业航天**），系统将自动搜索匹配的行业与概念板块，并挖掘关联的细分子板块进行拆解推理。")
    
    board_query = st.text_input("🏷️ 请输入板块关键词", "", key="board_query")

    if st.button("搜索板块", key="btn_board_search"):
        if not board_query.strip():
            st.warning("请输入有效的板块关键词！")
        else:
            with st.spinner("正在搜索相关板块..."):
                results = fetcher.search_board(board_query)
            
            if not results:
                st.error(f"未找到与 '{board_query}' 匹配的板块，请换个关键词试试。")
            else:
                st.session_state['board_results'] = results
                st.success(f"共找到 {len(results)} 个匹配板块：")
    
    # 展示搜索结果并提供诊断按钮
    if 'board_results' in st.session_state and st.session_state['board_results']:
        results = st.session_state['board_results']
        
        options = [f"{r['name']} ({r['type']}) | 涨跌幅: {r['change_pct']}%" for r in results]
        selected_idx = st.selectbox("选择要诊断的板块：", range(len(options)), format_func=lambda i: options[i], key="board_select")
        
        selected = results[selected_idx]
        
        extra_board_notes = st.text_area("💡 附加经验/想法（可选）", placeholder="例如：我认为商业航天最近受政策催化，重点关注火箭发射相关...", height=80, key="board_notes")
        
        # 子板块深度拆解开关
        enable_sub = st.checkbox("🔬 开启子板块深度拆解（耗时较长，但能发现细分机会）", value=True, key="enable_sub_board")
        
        if st.button("🚀 开始板块诊断", key="btn_board_analyze"):
            board_name = selected['name']
            board_type = selected['type']
            
            with st.status(f"正在诊断板块: {board_name}...", expanded=True) as status:
                st.write(f"1. 已锁定: **{board_name}** ({board_type})")
                
                sub_boards = None
                if enable_sub:
                    st.write("2. 正在通过成分股交叉分析，挖掘关联子板块...")
                    sub_boards = fetcher.find_related_sub_boards(board_name)
                    if sub_boards:
                        st.write(f"   ✅ 发现 **{len(sub_boards)}** 个关联细分子板块：")
                        for sb in sub_boards:
                            st.write(f"   - {sb['name']} (重叠 {sb['overlap_count']} 只股票, {sb['overlap_ratio']})")
                    else:
                        st.write("   ⚠️ 未发现明显的细分子板块关联，将仅分析主板块。")
                
                st.write("3. 正在拉取板块历史走势与成分股数据...")
                data_ctx = fetcher.get_board_analysis_context(board_name, board_type, sub_boards)
                
                # 追加用户临时输入的经验
                if extra_board_notes.strip():
                    data_ctx += f"\n\n## 用户附加的个人判断与经验\n{extra_board_notes.strip()}\n"
                
                st.write(f"4. 数据就绪，正在呼叫 {analyzer.provider.upper()} 进行板块拆解推理...")
                analysis_result = analyzer.analyze_board(data_ctx, board_name)
                
                status.update(label="板块诊断完成！", state="complete")
            
            st.success("板块分析报告已生成：")
            st.markdown(f"### 【{board_name} - {board_type}】")
            st.markdown(analysis_result)
