import pandas as pd

class QuantEngine:
    """内置短线动能与情绪周期量化引擎"""

    @staticmethod
    def evaluate_stock(spot: dict, df_k: pd.DataFrame, sector_info: dict) -> dict:
        """评估个股量化得分与策略信号"""
        if df_k is None or len(df_k) < 10:
            return {"score": 0, "signal": "数据不足", "details": []}

        score = 50
        details = []
        signal = "持仓观察"

        # 1. 均线系统判定
        closes = pd.to_numeric(df_k['收盘'], errors='coerce')
        current_price = spot.get('price', closes.iloc[-1])
        ma5 = closes.rolling(5).mean().iloc[-1]
        ma10 = closes.rolling(10).mean().iloc[-1]

        if current_price >= ma5:
            score += 15
            details.append("股价站上5日均线 (+15分)")
        elif current_price < ma10:
            score -= 20
            details.append("股价跌破10日防守线 (-20分)")
            signal = "严格止损/空仓"
        
        if ma5 > ma10:
            score += 10
            details.append("均线多头排列 (+10分)")

        # 2. 资金流向判定 (若有)
        fund = spot.get('fund_flow', {})
        main_in = fund.get('main_net_in', 0)
        if main_in > 50000000: # 5000万
            score += 15
            details.append(f"主力大单净流入超5000万 (+15分)")
        elif main_in < -50000000:
            score -= 20
            details.append(f"主力大单净流出超5000万 (-20分)")

        # 3. 盘口与形态特征
        high = spot.get('high', 0)
        open_p = spot.get('open', 0)
        if current_price == high and spot.get('change_pct', 0) > 9:
            score += 15
            details.append("强势封板 (+15分)")
        elif high > current_price * 1.03:
            score -= 10
            details.append("盘中长上影线/冲高回落 (-10分)")

        # 4. 行业板块共振
        if sector_info:
            if sector_info.get('rank', 999) <= 5 and sector_info.get('avg_chg', 0) > 1:
                score += 15
                details.append("所属板块处于主升/启动期 (+15分)")
            elif sector_info.get('avg_chg', 0) < -1:
                score -= 10
                details.append("所属板块弱势退潮 (-10分)")

        # 综合评级
        score = min(max(score, 0), 100) # 0-100
        
        if score >= 85 and signal != "严格止损/空仓":
            signal = "强烈关注/买入序列"
        elif score >= 75 and signal != "严格止损/空仓":
            signal = "轻仓试错/持有"
        elif score < 60:
            signal = "回避/减仓"

        return {
            "score": score,
            "signal": signal,
            "details": details
        }

    @staticmethod
    def evaluate_sector(board_history: str, constituents_info: str) -> dict:
        """评估板块所处情绪周期阶段"""
        state = "潜伏期"
        signal = "持续观察"
        score = 30
        details = []

        # 解析动能和龙头表现 (简化启发式)
        if "📈 攻击" in board_history:
            state = "启动期"
            score = 60
            signal = "轻仓试错"
            details.append("板块指数近5日呈现攻击态势")
            
            # 判断是否进入主升
            if "领涨股" in constituents_info and "(+" in constituents_info:
                # 假设涨幅大于5%算强势领涨
                try:
                    chg_str = constituents_info.split("(+")[1].split("%")[0]
                    if float(chg_str) > 5.0:
                        state = "主升期"
                        score = 85
                        signal = "重点参与/重仓"
                        details.append(f"板块龙头标的强势领涨 (+{chg_str}%)")
                except Exception:
                    pass
        elif "📉 回撤" in board_history:
            state = "退潮期"
            score = 20
            signal = "清仓/回避"
            details.append("板块指数呈现回撤态势")
        
        # 判断高潮
        if state == "主升期" and score == 85:
            # 伪逻辑：如果特别强且连涨，提示高潮
            if "涨停" in constituents_info or "连板" in constituents_info:
                state = "高潮期"
                score = 70
                signal = "减仓预警/只出不进"
                details.append("板块进入情绪高点，防范极致拥挤")

        return {
            "state": state,
            "score": score,
            "signal": signal,
            "details": details
        }
