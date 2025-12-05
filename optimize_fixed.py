"""
Fixed Strategy Optimization with Correct Profit Calculation
"""

import pandas as pd
import numpy as np


def calculate_atr(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    """Calculate ATR for entire dataframe"""
    df = df.copy()
    df['hl'] = df['high'] - df['low']
    df['hc'] = abs(df['high'] - df['close'].shift(1))
    df['lc'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['hl', 'hc', 'lc']].max(axis=1)
    df['atr'] = df['tr'].rolling(window=period).mean()
    return df['atr'].values


def compute_emas(df: pd.DataFrame, fast_period: int = 9, slow_period: int = 15) -> pd.DataFrame:
    """Calculate EMA indicators"""
    df = df.copy()
    df["EMA_fast"] = df["close"].ewm(span=fast_period, adjust=False).mean()
    df["EMA_slow"] = df["close"].ewm(span=slow_period, adjust=False).mean()
    return df


def is_bearish_hammer(row, max_lower_shadow_factor=0.65, min_upper_shadow_ratio=1.5) -> bool:
    """Bearish hammer pattern detection"""
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if c >= o:
        return False
    body = o - c
    upper_shadow = h - o
    lower_shadow = c - l
    if lower_shadow > max_lower_shadow_factor * body:
        return False
    if upper_shadow < min_upper_shadow_ratio * body:
        return False
    return True


def is_bullish_hammer(row, max_upper_shadow_factor=0.65, min_lower_shadow_ratio=1.5) -> bool:
    """Bullish hammer pattern detection"""
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if c <= o:
        return False
    body = c - o
    upper_shadow = h - c
    lower_shadow = o - l
    if upper_shadow > max_upper_shadow_factor * body:
        return False
    if lower_shadow < min_lower_shadow_ratio * body:
        return False
    return True


def backtest_with_params(df: pd.DataFrame, buy_sl_mult: float, buy_tp_mult: float, 
                         sell_sl_mult: float, sell_tp_mult: float,
                         max_lower_shadow: float = 0.65, min_upper_shadow: float = 1.5) -> dict:
    """
    CORRECTED BACKTEST - Calculates REAL P&L
    """

    required_cols = ["open", "high", "low", "close", "volume"]
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"Missing required columns. Need: {required_cols}")

    df = df.copy()
    df = compute_emas(df, 9, 15)
    df["atr"] = calculate_atr(df, 14)

    df["is_bearish"] = df.apply(
        lambda row: is_bearish_hammer(row, max_lower_shadow, min_upper_shadow), 
        axis=1
    )
    df["is_bullish"] = df.apply(
        lambda row: is_bullish_hammer(row, max_lower_shadow, min_upper_shadow), 
        axis=1
    )

    df["buy_signal"] = df["is_bullish"]
    df["sell_signal"] = df["is_bearish"]

    trades = []

    for i in range(100, len(df)):
        row = df.iloc[i]

        if row["buy_signal"]:
            entry = row["close"]
            atr = row["atr"]

            if atr > 0:
                sl = entry - (buy_sl_mult * atr)
                tp = entry + (buy_tp_mult * atr)
            else:
                continue

            future_data = df.iloc[i + 1 : i + 100]
            exit_idx = None
            hit_tp = False

            for ts, future_row in future_data.iterrows():
                if future_row["high"] >= tp:
                    exit_idx = ts
                    hit_tp = True
                    break
                if future_row["low"] <= sl:
                    exit_idx = ts
                    hit_tp = False
                    break

            if exit_idx is not None:
                if hit_tp:
                    # TP hit: profit = TP distance
                    profit = buy_tp_mult * atr
                else:
                    # SL hit: loss = -SL distance
                    profit = -(buy_sl_mult * atr)

                trades.append({
                    "type": "BUY",
                    "entry": entry,
                    "profit": profit,
                    "hit_tp": hit_tp,
                })

        elif row["sell_signal"]:
            entry = row["close"]
            atr = row["atr"]

            if atr > 0:
                sl = entry + (sell_sl_mult * atr)
                tp = entry - (sell_tp_mult * atr)
            else:
                continue

            future_data = df.iloc[i + 1 : i + 100]
            exit_idx = None
            hit_tp = False

            for ts, future_row in future_data.iterrows():
                if future_row["low"] <= tp:
                    exit_idx = ts
                    hit_tp = True
                    break
                if future_row["high"] >= sl:
                    exit_idx = ts
                    hit_tp = False
                    break

            if exit_idx is not None:
                if hit_tp:
                    # TP hit: profit = TP distance
                    profit = sell_tp_mult * atr
                else:
                    # SL hit: loss = -SL distance
                    profit = -(sell_sl_mult * atr)

                trades.append({
                    "type": "SELL",
                    "entry": entry,
                    "profit": profit,
                    "hit_tp": hit_tp,
                })

    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0,
            "profit_factor": 0,
            "total_return": 0,
            "avg_win": 0,
            "avg_loss": 0,
        }

    trades_df = pd.DataFrame(trades)
    winners = trades_df[trades_df["profit"] > 0]
    losers = trades_df[trades_df["profit"] <= 0]

    win_count = len(winners)
    total_trades = len(trades_df)
    win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0

    total_profit = trades_df["profit"].sum()
    
    # CORRECTED profit_factor
    if len(losers) > 0 and losers["profit"].sum() != 0:
        profit_factor = winners["profit"].sum() / abs(losers["profit"].sum())
    else:
        profit_factor = float('inf') if total_profit > 0 else 0

    # CORRECTED total return (as percentage of wins vs losses)
    if abs(losers["profit"].sum()) > 0:
        total_return_pct = (winners["profit"].sum() / abs(losers["profit"].sum())) * 100
    else:
        total_return_pct = 100 if total_profit > 0 else 0

    avg_win = winners["profit"].mean() if len(winners) > 0 else 0
    avg_loss = abs(losers["profit"].mean()) if len(losers) > 0 else 0

    return {
        "total_trades": total_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "total_return": total_return_pct,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "total_profit": total_profit,
        "winners": len(winners),
        "losers": len(losers),
    }


