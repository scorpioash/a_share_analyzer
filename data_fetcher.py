import streamlit as st
import akshare as ak
import pandas as pd
pd.options.mode.string_storage = "python"

import datetime
from datetime import datetime, date
import os
import contextlib
import urllib3
import ssl
import logging
import time
import json
import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logger = logging.getLogger("AShareFetcher")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


# ===========================================================================
# EastMoneyDirectAPI — 东财接口直连实现
# ---------------------------------------------------------------------------
# 为什么要自己写:
#   1. akshare 内部对东财的调用有固定的 User-Agent / 域名，TUN 模式下某些 CDN 被拒
#   2. 东财 push 接口有多个数字前缀域名 (82/push2/72/78/push2his)，可轮询容灾
#   3. 浏览器访问东财是能通的,说明关键在于请求头完整度和 TLS 指纹
#   4. 我们自主控制 Session、重试、代理策略,彻底绕过 requests 的代理自动解析 bug
# ===========================================================================
class EastMoneyDirectAPI:
    """直连东财的实时行情接口。TUN 模式/代理环境下更稳定。"""

    # 东财 push 接口有多个可用域名 (CDN 分流),依次轮询
    PUSH_HOSTS = ['push2.eastmoney.com', '82.push2.eastmoney.com',
                  '72.push2.eastmoney.com', '78.push2.eastmoney.com']
    PUSH_HIS_HOSTS = ['push2his.eastmoney.com']

    # 模拟浏览器的完整请求头 (关键:Referer 必须是 eastmoney 下的页面)
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://quote.eastmoney.com/',
        'Origin': 'https://quote.eastmoney.com',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'Connection': 'keep-alive',
    }

    def __init__(self, timeout: int = 10, max_retries: int = 2):
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = None

    def _build_session(self, proxies: dict = None) -> requests.Session:
        """构建独立 session，完全自主控制 TLS/代理/重试"""
        s = requests.Session()
        s.headers.update(self.DEFAULT_HEADERS)

        # 独立的重试策略 (只重试连接错误,不重试 HTTP 错误)
        retry = Retry(
            total=self.max_retries,
            connect=self.max_retries,
            read=0,
            backoff_factor=0.5,
            status_forcelist=[],  # 不重试 HTTP 错误,因为是东财风控
            allowed_methods=['GET'],
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=5, pool_maxsize=5)
        s.mount('http://', adapter)
        s.mount('https://', adapter)

        # 代理配置 —— 支持 3 种策略
        if proxies == "bypass":
            # 明确 bypass:不走任何代理
            s.proxies = {}
            s.trust_env = False   # ⭐ 关键:不读环境变量里的代理
        elif proxies == "system":
            # 跟随系统代理
            s.trust_env = True
        elif isinstance(proxies, dict):
            # 显式指定代理
            s.proxies = proxies
            s.trust_env = False
        else:
            # 默认:follow 环境 (适合 TUN 模式)
            s.trust_env = True

        return s

    def _get(self, host: str, path: str, params: dict, session: requests.Session) -> dict:
        """发一次请求,返回 JSON dict。任何异常向上抛。"""
        url = f"https://{host}{path}"
        # 加 _ 时间戳避免 CDN 缓存
        params = dict(params)
        params['_'] = str(int(time.time() * 1000))
        resp = session.get(url, params=params, timeout=self.timeout, verify=False)
        resp.raise_for_status()
        return resp.json()

    def _try_multi_hosts(self, hosts: list, path: str, params: dict,
                         proxies=None, diag=None) -> dict:
        """依次尝试多个 host,任意一个成功即返回。"""
        last_err = None
        session = self._build_session(proxies=proxies)

        # 为每次调用随机化 host 顺序,避免总打同一个节点
        shuffled = list(hosts)
        random.shuffle(shuffled)

        failed_hosts = []
        for host in shuffled:
            try:
                t0 = time.time()
                data = self._get(host, path, params, session)
                if diag:
                    diag(f"EastMoney {host}{path} ✓ ({time.time()-t0:.2f}s)")
                return data
            except Exception as e:
                last_err = e
                failed_hosts.append(f"{host}:{type(e).__name__}")
                continue

        # 所有 host 都失败才打一条简洁日志 (DEBUG 级别,不污染主日志)
        if diag:
            err_brief = type(last_err).__name__ if last_err else "Unknown"
            diag(f"EastMoney 所有节点失败 ({err_brief}) —— 已自动降级到其他源", "DEBUG")

        raise last_err if last_err else RuntimeError("所有 east host 均失败")

    # ------------------------------------------------------------------
    # API 1: 获取单只股票的实时行情快照
    # ------------------------------------------------------------------
    def get_quote(self, code: str, proxies=None, diag=None) -> dict:
        """
        获取单股实时行情。
        返回字典含: price/open/high/low/volume/change_pct/prev_close/name
        """
        clean_code = code.replace('sh', '').replace('sz', '')
        # secid: 0=深市, 1=沪市 (6 开头为沪市, 0/3 开头为深市)
        market = '1' if clean_code.startswith(('6', '9')) else '0'
        secid = f"{market}.{clean_code}"

        params = {
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
            'invt': '2',
            'fltt': '2',
            'fields': 'f43,f44,f45,f46,f47,f48,f50,f57,f58,f60,f116,f117,f168,f169,f170',
            'secid': secid,
        }
        # f43=最新价 f44=最高 f45=最低 f46=今开 f47=成交量
        # f48=成交额 f50=量比 f57=代码 f58=名称 f60=昨收
        # f116=总市值 f117=流通市值 f168=换手率 f169=涨跌额 f170=涨跌幅

        data = self._try_multi_hosts(
            self.PUSH_HOSTS, '/api/qt/stock/get', params,
            proxies=proxies, diag=diag
        )

        d = data.get('data') or {}
        if not d:
            raise RuntimeError(f"东财接口返回空: {data}")

        def _num(v):
            if v in (None, '-', ''):
                return None
            try:
                return float(v)
            except Exception:
                return None

        return {
            'code': d.get('f57', clean_code),
            'name': d.get('f58', ''),
            'price': _num(d.get('f43')),
            'high': _num(d.get('f44')),
            'low': _num(d.get('f45')),
            'open': _num(d.get('f46')),
            'volume': _num(d.get('f47')),
            'amount': _num(d.get('f48')),
            'prev_close': _num(d.get('f60')),
            'change_pct': _num(d.get('f170')),
            'change_amt': _num(d.get('f169')),
            'source': 'EM-Direct',
        }

    # ------------------------------------------------------------------
    # API 2: 获取分时数据 (今日)
    # ------------------------------------------------------------------
    def get_intraday(self, code: str, proxies=None, diag=None) -> pd.DataFrame:
        """
        获取今日 1 分钟分时数据。
        返回 DataFrame 含: Time/Price/Volume/AvgPrice
        """
        clean_code = code.replace('sh', '').replace('sz', '')
        market = '1' if clean_code.startswith(('6', '9')) else '0'
        secid = f"{market}.{clean_code}"

        params = {
            'fields1': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58',
            'ut': '7eea3edcaed734bea9cbfc24409ed989',
            'ndays': '1',  # 只要今日
            'iscr': '0',
            'iscca': '0',
            'secid': secid,
        }

        data = self._try_multi_hosts(
            self.PUSH_HIS_HOSTS, '/api/qt/stock/trends2/get', params,
            proxies=proxies, diag=diag
        )

        d = data.get('data') or {}
        trends = d.get('trends') or []
        if not trends:
            return pd.DataFrame()

        # 每条格式: "2026-04-22 09:31,price,open,high,low,volume,amount,avgprice"
        rows = []
        for line in trends:
            parts = line.split(',')
            if len(parts) >= 8:
                try:
                    rows.append({
                        'Time': parts[0],
                        'Price': float(parts[2]),
                        'Volume': float(parts[5]),
                        'AvgPrice': float(parts[7]),
                    })
                except Exception:
                    continue

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        # 过滤今日 (防御性,东财本身 ndays=1 已经是今日)
        today = datetime.now().strftime('%Y-%m-%d')
        df['_dt'] = pd.to_datetime(df['Time'], errors='coerce')
        df = df[df['_dt'].dt.strftime('%Y-%m-%d') == today].drop(columns=['_dt'])
        df['Time'] = pd.to_datetime(df['Time']).dt.strftime('%H:%M')
        return df.reset_index(drop=True)


# 全局单例
_em_api = EastMoneyDirectAPI()


# ===========================================================================
# ClashHelper — 探测本地 Clash/Mihomo,生成配置片段供用户复制
# ---------------------------------------------------------------------------
# 现实:
#   Clash/Mihomo 的规则热注入 API 在不同版本/分支(Premium/Meta/Mihomo)
#   行为不一致,有些版本的 PUT /configs 会清空整个规则表,非常危险。
#   所以本类不做"偷偷注入"、不改用户配置文件,只做两件事:
#     1. 检测 Clash 是否运行,拿到代理组列表
#     2. 生成可直接复制的 YAML 片段,引导用户自己加到配置里
# ===========================================================================
class ClashHelper:
    EASTMONEY_DOMAINS = [
        'eastmoney.com',
        'push2.eastmoney.com',
        'push2his.eastmoney.com',
        '82.push2.eastmoney.com',
        '72.push2.eastmoney.com',
        '78.push2.eastmoney.com',
        'quote.eastmoney.com',
    ]

    # 常见 Clash 系控制端口
    COMMON_API_URLS = [
        'http://127.0.0.1:9090',
        'http://127.0.0.1:9097',   # 某些 ClashX 变体
        'http://127.0.0.1:59090',  # ClashMeta 某些发行版
    ]

    def __init__(self):
        self._detected_url = None
        self._detected_groups = []

    def detect(self, timeout: float = 1.0) -> dict:
        """快速探测 (<2s),返回 {found, api_url, version, groups, rules_count}"""
        result = {'found': False, 'api_url': None, 'version': None,
                  'groups': [], 'rules_count': 0}
        # 允许用户通过环境变量覆盖
        candidates = [os.environ.get("CLASH_API_URL")] if os.environ.get("CLASH_API_URL") else []
        candidates += self.COMMON_API_URLS
        for url in candidates:
            if not url:
                continue
            url = url.rstrip('/')
            try:
                s = requests.Session()
                s.trust_env = False
                s.proxies = {}
                resp = s.get(f"{url}/version", timeout=timeout)
                if resp.status_code != 200:
                    continue
                result['found'] = True
                result['api_url'] = url
                try:
                    result['version'] = resp.json().get('version', 'unknown')
                except Exception:
                    pass
                # 拉代理组
                try:
                    r2 = s.get(f"{url}/proxies", timeout=timeout + 1)
                    if r2.status_code == 200:
                        p = r2.json().get('proxies', {})
                        result['groups'] = [
                            name for name, info in p.items()
                            if info.get('type') in ('Selector', 'URLTest', 'Fallback', 'LoadBalance')
                        ]
                except Exception:
                    pass
                # 拉规则数
                try:
                    r3 = s.get(f"{url}/rules", timeout=timeout + 1)
                    if r3.status_code == 200:
                        result['rules_count'] = len(r3.json().get('rules', []))
                except Exception:
                    pass
                self._detected_url = url
                self._detected_groups = result['groups']
                return result
            except Exception:
                continue
        return result

    def suggest_group(self) -> str:
        if not self._detected_groups:
            return "PROXY"
        for kw in ['节点选择', '手动选择', 'PROXY', 'Proxy', 'Select', '代理']:
            for g in self._detected_groups:
                if kw.lower() in g.lower() or kw in g:
                    return g
        return self._detected_groups[0]

    def rule_snippet_yaml(self, target_group: str = None) -> str:
        """生成 Clash YAML 格式的 rules 片段"""
        g = target_group or self.suggest_group()
        lines = [f"  - DOMAIN-SUFFIX,{d},{g}" for d in self.EASTMONEY_DOMAINS]
        return "\n".join(lines)


