import streamlit as st
# Force Reload: v2.0 - Updated with manual PDF/MD export support
import os
import sys

# 注入根目录路径
sys.path.append(os.path.abspath("."))

from data_fetcher import AShareDataFetcher
from llm_analyzer import LLMAnalyzer
from visual_style import inject_premium_style, show_error_clean
from market_monitor import render_market_monitor
from report_exporter import ReportExporter

# --- 注入视觉与监控 ---
inject_premium_style()

# Initialize components
if 'fetcher' not in st.session_state:
    st.session_state['fetcher'] = AShareDataFetcher()

fetcher = st.session_state['fetcher']
analyzer = LLMAnalyzer() 
exporter = ReportExporter()

# 渲染侧边栏市场心跳仪表盘
render_market_monitor(fetcher)

st.title("📊 板块分析")
st.markdown("输入板块关键词，结合您的个性化铁律进行深度拆解。如需调整板块分析准则，请前往左侧 **[📋 策略配置]** 界面。")

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
    options = [f"{r['name']} ({r['type']})" for r in results]
    selected_idx = st.selectbox("选择要诊断的板块：", range(len(options)), format_func=lambda i: options[i], key="board_select")
    selected = results[selected_idx]
    
    extra_board_notes = st.text_area("💡 附加经验/想法（可选）", placeholder="例如：我认为商业航天最近受政策催化，重点关注火箭发射相关...", height=80, key="board_notes")
    enable_sub = st.checkbox("🔬 开启子板块深度拆解", value=True, key="enable_sub_board")
    
    # --- State Preservation Logic ---
    if 'last_board_analysis' not in st.session_state:
        st.session_state['last_board_analysis'] = None

    # 展示结果
    if st.session_state['last_board_analysis']:
        res = st.session_state['last_board_analysis']
        st.markdown(f"### 🎯 【{res['name']} - {res['type']}】深度诊断报告")
        
        # 修正 Markdown 渲染（确保加粗成功）
        cleaned_result = res['result'].replace('**"', ' **"').replace('"**', '"** ')
        st.markdown(cleaned_result)
        
        # --- 导出功能区域 (手动) ---
        st.markdown("#### 📥 导出与保存")
        exp_col1, exp_col2, exp_col3 = st.columns([1, 1, 2])
        
        # 实时生成内容，不写盘
        md_content = exporter.generate_markdown(res['name'], res['type'], res['result'])
        pdf_bytes = exporter.generate_pdf(res['name'], res['type'], res['result'])
        filename_base = f"Report_{res['name']}_{res['type']}"
        
        if md_content:
            exp_col1.download_button("下载 Markdown", md_content, f"{filename_base}.md", "text/markdown", key="dl_md_board")
        if pdf_bytes:
            exp_col2.download_button("下载 PDF 报告", pdf_bytes, f"{filename_base}.pdf", "application/pdf", key="dl_pdf_board")

        if st.button("🧹 清除诊断结果", key="btn_clear_analysis"):
            st.session_state['last_board_analysis'] = None
            st.rerun()
        st.divider()

    if st.button("🚀 开始板块诊断", key="btn_board_analyze"):
        try:
            board_name = selected['name']
            board_type = selected['type']
            st.session_state['last_board_analysis'] = None
            
            with st.status(f"正在诊断板块: {board_name}...", expanded=True) as status:
                st.write(f"1. 已锁定: **{board_name}** ({board_type})")
                sub_boards = None
                if enable_sub:
                    st.write("2. 正在挖掘关联子板块...")
                    sub_boards = fetcher.find_related_sub_boards(board_name)
                
                st.write("3. 正在拉取核心数据...")
                data_ctx = fetcher.get_board_analysis_context(board_name, board_type, sub_boards)
                if extra_board_notes.strip():
                    data_ctx += f"\n\n## 用户附加的个人判断与经验\n{extra_board_notes.strip()}\n"
                
                st.write("4. 正在呼叫模型进行推理...")
                analysis_result = analyzer.analyze_board(data_ctx, board_name)
                
                st.session_state['last_board_analysis'] = {
                    'name': board_name,
                    'type': board_type,
                    'result': analysis_result
                }
                status.update(label="板块诊断完成！", state="complete")
                st.rerun()
        except Exception as e:
            show_error_clean(f"板块分析中断: {str(e)}")
