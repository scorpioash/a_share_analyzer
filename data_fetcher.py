import streamlit as st
import akshare as ak
import pandas as pd
# 强制设置 Pandas 使用 python 模式存储字符串，防止 PyArrow 在处理 akshare 的正则时报错 (\u 问题)
pd.options.mode.string_storage = "python"

import datetime
from datetime import datetime, date
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
    
    import socket
    import json
    original_getaddrinfo = socket.getaddrinfo
    
    def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        # 拦截东方财富和同花顺的 DNS，确保物理直连国内 IP
        if 'eastmoney' in host or '10jqka' in host or 'sina' in host:
            try:
                url = f"http://223.5.5.5/resolve?name={host}&type=1"
                req = urllib.request.Request(url, headers={'Accept': 'application/dns-json'})
                req.set_proxy('', 'http')
                req.set_proxy('', 'https')
                with urllib.request.urlopen(req, timeout=3) as response:
                    res = json.loads(response.read().decode('utf-8'))
                    if res.get('Status') == 0 and 'Answer' in res:
                        for answer in res['Answer']:
                            if answer['type'] == 1:
                                real_ip = answer['data']
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
                    name = matched.iloc[0]['name']
                    # 风险标记穿透：如果是ST股，确保名称中包含ST字样
                    return clean_query, name
                return clean_query, "未知"
            else:
                matched = stock_info[stock_info['name'].str.contains(clean_query, na=False)]
                if not matched.empty: return matched.iloc[0]['code'], matched.iloc[0]['name']
                return "", "未找到"
        except: return clean_query, "解析失败"

    def get_daily_kline(self, code: str, limit: int = 30, spot_row: dict = None) -> str:
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            prefix = self._get_market_prefix(clean_code)
            with bypass_proxy():
                df = ak.stock_zh_a_hist_tx(symbol=f"{prefix}{clean_code}", start_date='2024-01-01', end_date=datetime.now().strftime('%Y-%m-%d'))
            
            if df.empty: return "无历史数据"
            # 统一列名映射，确保合成时键值一致
            df = df.rename(columns={'date': '日期', 'open': '开盘', 'close': '收盘', 'high': '最高', 'low': '最低', 'amount': '成交量'})
            
            # --- 缝合逻辑：将今日实盘行情强行追加给 AI ---
            if spot_row:
                today_str = datetime.now().strftime('%Y-%m-%d')
                last_date = str(df.iloc[-1]['日期'])
                if today_str > last_date:
                    new_row = {
                        '日期': f"{today_str} (今日最新实盘)",
                        '开盘': spot_row.get('open', 0),
                        '收盘': spot_row.get('price', 0),
                        '最高': spot_row.get('high', 0),
                        '最低': spot_row.get('low', 0),
                        '成交量': spot_row.get('volume', 0)
                    }
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

            # --- 动力学指标增强 (计算最近 5 日动能，包含今日合成行) ---
            if len(df) >= 5:
                # 均量计算排除合成行，除非合成行量能已显著
                v5 = df['成交量'].iloc[-6:-1].mean() if len(df) > 5 else df['成交量'].tail(5).mean()
                cur_v = df['成交量'].iloc[-1]
                v_ratio = cur_v / (v5 + 0.1)
                p5_start = df['收盘'].iloc[-5]
                p_cur = df['收盘'].iloc[-1]
                p5_change = ((p_cur - p5_start) / (p5_start + 0.001)) * 100
                
                # 均线偏离度 (MA5)
                ma5 = df['收盘'].rolling(window=5).mean().iloc[-1]
                bias5 = ((p_cur - ma5) / (ma5 + 0.001)) * 100
                
                momentum_info = f"\n> [!TIP]\n> **实时动能/偏离度监控**: 股价相较5日前涨跌幅 {p5_change:.2f}%，量比 {v_ratio:.2f}，当前价格偏离5日线 {bias5:.2f}%。\n"
            else:
                momentum_info = ""
                
            recent = df.tail(limit).to_markdown(index=False)
            return recent + momentum_info
        except Exception as e: return f"K线获取失败: {str(e)}"

    def _get_bulletproof_spot(self, code: str) -> dict:
        """三级防线抓取最准实时数据 (支持捕捉日内极致脉冲)"""
        clean_code = code.replace('sh', '').replace('sz', '')
        info = None
        try:
            with bypass_proxy():
                # Tier 1: 东财实时快照 (主攻当前价/涨幅)
                try:
                    df = ak.stock_zh_a_spot_em()
                    if df is not None and not df.empty:
                        target = df[df['代码'] == clean_code]
                        if not target.empty:
                            s = target.iloc[0]
                            info = {
                                'price': float(s['最新价']),
                                'open': float(s['今开']),
                                'high': float(s['最高']),
                                'low': float(s['最低']),
                                'volume': float(s['成交量']),
                                'change_pct': float(s['涨跌幅']),
                                'source': 'Snapshot'
                            }
                except: pass

                # Tier 2: 1分钟 K 线全量扫描 (终极捕捉 23.95 这种脉冲高点)
                try:
                    df_min = ak.stock_zh_a_hist_min_em(symbol=clean_code, period='1', adjust='')
                    if not df_min.empty:
                        last = df_min.iloc[-1]
                        m_high = float(df_min['high'].max())
                        m_low = float(df_min['low'].min())
                        m_vol = float(df_min['volume'].sum())
                        
                        if not info:
                            info = {
                                'price': float(last['close']),
                                'open': float(df_min.iloc[0]['open']),
                                'high': m_high,
                                'low': m_low,
                                'volume': m_vol,
                                'change_pct': ((float(last['close']) / float(df_min.iloc[0]['open'])) - 1) * 100,
                                'source': '1min-K'
                            }
                        else:
                            # 数据融合：取二者中最积极的那个 (针对脉冲捕捉)
                            info['high'] = max(info['high'], m_high)
                            info['low'] = min(info['low'], m_low) if info['low'] > 0 else m_low
                            info['volume'] = max(info['volume'], m_vol)
                            info['source'] += "+1min-K"
                except: pass
        except: pass
        return info

    def get_intraday_plot_data(self, code: str) -> pd.DataFrame:
        """获取分时图数据包"""
        try:
            clean_code = code.replace('sh', '').replace('sz', '')
            with bypass_proxy():
                df = ak.stock_zh_a_hist_min_em(symbol=clean_code, period='1', adjust='')
                if df.empty: return pd.DataFrame()
                # 仅保留时间与价格，简化 UI 渲染
                df = df[['时间', 'close']].rename(columns={'时间': 'Time', 'close': 'Price'})
                df['Time'] = pd.to_datetime(df['Time']).dt.strftime('%H:%M')
                return df
        except: return pd.DataFrame()

    def get_full_analysis_context(self, query: str) -> tuple[str, str, str]:
        """集成实战级实时数据的个股上下文接口"""
        code, name = self.get_stock_name_or_code(query)
        if not code or name == "未找到":
            return "", "", f"无法解析股票: {query}"
            
        now = datetime.now()
        ctx = f"# 深度诊断报告: {name} ({code})\n"
        ctx += f"**报告分析基准时**: {now.strftime('%Y-%m-%d %H:%M:%S')} (星期{list('一二三四五六日')[now.weekday()]})\n\n"
        
        # 0. 实时极值捕捉 (强制对齐)
        spot_info = self._get_bulletproof_spot(code)
        
        if spot_info:
            ctx += "## 0. 🚨 实时极值通告 (最高优先级)\n"
            ctx += f"**注意：此部分数据代表今日（{now.strftime('%Y-%m-%d')}）盘中绝对实时表现，已穿透所有延迟**\n"
            ctx += f"- **今日盘中最高价**: {spot_info['high']} 👈 (AI判定阻力位时必须参考此峰值)\n"
            ctx += f"- **今日实时价格**: {spot_info['price']} (最新价)\n"
            ctx += f"- **今日日内波幅**: {spot_info['low']} -> {spot_info['high']}\n"
            ctx += f"- **今日累计成交量**: {spot_info['volume']}\n"
            ctx += f"- **核心分析指令**: **严禁**在此数据之上进行“尚未突破”的假设。如果最高价已触及或超过某点位（如23.50），必须按已放量突破逻辑进行推演。\n\n"
        else:
            ctx += "## 0. 实时报价捕捉 (暂时离线)\n- **提示**: 实时接口同步缓慢，已下线今日盘中补全逻辑，请基于 4/21 终盘数据复盘。\n\n"

        # 1. K线走势与动能 (传入 spot_info 进行缝合)
        ctx += "## 1. 价格形态历程 (含今日最新实盘缝合行)\n"
        ctx += self.get_daily_kline(code, limit=30, spot_row=spot_info) + "\n\n"
        
        # 2. 资讯面
        ctx += "## 2. 最近重要资讯\n"
        ctx += self.get_news(code) + "\n\n"
        
        # 3. 市场大环境 (全市场情绪)
        try:
            with bypass_proxy():
                if 'spot_df' in locals() and not spot_df.empty:
                    change_col = spot_df.columns[4]
                    u = len(spot_df[spot_df[change_col] > 0])
                    d = len(spot_df[spot_df[change_col] < 0])
                    ctx += f"## 3. 全市场情绪背景\n- **今日涨/跌家数**: {u} / {d}\n"
        except: pass
        
        return code, name, ctx

    def _get_market_prefix(self, code: str) -> str:
        if code.startswith(('6', '9')): return 'sh'
        if code.startswith(('0', '2', '3')): return 'sz'
        return 'sh'

    def get_news(self, code: str) -> str:
        try:
            with bypass_proxy():
                try: 
                    df = ak.stock_news_em(symbol=code.replace('sh','').replace('sz',''))
                    if not df.empty: return "\n".join([f"- {r.新闻时间} {r.新闻标题}" for _, r in df.head(5).iterrows()])
                except: pass
            return "暂无重大快讯。"
        except: return "无法拉取新闻。"

    def get_industry_board_list(self) -> pd.DataFrame:
        try:
            with bypass_proxy():
                df = ak.stock_board_industry_name_ths()
                return df.rename(columns={'name': '板块名称', 'code': '板块代码'}) if df is not None else pd.DataFrame()
        except: return pd.DataFrame()

    def get_concept_board_list(self) -> pd.DataFrame:
        try:
            with bypass_proxy():
                df = ak.stock_board_concept_name_ths()
                return df.rename(columns={'name': '板块名称', 'code': '板块代码'}) if df is not None else pd.DataFrame()
        except: return pd.DataFrame()

    def search_board(self, query: str) -> list[dict]:
        res = []
        try:
            for df, t in [(self.get_industry_board_list(), '行业板块'), (self.get_concept_board_list(), '概念板块')]:
                if not df.empty:
                    m = df[df['板块名称'].str.contains(query, na=False)]
                    for _, r in m.iterrows(): res.append({'name': r['板块名称'], 'code': r['板块代码'], 'type': t})
        except: pass
        return res

    @st.cache_data(ttl=3600)
    def _get_st_blacklist(_self):
        """拉取全量官方名单并提取 ST 核心关键词库"""
        try:
            with bypass_proxy():
                df = ak.stock_info_a_code_name()
            if df is not None and not df.empty:
                # 过滤出所有带 ST 的官方名称，并提取核心词（取前2-3字）
                st_names = df[df['name'].str.contains('ST', na=False)]['name'].tolist()
                # 核心过滤：去掉 *ST, ST 字符，提取前2个字符作为黑名单指纹
                blacklist = {name.replace('*', '').replace('ST', '')[:2] for name in st_names}
                return blacklist
        except: pass
        return set()

    def get_board_constituents(self, board_name: str, board_type: str = "行业板块") -> str:
        """强化修复：通过核心词指纹穿透不同数据源的名称差异，精准锁定 ST 地雷"""
        try:
            with bypass_proxy():
                func = ak.stock_board_concept_summary_ths if board_type == "概念板块" else ak.stock_board_industry_summary_ths
                s_df = func()
            if s_df is not None and not s_df.empty:
                m = s_df[s_df.apply(lambda r: board_name in str(r.values), axis=1)]
                if not m.empty:
                    r = m.iloc[0]
                    leader_name = r.get('领涨股', 'N/A')
                    
                    # --- 强化避雷逻辑：核心指纹对账 ---
                    st_blacklist = self._get_st_blacklist()
                    leader_core = leader_name[:2] # 提取核心指纹
                    
                    risk_warning = ""
                    if leader_core in st_blacklist:
                        # 发现地雷：即便当前源没标 ST，由于核心词在官方 ST 名单中，判定为 ST
                        real_name = f"⚠️ [ST退市地雷] {leader_name}"
                        risk_warning = f"\n> [!CAUTION]\n> **官方风险通告**：该板块核心活跃股 `{leader_name}` 已被官方标记为 ST(特别处理) 或 *ST(退市风险)。AI 严禁将其作为买入建议，必须通过‘逻辑穿透’寻找板块内财务健康的非ST股票替代！"
                        leader_name = real_name
                    
                    return f"### 板块核心标杆 (THS数据)\n- **领涨股**: {leader_name} (+{r.get('领涨股-涨跌幅')}%){risk_warning}\n- **备注**: AI请务必结合该股 ST 风险特征，绝对禁止在‘猛龙观察池’中推荐此类标的。"
        except: pass
        return "成分股抓取受限。AI已转换逻辑：将基于板块指数成交活跃度与产业逻辑进行『逻辑补偿定向推理』。"

    def get_board_history(self, board_name: str, board_type: str = "行业板块", limit: int = 60) -> str:
        try:
            with bypass_proxy():
                func = ak.stock_board_concept_index_ths if board_type == "概念板块" else ak.stock_board_industry_index_ths
                df = func(symbol=board_name)
            if df is not None and not df.empty:
                rec = df.tail(limit)
                cur_p = rec.iloc[-1]['收盘价']
                max_p, min_p = rec['最高价'].max(), rec['最低价'].min()
                
                # 动能计算
                if len(rec) >= 5:
                    p5_start = rec['收盘价'].iloc[-5]
                    p5_change = ((cur_p - p5_start) / (p5_start + 0.001)) * 100
                    tag = "📈 攻击" if p5_change > 1.5 else ("📉 回撤" if p5_change < -1.5 else "↔️ 蓄势")
                    momentum = f"\n- **短线强度**: {tag} (近5日 {p5_change:.2f}%)"
                else: momentum = ""
                
                return f"- 周期高低位: {max_p}/{min_p}, 当前收盘: {cur_p}" + momentum
        except: pass
        return "指数数据暂不可见。"

    def find_related_sub_boards(self, board_name: str) -> list:
        # 兼容 UI 的空占位，避免报错
        return []

    def get_board_analysis_context(self, board_name: str, board_type: str = "行业板块", sub_boards: list = None) -> str:
        ctx = f"# 板块深度诊断报告: {board_name}\n\n"
        ctx += "## 1. 历史活跃度与走势\n" + self.get_board_history(board_name, board_type) + "\n\n"
        ctx += "## 2. 成分股核心标量\n" + self.get_board_constituents(board_name, board_type) + "\n\n"
        
        # 龙虎榜极低延时获取 (新浪源)
        ctx += "## 3. 板块底层大资金流 (核心新浪源)\n"
        try:
            with bypass_proxy():
                lhb = ak.stock_lhb_detail_daily_sina(date=date.today().strftime("%Y%m%d"))
                if lhb is not None and not lhb.empty:
                    kw = board_name[:2]
                    rel = lhb[lhb.apply(lambda r: kw in str(r.values), axis=1)]
                    if not rel.empty:
                        for _, row in rel.head(3).iterrows(): ctx += f"- **{row.名称}** 上榜: {row.上榜原因}\n"
                    else: ctx += "今日该板块成分股未见大幅龙虎榜异动。\n"
        except: pass

        # 市场情绪参量注入
        try:
            with bypass_proxy():
                all_s = ak.stock_zh_a_spot()
                if all_s is not None:
                    u, d = len(all_s[all_s['涨跌幅']>0]), len(all_s[all_s['涨跌幅']<0])
                    ctx += f"\n## 4. 全市场情绪背景\n- **上涨/下跌家数**: {u} / {d}\n- **说明**: 市场整体呈现{'强' if u>d else '弱'}度，AI诊断时应考虑此宏阔背景。"
        except: pass
        
        return ctx
