import streamlit as st

def inject_premium_style():
    """注入全站 Premium 视觉样式"""
    st.markdown("""
        <style>
        /* 全局字体与平滑度 */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }

        /* 强力压缩顶部空白，整体上移 */
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 1rem !important;
        }

        /* 侧边栏主体 */
        [data-testid="stSidebar"] {
            background-color: rgba(26, 32, 44, 1);
            border-right: 1px solid rgba(255, 215, 0, 0.15);
        }

        /* 一体化卡片矩阵核心样式 - 压缩版 */
        .card-grid [data-testid="stHorizontalBlock"] [data-testid="column"] {
            background: rgba(255, 255, 255, 0.035) !important;
            border: 1px solid rgba(212, 175, 55, 0.15) !important;
            border-radius: 16px !important;
            padding: 12px 10px !important;
            text-align: center !important;
            min-height: 190px !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: space-between !important;
            transition: transform 0.2s ease, box-shadow 0.2s ease, background-color 0.2s ease !important;
        }
        
        /* 侧边栏整体文字高亮补丁 */
        [data-testid="stSidebar"] h1, 
        [data-testid="stSidebar"] h2, 
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] summary {
            color: #FFFFFF !important;
            opacity: 1 !important;
        }
        
        /* 特殊处理折叠面板 (Expander) 的表头文字 */
        [data-testid="stSidebar"] [data-testid="stExpander"] summary p {
            color: #FFFFFF !important;
        }
        
        /* 确保输入框内的文字清晰可见（暗色文字在白底上） */
        [data-testid="stSidebar"] input, 
        [data-testid="stSidebar"] select, 
        [data-testid="stSidebar"] textarea {
            color: #1A202C !important;
            font-weight: 600 !important;
        }

        /* 底部“当前启用模型”提示框强化 */
        .model-status-box {
            background-color: rgba(255, 255, 255, 0.05) !important;
            border: 1px solid rgba(212, 175, 55, 0.5) !important;
            padding: 10px;
            border-radius: 8px;
            color: #D4AF37 !important;
            font-weight: bold;
            text-align: center;
        }

        /* 侧边栏导航链接 */
        [data-testid="stSidebarNav"] * {
            color: #E0E0E0 !important;
        }
        [data-testid="stSidebarNav"] .css-17l29f0 {
             color: #D4AF37 !important;
             font-weight: 800;
        }

        /* 卡片风格化 */
        .stMetric {
            background: rgba(255, 255, 255, 0.03);
            padding: 15px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            transition: transform 0.3s ease;
        }
        .stMetric:hover {
            transform: translateY(-5px);
            border: 1px solid rgba(212, 175, 55, 0.4);
        }

        /* AI 呼吸灯动效 */
        @keyframes breath {
            0% { box-shadow: 0 0 5px rgba(212, 175, 55, 0.2); }
            50% { box-shadow: 0 0 20px rgba(212, 175, 55, 0.6); }
            100% { box-shadow: 0 0 5px rgba(212, 175, 55, 0.2); }
        }
        .ai-thinking {
            animation: breath 2s infinite ease-in-out;
            border: 1px solid #D4AF37 !important;
            border-radius: 10px;
            padding: 10px;
            background: rgba(212, 175, 55, 0.05);
        }

        /* 隐藏 Streamlit 原生报错中的干扰链接 */
        .stException pre {
            /* display: none !important; */
        }
        .stException .css-1dp5vir {
            /* display: none !important; */
        }
        
        /* 针对最新版 streamlit 的降噪 */
        [data-testid="stException"] {
            background-color: #330000;
            color: #ff4b4b;
        }
        [data-testid="stException"] summary {
            display: none !important;
        }

        /* 极致汉化：屏蔽右上角与底部的英文原生组件 */
        .stDeployButton, [data-testid="stAppDeploy"], [data-testid="stStatusWidget"] {
            display: none !important;
        }
        #MainMenu, header[data-testid="stHeader"] {
            visibility: hidden !important;
            display: none !important;
        }
        footer {
            visibility: hidden !important;
        }
        button[title="View source"] {
            display: none !important;
        }

        /* 强力放大右上角 API 配置按钮 - 修正为横向不换行 */
        [data-testid="stPopover"] button {
            font-size: 1.25rem !important;
            font-weight: 900 !important;
            padding: 0.6rem 1.5rem !important;
            border: 2px solid rgba(212, 175, 55, 0.7) !important;
            background-color: rgba(212, 175, 55, 0.08) !important;
            color: #D4AF37 !important;
            border-radius: 12px !important;
            white-space: nowrap !important;
            min-width: 160px !important;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        [data-testid="stPopover"] button:hover {
            border: 2px solid rgba(212, 175, 55, 1) !important;
            background-color: rgba(212, 175, 55, 0.2) !important;
            box-shadow: 0 0 25px rgba(212, 175, 55, 0.3);
            transform: translateY(-2px);
        }

        /* 一体化卡片矩阵核心样式 */
        .card-grid [data-testid="stHorizontalBlock"] [data-testid="column"] {
            background: rgba(255, 255, 255, 0.035) !important;
            border: 1px solid rgba(212, 175, 55, 0.15) !important;
            border-radius: 16px !important;
            padding: 25px 15px !important;
            text-align: center !important;
            min-height: 230px !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: space-between !important;
            transition: transform 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275), box-shadow 0.2s ease, background 0.2s ease !important;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1) !important;
        }
        
        .card-grid [data-testid="column"]:hover {
            background: rgba(255, 255, 255, 0.08) !important;
            border: 1px solid rgba(212, 175, 55, 0.5) !important;
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.3), 0 0 20px rgba(212, 175, 55, 0.15) !important;
            transform: translateY(-10px) scale(1.02) !important;
        }

        .card-desc {
            color: #1A1A1A !important;
            font-size: 0.82rem !important;
            font-weight: 500 !important;
            margin-top: 5px !important;
            margin-bottom: 20px !important;
            line-height: 1.5 !important;
            min-height: 2.5rem !important;
        }

        /* 强制首页卡片链接入盒并居中 */
        .card-grid div.stPageLink {
            margin-top: auto !important;
            text-align: center !important;
            width: 100% !important;
        }
        .card-grid div.stPageLink button {
            width: 95% !important;
            margin: 0 auto !important;
            font-size: 0.85rem !important;
            background: rgba(212, 175, 55, 0.1) !important;
            border: 1px solid rgba(212, 175, 55, 0.3) !important;
        }
        .card-grid div.stPageLink button:hover {
            background: rgba(212, 175, 55, 0.25) !important;
            border: 1px solid #D4AF37 !important;
        }

        /* 标题区绝对对齐优化 - 压缩版 */
        .centered-header {
            text-align: center;
            margin-bottom: 1.5rem;
            width: 100%;
        }
        </style>
    """, unsafe_allow_html=True)