_clash_helper = ClashHelper()


# ===========================================================================
# 代理策略辅助工具
# ===========================================================================
def _get_proxy_strategy(strategy: str = None) -> object:
    """根据 AK_NET_MODE 环境变量返回对应的代理策略给 EastMoneyDirectAPI。

    AK_NET_MODE 值:
        system  - 跟随系统代理 (TUN 模式 / 智能分流 推荐)⭐
        bypass  - 完全不走代理 (国内网络直连)
        force   - 强制使用 AK_PROXY_URL 指定的代理 (绕过 PAC 分流规则)
    """
    if strategy is None:
        strategy = os.environ.get("AK_NET_MODE", "system").lower()

    if strategy == "bypass":
        return "bypass"
    if strategy == "force":
        proxy_url = os.environ.get("AK_PROXY_URL", "http://127.0.0.1:7890")
        if not proxy_url.startswith(('http://', 'https://', 'socks5://', 'socks5h://')):
            proxy_url = 'http://' + proxy_url
        return {"http": proxy_url, "https": proxy_url}
    # system 或默认
    return "system"




@contextlib.contextmanager
def bypass_proxy(enable_dns_hijack: bool = True, mode: str = "auto"):
    """智能代理管理上下文。
    
    mode 参数:
        "bypass"  - 强制绕过所有代理（旧行为，纯国内直连）
        "use"     - 强制使用系统代理（全局代理/智能分流用户）
        "auto"    - 自动：读取 AK_NET_MODE 环境变量，未设则用 bypass
        "keep"    - 保持当前环境不变（不碰代理设置）
    
    enable_dns_hijack: 是否启用阿里 DoH 劫持东财/新浪/同花顺 DNS
    
    环境变量覆盖:
        AK_NET_MODE=use     # 全局代理用户用这个
        AK_NET_MODE=bypass  # 默认行为
        AK_NET_MODE=keep    # 智能分流/PAC 用户用这个(最推荐)
        AK_DNS_HIJACK=0     # 关闭 DNS 劫持
    """
    # 从环境变量读配置（允许运行时动态调整，不改代码）
    if mode == "auto":
        mode = os.environ.get("AK_NET_MODE", "bypass").lower()
    if os.environ.get("AK_DNS_HIJACK", "").strip() == "0":
        enable_dns_hijack = False

    # keep 模式：啥都不动,直接 yield
    if mode == "keep":
        yield
        return

    # use 模式：保留代理，只关 DNS 劫持（代理会自己解析域名）
    if mode == "use":
        import urllib.request
        import socket
        original_getaddrinfo = socket.getaddrinfo
        # use 模式下不做任何 DNS 劫持，让代理处理
        try:
            yield
        finally:
            pass
        return

    # bypass 模式（默认,原逻辑）：清代理环境变量 + 可选 DNS 劫持
    proxy_keys = ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']
    saved_env = {}
    for k in proxy_keys:
        if k in os.environ:
            saved_env[k] = os.environ.pop(k)

    saved_no_proxy = os.environ.get('NO_PROXY')
    saved_no_proxy_lower = os.environ.get('no_proxy')
    os.environ['NO_PROXY'] = '*'
    os.environ['no_proxy'] = '*'

    import urllib.request
    original_getproxies = urllib.request.getproxies
    urllib.request.getproxies = lambda: {}

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
            headers['User-Agent'] = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                    '(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36')
        kwargs['headers'] = headers
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 15
        return original_request(self, method, url, **kwargs)

    requests.Session.merge_environment_settings = proxy_blocking_merge
    requests.Session.request = user_agent_request

    import socket
    import json
    original_getaddrinfo = socket.getaddrinfo

    def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if enable_dns_hijack and ('eastmoney' in host or '10jqka' in host or 'sina' in host):
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
                                return [(socket.AF_INET, socket.SOCK_STREAM,
                                         socket.IPPROTO_TCP, '', (real_ip, port))]
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
        self._spot_df_cache = None
        self._last_diagnostics = []

    # ------------------------------------------------------------------
    # 诊断日志
    # ------------------------------------------------------------------
    def _diag(self, msg: str, level: str = "INFO"):
        stamp = datetime.now().strftime("%H:%M:%S")
        self._last_diagnostics.append(f"[{stamp}] [{level}] {msg}")
        # DEBUG 级别不打控制台,只保留在 _last_diagnostics 供诊断面板查看
        level_fn = {
            'ERROR': logger.error,
            'WARN': logger.warning,
            'INFO': logger.info,
            'DEBUG': logger.debug,
        }.get(level, logger.info)
        level_fn(msg)

    def get_last_diagnostics(self) -> list:
        return list(self._last_diagnostics)

    # ------------------------------------------------------------------
    # 基础
    # ------------------------------------------------------------------
    def get_stock_name_or_code(self, query: str):
        clean_query = query.lower().replace('sh', '').replace('sz', '').strip()
        try:
            with bypass_proxy():
                stock_info = ak.stock_info_a_code_name()
            if clean_query.isdigit():
                matched = stock_info[stock_info['code'] == clean_query]
                if not matched.empty:
                    return clean_query, matched.iloc[0]['name']
                return clean_query, "未知"
            else:
                matched = stock_info[stock_info['name'].str.contains(clean_query, na=False)]
                if not matched.empty:
                    return matched.iloc[0]['code'], matched.iloc[0]['name']
                return "", "未找到"
        except Exception as e:
            self._diag(f"股票名/码解析失败: {e}", "ERROR")
            return clean_query, "解析失败"

    def _fetch_market_spot(self) -> pd.DataFrame:
        """抓全市场快照 (用于市场情绪分析)。
        东财版在代理下常失败,自动回落到新浪版。"""
        if self._spot_df_cache is not None and not self._spot_df_cache.empty:
            return self._spot_df_cache
        # 先试东财 (快,但代理下常挂)
        try:
            with bypass_proxy():
                df = ak.stock_zh_a_spot_em()
                if df is not None and not df.empty:
                    self._spot_df_cache = df
                    return df
        except Exception as e:
            self._diag(f"东财全市场快照跳过: {type(e).__name__}", "DEBUG")
        # 回落新浪 (慢一点,但代理友好)
        try:
            with bypass_proxy():
                if hasattr(ak, 'stock_zh_a_spot'):
                    df = ak.stock_zh_a_spot()
                    if df is not None and not df.empty:
                        self._spot_df_cache = df
                        return df
        except Exception as e:
            self._diag(f"新浪全市场快照也失败: {type(e).__name__}", "WARN")
        return pd.DataFrame()

    # ==================================================================
    # 核心：实时快照 —— 新浪主源 + 腾讯补位 + 东财可选
    # 设计原则:东财推送接口(push2his.eastmoney.com)在 TUN/PAC 代理下常被拒,
    # 新浪和腾讯的股票接口是普通股民日常访问的主站,通常不会被代理规则拦截。
    # ==================================================================
    def _get_bulletproof_spot(self, code: str):
        clean_code = code.replace('sh', '').replace('sz', '')
        prefix = self._get_market_prefix(clean_code)
        info = {}
        success_tiers = []
        today_str = datetime.now().strftime('%Y-%m-%d')

        def _merge(new_info: dict, src: str):
            if not new_info:
                return
            if not info:
                info.update(new_info)
                info['source'] = src
            else:
                if new_info.get('high'):
                    info['high'] = max(info.get('high', 0), new_info['high'])
                if new_info.get('low') and new_info['low'] > 0:
                    info['low'] = min(info['low'], new_info['low']) if info.get('low', 0) > 0 else new_info['low']
                if new_info.get('volume'):
                    info['volume'] = max(info.get('volume', 0), new_info['volume'])
                if new_info.get('price'):
                    info['price'] = new_info['price']
                if not info.get('prev_close') and new_info.get('prev_close'):
                    info['prev_close'] = new_info['prev_close']
                info['source'] = info.get('source', '') + '+' + src

        # ---------- Source P0: 东财直连 (自主实现,TUN 模式最稳) ⭐ ----------
        # 用自己写的 session,完全绕过 akshare 内部 requests 的代理怪癖
        # 多域名轮询 + 完整浏览器头 + TUN 模式友好
        t0 = time.time()
        try:
            proxies = _get_proxy_strategy()
            quote = _em_api.get_quote(
                code=clean_code,
                proxies=proxies,
                diag=self._diag,
            )
            if quote and quote.get('price') and quote['price'] > 0:
                p0 = {
                    'price': quote['price'],
                    'open': quote.get('open') or 0,
                    'high': quote.get('high') or 0,
                    'low': quote.get('low') or 0,
                    'volume': quote.get('volume') or 0,
                    'change_pct': quote.get('change_pct') or 0,
                    'prev_close': quote.get('prev_close'),
                }
                _merge(p0, 'EM-Direct')
                success_tiers.append('EM-Direct')
                self._diag(f"P0 东财直连 ✓ price={p0['price']} high={p0['high']} "
                          f"change={p0['change_pct']}% ({time.time()-t0:.2f}s)")
        except Exception as e:
            # 东财对代理环境常不友好,失败是预期内的,降到 DEBUG
            self._diag(f"P0 东财直连跳过: {type(e).__name__}", "DEBUG")

        # ---------- Source P1: 新浪实时行情 (主源,TUN/PAC 友好) ----------
        # stock_individual_spot_xq 或 stock_zh_a_spot_sina,后者是全市场快照返回大,
        # 用 stock_bid_ask_em 作为东财补位 — 但我们先尝试新浪的个股接口
        t0 = time.time()
        try:
            with bypass_proxy():
                # 用雪球个股实时 (基础设施稳,TUN 友好)
                if hasattr(ak, 'stock_individual_spot_xq'):
                    try:
                        df_xq = ak.stock_individual_spot_xq(symbol=f"{prefix.upper()}{clean_code}")
                        if df_xq is not None and not df_xq.empty:
                            d = dict(zip(df_xq['item'], df_xq['value']))
                            p1 = {
                                'price': float(d.get('现价', 0) or 0),
                                'open': float(d.get('今开', 0) or 0),
                                'high': float(d.get('最高', 0) or 0),
                                'low': float(d.get('最低', 0) or 0),
                                'volume': float(d.get('成交量', 0) or 0),
                                'change_pct': float(d.get('涨幅', 0) or 0),
                                'prev_close': float(d.get('昨收', 0) or 0) or None,
                            }
                            if p1['price'] > 0:
                                _merge(p1, 'XueQiu')
                                success_tiers.append('XueQiu')
                                self._diag(f"P1 雪球个股 ✓ price={p1['price']} high={p1['high']} ({time.time()-t0:.2f}s)")
                    except Exception as e:
                        self._diag(f"P1 雪球个股异常: {type(e).__name__}: {e}", "WARN")
        except Exception as e:
            self._diag(f"P1 外层异常: {type(e).__name__}: {e}", "WARN")

        # ---------- Source P2: 新浪全市场快照 ----------
        if not info:
            t0 = time.time()
            try:
                with bypass_proxy():
                    if hasattr(ak, 'stock_zh_a_spot'):
                        df = ak.stock_zh_a_spot()
                        if df is not None and not df.empty:
                            # 兼容不同的代码列名
                            code_col = None
                            for c in ['代码', 'code', 'symbol']:
                                if c in df.columns:
                                    code_col = c
                                    break
                            if code_col:
                                full_code = f"{prefix}{clean_code}"
                                # 新浪代码通常带 sh/sz 前缀
                                target = df[df[code_col].isin([full_code, clean_code])]
                                if not target.empty:
                                    s = target.iloc[0]
                                    p2 = {
                                        'price': float(s.get('最新价', 0) or 0),
                                        'open': float(s.get('今开', s.get('开盘价', 0)) or 0),
                                        'high': float(s.get('最高', 0) or 0),
                                        'low': float(s.get('最低', 0) or 0),
                                        'volume': float(s.get('成交量', 0) or 0),
                                        'change_pct': float(s.get('涨跌幅', 0) or 0),
                                        'prev_close': float(s.get('昨收', 0) or 0) or None,
                                    }
                                    if p2['price'] > 0:
                                        _merge(p2, 'SinaSpot')
                                        success_tiers.append('SinaSpot')
                                        self._diag(f"P2 新浪快照 ✓ price={p2['price']} ({time.time()-t0:.2f}s)")
            except Exception as e:
                self._diag(f"P2 新浪快照异常: {type(e).__name__}: {e}", "WARN")

        # ---------- Source P3: 新浪日内分时 (拿今日最新分钟,可靠今日数据) ----------
        # 从分时数据推算当前价/今日高低
        if not info or not info.get('high'):
            t0 = time.time()
            try:
                with bypass_proxy():
                    if hasattr(ak, 'stock_intraday_sina'):
                        try:
                            df_sina_min = ak.stock_intraday_sina(
                                symbol=f"{prefix}{clean_code}",
                                date=today_str.replace('-', '')
                            )
                            if df_sina_min is not None and not df_sina_min.empty:
                                # 检查是否今日数据
                                date_col = None
                                for c in ['date', 'ticktime', '日期', '时间']:
                                    if c in df_sina_min.columns:
                                        date_col = c
                                        break
                                price_col = None
                                for c in ['price', '成交价', 'close']:
                                    if c in df_sina_min.columns:
                                        price_col = c
                                        break
                                vol_col = None
                                for c in ['volume', '成交量']:
                                    if c in df_sina_min.columns:
                                        vol_col = c
                                        break
                                if price_col:
                                    prices = pd.to_numeric(df_sina_min[price_col], errors='coerce').dropna()
                                    vols = pd.to_numeric(df_sina_min[vol_col], errors='coerce').dropna() if vol_col else None
                                    if not prices.empty:
                                        p3 = {
                                            'price': float(prices.iloc[-1]),
                                            'open': float(prices.iloc[0]),
                                            'high': float(prices.max()),
                                            'low': float(prices.min()),
                                            'volume': float(vols.sum()) if vols is not None else 0,
                                        }
                                        _merge(p3, 'SinaIntraday')
                                        success_tiers.append('SinaIntraday')
                                        self._diag(f"P3 新浪今日分时 ✓ N={len(df_sina_min)} price={p3['price']} ({time.time()-t0:.2f}s)")
                        except Exception as e:
                            self._diag(f"P3 新浪分时异常: {type(e).__name__}: {e}", "WARN")
            except Exception as e:
                self._diag(f"P3 外层异常: {type(e).__name__}: {e}", "WARN")

        # ---------- Source P4: 腾讯日线 (补 prev_close 用,本身不是今日实时) ----------
        if not info.get('prev_close'):
            try:
                with bypass_proxy():
                    df_tx = ak.stock_zh_a_hist_tx(
                        symbol=f"{prefix}{clean_code}",
                        start_date='2024-01-01',
                        end_date=today_str
                    )
                    if df_tx is not None and not df_tx.empty and len(df_tx) >= 2:
                        last_row = df_tx.iloc[-1]
                        prev_row = df_tx.iloc[-2]
                        # 如果腾讯日线最后一行是今日,说明收盘后拿到了今日日线,昨收是倒数第二
                        last_date = str(last_row.get('date', '')).strip()
                        if last_date == today_str:
                            info['prev_close'] = float(prev_row.get('close', 0) or 0) or None
                            self._diag(f"P4 腾讯日线补充 prev_close={info.get('prev_close')} (来自昨日收盘)")
                            # 如果还没有 price,用腾讯日线最后一行(可能是今日收盘)
                            if not info.get('price'):
                                info['price'] = float(last_row.get('close', 0) or 0)
                                info['open'] = float(last_row.get('open', 0) or 0)
                                info['high'] = float(last_row.get('high', 0) or 0)
                                info['low'] = float(last_row.get('low', 0) or 0)
                                info['source'] = info.get('source', '') + '+TX-Daily(today)'
                                success_tiers.append('TX-Daily(today)')
                        else:
                            # 最后一行不是今日,盘中东财/新浪都失败时才用这个
                            if not info:
                                info['price'] = float(last_row.get('close', 0) or 0)
                                info['open'] = float(last_row.get('open', 0) or 0)
                                info['high'] = float(last_row.get('high', 0) or 0)
                                info['low'] = float(last_row.get('low', 0) or 0)
                                info['prev_close'] = float(prev_row.get('close', 0) or 0) or None
                                info['source'] = 'TX-Daily(stale-last-trading-day)'
                                success_tiers.append('TX-Daily(stale)')
                                self._diag(f"P4 腾讯日线兜底 ⚠️ 非今日数据,last={last_date}", "WARN")
                            else:
                                info['prev_close'] = float(last_row.get('close', 0) or 0) or None
                                self._diag(f"P4 腾讯日线补充 prev_close={info.get('prev_close')} (最后一个交易日)")
            except Exception as e:
                self._diag(f"P4 腾讯日线异常: {type(e).__name__}: {e}", "WARN")

        # ---------- Source P5: 东财 (可选增强,如果前几层都成功了就跳过) ----------
        # 东财仅在 AK_ENABLE_EASTMONEY=1 时启用(默认关,避免 PAC/TUN 卡死)
        if os.environ.get("AK_ENABLE_EASTMONEY", "1") == "1" and not info:
            t0 = time.time()
            try:
                with bypass_proxy():
                    df = ak.stock_zh_a_spot_em()
                    if df is not None and not df.empty:
                        self._spot_df_cache = df
                        target = df[df['代码'] == clean_code]
                        if not target.empty:
                            s = target.iloc[0]
                            prev_close = None
                            for key in ['昨收', '昨收价', '前收盘']:
                                if key in s.index:
                                    try:
                                        prev_close = float(s[key])
                                        break
                                    except Exception:
                                        pass
                            p5 = {
                                'price': float(s['最新价']),
                                'open': float(s['今开']),
                                'high': float(s['最高']),
                                'low': float(s['最低']),
                                'volume': float(s['成交量']),
                                'change_pct': float(s['涨跌幅']),
                                'prev_close': prev_close,
                            }
                            _merge(p5, 'EM-Spot')
                            success_tiers.append('EM-Spot')
                            self._diag(f"P5 东财快照 ✓ price={p5['price']} ({time.time()-t0:.2f}s)")
            except Exception as e:
                self._diag(f"P5 东财快照异常(东财对 TUN/PAC 代理不友好,正常现象): "
                          f"{type(e).__name__}: {e}", "WARN")

        if info and info.get('price', 0) > 0:
            # 补全所有字段
            defaults = {
                'price': 0, 'open': 0, 'high': 0, 'low': 0,
                'volume': 0, 'change_pct': 0, 'prev_close': None, 'source': ''
            }
            for k, v in defaults.items():
                if k not in info:
                    info[k] = v
            # 如果 change_pct 没被填充,且有 price + prev_close,自动算
            if info['change_pct'] == 0 and info.get('prev_close') and info['prev_close'] > 0:
                info['change_pct'] = round(
                    (info['price'] - info['prev_close']) / info['prev_close'] * 100, 2
                )
            # 标注数据是否今日
            is_stale = 'stale' in info.get('source', '').lower()
            info['is_today'] = not is_stale
            self._diag(f"最终成功 source={info.get('source')} 今日={info['is_today']} 命中={success_tiers}")
            return info

        self._diag("所有数据源均失败，实时报价不可得", "ERROR")
        return None

    # ==================================================================
    # 日 K 线
    # ==================================================================
    def get_daily_kline(self, code: str, limit: int = 30, spot_row: dict = None):
        try:
            clean_code = code.lower().replace('sh', '').replace('sz', '')
            prefix = self._get_market_prefix(clean_code)
            with bypass_proxy():
                df = ak.stock_zh_a_hist_tx(
                    symbol=f"{prefix}{clean_code}",
                    start_date='2024-01-01',
                    end_date=datetime.now().strftime('%Y-%m-%d')
                )
            if df.empty:
                return "无历史数据", pd.DataFrame()

            df = df.rename(columns={
                'date': '日期', 'open': '开盘', 'close': '收盘',
                'high': '最高', 'low': '最低', 'amount': '成交量'
            })

            if spot_row:
                today_str = datetime.now().strftime('%Y-%m-%d')
                last_date = str(df.iloc[-1]['日期'])
                new_row = {
                    '日期': f"{today_str} (今日最新实盘)",
                    '开盘': spot_row.get('open', 0),
                    '收盘': spot_row.get('price', 0),
                    '最高': spot_row.get('high', 0),
                    '最低': spot_row.get('low', 0),
                    '成交量': spot_row.get('volume', 0)
                }
                if today_str in last_date:
                    for col in ['开盘', '收盘', '最高', '最低', '成交量']:
                        df.iloc[-1, df.columns.get_loc(col)] = new_row[col]
                    df.iloc[-1, df.columns.get_loc('日期')] = new_row['日期']
                else:
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

            momentum_info = ""
            if len(df) >= 5:
                v5 = df['成交量'].iloc[-6:-1].mean() if len(df) > 5 else df['成交量'].tail(5).mean()
                cur_v = df['成交量'].iloc[-1]
                v_ratio = cur_v / (v5 + 0.1)
                p5_start = df['收盘'].iloc[-5]
                p_cur = df['收盘'].iloc[-1]
                p5_change = ((p_cur - p5_start) / (p5_start + 0.001)) * 100
                ma5 = df['收盘'].rolling(window=5).mean().iloc[-1]
                bias5 = ((p_cur - ma5) / (ma5 + 0.001)) * 100
                momentum_info = (
                    f"\n> [!TIP]\n> **实时动能/偏离度监控**: 股价相较5日前涨跌幅 "
                    f"{p5_change:.2f}%，量比 {v_ratio:.2f}，当前价格偏离5日线 {bias5:.2f}%。\n"
                )
            recent = df.tail(limit).to_markdown(index=False)
            return recent + momentum_info, df
        except Exception as e:
            self._diag(f"K线抓取失败: {e}", "ERROR")
            return f"K线获取失败: {str(e)}", pd.DataFrame()

    def _calc_key_levels(self, daily_df: pd.DataFrame, lookback: int = 20):
        try:
            if daily_df.empty or len(daily_df) < 5:
                return {}
            recent = daily_df.tail(lookback)
            highs = pd.to_numeric(recent['最高'], errors='coerce').dropna()
            lows = pd.to_numeric(recent['最低'], errors='coerce').dropna()
            closes = pd.to_numeric(recent['收盘'], errors='coerce').dropna()
            if highs.empty:
                return {}
            return {
                'resistance': float(highs.iloc[:-1].max()) if len(highs) > 1 else float(highs.max()),
                'support': float(lows.iloc[:-1].min()) if len(lows) > 1 else float(lows.min()),
                'ma5': float(closes.rolling(window=5).mean().iloc[-1]) if len(closes) >= 5 else None,
                'ma10': float(closes.rolling(window=10).mean().iloc[-1]) if len(closes) >= 10 else None,
                'ma20': float(closes.rolling(window=20).mean().iloc[-1]) if len(closes) >= 20 else None,
            }
        except Exception:
            return {}

    # ==================================================================
    # 分时 —— 新浪优先(TUN/PAC 友好), 东财可选, 强制过滤今日
    # ==================================================================
    def get_intraday_plot_data(self, code: str) -> pd.DataFrame:
        clean_code = code.replace('sh', '').replace('sz', '')
        prefix = self._get_market_prefix(clean_code)
        today_str = datetime.now().strftime('%Y-%m-%d')

        # ---- P0: 东财直连分时 (自主实现,TUN 模式最稳) ⭐ ----
        try:
            proxies = _get_proxy_strategy()
            df = _em_api.get_intraday(
                code=clean_code,
                proxies=proxies,
                diag=self._diag,
            )
            if df is not None and not df.empty:
                self._diag(f"分时来源: 东财直连 (今日N={len(df)}) ✓")
                return df
        except Exception as e:
            self._diag(f"分时 P0 东财直连跳过: {type(e).__name__}", "DEBUG")

        # P1: 新浪日内分时 (可指定日期,最可靠)
        try:
            with bypass_proxy():
                if hasattr(ak, 'stock_intraday_sina'):
                    df = ak.stock_intraday_sina(
                        symbol=f"{prefix}{clean_code}",
                        date=today_str.replace('-', '')
                    )
                    if df is not None and not df.empty:
                        self._diag(f"分时 P1 新浪日内 原始N={len(df)}")
                        # 新浪 stock_intraday_sina 返回列: ticktime/price/volume/prev_price/kind
                        # 转成标准格式
                        out = self._format_sina_intraday(df)
                        if not out.empty:
                            self._diag(f"分时来源: 新浪日内 (今日N={len(out)}) ✓")
                            return out
        except Exception as e:
            self._diag(f"分时 P1 新浪日内 失败: {type(e).__name__}: {e}", "WARN")

        # P2: 新浪分钟 (返回多日,必须过滤今日)
        try:
            with bypass_proxy():
                if hasattr(ak, 'stock_zh_a_minute'):
                    df = ak.stock_zh_a_minute(symbol=f"{prefix}{clean_code}", period='1', adjust='')
                    if df is not None and not df.empty:
                        self._diag(f"分时 P2 新浪分钟 原始N={len(df)} (含多日,过滤今日)")
                        df = df.rename(columns={'day': '时间'})
                        out = self._format_intraday(df, filter_today=True)
                        if not out.empty:
                            self._diag(f"分时来源: 新浪分钟 (今日N={len(out)}) ✓")
                            return out
                        self._diag("新浪分钟过滤后无今日数据", "WARN")
        except Exception as e:
            self._diag(f"分时 P2 新浪分钟 失败: {type(e).__name__}: {e}", "WARN")

        # P3: 东财 1min (可选,AK_ENABLE_EASTMONEY=0 关闭)
        if os.environ.get("AK_ENABLE_EASTMONEY", "1") == "1":
            try:
                with bypass_proxy():
                    df = ak.stock_zh_a_hist_min_em(symbol=clean_code, period='1', adjust='')
                if df is not None and not df.empty:
                    self._diag(f"分时 P3 东财 原始N={len(df)}")
                    out = self._format_intraday(df, filter_today=True)
                    if not out.empty:
                        self._diag(f"分时来源: 东财 1min (今日N={len(out)}) ✓")
                        return out
                    self._diag("东财返回数据但无今日记录,继续降级", "WARN")
            except Exception as e:
                self._diag(f"分时 P3 东财 失败(TUN/PAC 下常见): {type(e).__name__}: {e}", "WARN")

        self._diag("分时数据全源失败或无今日数据", "ERROR")
        return pd.DataFrame()

    @staticmethod
    def _format_sina_intraday(df: pd.DataFrame) -> pd.DataFrame:
        """新浪 stock_intraday_sina 返回格式: ticktime/price/volume/prev_price/kind
        转成标准分时: Time/Price/Volume/AvgPrice
        """
        try:
            out = df.copy()
            col_map = {}
            for c in out.columns:
                cl = str(c).lower().strip()
                if cl in ('ticktime', 'time', '时间', 'day'):
                    col_map[c] = 'Time'
                elif cl in ('price', '成交价', 'close', '最新价', '现价'):
                    col_map[c] = 'Price'
                elif cl in ('volume', '成交量', 'vol'):
                    col_map[c] = 'Volume'
            out = out.rename(columns=col_map)
            needed = [c for c in ['Time', 'Price', 'Volume'] if c in out.columns]
            if 'Time' not in needed or 'Price' not in needed:
                return pd.DataFrame()
            out = out[needed].copy()
            out['Price'] = pd.to_numeric(out['Price'], errors='coerce')
            if 'Volume' in out.columns:
                out['Volume'] = pd.to_numeric(out['Volume'], errors='coerce')
            out = out.dropna(subset=['Price'])
            # 计算均价线
            if 'Volume' in out.columns and out['Volume'].sum() > 0:
                out['_cum_pv'] = (out['Price'] * out['Volume']).cumsum()
                out['_cum_v'] = out['Volume'].cumsum().replace(0, pd.NA)
                out['AvgPrice'] = (out['_cum_pv'] / out['_cum_v']).round(3)
                out = out.drop(columns=['_cum_pv', '_cum_v'])
            # ticktime 可能是 HH:MM:SS 格式,只保留 HH:MM
            out['Time'] = out['Time'].astype(str).str.extract(r'(\d{1,2}:\d{2})')[0]
            out = out.dropna(subset=['Time'])
            return out.reset_index(drop=True)
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def _format_intraday(df: pd.DataFrame, filter_today: bool = False) -> pd.DataFrame:
        """统一分时格式。filter_today=True 时只保留今日的记录,防止多日混合。"""
        try:
            col_time = '时间' if '时间' in df.columns else df.columns[0]
            out = df.rename(columns={col_time: 'Time'}).copy()
            mapping = {}
            if 'close' in out.columns:
                mapping['close'] = 'Price'
            elif '收盘' in out.columns:
                mapping['收盘'] = 'Price'
            if 'volume' in out.columns:
                mapping['volume'] = 'Volume'
            elif '成交量' in out.columns:
                mapping['成交量'] = 'Volume'
            out = out.rename(columns=mapping)
            cols = ['Time'] + [c for c in ['Price', 'Volume'] if c in out.columns]
            out = out[cols].copy()
            if 'Price' in out.columns:
                out['Price'] = pd.to_numeric(out['Price'], errors='coerce')
            if 'Volume' in out.columns:
                out['Volume'] = pd.to_numeric(out['Volume'], errors='coerce')
            out = out.dropna(subset=['Price'])

            # 解析日期时间,过滤今日(如需要)
            out['_dt'] = pd.to_datetime(out['Time'], errors='coerce')
            out = out.dropna(subset=['_dt'])
            if filter_today:
                today_str = datetime.now().strftime('%Y-%m-%d')
                today_mask = out['_dt'].dt.strftime('%Y-%m-%d') == today_str
                out = out[today_mask].copy()
                if out.empty:
                    return pd.DataFrame()

            # 均价线(只基于过滤后的今日数据)
            if 'Volume' in out.columns and 'Price' in out.columns:
                out['_cum_pv'] = (out['Price'] * out['Volume']).cumsum()
                out['_cum_v'] = out['Volume'].cumsum().replace(0, pd.NA)
                out['AvgPrice'] = (out['_cum_pv'] / out['_cum_v']).round(3)
                out = out.drop(columns=['_cum_pv', '_cum_v'])

            out['Time'] = out['_dt'].dt.strftime('%H:%M')
            out = out.drop(columns=['_dt'])
            return out.dropna(subset=['Time']).reset_index(drop=True)
        except Exception:
            return pd.DataFrame()

    def _intraday_to_text_samples(self, intraday_df: pd.DataFrame, step_minutes: int = 15) -> str:
        if intraday_df.empty:
            return "今日分时数据暂未抓到。"
        try:
            df = intraday_df.copy()
            stride = max(1, step_minutes)
            sampled = df.iloc[::stride]
            if len(df) and (sampled.iloc[-1]['Time'] != df.iloc[-1]['Time']):
                sampled = pd.concat([sampled, df.tail(1)], ignore_index=True)
            lines = []
            for _, r in sampled.iterrows():
                avg_part = f" | 均价 {r['AvgPrice']}" if 'AvgPrice' in r and pd.notna(r.get('AvgPrice', None)) else ""
                vol_part = f" | 量 {int(r['Volume'])}" if 'Volume' in r and pd.notna(r.get('Volume', None)) else ""
                lines.append(f"- {r['Time']}  现价 {r['Price']}{avg_part}{vol_part}")
            return "\n".join(lines)
        except Exception:
            return "分时数据采样失败。"

    # ==================================================================
    # 主入口 —— 关键：明确告知 AI 数据状态
    # ==================================================================
    def get_full_analysis_context(self, query: str):
        self._spot_df_cache = None
        self._last_diagnostics = []

        code, name = self.get_stock_name_or_code(query)
        if not code or name == "未找到":
            return "", "", f"无法解析股票: {query}"

        now = datetime.now()
        is_trading_hour = (
            now.weekday() < 5 and
            ((now.hour == 9 and now.minute >= 30) or (9 < now.hour < 11) or
             (now.hour == 11 and now.minute <= 30) or
             (13 <= now.hour < 15))
        )

        ctx = f"# 深度诊断报告: {name} ({code})\n"
        ctx += (f"**报告分析基准时**: {now.strftime('%Y-%m-%d %H:%M:%S')} "
                f"(星期{list('一二三四五六日')[now.weekday()]}"
                f"{'，盘中' if is_trading_hour else '，非交易时段'})\n\n")

        spot_info = self._get_bulletproof_spot(code)
        kline_md, daily_df = self.get_daily_kline(code, limit=30, spot_row=spot_info)
        levels = self._calc_key_levels(daily_df, lookback=20)

        # 分别评估：K线 / 实时 / 分时 三类数据的可用性
        has_kline = not daily_df.empty
        has_spot = spot_info is not None

        if has_spot:
            prev_close = spot_info.get('prev_close')
            if prev_close is None and has_kline and len(daily_df) >= 2:
                try:
                    prev_close = float(daily_df.iloc[-2]['收盘'])
                except Exception:
                    prev_close = None

            ctx += "## 0. 🚨 实时极值通告 (最高优先级)\n"
            ctx += (f"**此部分代表今日 ({now.strftime('%Y-%m-%d %H:%M')}) 盘中实时表现**\n")
            ctx += (f"**【真理点位】**：今日最高 **{spot_info['high']}**，"
                    f"当前价 **{spot_info['price']}** (数据源: {spot_info.get('source', 'N/A')})\n")

            if levels:
                r, s = levels.get('resistance'), levels.get('support')
                dyn_lines = []
                if r is not None:
                    if spot_info['high'] >= r:
                        dyn_lines.append(
                            f"  - 今日最高 {spot_info['high']} **已触及/突破** 近20日阻力位 {r:.2f}，"
                            f"AI 请按『已突破并站稳 / 冲高回落』两种情景分别分析。"
                        )
                    else:
                        gap = (r - spot_info['price']) / (spot_info['price'] + 0.001) * 100
                        dyn_lines.append(f"  - 近20日阻力位约 {r:.2f}，当前价距阻力 {gap:.2f}%。")
                if s is not None:
                    dyn_lines.append(f"  - 近20日支撑位约 {s:.2f}。")
                if levels.get('ma5') is not None:
                    dyn_lines.append(
                        f"  - 均线体系：MA5 {levels['ma5']:.2f}"
                        + (f" / MA10 {levels['ma10']:.2f}" if levels.get('ma10') else "")
                        + (f" / MA20 {levels['ma20']:.2f}" if levels.get('ma20') else "")
                    )
                if dyn_lines:
                    ctx += "- **核心分析指令 (基于动态计算)**:\n" + "\n".join(dyn_lines) + "\n"

            prev_str = f"{prev_close:.2f}" if prev_close is not None else "N/A"
            ctx += (
                f"- **行情对比**：昨收 {prev_str}，今开 {spot_info['open']}，"
                f"最高 {spot_info['high']}，最低 {spot_info['low']}，"
                f"当前 {spot_info['price']} (涨跌 {spot_info.get('change_pct', 0):.2f}%)\n\n"
            )
        elif has_kline:
            # 关键修复：K线有，只是实时盘口缺 —— AI 仍可以做历史结构分析
            last_date = str(daily_df.iloc[-1]['日期']) if has_kline else "N/A"
            last_close = daily_df.iloc[-1]['收盘'] if has_kline else "N/A"
            ctx += "## 0. ℹ️ 实时盘口数据不可用 (K线/资讯等其他数据正常)\n"
            if is_trading_hour:
                ctx += (f"当前为 A 股交易时段 ({now.strftime('%H:%M')})，"
                        f"但实时盘口接口暂时不通。**K 线、资讯、板块、全市场情绪等数据仍可用**。\n")
            else:
                ctx += f"当前为非交易时段 ({now.strftime('%H:%M')})，实时盘口不可用属正常。\n"

            # 先把能用的历史数据要点摆出来，让 AI 有抓手
            ctx += f"- **最近一个交易日**: {last_date}，收盘 {last_close}\n"
            if levels:
                if levels.get('ma5') is not None:
                    ctx += (f"- **均线体系 (基于历史K线计算)**：MA5 {levels['ma5']:.2f}"
                            + (f" / MA10 {levels['ma10']:.2f}" if levels.get('ma10') else "")
                            + (f" / MA20 {levels['ma20']:.2f}" if levels.get('ma20') else "") + "\n")
                if levels.get('resistance') is not None:
                    ctx += (f"- **近20日阻力/支撑**：阻力 {levels['resistance']:.2f} / "
                            f"支撑 {levels.get('support', 0):.2f}\n")

            # 明确区分：哪些可做 / 哪些禁止
            ctx += "\n**分析指令**：\n"
            ctx += "- ✅ **可以基于下方【K线表】做完整的趋势/均线/形态/变盘点分析**，这些数据是可靠的。\n"
            ctx += "- ✅ 资讯面、板块、全市场情绪(本报告后续章节)若有数据均可正常使用。\n"
            if is_trading_hour:
                ctx += "- ⚠️ 仅限定：**禁止凭空给出今日盘中具体数值**(如『今日现价 XX』『今日涨 X%』『今日最高 X』)，"
                ctx += "因为实时盘口缺失。但可以说『截至最近一个交易日收盘 XX』或『当前盘中实时数据暂不可得』。\n"
            ctx += "- ✅ 最终评级与操作建议必须给出，不得以数据不全为由拒绝结论。\n"

            ctx += "\n**实时抓取诊断日志** (供排查):\n```\n"
            for line in self._last_diagnostics[-8:]:
                ctx += line + "\n"
            ctx += "```\n\n"
        else:
            # 最糟情况：K线和实时都挂了
            ctx += "## 0. ❌ 数据抓取全面失败\n"
            ctx += (f"时间 {now.strftime('%H:%M')}，K线与实时数据均未能抓取到。\n"
                    f"- 请检查网络/代理设置或 akshare 版本。\n"
                    f"- AI 可基于资讯面与板块数据做定性判断(如有)，但禁止给出具体价位或均线数值。\n")
            ctx += "\n**抓取诊断日志**:\n```\n"
            for line in self._last_diagnostics[-10:]:
                ctx += line + "\n"
            ctx += "```\n\n"

        # K 线段：明确标注数据源与可用性
        if has_kline:
            ctx += "## 1. ✅ 价格形态历程 (可信数据,AI 必须据此分析趋势/均线/形态)\n"
        else:
            ctx += "## 1. ❌ K 线数据不可用\n"
        ctx += kline_md + "\n\n"

        ctx += "## 2. 今日分时走势采样 (每15分钟)\n"
        intraday_df = self.get_intraday_plot_data(code)
        if intraday_df.empty:
            if is_trading_hour:
                ctx += ("分时数据暂时抓不到 —— 只影响『今日盘中节奏』判断，"
                        "**不影响**基于 K 线的趋势结构分析。\n\n")
            else:
                ctx += "当前非交易时段，暂无分时数据。\n\n"
        else:
            ctx += self._intraday_to_text_samples(intraday_df, step_minutes=15) + "\n\n"

        ctx += "## 3. 最近重要资讯\n"
        ctx += self.get_news(code) + "\n\n"

        try:
            spot_df = self._fetch_market_spot()
            if not spot_df.empty and '涨跌幅' in spot_df.columns:
                chg = pd.to_numeric(spot_df['涨跌幅'], errors='coerce')
                u = int((chg > 0).sum())
                d = int((chg < 0).sum())
                flat = int((chg == 0).sum())
                sentiment = '偏强' if u > d * 1.2 else ('偏弱' if d > u * 1.2 else '分化')
                ctx += (f"## 4. 全市场情绪背景\n"
                        f"- **今日 涨/跌/平 家数**: {u} / {d} / {flat}\n"
                        f"- **整体情绪**: {sentiment}\n")
        except Exception:
            pass

        return code, name, ctx

    # ==================================================================
    # Streamlit：分时图渲染
    # ==================================================================
    def render_intraday_chart_streamlit(self, code: str, name: str = "") -> bool:
        df = self.get_intraday_plot_data(code)
        if df.empty:
            st.info(f"暂未获取到 {name or code} 的分时数据。")
            with st.expander("🔍 查看分时抓取诊断日志"):
                for line in self._last_diagnostics:
                    st.text(line)
            return False

        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True,
                row_heights=[0.72, 0.28], vertical_spacing=0.04,
                subplot_titles=("分时走势", "分时成交量")
            )
            fig.add_trace(
                go.Scatter(x=df['Time'], y=df['Price'], mode='lines',
                           name='现价', line=dict(color='#d62728', width=1.6)),
                row=1, col=1
            )
            if 'AvgPrice' in df.columns:
                fig.add_trace(
                    go.Scatter(x=df['Time'], y=df['AvgPrice'], mode='lines',
                               name='均价', line=dict(color='#f2a900', width=1.2, dash='dot')),
                    row=1, col=1
                )
            if 'Volume' in df.columns:
                colors = []
                prev = None
                for p in df['Price']:
                    colors.append('#ef5350' if (prev is None or p >= prev) else '#26a69a')
                    prev = p
                fig.add_trace(
                    go.Bar(x=df['Time'], y=df['Volume'], name='量',
                           marker_color=colors, opacity=0.75),
                    row=2, col=1
                )
            fig.update_layout(
                height=460, margin=dict(l=20, r=20, t=40, b=20),
                legend=dict(orientation='h', y=1.08),
                hovermode='x unified',
            )
            fig.update_xaxes(showgrid=False)
            fig.update_yaxes(showgrid=True, gridcolor='rgba(0,0,0,0.06)')
            st.plotly_chart(fig, use_container_width=True)
            return True
        except ImportError:
            st.caption(f"{name or code} · 分时走势 (简版，装 plotly 可看增强版)")
            chart_df = df.set_index('Time')[['Price'] + (['AvgPrice'] if 'AvgPrice' in df.columns else [])]
            st.line_chart(chart_df)
            if 'Volume' in df.columns:
                st.caption("分时成交量")
                st.bar_chart(df.set_index('Time')[['Volume']])
            return True
        except Exception as e:
            st.warning(f"分时图渲染异常: {e}")
            return False

    # ==================================================================
    # 一键诊断面板 (UI)
    # ==================================================================
    def render_diagnostics_panel(self, code: str, title: str = "🔍 实时数据抓取诊断"):
        with st.expander(title, expanded=False):
            st.caption("诊断实时数据抓取问题。TUN 代理用户请优先用 'system' 模式。")

            # 网络模式切换 (新方案:system/bypass/force)
            current_mode = os.environ.get("AK_NET_MODE", "system").lower()
            if current_mode not in ("system", "bypass", "force"):
                current_mode = "system"
            mode_label = {
                "system": "✅ 跟随系统 (TUN/全局代理推荐) ⭐",
                "bypass": "🚫 强制直连 (国内裸奔网络)",
                "force":  "🔧 强制走 AK_PROXY_URL 指定代理",
            }
            new_mode = st.radio(
                "网络模式 (切换后立即生效):",
                options=["system", "bypass", "force"],
                format_func=lambda m: mode_label.get(m, m),
                index=["system", "bypass", "force"].index(current_mode),
                key=f"netmode_{code}",
                horizontal=True,
            )
            if new_mode != current_mode:
                os.environ["AK_NET_MODE"] = new_mode
                st.success(f"已切换到 {mode_label.get(new_mode)}")

            if new_mode == "force":
                current_proxy = os.environ.get("AK_PROXY_URL", "http://127.0.0.1:7890")
                new_proxy = st.text_input(
                    "代理地址 (AK_PROXY_URL):",
                    value=current_proxy,
                    key=f"proxyurl_{code}",
                    help="Clash 默认 http://127.0.0.1:7890, V2ray 通常 10809",
                )
                if new_proxy != current_proxy:
                    os.environ["AK_PROXY_URL"] = new_proxy

            # 单独测试东财直连 API
            st.markdown("---")
            if st.button(f"⚡ 测试东财直连 API ({code})", key=f"em_direct_{code}_{int(time.time())}"):
                self._last_diagnostics = []
                with st.spinner("测试东财直连..."):
                    try:
                        proxies = _get_proxy_strategy()
                        self._diag(f"代理策略: {proxies}")
                        t0 = time.time()
                        quote = _em_api.get_quote(code, proxies=proxies, diag=self._diag)
                        elapsed = time.time() - t0
                        st.success(f"✅ 东财直连成功 ({elapsed:.2f}s)")
                        st.json(quote)
                    except Exception as e:
                        st.error(f"❌ 东财直连失败: {type(e).__name__}: {e}")

                    try:
                        t0 = time.time()
                        df = _em_api.get_intraday(code, proxies=_get_proxy_strategy(), diag=self._diag)
                        elapsed = time.time() - t0
                        if not df.empty:
                            st.success(f"✅ 东财分时成功 ({elapsed:.2f}s, N={len(df)})")
                            st.dataframe(df.tail(5), use_container_width=True)
                        else:
                            st.warning("东财分时返回空")
                    except Exception as e:
                        st.error(f"❌ 东财分时失败: {type(e).__name__}: {e}")

                for line in self._last_diagnostics:
                    if '[ERROR]' in line:
                        st.error(line)
                    elif '[WARN]' in line:
                        st.warning(line)
                    else:
                        st.text(line)

            # ---- Clash 探测与规则生成 ----
            st.markdown("---")
            st.markdown("**🔧 让东财也走代理 (修复 ProxyError)**")
            st.caption(
                "东财被代理客户端默认判为『直连』,但直连被网络环境拦截 -> ProxyError。"
                "下方按钮会探测你的 Clash/Mihomo 并生成配置片段,你复制到自己的配置文件里即可。"
            )
            if st.button(f"🔍 探测本地 Clash/Mihomo", key=f"clash_probe_{code}_{int(time.time())}"):
                with st.spinner("探测中..."):
                    info = _clash_helper.detect()
                if info['found']:
                    st.success(
                        f"✅ 检测到 Clash/Mihomo 运行中\n\n"
                        f"- API: `{info['api_url']}`\n"
                        f"- 版本: `{info['version']}`\n"
                        f"- 代理组: {len(info['groups'])} 个\n"
                        f"- 当前规则数: {info['rules_count']}"
                    )
                    target_group = _clash_helper.suggest_group()

                    st.markdown("**👇 请把下面的规则添加到你的 Clash 配置文件 `rules:` 段最前面：**")
                    snippet = _clash_helper.rule_snippet_yaml(target_group)
                    st.code(snippet, language="yaml")

                    st.info(
                        f"📝 **操作步骤**：\n"
                        f"1. 打开你的 Clash 配置文件 (通常在 `~/.config/clash/` 或客户端 UI 里)\n"
                        f"2. 找到 `rules:` 这一段\n"
                        f"3. 把上面 {len(_clash_helper.EASTMONEY_DOMAINS)} 行粘贴到 `rules:` 下面最前面 "
                        f"(放在其他规则之前,否则可能被先匹配到直连)\n"
                        f"4. 保存并在 Clash 客户端里重新加载配置 (或热重载)\n"
                        f"5. 重启本应用即可看到东财正常响应\n\n"
                        f"⚠️ 如果你用的是**订阅链接**,需要配置客户端的『覆写规则』功能,"
                        f"否则下次订阅更新会把你的改动覆盖。具体操作参见你的客户端文档。"
                    )

                    if info['groups']:
                        with st.expander("🔍 检测到的代理组"):
                            for g in info['groups']:
                                st.text(g)
                            st.caption(
                                f"已选择 **{target_group}** 作为东财规则的目标组。"
                                f"如果你想改成其他组,手动编辑上面的 YAML 即可。"
                            )
                else:
                    st.warning(
                        "❌ 未检测到本地 Clash/Mihomo\n\n"
                        "可能原因:\n"
                        "- 你用的不是 Clash 系 (如 V2rayN/Surge/Shadowrocket 等)\n"
                        "- Clash 关闭了外部控制 API (external-controller)\n"
                        "- API 端口不是默认的 9090/9097/59090\n\n"
                        "不影响主流程 —— 雪球+新浪数据源依然可用。"
                    )
                    st.markdown("**如果你想手动配置你的代理客户端,以下是通用的域名列表:**")
                    st.code("\n".join(_clash_helper.EASTMONEY_DOMAINS))
                    st.caption("把这些域名在你的代理客户端里配置为『走代理』即可。")

            st.markdown("---")
            if st.button(f"🧪 测试所有数据源 ({code})", key=f"diag_{code}_{int(time.time())}"):
                self._last_diagnostics = []
                with st.spinner("抓取中..."):
                    spot = self._get_bulletproof_spot(code)
                    intraday = self.get_intraday_plot_data(code)

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**实时快照**")
                    if spot:
                        st.success(f"✅ 成功 (源: {spot.get('source')})")
                        st.json(spot)
                    else:
                        st.error("❌ 全部失败")
                with col2:
                    st.markdown("**分时数据**")
                    if not intraday.empty:
                        st.success(f"✅ 成功 ({len(intraday)} 条)")
                        st.dataframe(intraday.tail(5), use_container_width=True)
                    else:
                        st.error("❌ 失败")

                st.markdown("**诊断日志：**")
                for line in self._last_diagnostics:
                    if '[ERROR]' in line:
                        st.error(line)
                    elif '[WARN]' in line:
                        st.warning(line)
                    else:
                        st.text(line)

                # 智能建议
                log_text = "\n".join(self._last_diagnostics)
                if "RemoteDisconnected" in log_text or "ConnectionError" in log_text:
                    st.warning(
                        "💡 **检测到 ConnectionError/RemoteDisconnected** ——"
                        "东财在 TCP 层拒绝连接。**尝试切换上方网络模式为『跟随系统代理』** "
                        "(`keep`) 再测一次。如果你挂着代理上网，这个模式通常最有效。"
                    )
                if "KeepProxy" in log_text and "✓" in log_text:
                    st.success(
                        "🎯 已确认：使用系统代理可以访问东财。"
                        "**建议在 .env 里设置 `AK_NET_MODE=keep` 永久生效**"
                    )

    # ==================================================================
    # 其余功能
    # ==================================================================
    def _get_market_prefix(self, code: str) -> str:
        if code.startswith(('6', '9')):
            return 'sh'
        if code.startswith(('0', '2', '3')):
            return 'sz'
        return 'sh'

    def get_news(self, code: str) -> str:
        try:
            with bypass_proxy():
                try:
                    df = ak.stock_news_em(symbol=code.replace('sh', '').replace('sz', ''))
                    if not df.empty:
                        return "\n".join([f"- {r.新闻时间} {r.新闻标题}" for _, r in df.head(5).iterrows()])
                except Exception:
                    pass
            return "暂无重大快讯。"
        except Exception:
            return "无法拉取新闻。"

    def get_industry_board_list(self) -> pd.DataFrame:
        try:
            with bypass_proxy():
                df = ak.stock_board_industry_name_ths()
                return df.rename(columns={'name': '板块名称', 'code': '板块代码'}) if df is not None else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    def get_concept_board_list(self) -> pd.DataFrame:
        try:
            with bypass_proxy():
                df = ak.stock_board_concept_name_ths()
                return df.rename(columns={'name': '板块名称', 'code': '板块代码'}) if df is not None else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    def search_board(self, query: str) -> list:
        res = []
        try:
            for df, t in [(self.get_industry_board_list(), '行业板块'),
                          (self.get_concept_board_list(), '概念板块')]:
                if not df.empty:
                    m = df[df['板块名称'].str.contains(query, na=False)]
                    for _, r in m.iterrows():
                        res.append({'name': r['板块名称'], 'code': r['板块代码'], 'type': t})
        except Exception:
            pass
        return res

    @st.cache_data(ttl=3600)
    def _get_st_blacklist(_self):
        try:
            with bypass_proxy():
                df = ak.stock_info_a_code_name()
            if df is not None and not df.empty:
                st_names = df[df['name'].str.contains('ST', na=False)]['name'].tolist()
                return {name.replace('*', '').replace('ST', '')[:2] for name in st_names}
        except Exception:
            pass
        return set()

    def get_board_constituents(self, board_name: str, board_type: str = "行业板块") -> str:
        try:
            with bypass_proxy():
                func = ak.stock_board_concept_summary_ths if board_type == "概念板块" else ak.stock_board_industry_summary_ths
                s_df = func()
            if s_df is not None and not s_df.empty:
                m = s_df[s_df.apply(lambda r: board_name in str(r.values), axis=1)]
                if not m.empty:
                    r = m.iloc[0]
                    leader_name = r.get('领涨股', 'N/A')
                    st_blacklist = self._get_st_blacklist()
                    leader_core = leader_name[:2]
                    risk_warning = ""
                    if leader_core in st_blacklist:
                        real_name = f"⚠️ [ST退市地雷] {leader_name}"
                        risk_warning = (
                            f"\n> [!CAUTION]\n> **官方风险通告**：该板块核心活跃股 `{leader_name}` "
                            f"已被官方标记为 ST(特别处理) 或 *ST(退市风险)。AI 严禁将其作为买入建议，"
                            f"必须通过『逻辑穿透』寻找板块内财务健康的非ST股票替代！"
                        )
                        leader_name = real_name
                    return (
                        f"### 板块核心标杆 (THS数据)\n"
                        f"- **领涨股**: {leader_name} (+{r.get('领涨股-涨跌幅')}%){risk_warning}\n"
                        f"- **备注**: AI请务必结合该股 ST 风险特征，绝对禁止在『猛龙观察池』中推荐此类标的。"
                    )
        except Exception:
            pass
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
                if len(rec) >= 5:
                    p5_start = rec['收盘价'].iloc[-5]
                    p5_change = ((cur_p - p5_start) / (p5_start + 0.001)) * 100
                    tag = "📈 攻击" if p5_change > 1.5 else ("📉 回撤" if p5_change < -1.5 else "↔️ 蓄势")
                    momentum = f"\n- **短线强度**: {tag} (近5日 {p5_change:.2f}%)"
                else:
                    momentum = ""
                return f"- 周期高低位: {max_p}/{min_p}, 当前收盘: {cur_p}" + momentum
        except Exception:
            pass
        return "指数数据暂不可见。"

    def find_related_sub_boards(self, board_name: str) -> list:
        return []

    def get_board_analysis_context(self, board_name: str, board_type: str = "行业板块", sub_boards: list = None) -> str:
        ctx = f"# 板块深度诊断报告: {board_name}\n\n"
        ctx += "## 1. 历史活跃度与走势\n" + self.get_board_history(board_name, board_type) + "\n\n"
        ctx += "## 2. 成分股核心标量\n" + self.get_board_constituents(board_name, board_type) + "\n\n"
        ctx += "## 3. 板块底层大资金流 (核心新浪源)\n"
        try:
            with bypass_proxy():
                lhb = ak.stock_lhb_detail_daily_sina(date=date.today().strftime("%Y%m%d"))
                if lhb is not None and not lhb.empty:
                    kw = board_name[:2]
                    rel = lhb[lhb.apply(lambda r: kw in str(r.values), axis=1)]
                    if not rel.empty:
                        for _, row in rel.head(3).iterrows():
                            ctx += f"- **{row.名称}** 上榜: {row.上榜原因}\n"
                    else:
                        ctx += "今日该板块成分股未见大幅龙虎榜异动。\n"
        except Exception:
            pass
        try:
            with bypass_proxy():
                all_s = ak.stock_zh_a_spot()
                if all_s is not None and not all_s.empty and '涨跌幅' in all_s.columns:
                    chg = pd.to_numeric(all_s['涨跌幅'], errors='coerce')
                    u = int((chg > 0).sum())
                    d = int((chg < 0).sum())
                    ctx += (f"\n## 4. 全市场情绪背景\n"
                            f"- **上涨/下跌家数**: {u} / {d}\n"
                            f"- **说明**: 市场整体呈现{'强' if u > d else '弱'}度，AI诊断时应考虑此宏阔背景。")
        except Exception:
            pass
        return ctx

    # ==================================================================
    # 📉 功能复位区：恢复行情中心、盘口异动、财务、龙虎榜等页面的数据接口
    # 这些方法供 3-10 号页面调用,统一走 bypass_proxy 保证代理环境兼容。
    #
    # ⚠️ 重要:本区所有方法名故意与上方的 get_news/get_board_constituents **错开**,
    #         避免重复定义导致"后定义覆盖前定义"的 bug。
    #         - 资讯中心用 get_stock_news_detail (返回 DataFrame)
    #         - 上方智能诊股用 get_news (返回 str) ← 不动
    #         - 板块分析用 get_board_constituents (返回 str) ← 不动
    #         - 板块大盘用 get_board_list (返回 DataFrame)
    # ==================================================================

    def get_realtime_quotes(self, market_type: str = "沪深主板") -> pd.DataFrame:
        """全市场实时行情 — 3_📈_行情中心.py 调用"""
        try:
            with bypass_proxy():
                df = ak.stock_zh_a_spot_em()
                if df is None or df.empty:
                    # 东财挂了就用新浪兜底
                    if hasattr(ak, 'stock_zh_a_spot'):
                        df = ak.stock_zh_a_spot()
                if df is None or df.empty:
                    return pd.DataFrame()
                if '代码' not in df.columns:
                    return df  # 新浪版可能是 symbol 列,直接返回

                if market_type == "创业板":
                    df = df[df['代码'].str.startswith('3')]
                elif market_type == "科创板":
                    df = df[df['代码'].str.startswith('68')]
                elif market_type == "北交所":
                    df = df[df['代码'].str.startswith(('8', '43', '92'))]
                elif market_type == "沪深主板":
                    df = df[df['代码'].str.startswith(('60', '00'))]
                return df.reset_index(drop=True)
        except Exception as e:
            self._diag(f"行情中心抓取失败: {e}", "ERROR")
        return pd.DataFrame()

    def get_limit_pool(self, pool_type: str = "涨停") -> pd.DataFrame:
        """特征股池 — 4_🔥_盘口异动.py 调用"""
        today = datetime.now().strftime("%Y%m%d")
        try:
            with bypass_proxy():
                if pool_type == "涨停":
                    if hasattr(ak, 'stock_zt_pool_em'):
                        return ak.stock_zt_pool_em(date=today)
                elif pool_type == "跌停":
                    # akshare 新版叫 stock_zt_pool_dtgc_em
                    for fn in ['stock_zt_pool_dtgc_em', 'stock_dt_pool_em']:
                        if hasattr(ak, fn):
                            try:
                                return getattr(ak, fn)(date=today)
                            except Exception:
                                continue
                elif pool_type == "昨日涨停":
                    if hasattr(ak, 'stock_zt_pool_previous_em'):
                        return ak.stock_zt_pool_previous_em(date=today)
                elif pool_type == "炸板":
                    # 正确函数名是 stock_zt_pool_zbgc_em,不是 stock_zt_pool_zbg_em
                    for fn in ['stock_zt_pool_zbgc_em', 'stock_zt_pool_zbg_em']:
                        if hasattr(ak, fn):
                            try:
                                return getattr(ak, fn)(date=today)
                            except Exception:
                                continue
                elif pool_type == "强势股":
                    if hasattr(ak, 'stock_zt_pool_strong_em'):
                        try:
                            return ak.stock_zt_pool_strong_em(date=today)
                        except Exception:
                            pass
                    if hasattr(ak, 'stock_rank_cxg_ths'):
                        try:
                            return ak.stock_rank_cxg_ths(symbol="历史新高")
                        except Exception:
                            pass
                elif pool_type == "次新股":
                    for fn in ['stock_zt_pool_sub_new_em', 'stock_zh_a_new_em']:
                        if hasattr(ak, fn):
                            try:
                                return getattr(ak, fn)(date=today) if fn.endswith('_em') and 'pool' in fn else getattr(ak, fn)()
                            except Exception:
                                continue
        except Exception as e:
            self._diag(f"股池 {pool_type} 抓取失败: {e}", "WARN")
        return pd.DataFrame()

    def get_market_changes(self, symbol: str = "大笔买入") -> pd.DataFrame:
        """盘中异动监控 — 4_🔥_盘口异动.py 调用
        正确的 akshare 函数名是 stock_changes_em,不是 stock_market_change_em
        """
        try:
            with bypass_proxy():
                if hasattr(ak, 'stock_changes_em'):
                    return ak.stock_changes_em(symbol=symbol)
                if hasattr(ak, 'stock_market_change_em'):
                    return ak.stock_market_change_em(symbol=symbol)
        except Exception as e:
            self._diag(f"盘口异动抓取失败: {e}", "WARN")
        return pd.DataFrame()

    def get_earnings_summary(self, date_str: str, report_type: str = "业绩快报") -> pd.DataFrame:
        """业绩汇总 — 5_📋_财务数据.py 调用
        date_str: 格式 20261231 (财报披露日期)
        """
        try:
            with bypass_proxy():
                if report_type == "业绩快报":
                    for fn in ['stock_yjkb_em', 'stock_zykb_em']:
                        if hasattr(ak, fn):
                            try:
                                return getattr(ak, fn)(date=date_str)
                            except Exception:
                                continue
                elif report_type == "业绩预告":
                    for fn in ['stock_yjyg_em', 'stock_zyyg_em']:
                        if hasattr(ak, fn):
                            try:
                                return getattr(ak, fn)(date=date_str)
                            except Exception:
                                continue
                elif report_type == "业绩报表":
                    if hasattr(ak, 'stock_yjbb_em'):
                        return ak.stock_yjbb_em(date=date_str)
        except Exception as e:
            self._diag(f"财务 {report_type} 抓取失败: {e}", "WARN")
        return pd.DataFrame()

    def get_institutional_research(self) -> pd.DataFrame:
        """机构调研记录 — 5_📋_财务数据.py 调用"""
        try:
            with bypass_proxy():
                today = datetime.now().strftime("%Y%m%d")
                # 新版函数名 stock_jgdy_detail_em,旧版 stock_jg_dy_detail_em
                for fn in ['stock_jgdy_detail_em', 'stock_jg_dy_detail_em']:
                    if hasattr(ak, fn):
                        try:
                            func = getattr(ak, fn)
                            # 有的版本要传 date,有的不要
                            try:
                                return func(date=today)
                            except TypeError:
                                return func()
                        except Exception:
                            continue
        except Exception as e:
            self._diag(f"机构调研抓取失败: {e}", "WARN")
        return pd.DataFrame()

    def get_global_news(self) -> pd.DataFrame:
        """7×24 全球财经快讯 — 6_📰_资讯中心.py 调用"""
        try:
            with bypass_proxy():
                # 备选多个接口,依次尝试
                for fn_name in ['stock_info_global_em', 'stock_info_global_sina',
                                'stock_info_global_cls', 'news_cctv']:
                    if hasattr(ak, fn_name):
                        try:
                            df = getattr(ak, fn_name)()
                            if df is not None and not df.empty:
                                return df
                        except Exception:
                            continue
        except Exception as e:
            self._diag(f"全球快讯抓取失败: {e}", "WARN")
        return pd.DataFrame()

    def get_stock_news_detail(self, code: str) -> pd.DataFrame:
        """个股新闻表格 — 6_📰_资讯中心.py 调用

        注意:这个方法返回 DataFrame,与上方 get_news(返回 str) 故意错开名字,
             避免重复定义覆盖智能诊股的 get_news。
        """
        try:
            clean_code = code.replace('sh', '').replace('sz', '')
            with bypass_proxy():
                return ak.stock_news_em(symbol=clean_code)
        except Exception as e:
            self._diag(f"个股新闻抓取失败: {e}", "WARN")
        return pd.DataFrame()

    def get_daily_dragon_tiger(self, date_str: str = None) -> pd.DataFrame:
        """每日龙虎榜 — 7_🐉_龙虎榜与资金流.py 调用"""
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")
        try:
            with bypass_proxy():
                if hasattr(ak, 'stock_lhb_detail_em'):
                    try:
                        return ak.stock_lhb_detail_em(start_date=date_str, end_date=date_str)
                    except Exception:
                        pass
                if hasattr(ak, 'stock_lhb_detail_daily_sina'):
                    return ak.stock_lhb_detail_daily_sina(date=date_str)
        except Exception as e:
            self._diag(f"龙虎榜抓取失败: {e}", "WARN")
        return pd.DataFrame()

    def get_fund_flow_rank(self, indicator: str = "今日") -> pd.DataFrame:
        """资金流向排行 — 7_🐉_龙虎榜与资金流.py 调用"""
        try:
            with bypass_proxy():
                if hasattr(ak, 'stock_individual_fund_flow_rank'):
                    return ak.stock_individual_fund_flow_rank(indicator=indicator)
        except Exception as e:
            self._diag(f"资金流向排行抓取失败: {e}", "WARN")
        return pd.DataFrame()

    def get_top_shareholders(self, code: str) -> pd.DataFrame:
        """十大流通股东 — 8_👥_股东研究.py 调用
        修正:stock_main_stock_holder_em 不是有效函数名
        """
        clean_code = code.replace('sh', '').replace('sz', '')
        prefix = self._get_market_prefix(clean_code)
        try:
            with bypass_proxy():
                # 新版 akshare
                if hasattr(ak, 'stock_gdfx_free_top_10_em'):
                    try:
                        return ak.stock_gdfx_free_top_10_em(
                            symbol=f"{prefix}{clean_code}",
                            date=datetime.now().strftime("%Y%m%d")
                        )
                    except Exception:
                        pass
                # 旧版
                if hasattr(ak, 'stock_main_stock_holder'):
                    return ak.stock_main_stock_holder(stock=clean_code)
        except Exception as e:
            self._diag(f"十大股东抓取失败: {e}", "WARN")
        return pd.DataFrame()

    def get_shareholder_count_detail(self, code: str) -> pd.DataFrame:
        """股东户数趋势 (DataFrame版) — 8_👥_股东研究.py 调用"""
        try:
            clean_code = code.replace('sh', '').replace('sz', '')
            with bypass_proxy():
                for fn in ['stock_zh_a_gdhs_detail_em', 'stock_zh_a_gdhs']:
                    if hasattr(ak, fn):
                        try:
                            return getattr(ak, fn)(symbol=clean_code)
                        except Exception:
                            continue
        except Exception as e:
            self._diag(f"股东户数抓取失败: {e}", "WARN")
        return pd.DataFrame()

    def get_board_list(self, board_type: str = "行业") -> pd.DataFrame:
        """板块大盘列表 — 9_🏷️_板块大盘.py 调用"""
        try:
            with bypass_proxy():
                if board_type == "行业":
                    # 东财行业板块带涨跌幅 (更适合做排行)
                    if hasattr(ak, 'stock_board_industry_name_em'):
                        try:
                            return ak.stock_board_industry_name_em()
                        except Exception:
                            pass
                    if hasattr(ak, 'stock_board_industry_name_ths'):
                        return ak.stock_board_industry_name_ths()
                else:
                    if hasattr(ak, 'stock_board_concept_name_em'):
                        try:
                            return ak.stock_board_concept_name_em()
                        except Exception:
                            pass
                    if hasattr(ak, 'stock_board_concept_name_ths'):
                        return ak.stock_board_concept_name_ths()
        except Exception as e:
            self._diag(f"板块列表抓取失败: {e}", "WARN")
        return pd.DataFrame()

    def get_stock_heat_rank(self) -> pd.DataFrame:
        """股票热度排行 — 10_🌡️_市场情绪与热度.py 调用"""
        try:
            with bypass_proxy():
                for fn in ['stock_hot_rank_em', 'stock_hot_rank_detail_em',
                           'stock_hot_rank_wc', 'stock_hot_search_baidu']:
                    if hasattr(ak, fn):
                        try:
                            df = getattr(ak, fn)()
                            if df is not None and not df.empty:
                                return df
                        except Exception:
                            continue
        except Exception as e:
            self._diag(f"个股热度抓取失败: {e}", "WARN")
        return pd.DataFrame()

    def get_market_sentiment(self) -> pd.DataFrame:
        """市场赚钱效应温度计 — 10_🌡️_市场情绪与热度.py 调用

        基于全市场快照计算涨跌/涨停/大涨大跌等情绪指标
        """
        try:
            df = self._fetch_market_spot()
            if df is None or df.empty or '涨跌幅' not in df.columns:
                return pd.DataFrame()
            chg = pd.to_numeric(df['涨跌幅'], errors='coerce')
            up = int((chg > 0).sum())
            down = int((chg < 0).sum())
            flat = int((chg == 0).sum())
            total = up + down + flat
            limit_up = int((chg >= 9.8).sum())
            limit_down = int((chg <= -9.8).sum())
            big_up = int((chg >= 5).sum())
            big_down = int((chg <= -5).sum())
            sentiment = ("偏强" if up > down * 1.2
                         else "偏弱" if down > up * 1.2
                         else "分化")

            def _pct(n):
                return f"{(n/total*100):.1f}%" if total else "-"

            return pd.DataFrame([
                {"指标": "上涨家数", "数值": up, "占比": _pct(up)},
                {"指标": "下跌家数", "数值": down, "占比": _pct(down)},
                {"指标": "平盘家数", "数值": flat, "占比": _pct(flat)},
                {"指标": "涨停家数", "数值": limit_up, "占比": _pct(limit_up)},
                {"指标": "跌停家数", "数值": limit_down, "占比": _pct(limit_down)},
                {"指标": "大涨(≥5%)家数", "数值": big_up, "占比": _pct(big_up)},
                {"指标": "大跌(≤-5%)家数", "数值": big_down, "占比": _pct(big_down)},
                {"指标": "全市场情绪", "数值": sentiment, "占比": "-"},
            ])
        except Exception as e:
            self._diag(f"市场情绪抓取失败: {e}", "WARN")
        return pd.DataFrame()

    def get_board_constituents_detail(self, board_name: str,
                                      board_type: str = "行业板块") -> pd.DataFrame:
        """板块成分股明细 (DataFrame版) — 9_🏷️_板块大盘.py 调用

        注意:这个方法返回 DataFrame,与上方 get_board_constituents(返回 str) 错开名字
        """
        try:
            with bypass_proxy():
                if board_type == "概念板块":
                    for fn in ['stock_board_concept_cons_em', 'stock_board_concept_cons_ths']:
                        if hasattr(ak, fn):
                            try:
                                return getattr(ak, fn)(symbol=board_name)
                            except Exception:
                                continue
                else:
                    for fn in ['stock_board_industry_cons_em', 'stock_board_industry_cons_ths']:
                        if hasattr(ak, fn):
                            try:
                                return getattr(ak, fn)(symbol=board_name)
                            except Exception:
                                continue
        except Exception as e:
            self._diag(f"板块成分股明细抓取失败: {e}", "WARN")
        return pd.DataFrame()