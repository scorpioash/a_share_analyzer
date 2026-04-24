import logging
import time
from pytdx.hq import TdxHq_API
from pytdx.params import TDXParams

# 配置日志
logger = logging.getLogger("TDXProvider")
logger.setLevel(logging.INFO)

class TDXProvider:
    """通达信行情直连引擎 — 采用二进制协议，免疫 HTTP 代理拦截"""
    
    # 常用通达信主站列表 (Host, Port)
    TDX_SERVERS = [
        # 主力主站 (南京/上海/广州等)
        ("119.147.212.81", 7709),
        ("221.231.141.60", 7709),
        ("101.227.73.20", 7709),
        ("114.80.63.12", 7709),
        ("124.160.88.183", 7709),
        ("61.153.144.179", 7709),
        ("114.80.149.19", 7709),
        ("119.29.51.30", 7709),
        ("218.75.126.9", 7709),
        ("115.238.18.120", 7709),
        ("124.160.88.183", 7709),
        ("60.191.117.167", 7709),
        # 443 端口穿透能力更强
        ("119.147.212.81", 443),
        ("114.80.149.22", 443),
        ("106.120.222.203", 443),
    ]

    def __init__(self):
        self.api = TdxHq_API(heartbeat=True)
        self.is_connected = False

    def connect(self):
        """连接最快的通达信服务器"""
        if self.is_connected:
            return True
            
        for host, port in self.TDX_SERVERS:
            try:
                # 降低超时等待，快速轮询
                if self.api.connect(host, port, time_out=1.5):
                    logger.info(f"通达信连接成功: {host}:{port}")
                    self.is_connected = True
                    return True
            except Exception:
                continue
        
        logger.error("所有通达信服务器均无法连接，已自动切换至备选数据源。")
        return False

    def disconnect(self):
        if self.is_connected:
            self.api.disconnect()
            self.is_connected = False

    def _get_market_code(self, stock_code: str):
        """
        根据代码判断市场
        0: 深圳 (SZ)
        1: 上海 (SH)
        """
        if stock_code.startswith(('60', '68', '11', '51')):
            return 1 # 上海
        else:
            return 0 # 深圳（含创业板、北交所、深债等）

    def get_realtime_quote(self, stock_code: str):
        """获取实时报价数据"""
        if not self.connect():
            return None

        try:
            market = self._get_market_code(stock_code)
            # get_security_quotes 接收列表，返回列表
            quotes = self.api.get_security_quotes([(market, stock_code)])
            
            if not quotes:
                return None
            
            q = quotes[0]
            # 数据清洗与映射
            # price: 现价, last_close: 昨收, open: 开盘, high: 最高, low: 最低
            # TDX 返回的是整数格式（原价 * 100 或更多，取决于精算单位），但 pytdx 通常已经帮我们转成了浮点数
            
            # 计算涨跌幅
            price = q.get('price', 0)
            last_close = q.get('last_close', 0)
            change_pct = 0
            if last_close > 0:
                change_pct = round((price - last_close) / last_close * 100, 2)

            return {
                "name": q.get('name', 'Unknown'),
                "code": stock_code,
                "price": price,
                "open": q.get('open', 0),
                "high": q.get('high', 0),
                "low": q.get('low', 0),
                "last_close": last_close,
                "volume": q.get('vol', 0), # 单位：手
                "amount": q.get('amount', 0),
                "change_pct": change_pct,
                # 盘口深度 (买卖五档)
                "depth": {
                    "bid": [q.get(f'bid{i}', 0) for i in range(1, 6)],
                    "bid_vol": [q.get(f'bid_vol{i}', 0) for i in range(1, 6)],
                    "ask": [q.get(f'ask{i}', 0) for i in range(1, 6)],
                    "ask_vol": [q.get(f'ask_vol{i}', 0) for i in range(1, 6)],
                },
                "server_time": q.get('server_time', ''),
                "source": "TDX"
            }
        except Exception as e:
            logger.error(f"TDX 获取报价异常 ({stock_code}): {e}")
            self.is_connected = False # 标记连接可能已失效
            return None

    def get_kline(self, stock_code: str, count=100):
        """获取日 K 线数据"""
        if not self.connect():
            return None
            
        try:
            market = self._get_market_code(stock_code)
            # 9: 日K, 4: 1分钟, 0: 5分钟 ...
            klines = self.api.get_security_bars(9, market, stock_code, 0, count)
            return klines
        except Exception as e:
            logger.error(f"TDX 获取K线异常 ({stock_code}): {e}")
            return None

if __name__ == "__main__":
    # 简单的冒烟测试
    provider = TDXProvider()
    print("测试获取贵州茅台 (600519)...")
    res = provider.get_realtime_quote("600519")
    if res:
        print(f"报价结果: {res}")
    else:
        print("获取失败")
    provider.disconnect()
