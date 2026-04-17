import akshare as ak
import pandas as pd
import datetime
import os

# --- 强制国内数据直连：防止代理软件拦截国内证券交易所数据导致 SSL 报错 ---
os.environ["NO_PROXY"] = "localhost,127.0.0.1,.bse.cn,.eastmoney.com,.sina.com.cn,.163.com"
os.environ["no_proxy"] = "localhost,127.0.0.1,.bse.cn,.eastmoney.com,.sina.com.cn,.163.com"
# ---------------------------------------------------------------------------------
try:
    import ssl
    import requests
    import urllib3
    # 禁用 urllib3 的安全警告
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    # 取消内置库的证书校验
    ssl._create_default_https_context = ssl._create_unverified_context
    # Hook requests session 取消底层抓取的证书校验
    _orig_request = requests.Session.request
    def _patched_request(*args, **kwargs):
        kwargs['verify'] = False
        return _orig_request(*args, **kwargs)
    requests.Session.request = _patched_request
except Exception:
    pass
# ---------------------------------------------------------------------------------
class AShareDataFetcher:
    def __init__(self):
        pass

    def get_stock_name_or_code(self, query: str) -> tuple[str, str]:
        """传入名字或代码，返回标准化的 (代码, 名称) 元组"""
        clean_query = query.lower().replace('sh', '').replace('sz', '').strip()
        try:
            stock_info = ak.stock_info_a_code_name()
            # 判断是否纯数字 (假设为代码)
            if clean_query.isdigit():
                matched = stock_info[stock_info['code'] == clean_query]
                if not matched.empty:
                    return clean_query, matched.iloc[0]['name']
                return clean_query, "未知名称"
            else:
                # 假设是名称
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
        """获取近期日K线，并计算五日/十日/二十日均线"""
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            # 使用 akshare 获取 A 股日频数据（不复权，或前复权）
            df = ak.stock_zh_a_hist(symbol=clean_code, period="daily", adjust="qfq")
            if df.empty:
                return "暂无K线数据"
            
            # 保留最近 limit 天计算
            df = df.tail(limit).copy()
            df['日期'] = pd.to_datetime(df['日期']).dt.strftime('%Y-%m-%d')
            
            # 计算简单的均线 (粗略计算，严谨需要更长时间周期，但为了快速运行做演示)
            df['MA5'] = df['收盘'].rolling(window=5, min_periods=1).mean().round(2)
            df['MA10'] = df['收盘'].rolling(window=10, min_periods=1).mean().round(2)
            df['MA20'] = df['收盘'].rolling(window=20, min_periods=1).mean().round(2)
            
            # 只取最近几天的记录以节省 Token
            recent_df = df.tail(5)
            
            # 构建 markdown 表格
            headers = ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "振幅", "涨跌幅", "涨跌额", "换手率", "MA5", "MA10", "MA20"]
            
            # 处理可能的列名差异
            available_cols = []
            for h in headers:
                if h in recent_df.columns:
                    available_cols.append(h)
                    
            if not available_cols:
                 return df.tail(5).to_markdown()
                 
            return recent_df[available_cols].to_markdown(index=False)
        except Exception as e:
            return f"获取K线数据失败: {e}"

    def get_basic_info(self, code: str) -> str:
        """获取基本面信息（市盈率、市净率等）"""
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
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
        """获取个股最近的新闻"""
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
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
        """组装供大模型使用的分析上下文。返回 (code, name, context)"""
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
    # 简单测试入口
    fetcher = AShareDataFetcher()
    print(fetcher.get_full_analysis_context("600519"))
