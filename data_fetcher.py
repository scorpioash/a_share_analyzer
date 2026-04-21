import streamlit as st
import akshare as ak
import pandas as pd
# 强制设置 Pandas 使用 python 模式存储字符串，防止 PyArrow 在处理 akshare 的正则时报错 (\u 问题)
pd.options.mode.string_storage = "python"

import datetime
import os
import contextlib
import urllib3
import ssl

# 全局关闭 SSL 验证警告，并尝试绕过部分环境下的 SSLEOFError
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

@contextlib.contextmanager
def bypass_proxy():
    """临时隔离系统的全局/底层代理，确保国内直连抓取数据，而不会影响主线程调取跨境大模型"""
    proxy_keys = ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']
    saved_env = {}
    for k in proxy_keys:
        if k in os.environ:
            saved_env[k] = os.environ.pop(k)
            
    # 强制让 requests / urllib3 忽略所有 Windows 注册表的系统代理
    saved_no_proxy = os.environ.get('NO_PROXY')
    saved_no_proxy_lower = os.environ.get('no_proxy')
    os.environ['NO_PROXY'] = '*'
    os.environ['no_proxy'] = '*'

    # 暴力拦截 urllib.request 去读取 Windows 系统代理设置
    import urllib.request
    original_getproxies = urllib.request.getproxies
    urllib.request.getproxies = lambda: {}
    
    # 彻底物理拦截 requests 库底层的代理合并逻辑，防止内部缓存代理设置
    import requests
    original_merge_env = requests.Session.merge_environment_settings
    original_request = requests.Session.request
    
    def proxy_blocking_merge(self, url, proxies, stream, verify, cert):
        settings = original_merge_env(self, url, proxies, stream, verify, cert)
        settings['proxies'] = {"http": None, "https": None}
        return settings
        
    def user_agent_request(self, method, url, **kwargs):
        headers = kwargs.get('headers') or {}
        if 'User-Agent' not in headers:
            headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
        kwargs['headers'] = headers
        return original_request(self, method, url, **kwargs)
        
    requests.Session.merge_environment_settings = proxy_blocking_merge
    requests.Session.request = user_agent_request
    
    # 【终极杀招】：拦截 socket.getaddrinfo 解决 Fake-IP 导致的连接截断问题
    # 很多代理软件会在 OS 层下发 Fake-IP（如 198.18.0.x），导致代码直连时无法路由。
    # 这里我们强制使用阿里公共 DNS (223.5.5.5) 为东方财富域名获取真实物理 IP，绕过操作系统 DNS 污染。
    import socket
    import json
    original_getaddrinfo = socket.getaddrinfo
    
    def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if 'eastmoney' in host or '10jqka' in host:
            try:
                url = f"http://223.5.5.5/resolve?name={host}&type=1"
                req = urllib.request.Request(url, headers={'Accept': 'application/dns-json'})
                # 确保 DNS 查询本身也不走代理
                req.set_proxy('', 'http')
                req.set_proxy('', 'https')
                with urllib.request.urlopen(req, timeout=3) as response:
                    res = json.loads(response.read().decode('utf-8'))
                    if res.get('Status') == 0 and 'Answer' in res:
                        for answer in res['Answer']:
                            if answer['type'] == 1:
                                real_ip = answer['data']
                                # 返回标准的 socket addrinfo 结构
                                return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (real_ip, port))]
            except Exception:
                pass
        return original_getaddrinfo(host, port, family, type, proto, flags)
        
    socket.getaddrinfo = patched_getaddrinfo
    
    try:
        yield
    finally:
        for k, v in saved_env.items():
            os.environ[k] = v
            
        if saved_no_proxy is not None:
            os.environ['NO_PROXY'] = saved_no_proxy
        else:
            os.environ.pop('NO_PROXY', None)
            
        if saved_no_proxy_lower is not None:
            os.environ['no_proxy'] = saved_no_proxy_lower
        else:
            os.environ.pop('no_proxy', None)
            
        urllib.request.getproxies = original_getproxies
        requests.Session.merge_environment_settings = original_merge_env
        requests.Session.request = original_request
        socket.getaddrinfo = original_getaddrinfo

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
            prefix = self._get_market_prefix(clean_code)
            symbol_tx = f"{prefix}{clean_code}"
            with bypass_proxy():
                df = ak.stock_zh_a_hist_tx(symbol=symbol_tx, start_date='2024-01-01', end_date=datetime.datetime.now().strftime('%Y-%m-%d'))
            if df.empty:
                return "暂无K线数据"
            
            # 腾讯源列名: date, open, close, high, low, amount
            df = df.rename(columns={'date': '日期', 'open': '开盘', 'close': '收盘', 'high': '最高', 'low': '最低', 'amount': '成交量'})
            df = df.tail(limit).copy()
            df['日期'] = pd.to_datetime(df['日期']).dt.strftime('%Y-%m-%d')
            df['MA5'] = df['收盘'].rolling(window=5, min_periods=1).mean().round(2)
            df['MA10'] = df['收盘'].rolling(window=10, min_periods=1).mean().round(2)
            df['MA20'] = df['收盘'].rolling(window=20, min_periods=1).mean().round(2)
            
            recent_df = df.tail(5)
            headers = ["日期", "开盘", "收盘", "最高", "最低", "成交量", "MA5", "MA10", "MA20"]
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
            news_lines = []
            
            import pandas as pd
            orig_storage = pd.options.mode.string_storage
            try:
                pd.options.mode.string_storage = "python"
                with bypass_proxy():
                    # 优先尝试东方财富源，失败则静默跳过
                    try:
                        df = ak.stock_news_em(symbol=clean_code)
                        if not df.empty:
                            for _, row in df.head(8).iterrows():
                                link = row.get('新闻链接', '')
                                title = row.get('新闻标题', '未知标题')
                                time_str = row.get('新闻时间', '')
                                if link:
                                    news_lines.append(f"- [{time_str}] [{title}]({link})")
                                else:
                                    news_lines.append(f"- [{time_str}] {title}")
                    except Exception:
                        pass
                    
                    # 如果EM源失败，尝试同花顺全球快讯作为补充
                    if not news_lines:
                        try:
                            df_global = ak.stock_info_global_ths()
                            if df_global is not None and not df_global.empty:
                                for _, row in df_global.head(5).iterrows():
                                    title = row.get('内容', row.get('title', '未知'))
                                    time_str = row.get('时间', row.get('发布时间', ''))
                                    news_lines.append(f"- [{time_str}] {str(title)[:80]}")
                        except Exception:
                            pass
            except Exception as inner_e:
                print(f"新闻接口内部错误: {inner_e}")
            finally:
                pd.options.mode.string_storage = orig_storage
                
            if news_lines:
                return "\n".join(news_lines)
            return "最近暂无重大新闻，或接口暂时不可用。"
        except Exception as e:
            return f"获取新闻失败: {e}"

    def get_realtime_quotes(self, market: str = "主板") -> "pd.DataFrame":
        """获取各类市场的实时行情榜单 (使用新浪源，兼容代理环境)"""
        try:
            with bypass_proxy():
                df = ak.stock_zh_a_spot()
            if df is None or df.empty:
                return None
            # 新浪源列名映射
            col_map = {'代码': '代码', '名称': '名称', '最新价': '最新价', '涨跌幅': '涨跌幅'}
            # 按市场过滤
            df['代码'] = df['代码'].astype(str)
            if market == "主板":
                df = df[df['代码'].str.match(r'^(sh6|sz0)')]
            elif market == "科创板":
                df = df[df['代码'].str.contains('688')]
            elif market == "创业板":
                df = df[df['代码'].str.match(r'^sz30')]
            elif market == "北交所":
                df = df[df['代码'].str.match(r'^bj')]
            return df
        except Exception as e:
            print(f"获取实时行情异常: {e}")
            return None

    def get_market_changes(self, symbol: str = "火箭发射") -> "pd.DataFrame":
        """获取盘口异动数据
        symbol 可选: '火箭发射', '快速反弹', '大笔买入', '封涨停板', '打开跌停板', '有大买盘',
                    '竞价上涨', '高开5日线', '向上缺口', '60日新高', '60日大幅上涨', '加速下跌',
                    '高台跳水', '大笔卖出', '封跌停板', '打开涨停板', '有大卖盘', '竞价下跌',
                    '低开5日线', '向下缺口', '60日新低', '60日大幅下跌'
        """
        try:
            with bypass_proxy():
                df = ak.stock_changes_em(symbol=symbol)
            return df
        except Exception as e:
            print(f"获取盘口异动异常: {e}")
            return None

    def get_limit_pool(self, pool_type: str = "涨停") -> "pd.DataFrame":
        """获取涨停/跌停/炸板/强势等股池"""
        import datetime
        date_str = datetime.datetime.now().strftime("%Y%m%d")
        
        # 尝试获取当天数据，如果失败获取上一交易日数据，由于akshare设计，可能不需要传日期
        try:
            with bypass_proxy():
                if pool_type == "涨停":
                    df = ak.stock_zt_pool_em(date=date_str)
                elif pool_type == "跌停":
                    df = ak.stock_zt_pool_dtgc_em(date=date_str)
                elif pool_type == "昨日涨停":
                    df = ak.stock_zt_pool_previous_em(date=date_str)
                elif pool_type == "强势股":
                    df = ak.stock_zt_pool_strong_em(date=date_str)
                elif pool_type == "次新股":
                    df = ak.stock_zt_pool_sub_new_em(date=date_str)
                elif pool_type == "炸板":
                    df = ak.stock_zt_pool_zbgc_em(date=date_str)
                else:
                    return None
            return df
        except Exception as e:
            # 如果带日期失败，尝试不带日期的最新数据调用
            try:
                with bypass_proxy():
                    if pool_type == "涨停": return ak.stock_zt_pool_em()
                    elif pool_type == "跌停": return ak.stock_zt_pool_dtgc_em()
                    elif pool_type == "昨日涨停": return ak.stock_zt_pool_previous_em()
                    elif pool_type == "强势股": return ak.stock_zt_pool_strong_em()
                    elif pool_type == "次新股": return ak.stock_zt_pool_sub_new_em()
                    elif pool_type == "炸板": return ak.stock_zt_pool_zbgc_em()
            except Exception as e2:
                print(f"获取{pool_type}股池异常: {e2}")
                return None
            return None

    def get_earnings_summary(self, date: str, report_type: str = "业绩快报") -> "pd.DataFrame":
        """获取特定报告期的业绩表（快报/预告等）"""
        try:
            with bypass_proxy():
                if report_type == "业绩快报":
                    df = ak.stock_yjkb_em(date=date)
                elif report_type == "业绩预告":
                    df = ak.stock_yjyg_em(date=date)
                else:
                    return None
            return df
        except Exception as e:
            print(f"获取{report_type}异常: {e}")
            return None

    def get_institutional_research(self) -> "pd.DataFrame":
        """获取最新机构调研详细数据"""
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            with bypass_proxy():
                try:
                    df = ak.stock_jgdy_detail_em()
                    return df
                except Exception:
                    # 如果SSL错误，尝试用 stock_jgdy_tj_em 替代
                    try:
                        df = ak.stock_jgdy_tj_em()
                        return df
                    except Exception:
                        return None
        except Exception as e:
            print(f"获取机构调研数据异常: {e}")
            return None

    def get_global_news(self) -> "pd.DataFrame":
        """获取全球财经快讯 (优先同花顺源)"""
        try:
            with bypass_proxy():
                try:
                    df = ak.stock_info_global_ths()
                except Exception:
                    df = ak.stock_info_global_sina()
            if df is not None and not df.empty:
                cols_map = {'文章连接': 'url', '文章链接': 'url', '时间': '发布时间'}
                df = df.rename(columns={k: v for k, v in cols_map.items() if k in df.columns})
            return df
        except Exception as e:
            print(f"获取财经快讯异常: {e}")
            return None

    def get_daily_dragon_tiger(self, date: str) -> "pd.DataFrame":
        """获取某日/某段时间的龙虎榜全量数据
        date: YYYYMMDD 格式，会自动构建为当日的 start_date=date, end_date=date
        """
        try:
            with bypass_proxy():
                df = ak.stock_lhb_detail_em(start_date=date, end_date=date)
            return df
        except Exception as e:
            print(f"获取每日龙虎榜异常: {e}")
            return None

    def get_fund_flow_rank(self, indicator: str = "今日") -> "pd.DataFrame":
        """获取资金流向排名（今日、3日、5日、10日）"""
        try:
            with bypass_proxy():
                try:
                    df = ak.stock_individual_fund_flow_rank(indicator=indicator)
                    return df
                except Exception as e:
                    print(f"资金流向主接口失败，尝试降级: {e}")
                    # SSL 降级：尝试用概览或概念资金流替代，或者返回空
                    try:
                        df = ak.stock_market_fund_flow()
                        return df
                    except:
                        return None
        except Exception as e:
            print(f"获取资金流向排名异常: {e}")
            return None

    def get_board_list(self, board_type: str = "行业") -> "pd.DataFrame":
        """获取同花顺/东方财富全量板块列表"""
        try:
            with bypass_proxy():
                if board_type == "行业":
                    df = ak.stock_board_industry_name_ths()
                else:
                    df = ak.stock_board_concept_name_ths()
            return df
        except Exception as e:
            print(f"获取{board_type}板块列表异常: {e}")
            return None

    def get_historical_trend(self, code: str, days: int = 250) -> str:
        """抽取近 N 个交易日的历史行情核心趋势微缩版，赋予 AI 长线记忆 (腾讯源)"""
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            prefix = self._get_market_prefix(clean_code)
            symbol_tx = f"{prefix}{clean_code}"
            import datetime
            end_date = datetime.datetime.now()
            start_date = end_date - datetime.timedelta(days=days * 2)
            
            with bypass_proxy():
                df = ak.stock_zh_a_hist_tx(symbol=symbol_tx, start_date=start_date.strftime('%Y-%m-%d'), end_date=end_date.strftime('%Y-%m-%d'))
            
            if df.empty:
                return "暂无历史行情数据"
            
            # 腾讯源列名映射
            df = df.rename(columns={'date': '日期', 'open': '开盘', 'close': '收盘', 'high': '最高', 'low': '最低', 'amount': '成交量'})
            
            recent_df = df.tail(days)
            if recent_df.empty:
                return "暂无足够的历史行情数据"
                
            max_price = recent_df['最高'].max()
            min_price = recent_df['最低'].min()
            current_price = recent_df.iloc[-1]['收盘']
            
            trend_md = (
                f"- **周期统计**: 过去 {len(recent_df)} 个交易日\n"
                f"- **区间最高**: {max_price}，**区间最低**: {min_price} (当前收盘价 {current_price})\n"
                f"- **当前股价位置**: 位于近区间的 {((current_price - min_price) / (max_price - min_price + 0.001)) * 100:.1f}%\n"
            )
            # 抽样几条关键日期供 LLM 判断趋势
            sample_df = recent_df.iloc[::20]
            sample_strs = [f"{str(row['日期'])[:10]}收:{row['收盘']}" for idx, row in sample_df.iterrows()]
            trend_md += f"- **走势抽样速览**: {', '.join(sample_strs)}\n"
            return trend_md
        except Exception as e:
            return f"获取历史趋势失败: {e}"

    def get_block_trades_and_repurchase(self, code: str) -> str:
        """大宗交易与回购动作监控"""
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            report = ""
            with bypass_proxy():
                # 查询大宗交易
                try:
                    df_block = ak.stock_block_trade_em()
                    if not df_block.empty and '证券代码' in df_block.columns:
                        matched = df_block[df_block['证券代码'] == clean_code]
                        if not matched.empty:
                            report += f"- **存在大宗交易**: 近期出现大宗交易，总计金额 {matched['成交额'].sum() / 10000:.2f} 万元。\n"
                        else:
                            report += "- **大宗交易**: 近期未发现大规模异常大宗。\n"
                except:
                    report += "- **大宗交易**: 数据获取出错。\n"
                    
                # 查询最新披露的回购计划
                try:
                    df_repo = ak.stock_repurchase_em()
                    if not df_repo.empty and '代码' in df_repo.columns:
                        matched = df_repo[df_repo['代码'] == clean_code]
                        if not matched.empty:
                            report += f"- **触发回购方案**: 最新公告有回购计划，状态：{matched.iloc[0]['状态']}（金额：{matched.iloc[0]['回购金额']}）。\n"
                        else:
                            report += "- **公司回购**: 当前暂无处于执行期的回购预案。\n"
                except:
                    pass
            return report if report else "无相关异常记录。"
        except Exception as e:
            return f"获取大宗与回购失败: {e}"

    def _get_market_prefix(self, code: str) -> str:
        """根据股票代码判断市场前缀 sh/sz/bj"""
        clean = code.strip()
        if clean.startswith(('6', '9')):
            return 'sh'
        elif clean.startswith(('0', '2', '3')):
            return 'sz'
        elif clean.startswith(('4', '8')):
            return 'bj'
        return 'sh'

    def get_fund_flow(self, code: str) -> str:
        """获取个股资金流向（近期主力/超大单/大单/中单/小单净流入）"""
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            market = self._get_market_prefix(clean_code)
            with bypass_proxy():
                df = ak.stock_individual_fund_flow(stock=clean_code, market=market)
            if df.empty:
                return "暂无资金流向数据"
            recent = df.tail(5)
            headers = [c for c in recent.columns if c != '']
            return recent[headers].to_markdown(index=False)
        except Exception as e:
            return f"获取资金流向失败: {e}"

    def get_top_shareholders(self, code: str) -> "pd.DataFrame":
        """获取十大流通股东 - 增强版（含日期回溯探测）"""
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            market = self._get_market_prefix(clean_code)
            symbol_with_prefix = f"{market}{clean_code}"
            
            df = pd.DataFrame()
            with bypass_proxy():
                import datetime
                curr_year = datetime.date.today().year
                # 策略：如果""(最新)失败，回溯探测近两年的所有财报截止日
                test_dates = [""]
                for y in [curr_year, curr_year-1]:
                    test_dates.extend([f"{y}0331", f"{y}0630", f"{y}0930", f"{y}1231"])
                
                found = False
                # 接口尝试列表：流通十大 -> 十大股东
                for api_func in [ak.stock_gdfx_free_top_10_em, ak.stock_gdfx_top_10_em]:
                    for s in [symbol_with_prefix, clean_code]:
                        for d in test_dates:
                            try:
                                temp = api_func(symbol=s, date=d)
                                if temp is not None and not temp.empty:
                                    df = temp
                                    found = True
                                    break
                            except Exception:
                                continue
                        if found: break
                    if found: break
            
            if df.empty:
                # 终极保底：尝试获取基本面快照作为替代展示
                try:
                    with bypass_proxy():
                        df = ak.stock_individual_info_em(symbol=clean_code)
                        if not df.empty:
                            return df.rename(columns={'item': '项目', 'value': '数值'})
                except: pass
                return None
                
            # 标准化处理
            cols_map = {
                '股东名称': '股东名称', '持股人名称': '股东名称', 
                '持股数量': '持股数', '持股数量(股)': '持股数',
                '持股比例': '持股比例', '持股比例(%)': '持股比例'
            }
            df = df.rename(columns=cols_map)
            target_cols = ['股东名称', '持股数', '持股比例', '增减', '变动比例']
            available = [c for c in target_cols if c in df.columns]
            
            return df[available].head(10) if available else df.head(10)
        except Exception as e:
            print(f"获取股东数据发生异常: {e}")
            return None

    def get_profit_forecast(self, code: str) -> str:
        """获取机构盈利预测"""
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            with bypass_proxy():
                df = ak.stock_profit_forecast_em(symbol=clean_code)
            if df.empty:
                return "暂无盈利预测数据"
            return df.head(5).to_markdown(index=False)
        except Exception as e:
            return f"获取盈利预测失败: {e}"

    def get_revenue_breakdown(self, code: str) -> str:
        """获取主营构成（按产品/地区拆分营收）"""
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            with bypass_proxy():
                df = ak.stock_zygc_em(symbol=clean_code)
            if df.empty:
                return "暂无主营构成数据"
            # 只取最近一期
            if '报告日期' in df.columns:
                latest_date = df['报告日期'].iloc[0]
                df = df[df['报告日期'] == latest_date]
            cols = ['主营构成', '主营收入', '收入比例', '主营成本', '成本比例', '主营利润', '利润比例']
            available = [c for c in cols if c in df.columns]
            if not available:
                return df.head(8).to_markdown(index=False)
            return df[available].head(8).to_markdown(index=False)
        except Exception as e:
            return f"获取主营构成失败: {e}"

    def get_margin_data(self, code: str) -> str:
        """获取个股融资融券余额数据"""
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            with bypass_proxy():
                df = ak.stock_margin_detail_sse(date="")
            if df.empty:
                return "暂无融资融券数据"
            if '标的证券代码' in df.columns:
                matched = df[df['标的证券代码'] == clean_code]
                if not matched.empty:
                    row = matched.iloc[0]
                    lines = []
                    for col in matched.columns:
                        lines.append(f"- {col}: {row[col]}")
                    return "\n".join(lines)
            return "未在融资融券标的中找到此股"
        except Exception as e:
            return f"获取融资融券数据失败: {e}"

    def get_dragon_tiger(self, code: str) -> str:
        """获取近期龙虎榜数据（如果有上榜记录）"""
        try:
            import datetime
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            today = datetime.date.today()
            # 用 start_date/end_date 一次性查最近7天
            end_date = today.strftime("%Y%m%d")
            start_date = (today - datetime.timedelta(days=7)).strftime("%Y%m%d")
            try:
                with bypass_proxy():
                    df = ak.stock_lhb_detail_em(start_date=start_date, end_date=end_date)
                if not df.empty and '代码' in df.columns:
                    matched = df[df['代码'] == clean_code]
                    if not matched.empty:
                        cols = ['代码', '名称', '上榜原因', '成交额', '买入额', '卖出额', '净额']
                        available = [c for c in cols if c in matched.columns]
                        return matched[available].to_markdown(index=False)
            except Exception:
                pass
            return "近7个交易日未上龙虎榜"
        except Exception as e:
            return f"获取龙虎榜数据失败: {e}"

    def get_shareholder_count(self, code: str) -> str:
        """获取股东户数变化趋势 - 鲁棒性增强版"""
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            df = pd.DataFrame()
            
            with bypass_proxy():
                # 尝试多个可靠的数据源
                sources = [
                    (ak.stock_zh_a_gdhs, {"symbol": clean_code}),
                    (ak.stock_hold_num_cninfo, {"date": ""})  # 巨潮全市场最新
                ]
                
                for func, kwargs in sources:
                    try:
                        temp = func(**kwargs)
                        if temp is not None and not temp.empty:
                            # 判定是否包含我们的目标股票
                            code_col = None
                            for c in ['证券代码', '代码', '股票代码']:
                                if c in temp.columns:
                                    code_col = c
                                    break
                            
                            if code_col:
                                temp[code_col] = temp[code_col].astype(str).str.zfill(6)
                                match = temp[temp[code_col] == clean_code]
                                if not match.empty:
                                    df = match
                                    break
                            else:
                                # 如果是单支股票接口返回的，没有代码列也行
                                df = temp
                                break
                    except Exception:
                        continue
            
            if df.empty:
                # 最终保底：从个股概况里抓个当前数值
                try:
                    info = ak.stock_individual_info_em(symbol=clean_code)
                    count_row = info[info['item'] == '股东人数']
                    if not count_row.empty:
                        return f"- 统计截止日期: 最新\n- 本次户数: {count_row['value'].values[0]}"
                except: pass
                return "未查到该股近期的股东户数数据"
                
            # 尝试识别日期列进行排序
            date_col = next((c for c in ['统计截止日期', '公告日期', '截止日期'] if c in df.columns), None)
            if date_col:
                try:
                    # 强转日期类型排序，确保 iloc[-1] 是最新的
                    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                    df = df.dropna(subset=[date_col]).sort_values(date_col, ascending=True)
                except:
                    pass
            
            latest_row = df.iloc[-1]
            lines = []
            # 灵活匹配显示列
            display_map = {
                '统计截止日期': '截止日期',
                '本次户数': '最新股东户数',
                '上次户数': '前一期户数',
                '增减比例': '户数增减比',
                '户数降幅': '户数降幅'
            }
            
            for key, label in display_map.items():
                for actual_col in df.columns:
                    if key in actual_col:
                        val = latest_row[actual_col]
                        # 格式化日期
                        if '日期' in actual_col and hasattr(val, 'strftime'):
                            val = val.strftime('%Y-%m-%d')
                        lines.append(f"- {label}: {val}")
                        break
            
            if not lines:
                # 极端兜底
                for col in df.columns[:min(4, len(df.columns))]:
                    lines.append(f"- {col}: {latest_row[col]}")
                    
            return "\n".join(lines)
        except Exception as e:
            return f"获取股东户数失败: {e}"

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
        context += self.get_news(code) + "\n\n"

        context += "## 4. 资金流向 (近5日主力/散户净流入)\n"
        context += self.get_fund_flow(code) + "\n\n"

        context += "## 5. 十大流通股东\n"
        sh_df = self.get_top_shareholders(code)
        if isinstance(sh_df, pd.DataFrame):
            context += sh_df.to_markdown(index=False) + "\n\n"
        else:
            context += "暂无股东数据\n\n"

        context += "## 6. 机构盈利预测\n"
        context += self.get_profit_forecast(code) + "\n\n"

        context += "## 7. 主营业务构成\n"
        context += self.get_revenue_breakdown(code) + "\n\n"

        context += "## 8. 融资融券余额\n"
        context += self.get_margin_data(code) + "\n\n"

        context += "## 9. 龙虎榜 (近5日)\n"
        context += self.get_dragon_tiger(code) + "\n\n"

        context += "## 10. 股东户数变化\n"
        context += self.get_shareholder_count(code) + "\n\n"

        context += "## 11. 长线历史行情与**静默技术指标** (近250个交易日提取)\n"
        context += self.get_historical_trend(code, days=250) + "\n"
        context += self.get_technical_indicators(code) + "\n\n"

        context += "## 12. 大宗交易与回购监控\n"
        context += self.get_block_trades_and_repurchase(code) + "\n\n"
        
        context += "## 13. 个股热度与市场情绪 (雪球/东财)\n"
        context += self.get_stock_popularity(code) + "\n"
        
        return code, name, context

    # ==================== 板块分析模块 ====================

    def get_technical_indicators(self, code: str) -> str:
        """
        [核心增强] 获取个股在同花顺 11 个技术极值榜单中的状态。
        如果是普通个股扫描，会返回该个股命中的所有极值标签。
        """
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            hits = []
            
            # 使用列表存储需要扫描的榜单 API 信息
            # 名称, 函数名, 参数(如果有)
            tech_tasks = [
                ("创月新高", ak.stock_rank_cxg_ths, {"symbol": "创月新高"}),
                ("半年新高", ak.stock_rank_cxg_ths, {"symbol": "半年新高"}),
                ("一年新高", ak.stock_rank_cxg_ths, {"symbol": "一年新高"}),
                ("连续上涨", ak.stock_rank_lxsz_ths, {}),
                ("向上突破", ak.stock_rank_xstp_ths, {"symbol": "60日均线"}),
                ("持续放量", ak.stock_rank_cxfl_ths, {}),
                ("持续缩量", ak.stock_rank_cxsl_ths, {}),
                ("量价齐升", ak.stock_rank_ljqs_ths, {}),
                ("险资举牌", ak.stock_rank_xzjp_ths, {}),
                ("创月新低", ak.stock_rank_cxd_ths, {"symbol": "创月新低"}),
                ("向下突破", ak.stock_rank_xxtp_ths, {"symbol": "60日均线"}),
            ]

            with bypass_proxy():
                for label, func, kwargs in tech_tasks:
                    try:
                        # 注意：由于实时并联抓取 11 个榜单较慢，此处未来可加入全局缓存
                        df = func(**kwargs)
                        if df is not None and not df.empty:
                            # 统一查找代码列
                            code_col = '股票代码' if '股票代码' in df.columns else (
                                '代码' if '代码' in df.columns else df.columns[1] # 兜底逻辑
                            )
                            # 判定是否命中
                            if clean_code in df[code_col].astype(str).tolist():
                                row = df[df[code_col].astype(str) == clean_code].iloc[0]
                                rank = row.get('排名', 'N/A')
                                detail = ""
                                if '连续天数' in df.columns:
                                    detail = f" (已持续 {row['连续天数']} 天)"
                                elif '突破均线' in df.columns:
                                    detail = f" (突破 {row['突破均线']})"
                                
                                hits.append(f"- 【{label}】: 处于榜单第 {rank} 名{detail}")
                    except Exception:
                        continue

            if not hits:
                return "技术面分析：目前该股表现平稳，未命中显着的技术极值（如新高、突破、异动放量等）榜单。"
            
            report = "### [!IMPORTANT] 发现以下静默技术面极值异动：\n"
            report += "\n".join(hits)
            report += "\n\n> 注：这些指标代表了当前市场最真实的技术派选股动向，请 AI 务必结合量价进行深度推演。"
            return report
        except Exception as e:
            return f"获取技术指标失败: {e}"

    def get_stock_popularity(self, code: str) -> str:
        """获取近期人气和热度，赋予 LLM 情绪因子的判断基准"""
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            report = ""
            with bypass_proxy():
                try:
                    df = ak.stock_hot_rank_em()
                    if not df.empty and '代码' in df.columns:
                        matched = df[df['代码'] == clean_code]
                        if not matched.empty:
                            rank = matched.iloc[0]['排名']
                            report += f"当前个股在东方财富全市场热度排第 {rank} 名，受高度关注！\n"
                except:
                    pass
            return report if report else "未登上涨幅或绝对热度榜的最前列，属于市场正常关注度。"
        except:
            return ""

    def get_technical_indicators(self, code: str) -> str:
        """静默调用同花顺十大技术指标，寻找极值形态供 LLM 重点剖析"""
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            hits = []
            
            # 使用包含关键因子的字典。若遇到网络错误静默跳过
            indicators = {
                "创新高": ak.stock_rank_cxg_ths,
                "创新低": ak.stock_rank_cxd_ths,
                "持续缩量": ak.stock_rank_cxsl_ths,
                "持续放量": ak.stock_rank_cxfl_ths,
                "量价齐升": ak.stock_rank_ljqs_ths,
                "向上突破": ak.stock_rank_xstp_ths,
                "向下突破": ak.stock_rank_xxtp_ths,
                "连续上涨": ak.stock_rank_lxsz_ths,
                "连续下跌": ak.stock_rank_lxxd_ths
            }
            
            with bypass_proxy():
                for name, func in indicators.items():
                    try:
                        df = func(symbol="全部只数")
                        # 创新高/低等接口通常第一列是代码，或者用通用搜索
                        if not df.empty:
                            # 将全表转字符串查找最快，不拘泥列名
                            if clean_code in df.to_string():
                                hits.append(name)
                    except Exception:
                        pass
                        
            if hits:
                return f"\n> [!IMPORTANT]\n> **🔴 触发技术面极值形态**：当前个股正处于全市场的【{'、'.join(hits)}】专榜中！请你在诊断分析时以此为强因子，重点评估其趋势反转或加速的可能性。"
            return ""
        except:
            return ""

    def get_market_sentiment(self) -> "pd.DataFrame":
        """获取大盘赚钱效应（全市场情绪温度）"""
        try:
            with bypass_proxy():
                df = ak.stock_market_activity_legu()
            return df
        except:
            return None

    def get_industry_board_list(self) -> "pd.DataFrame":
        """获取行业板块列表并补充涨跌幅（同花顺源，兼容代理环境）"""
        try:
            with bypass_proxy():
                # 获取基础列表
                df_name = ak.stock_board_industry_name_ths()
                # 获取涨跌幅汇总
                df_summary = ak.stock_board_industry_summary_ths()
                
                if df_name is not None and not df_name.empty:
                    df_name = df_name.rename(columns={'name': '板块名称', 'code': '板块代码'})
                    if df_summary is not None and not df_summary.empty:
                        # 尝试通过板块名称关联
                        # 同花顺的summary接口列名可能是中文
                        # 映射列名：'板块' -> '板块名称', '涨跌幅' -> '涨跌幅'
                        df_summary = df_summary.rename(columns={
                            df_summary.columns[1]: '板块名称', 
                            df_summary.columns[2]: '涨跌幅'
                        })
                        df = pd.merge(df_name, df_summary[['板块名称', '涨跌幅']], on='板块名称', how='left')
                        return df
                    return df_name
        except Exception as e:
            print(f"同花顺行业板块获取/合并失败: {e}")
            
        # 降级至东方财富
        try:
            with bypass_proxy():
                df = ak.stock_board_industry_name_em()
                if df is not None and not df.empty and '板块名称' in df.columns:
                    return df
        except Exception:
            pass
        return pd.DataFrame()

    def get_concept_board_list(self) -> pd.DataFrame:
        """获取概念板块列表并补充涨跌幅（同花顺源，兼容代理环境）"""
        try:
            with bypass_proxy():
                df_name = ak.stock_board_concept_name_ths()
                df_summary = ak.stock_board_concept_summary_ths()
                
                if df_name is not None and not df_name.empty:
                    df_name = df_name.rename(columns={'name': '板块名称', 'code': '板块代码'})
                    if df_summary is not None and not df_summary.empty:
                        df_summary = df_summary.rename(columns={
                            df_summary.columns[1]: '板块名称', 
                            df_summary.columns[2]: '涨跌幅'
                        })
                        df = pd.merge(df_name, df_summary[['板块名称', '涨跌幅']], on='板块名称', how='left')
                        return df
                    return df_name
        except Exception:
            pass
        # 降级至东方财富
        try:
            with bypass_proxy():
                df = ak.stock_board_concept_name_em()
                if df is not None and not df.empty and '板块名称' in df.columns:
                    return df
        except Exception as e:
            print(f"概念板块获取失败: {e}")
            return pd.DataFrame()
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
        """获取板块成分股（优先EM，失败时用THS板块概要中的领涨股信息）"""
        # 尝试东方财富源
        try:
            with bypass_proxy():
                if board_type == "概念板块":
                    df = ak.stock_board_concept_cons_em(symbol=board_name)
                else:
                    df = ak.stock_board_industry_cons_em(symbol=board_name)

            if not df.empty:
                cols_map = {'代码': '代码', '名称': '名称', '最新价': '最新价', '涨跌幅': '涨跌幅',
                            '涨跌额': '涨跌额', '成交量': '成交量', '成交额': '成交额', '换手率': '换手率'}
                available = [c for c in cols_map.keys() if c in df.columns]
                if '涨跌幅' in df.columns:
                    df = df.sort_values('涨跌幅', ascending=False)
                display_df = df[available].head(top_n)
                return display_df.to_markdown(index=False)
        except Exception:
            pass
        
        # 降级：使用同花顺板块概要获取领涨股等关键信息
        try:
            with bypass_proxy():
                if board_type == "概念板块":
                    summary_df = ak.stock_board_concept_summary_ths()
                else:
                    summary_df = ak.stock_board_industry_summary_ths()
            if summary_df is not None and not summary_df.empty:
                matched = summary_df[summary_df.apply(lambda r: board_name in str(r.values), axis=1)]
                if not matched.empty:
                    row = matched.iloc[0]
                    info = f"| 板块 | 涨跌幅 | 领涨股 | 领涨股涨幅 |\n|---|---|---|---|\n"
                    info += f"| {board_name} | {row.get('涨跌幅', 'N/A')}% | {row.get('领涨股', 'N/A')} | {row.get('领涨股-涨跌幅', 'N/A')}% |\n"
                    return info
        except Exception:
            pass
        
        return "成分股数据暂时无法获取（数据源受限），AI将基于板块历史走势与产业逻辑进行推演。"

    def get_board_history(self, board_name: str, board_type: str = "行业板块", limit: int = 250) -> str:
        """获取板块近期历史行情（同花顺指数优先，兼容代理环境）"""
        # 优先使用同花顺板块指数
        try:
            import datetime
            end_date = datetime.datetime.now().strftime('%Y%m%d')
            start_date = (datetime.datetime.now() - datetime.timedelta(days=limit * 2)).strftime('%Y%m%d')
            with bypass_proxy():
                if board_type == "概念板块":
                    df = ak.stock_board_concept_index_ths(symbol=board_name, start_date=start_date, end_date=end_date)
                else:
                    df = ak.stock_board_industry_index_ths(symbol=board_name, start_date=start_date, end_date=end_date)
            
            if df is not None and not df.empty:
                # THS列名: 日期, 开盘价, 最高价, 最低价, 收盘价, 成交量, 成交额
                df = df.rename(columns={'开盘价': '开盘', '最高价': '最高', '最低价': '最低', '收盘价': '收盘'})
                recent_df = df.tail(limit)
                if not recent_df.empty:
                    max_price = recent_df['最高'].max()
                    min_price = recent_df['最低'].min()
                    current_price = recent_df.iloc[-1]['收盘']
                    
                    trend_md = (
                        f"- **周期统计**: 过去 {len(recent_df)} 个交易日\n"
                        f"- **区间最高**: {max_price}，**区间最低**: {min_price} (当前收盘价 {current_price})\n"
                        f"- **当前位置**: 位于近区间的 {((current_price - min_price) / (max_price - min_price + 0.001)) * 100:.1f}%\n"
                    )
                    sample_df = recent_df.iloc[::20]
                    sample_strs = [f"{str(row['日期'])[:10]}收:{row['收盘']}" for idx, row in sample_df.iterrows()]
                    trend_md += f"- **走势关键点**: {', '.join(sample_strs)}\n"
                    return trend_md
        except Exception:
            pass
        
        # 降级至东方财富
        try:
            with bypass_proxy():
                if board_type == "概念板块":
                    df = ak.stock_board_concept_hist_em(symbol=board_name, period="日k", adjust="")
                else:
                    df = ak.stock_board_industry_hist_em(symbol=board_name, period="日k", adjust="")
            if df is not None and not df.empty:
                recent_df = df.tail(limit)
                max_price = recent_df['最高'].max()
                min_price = recent_df['最低'].min()
                current_price = recent_df.iloc[-1]['收盘']
                trend_md = (
                    f"- **周期统计**: 过去 {len(recent_df)} 个交易日\n"
                    f"- **区间最高**: {max_price}，**区间最低**: {min_price} (当前收盘价 {current_price})\n"
                    f"- **当前位置**: 位于近区间的 {((current_price - min_price) / (max_price - min_price + 0.001)) * 100:.1f}%\n"
                )
                return trend_md
        except Exception:
            pass
        return "板块历史行情数据暂时无法获取。"

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

        context += "## 1. 板块长线历史走势 (近250个交易日)\n"
        context += self.get_board_history(board_name, board_type, limit=250) + "\n\n"

        context += "## 2. 板块核心成分股（按涨跌幅排序 Top10）\n"
        constituents_md = self.get_board_constituents(board_name, board_type)
        context += constituents_md + "\n\n"
        
        # 融入龙虎榜特征（东方财富源，允许静默失败）
        context += "## 3. 板块近期龙虎榜活跃度\n"
        try:
            import datetime
            today_str = datetime.date.today().strftime("%Y%m%d")
            start_str = (datetime.date.today() - datetime.timedelta(days=3)).strftime("%Y%m%d")
            with bypass_proxy():
                lhb_df = ak.stock_lhb_detail_em(start_date=start_str, end_date=today_str)
            if not lhb_df.empty and '名称' in lhb_df.columns:
                board_cons = set()
                if "暂无" not in constituents_md and "无法获取" not in constituents_md:
                    import re
                    board_cons = set(re.findall(r'\|\s*\d+\s*\|\s*([^|]+?)\s*\|', constituents_md))
                lhb_names = set(lhb_df['名称'].tolist())
                matches = board_cons.intersection(lhb_names)
                if matches:
                    context += f"今日龙虎榜中，该板块有以下核心成分股上榜：{', '.join(matches)}\n\n"
                else:
                    context += "今日核心成分股未发现龙虎榜交易异动。\n\n"
            else:
                context += "今日龙虎榜数据暂未获取到。\n\n"
        except Exception:
             context += "龙虎榜数据源暂时不可用。\n\n"

        # 关联子板块数据
        if sub_boards:
            context += "## 4. 关联细分子板块一览\n"
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

        # 加入板块技术面检测
        context += "## 5. 板块技术极值特征 (静默扫描)\n"
        try:
            # 统计板块前10个成分股的极值命中情况
            import re
            board_cons = re.findall(r'\|\s*(\d+)\s*\|', constituents_md)
            if board_cons:
                hit_count = 0
                sample_size = min(len(board_cons), 10)
                # 拿典型的极值榜单做抽样
                with bypass_proxy():
                    high_df = ak.stock_rank_cxg_ths(symbol="半年新高")
                    break_df = ak.stock_rank_xstp_ths(symbol="20日均线")
                
                high_list = high_df['股票代码'].astype(str).tolist() if not high_df.empty else []
                break_list = break_df['股票代码'].astype(str).tolist() if not break_df.empty else []
                
                for c in board_cons[:sample_size]:
                    if c in high_list or c in break_list:
                        hit_count += 1
                
                context += f"抽样检测显示：该板块核心成分股中，约 {int(hit_count/sample_size*100)}% 的股票处于技术极值状态（新高/突破）。\n"
                if hit_count > 0:
                    context += "板块整体技术形态偏强，建议 AI 关注是否存在整体溢价机会。\n"
                else:
                    context += "板块成分股目前技术形态较为温和，建议 AI 从基本面或异动面寻找逻辑。\n"
        except Exception:
            context += "板块技术极值扫描失败。\n"

        # 加入市场整体情绪数据，防止 AI 产生“数据缺失”的错觉
        try:
             sentiment = self.get_market_sentiment()
             if sentiment:
                 context += "## 6. 全市场实时情绪参考\n"
                 context += f"- **上涨/下跌家数**: {sentiment['up']} / {sentiment['down']}\n"
                 context += f"- **全市场赚钱效应**: {sentiment['temperature']:.1f}%\n"
                 context += f"- **全市场成交额**: {sentiment['volume']:.1f} 亿元\n\n"
        except Exception:
             pass

        return context

    def get_realtime_quotes(self, market_type: str) -> "pd.DataFrame":
        """获取全市场实时行情数据并过滤 (新浪源，兼容代理)"""
        try:
            with bypass_proxy():
                df = ak.stock_zh_a_spot()
                if df is None or df.empty:
                    return None
            
            df['代码'] = df['代码'].astype(str)
            # 新浪源代码格式: sh600519, sz000001
            # 提取纯数字代码用于过滤
            df['_code'] = df['代码'].str.replace(r'^(sh|sz|bj)', '', regex=True)
            
            if market_type == "沪深主板":
                result = df[df['_code'].str.startswith(('600', '601', '603', '605', '000', '001', '002', '003'))]
            elif market_type == "创业板":
                result = df[df['_code'].str.startswith(('300', '301'))]
            elif market_type == "科创板":
                result = df[df['_code'].str.startswith('688')]
            elif market_type == "北交所":
                result = df[df['代码'].str.startswith('bj')]
            else:
                result = df
            
            return result.drop(columns=['_code'], errors='ignore')
        except Exception as e:
            print(f"获取实时行情失败: {e}")
            return None

    def get_market_sentiment(self) -> dict:
        """获取全市场情绪统计数据（涨跌家数、成交量等）"""
        try:
            with bypass_proxy():
                df = _fetch_all_spot_cached()
                if df is None or df.empty: return None
                
                up = len(df[df['涨跌幅'] > 0])
                down = len(df[df['涨跌幅'] < 0])
                flat = len(df) - up - down
                total_volume = df['成交额'].sum() / 100000000 # 亿元
                
                # 计算市场温度 (0-100)
                temp = (up / (up + down + 0.1)) * 100
                
                return {
                    'up': up,
                    'down': down,
                    'flat': flat,
                    'volume': total_volume,
                    'temperature': temp,
                    'count': len(df)
                }
        except Exception as e:
            print(f"获取市场情绪失败: {e}")
            return None

@st.cache_data(ttl=60)
def _fetch_all_spot_cached():
    import akshare as ak
    try:
        with bypass_proxy():
            return ak.stock_zh_a_spot()
    except:
        return None

if __name__ == "__main__":
    fetcher = AShareDataFetcher()
    print(fetcher.get_full_analysis_context("600519"))