def optimize_strategy_fixed():
    """Test multiple parameter combinations with CORRECT calculations"""

    print("\n" + "=" * 100)
    print("🔧 STRATEGY OPTIMIZATION - CORRECTED CALCULATIONS")
    print("=" * 100)

    # Test both BTC and GOLD
    files = [
        ("BTC_USD_M5.csv", "BTC_USD M5"),
        ("XAU_USD_M5.csv", "XAU_USD M5"),
    ]

    for filename, label in files:
        try:
            df = pd.read_csv(filename, parse_dates=["time"], index_col="time")
            df = df[["open", "high", "low", "close", "volume"]]
            print(f"\n✅ Loaded {label} ({len(df)} candles)")

            # Test best parameters from previous run
            test_params = [
                (1.0, 1.5, 1.5, 3.0, "Recommended #1"),
                (1.2, 1.5, 1.5, 3.0, "Recommended #2"),
                (0.8, 2.0, 2.0, 4.0, "Conservative"),
                (0.5, 2.5, 2.5, 5.0, "Wide SL"),
                (1.5, 1.0, 1.0, 2.0, "Tight"),
            ]

            print(f"\n   Testing key parameter combinations...")
            results = []

            for buy_sl, buy_tp, sell_sl, sell_tp, name in test_params:
                stats = backtest_with_params(df, buy_sl, buy_tp, sell_sl, sell_tp)
                
                results.append({
                    "name": name,
                    "buy_sl": buy_sl,
                    "buy_tp": buy_tp,
                    "sell_sl": sell_sl,
                    "sell_tp": sell_tp,
                    **stats
                })

            # Sort by win_rate + profit_factor
            results_sorted = sorted(
                results, 
                key=lambda x: (x["win_rate"] * 0.5 + x["profit_factor"] * 0.5), 
                reverse=True
            )

            print(f"\n   📊 Results for {label}:")
            print(f"   {'-' * 95}")

            for idx, r in enumerate(results_sorted, 1):
                ready = "✅" if (r["win_rate"] >= 55 and r["profit_factor"] >= 1.5) else "⚠️"
                print(f"\n   #{idx} {ready} {r['name']}")
                print(f"       BUY:  SL={r['buy_sl']}×ATR, TP={r['buy_tp']}×ATR")
                print(f"       SELL: SL={r['sell_sl']}×ATR, TP={r['sell_tp']}×ATR")
                print(f"       Win Rate: {r['win_rate']:.1f}% ({r['winners']}/{r['total_trades']}) | PF: {r['profit_factor']:.2f}x | Return: {r['total_return']:.1f}%")

        except FileNotFoundError:
            print(f"   ❌ {filename} not found")

    print("\n" + "=" * 100)
    print("⚠️ KEY INSIGHT:")
    print("=" * 100)
    print("""
Your current issue: Win rate is 32-35%, but you need 55%+ for a profitable strategy.

Why high profit factor but low win rate?
- Your TP is MUCH LARGER than SL (e.g., TP=3×ATR vs SL=1.5×ATR)
- When you WIN, you win big (3× reward)
- When you LOSE, you lose small (1.5× risk)
- But you're losing more often (68% of trades)

SOLUTIONS:
1. ✅ Increase win rate by tightening entry rules:
   - Stricter hammer pattern detection
   - Add trend confirmation (EMA filter)
   - Wait for multiple confirmations

2. ✅ Accept lower profit factor, improve win rate:
   - Use SL ≈ TP (1:1 R:R instead of 1:2)
   - Example: SL = 1.0×ATR, TP = 1.0×ATR
   - Aim for 55% win rate with 1:1 ratio = breakeven + fees

3. ✅ Hybrid approach (RECOMMENDED):
   - BUY: SL=1.0×ATR, TP=2.0×ATR (1:2 R:R)
   - SELL: SL=2.0×ATR, TP=2.0×ATR (1:1 R:R)  
   - Add EMA trend filter to increase win rate
""")
    print("=" * 100)


if __name__ == "__main__":
    optimize_strategy_fixed()
