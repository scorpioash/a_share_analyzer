import akshare as ak
from data_fetcher import bypass_proxy

with bypass_proxy():
    # Test stock_changes_em with correct param
    try:
        df = ak.stock_changes_em(symbol="火箭发射")
        print("stock_changes_em OK:", df.columns.tolist())
    except Exception as e:
        print(f"stock_changes_em FAIL: {e}")

    # Test lhb with start_date/end_date
    try:
        df = ak.stock_lhb_detail_em(start_date="20260414", end_date="20260418")
        print("stock_lhb_detail_em OK:", len(df), df.columns.tolist()[:5])
    except Exception as e:
        print(f"stock_lhb_detail_em FAIL: {e}")

    # Test fund flow rank
    try:
        df = ak.stock_individual_fund_flow_rank(indicator="今日")
        print("fund_flow_rank OK:", len(df))
    except Exception as e:
        print(f"fund_flow_rank FAIL: {e}")

    # Test institutional research
    try:
        df = ak.stock_jgdy_detail_em()
        print("jgdy OK:", len(df))
    except Exception as e:
        print(f"jgdy FAIL: {e}")
