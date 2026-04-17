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

if __name__ == "__main__":
    fetcher = AShareDataFetcher()
    print(fetcher.get_full_analysis_context("600519"))