def show_error_clean(msg: str):
    """显示干净的错误信息，无堆栈干扰"""
    st.error(f"🔴 系统提示：{msg}")

def _color_positive_negative(val):
    import pandas as pd
    if not isinstance(val, (int, float)) or pd.isna(val):
        return ''
    if val > 0:
        return 'color: #ff3333; font-weight: bold;'  # 红涨
    elif val < 0:
        return 'color: #00cc66; font-weight: bold;'  # 绿跌
    return 'color: #888888;'

def _format_percentage(val):
    import pandas as pd
    if pd.isna(val):
        return ""
    if isinstance(val, (int, float)):
        return f"{val:.2f}%"
    return str(val)

def _format_price(val):
    import pandas as pd
    if pd.isna(val):
        return ""
    if isinstance(val, (int, float)):
        return f"{val:.2f}"
    return str(val)

def render_styled_dataframe(df, **kwargs):
    """全局统一的 DataFrame 渲染函数，自动格式化数值并标红标绿"""
    import pandas as pd
    if df is None or df.empty:
        st.dataframe(df, **kwargs)
        return
        
    df_clean = df.copy()
    
    # 识别需要处理的列
    # 涨跌幅类 (需要百分号 + 变色)
    pct_cols = [c for c in df_clean.columns if any(k in c for k in ['幅', '换手率', '比率', '溢价', '振幅'])]
    # 绝对值类 (需要变色，不加百分号)
    val_cols = [c for c in df_clean.columns if any(k in c for k in ['涨跌额', '净流入', '净额', '差额', '主力净'])]
    
    # 将需要处理的列尽可能转为数值型
    for c in pct_cols + val_cols:
        df_clean[c] = pd.to_numeric(df_clean[c], errors='coerce')
        
    # 定义 Styler
    styled_df = df_clean.style
    
    # 格式化百分比
    if pct_cols:
        styled_df = styled_df.format({c: _format_percentage for c in pct_cols})
        
    # 上色
    color_cols = [c for c in (pct_cols + val_cols) if df_clean[c].dtype in ['float64', 'int64']]
    if color_cols:
        if hasattr(styled_df, 'map'):
            styled_df = styled_df.map(_color_positive_negative, subset=color_cols)
        else:
            styled_df = styled_df.applymap(_color_positive_negative, subset=color_cols)
            
    st.dataframe(styled_df, **kwargs)
