import streamlit as st
import os

# 页面配置
st.set_page_config(
    page_title="策略配置中心",
    page_icon="📋",
    layout="wide"
)

# 样式美化
st.markdown("""
    <style>
    .main {
        background-color: #f5f7f9;
    }
    .stTextArea textarea {
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 14px;
        line-height: 1.5;
        border-radius: 10px;
        border: 1px solid #d1d9e6;
        padding: 15px;
        background-color: #ffffff;
    }
    .header-box {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        padding: 20px;
        border-radius: 15px;
        margin-bottom: 25px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    </style>
""", unsafe_allow_html=True)

# 标题
st.markdown("""
    <div class="header-box">
        <h1 style='margin:0; font-size: 24px;'>📋 策略配置中心</h1>
        <p style='margin:5px 0 0 0; opacity:0.8;'>自定义 AI 分析助理的“灵魂”和“铁律”</p>
    </div>
""", unsafe_allow_html=True)

# 策略文件映射
STRATEGY_MAP = {
    "🔍 个股诊断策略": "my_strategy.md",
    "📊 板块分析策略": "my_board_strategy.md"
}

def load_strategy(filename):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    return f"# {filename} 策略文件\n\n在此输入您的策略逻辑..."

def save_strategy(filename, content):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        st.error(f"保存失败: {e}")
        return False

# 使用 Tab 切换不同策略
tab1, tab2 = st.tabs(["🔍 个股策略配置", "📊 板块策略配置"])

with tab1:
    filename = STRATEGY_MAP["🔍 个股诊断策略"]
    st.markdown(f"### 📝 编辑个股诊断核心策略 (`{filename}`)")
    content = load_strategy(filename)
    new_content = st.text_area("个股策略内容", value=content, height=500, key="stock_strat", label_visibility="collapsed")
    
    if st.button("💾 保存个股策略", type="primary", key="save_stock"):
        if save_strategy(filename, new_content):
            st.success("个股策略已更新！")
            st.balloons()

with tab2:
    filename = STRATEGY_MAP["📊 板块分析策略"]
    st.markdown(f"### 📝 编辑板块分析核心策略 (`{filename}`)")
    content = load_strategy(filename)
    new_content = st.text_area("板块策略内容", value=content, height=500, key="board_strat", label_visibility="collapsed")
    
    if st.button("💾 保存板块策略", type="primary", key="save_board"):
        if save_strategy(filename, new_content):
            st.success("板块策略已更新！")
            st.balloons()

st.divider()
st.info("💡 修改并保存后，相应功能的 AI 分析将立即采用最新的策略规则。")
