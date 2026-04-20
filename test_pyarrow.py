import pandas as pd
import json

# Force python backend
pd.options.mode.string_storage = "python"
pd.options.mode.dtype_backend = "numpy_nullable"

import akshare as ak
from data_fetcher import bypass_proxy

try:
    with bypass_proxy():
        df = ak.stock_news_em(symbol="600519")
    print("SUCCESS")
except Exception as e:
    print(f"FAILED: {e}")
