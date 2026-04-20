import akshare as ak
import pandas as pd
import datetime
import os
import contextlib

@contextlib.contextmanager
def bypass_proxy():
    """临时隔离系统的全局代理环境变量，保护国内直连数据不被代理劫持打断"""
    proxy_keys = ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']
    saved = {}
    for k in proxy_keys:
        if k in os.environ:
            saved[k] = os.environ.pop(k)
    try:
        yield
    finally:
        for k, v in saved.items():
            os.environ[k] = v

class AShareDataFetcher:
    def __init__(self):
        pass

    def get_stock_name_or_code(self, query: str) -> tuple[str, str]:
        clean_query = query.lower().replace('sh', '').replace('sz', '').strip()
        try:
            with bypass_proxy():
                stock_info = ak.stock_info_a_code_name()
            if clean_query.isdigit():
                matched = stock_info[stock_info['code'] == clean_query]
                if not matched.empty:
                    return clean_query, matched.iloc[0]['name']
                return clean_query, "未知名称"
            else:
                matched = stock_info[stock_info['name'].str.contains(clean_query, na=False)]
                if not matched.empty:
                    return matched.iloc[0]['code'], matched.iloc[0]['name']
                return "", "未找到对应股票"
        except Exception as e:
            return clean_query, f"解析失败: {e}"

    def get_stock_name(self, code: str) -> str:
        code, name = self.get_stock_name_or_code(code)
        return name

    def get_daily_kline(self, code: str, limit: int = 30) -> str:
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            with bypass_proxy():
                df = ak.stock_zh_a_hist(symbol=clean_code, period="daily", adjust="qfq")
            if df.empty:
                return "暂无K线数据"
            
            df = df.tail(limit).copy()
            df['日期'] = pd.to_datetime(df['日期']).dt.strftime('%Y-%m-%d')
            df['MA5'] = df['收盘'].rolling(window=5, min_periods=1).mean().round(2)
            df['MA10'] = df['收盘'].rolling(window=10, min_periods=1).mean().round(2)
            df['MA20'] = df['收盘'].rolling(window=20, min_periods=1).mean().round(2)
            
            recent_df = df.tail(5)
            headers = ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "振幅", "涨跌幅", "涨跌额", "换手率", "MA5", "MA10", "MA20"]
            available_cols = [h for h in headers if h in recent_df.columns]
                    
            if not available_cols:
                 return df.tail(5).to_markdown()
                 
            return recent_df[available_cols].to_markdown(index=False)
        except Exception as e:
            return f"获取K线数据失败: {e}"

    def get_basic_info(self, code: str) -> str:
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            with bypass_proxy():
                df = ak.stock_a_indicator_lg(symbol=clean_code)
            if df.empty:
                return "无基本面指标数据"
            recent = df.tail(1).iloc[0]
            info = (f"- 市盈率(PE): {recent.get('pe', '未知')}\n"
                    f"- 市净率(PB): {recent.get('pb', '未知')}\n"
                    f"- 股息率(Dividend Yield): {recent.get('dv_ratio', '未知')}%")
            return info
        except Exception as e:
            return f"获取基本面指标失败: {e}"
            
    def get_news(self, code: str) -> str:
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            with bypass_proxy():
                df = ak.stock_news_em(symbol=clean_code)
            if df.empty:
                return "最近暂无重大新闻"
            
            news_lines = []
            for _, row in df.head(5).iterrows():
                news_lines.append(f"- [{row.get('新闻时间', '')}] {row.get('新闻标题', '')}")
            
            return "\n".join(news_lines)
        except Exception as e:
            return f"获取新闻失败: {e}"

    def get_full_analysis_context(self, code_or_name: str) -> tuple[str, str, str]:
        code, name = self.get_stock_name_or_code(code_or_name)
        
        if not code:
            return "", name, f"无法找到股票: {code_or_name}"
            
        context = f"# 股票诊断: {name} ({code})\n\n"
        context += "## 1. 近期行情与均线特征 (前复权)\n"
        context += self.get_daily_kline(code) + "\n\n"
        
        context += "## 2. 核心财务估值指标\n"
        context += self.get_basic_info(code) + "\n\n"
        
        context += "## 3. 近期关键新闻面\n"
        context += self.get_news(code) + "\n"
        
        return code, name, context

    # ==================== 板块分析模块 ====================

    def get_industry_board_list(self) -> pd.DataFrame:
        """获取东方财富行业板块列表"""
        try:
            with bypass_proxy():
                df = ak.stock_board_industry_name_em()
            return df
        except Exception as e:
            return pd.DataFrame()

    def get_concept_board_list(self) -> pd.DataFrame:
        """获取东方财富概念板块列表"""
        try:
            with bypass_proxy():
                df = ak.stock_board_concept_name_em()
            return df
        except Exception as e:
            return pd.DataFrame()

    def search_board(self, query: str) -> list[dict]:
        """根据关键词模糊搜索板块（行业+概念），返回匹配结果列表"""
        results = []
        query_lower = query.lower().strip()
        try:
            industry_df = self.get_industry_board_list()
            if not industry_df.empty and '板块名称' in industry_df.columns:
                matched = industry_df[industry_df['板块名称'].str.contains(query_lower, case=False, na=False)]
                for _, row in matched.iterrows():
                    results.append({
                        'name': row['板块名称'],
                        'code': row.get('板块代码', ''),
                        'type': '行业板块',
                        'change_pct': row.get('涨跌幅', ''),
                        'total_mv': row.get('总市值', ''),
                    })
        except Exception:
            pass
        try:
            concept_df = self.get_concept_board_list()
            if not concept_df.empty and '板块名称' in concept_df.columns:
                matched = concept_df[concept_df['板块名称'].str.contains(query_lower, case=False, na=False)]
                for _, row in matched.iterrows():
                    results.append({
                        'name': row['板块名称'],
                        'code': row.get('板块代码', ''),
                        'type': '概念板块',
                        'change_pct': row.get('涨跌幅', ''),
                        'total_mv': row.get('总市值', ''),
                    })
        except Exception:
            pass
        return results

    def get_board_constituents(self, board_name: str, board_type: str = "行业板块", top_n: int = 10) -> str:
        """获取板块成分股（取涨跌幅前 top_n）"""
        try:
            with bypass_proxy():
                if board_type == "概念板块":
                    df = ak.stock_board_concept_cons_em(symbol=board_name)
                else:
                    df = ak.stock_board_industry_cons_em(symbol=board_name)

            if df.empty:
                return "暂无成分股数据"

            # 统一列名处理
            cols_map = {'代码': '代码', '名称': '名称', '最新价': '最新价', '涨跌幅': '涨跌幅',
                        '涨跌额': '涨跌额', '成交量': '成交量', '成交额': '成交额', '换手率': '换手率'}
            available = [c for c in cols_map.keys() if c in df.columns]

            if '涨跌幅' in df.columns:
                df = df.sort_values('涨跌幅', ascending=False)

            display_df = df[available].head(top_n)
            return display_df.to_markdown(index=False)
        except Exception as e:
            return f"获取成分股失败: {e}"

    def get_board_history(self, board_name: str, board_type: str = "行业板块", limit: int = 10) -> str:
        """获取板块近期历史行情"""
        try:
            with bypass_proxy():
                if board_type == "概念板块":
                    df = ak.stock_board_concept_hist_em(symbol=board_name, period="日k", adjust="")
                else:
                    df = ak.stock_board_industry_hist_em(symbol=board_name, period="日k", adjust="")

            if df.empty:
                return "暂无板块历史行情数据"

            df = df.tail(limit)
            headers = ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "振幅", "涨跌幅", "涨跌额", "换手率"]
            available = [h for h in headers if h in df.columns]
            if not available:
                return df.tail(limit).to_markdown()
            return df[available].to_markdown(index=False)
        except Exception as e:
            return f"获取板块历史行情失败: {e}"

    def find_related_sub_boards(self, board_name: str, max_results: int = 8) -> list[dict]:
        """基于主板块的成分股，反向查找这些股票所属的其他概念板块，发现细分子板块"""
        sub_boards = []
        try:
            # 先拿主板块的成分股代码
            with bypass_proxy():
                try:
                    main_cons = ak.stock_board_concept_cons_em(symbol=board_name)
                except Exception:
                    main_cons = ak.stock_board_industry_cons_em(symbol=board_name)

            if main_cons.empty or '代码' not in main_cons.columns:
                return sub_boards

            main_stock_codes = set(main_cons['代码'].tolist())

            # 拿全部概念板块列表
            concept_df = self.get_concept_board_list()
            if concept_df.empty or '板块名称' not in concept_df.columns:
                return sub_boards

            # 遍历概念板块，找与主板块成分股有交集的
            candidate_boards = []
            for _, row in concept_df.iterrows():
                concept_name = row['板块名称']
                if concept_name == board_name:
                    continue
                candidate_boards.append({
                    'name': concept_name,
                    'change_pct': row.get('涨跌幅', 0),
                })

            # 为了控制速度，只从跟关键词有弱关联的或涨跌幅靠前的板块里抽样检查
            # 先按涨跌幅绝对值排序（活跃板块优先）
            try:
                candidate_boards.sort(key=lambda x: abs(float(x.get('change_pct', 0) or 0)), reverse=True)
            except Exception:
                pass

            checked = 0
            for candidate in candidate_boards[:60]:
                if checked >= max_results:
                    break
                try:
                    with bypass_proxy():
                        cons = ak.stock_board_concept_cons_em(symbol=candidate['name'])
                    if cons.empty or '代码' not in cons.columns:
                        continue
                    overlap_codes = main_stock_codes & set(cons['代码'].tolist())
                    overlap_ratio = len(overlap_codes) / max(len(main_stock_codes), 1)
                    if overlap_ratio >= 0.15:  # 至少 15% 成分股重叠
                        sub_boards.append({
                            'name': candidate['name'],
                            'type': '概念板块',
                            'overlap_count': len(overlap_codes),
                            'overlap_ratio': f"{overlap_ratio:.0%}",
                            'change_pct': candidate['change_pct'],
                        })
                        checked += 1
                except Exception:
                    continue

        except Exception:
            pass
        return sub_boards

    def get_board_analysis_context(self, board_name: str, board_type: str = "行业板块",
                                    sub_boards: list[dict] = None) -> str:
        """组装板块分析上下文，含主板块走势 + 成分股 + 关联子板块数据"""
        context = f"# 板块诊断: {board_name} ({board_type})\n\n"

        context += "## 1. 板块近期走势 (近10个交易日)\n"
        context += self.get_board_history(board_name, board_type) + "\n\n"

        context += "## 2. 板块核心成分股（按涨跌幅排序 Top10）\n"
        context += self.get_board_constituents(board_name, board_type) + "\n\n"

        # 关联子板块数据
        if sub_boards:
            context += "## 3. 关联细分子板块一览\n"
            context += "以下是与主板块成分股高度重叠的细分概念板块：\n\n"
            context += "| 子板块名称 | 重叠股票数 | 重叠比例 | 今日涨跌幅 |\n"
            context += "|---|---|---|---|\n"
            for sb in sub_boards:
                context += f"| {sb['name']} | {sb['overlap_count']} | {sb['overlap_ratio']} | {sb['change_pct']}% |\n"
            context += "\n"

            # 取前3个关联度最高的子板块，拉取它们的走势
            for sb in sub_boards[:3]:
                context += f"### 子板块: {sb['name']} 近期走势\n"
                context += self.get_board_history(sb['name'], '概念板块', limit=5) + "\n\n"

        return context

if __name__ == "__main__":
    fetcher = AShareDataFetcher()
    print(fetcher.get_full_analysis_context("600519"))
