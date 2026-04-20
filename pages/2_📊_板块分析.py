import streamlit as st
from data_fetcher import AShareDataFetcher
from llm_analyzer import LLMAnalyzer

# Initialize components
if 'fetcher' not in st.session_state:
    st.session_state['fetcher'] = AShareDataFetcher()
if 'analyzer' not in st.session_state:
    st.session_state['analyzer'] = LLMAnalyzer()

fetcher = st.session_state['fetcher']
analyzer = st.session_state['analyzer']

st.title("📊 板块分析")
st.markdown("输入板块关键词，结合本地 `my_board_strategy.md` 经验，自动搜索行业与概念板块并挖掘细分子板块进行拆解推理。")

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
