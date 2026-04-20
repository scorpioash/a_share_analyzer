import akshare as ak
import pandas as pd
import sys

pd.options.mode.string_storage = "python"

def test_shareholders(code):
    print(f"--- Testing {code} ---")
    symbol = f"SH{code}" if code.startswith('6') else f"SZ{code}"
    
    # 1. Top 10 free
    print("Testing stock_gdfx_free_top_10_em...")
    try:
        df_free = ak.stock_gdfx_free_top_10_em(symbol=symbol, date="")
        print("Free count:", len(df_free))
    except Exception as e:
        print("Free failed:", type(e).__name__, e)

    # 2. Top 10
    print("Testing stock_gdfx_top_10_em...")
    try:
        df_top = ak.stock_gdfx_top_10_em(symbol=symbol, date="")
        print("Top count:", len(df_top))
        if not df_top.empty:
            print("Columns:", df_top.columns.tolist())
    except Exception as e:
        print("Top failed:", type(e).__name__, e)

    # 3. GDHS
    print("Testing stock_zh_a_gdhs...")
    try:
        df_gdhs = ak.stock_zh_a_gdhs(symbol=code)
        print("GDHS count:", len(df_gdhs))
        if not df_gdhs.empty:
            print("GDHS Columns:", df_gdhs.columns.tolist())
            print("Latest:", df_gdhs.iloc[0].to_dict())
    except Exception as e:
        print("GDHS failed:", type(e).__name__, e)

if __name__ == "__main__":
    test_shareholders("600519")
