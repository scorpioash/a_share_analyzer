import akshare as ak
import pandas as pd
import sys

pd.options.mode.string_storage = "python"

def test_600519():
    code = "600519"
    symbol_with_prefix = f"SH{code}"
    
    print(f"--- Testing {code} ---")
    
    # 1. Top 10 
    # Try different symbols
    apis = [ak.stock_gdfx_free_top_10_em, ak.stock_gdfx_top_10_em]
    symbols = [symbol_with_prefix, code]
    
    for api in apis:
        for s in symbols:
            print(f"Testing {api.__name__} with symbol='{s}'...")
            try:
                df = api(symbol=s, date="")
                print(f"  Success! Count: {len(df)}")
                if not df.empty:
                    print(f"  Columns: {df.columns.tolist()}")
            except Exception as e:
                print(f"  Failed: {type(e).__name__} - {e}")

    # 2. Shareholder count
    print("Testing stock_zh_a_gdhs...")
    try:
        df_gdhs = ak.stock_zh_a_gdhs(symbol=code)
        print(f"  Success! Count: {len(df_gdhs)}")
        if not df_gdhs.empty:
            print(f"  Latest row index -1:\n{df_gdhs.iloc[-1].to_dict()}")
    except Exception as e:
        print(f"  Failed: {e}")

if __name__ == "__main__":
    test_600519()
