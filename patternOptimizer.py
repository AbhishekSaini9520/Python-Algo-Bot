"""
Hammer Pattern Optimizer - Find the BEST pattern parameters
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
    df["EMA_lower"] = df[["EMA_fast", "EMA_slow"]].min(axis=1)
    df["EMA_upper"] = df[["EMA_fast", "EMA_slow"]].max(axis=1)
    return df


def is_bearish_hammer(row, max_lower_shadow=0.65, min_upper_shadow=1.5) -> bool:
    """Bearish hammer with tight parameters"""
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if c >= o:
        return False
    body = o - c
    if body < 0.0001:  # Reject doji-like
        return False
    upper_shadow = h - o
    lower_shadow = c - l
    if lower_shadow > max_lower_shadow * body:
        return False
    if upper_shadow < min_upper_shadow * body:
        return False
    return True


def is_bullish_hammer(row, max_upper_shadow=0.65, min_lower_shadow=1.5) -> bool:
    """Bullish hammer with tight parameters"""
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if c <= o:
        return False
    body = c - o
    if body < 0.0001:  # Reject doji-like
        return False
    upper_shadow = h - c
    lower_shadow = o - l
    if upper_shadow > max_upper_shadow * body:
        return False
    if lower_shadow < min_lower_shadow * body:
        return False
    return True


def is_uptrend(row) -> bool:
    """EMA trend filter"""
    return row["close"] > row["EMA_lower"]


def is_downtrend(row) -> bool:
    """EMA trend filter"""
    return row["close"] < row["EMA_upper"]


def backtest_with_pattern_params(df: pd.DataFrame, 
                                 max_lower_shadow: float, 
                                 min_upper_shadow: float,
                                 use_trend_filter: bool = True,
                                 buy_sl_mult: float = 1.0,
                                 buy_tp_mult: float = 1.5,
                                 sell_sl_mult: float = 1.5,
                                 sell_tp_mult: float = 3.0) -> dict:
    """Backtest with specific hammer pattern parameters"""

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

    df["is_uptrend"] = df.apply(is_uptrend, axis=1)
    df["is_downtrend"] = df.apply(is_downtrend, axis=1)

    if use_trend_filter:
        df["buy_signal"] = df["is_bullish"] & df["is_uptrend"]
        df["sell_signal"] = df["is_bearish"] & df["is_downtrend"]
    else:
        df["buy_signal"] = df["is_bullish"]
        df["sell_signal"] = df["is_bearish"]

    total_patterns = df["is_bullish"].sum() + df["is_bearish"].sum()

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
                profit = buy_tp_mult * atr if hit_tp else -(buy_sl_mult * atr)
                trades.append({"type": "BUY", "profit": profit, "hit_tp": hit_tp})

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
                profit = sell_tp_mult * atr if hit_tp else -(sell_sl_mult * atr)
                trades.append({"type": "SELL", "profit": profit, "hit_tp": hit_tp})

    if not trades:
        return {
            "total_patterns": total_patterns,
            "total_trades": 0,
            "win_rate": 0,
            "profit_factor": 0,
            "avg_win": 0,
            "avg_loss": 0,
        }

    trades_df = pd.DataFrame(trades)
    winners = trades_df[trades_df["profit"] > 0]
    losers = trades_df[trades_df["profit"] <= 0]

    win_rate = (len(winners) / len(trades_df)) * 100 if len(trades_df) > 0 else 0

    profit_factor = (
        winners["profit"].sum() / abs(losers["profit"].sum())
        if len(losers) > 0 and losers["profit"].sum() != 0
        else 0
    )

    avg_win = winners["profit"].mean() if len(winners) > 0 else 0
    avg_loss = abs(losers["profit"].mean()) if len(losers) > 0 else 0

    return {
        "total_patterns": total_patterns,
        "total_trades": len(trades_df),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "winners": len(winners),
        "losers": len(losers),
    }


def optimize_hammer_pattern():
    """Find the best hammer pattern parameters"""

    print("\n" + "=" * 110)
    print("🔨 HAMMER PATTERN OPTIMIZER - Finding the Best Pattern Detection")
    print("=" * 110)

    try:
        df = pd.read_csv("BTC_USD_M5.csv", parse_dates=["time"], index_col="time")
        df = df[["open", "high", "low", "close", "volume"]]
    except FileNotFoundError:
        print("❌ BTC_USD_M5.csv not found!")
        return

    # Test different hammer pattern parameters
    test_configs = [
        # (max_lower_shadow, min_upper_shadow, use_trend_filter, name)
        (0.65, 1.5, False, "Default (no trend)"),
        (0.65, 1.5, True, "Default + EMA filter"),
        (0.5, 2.0, True, "Strict + EMA filter"),
        (0.4, 2.5, True, "Very Strict + EMA"),
        (0.3, 3.0, True, "Ultra Strict + EMA"),
        (0.55, 1.8, True, "Balanced + EMA"),
    ]

    print(f"\n✅ Testing {len(test_configs)} hammer pattern configurations...\n")

    results = []

    for max_lower, min_upper, use_trend, name in test_configs:
        stats = backtest_with_pattern_params(
            df,
            max_lower_shadow=max_lower,
            min_upper_shadow=min_upper,
            use_trend_filter=use_trend,
            buy_sl_mult=1.0,
            buy_tp_mult=1.5,
            sell_sl_mult=1.5,
            sell_tp_mult=3.0
        )

        results.append({
            "name": name,
            "max_lower": max_lower,
            "min_upper": min_upper,
            "use_trend": use_trend,
            **stats
        })

    # Sort by profit_factor
    results_sorted = sorted(results, key=lambda x: x["profit_factor"], reverse=True)

    print("📊 RESULTS (sorted by Profit Factor):\n")
    print(f"{'Config':<30} {'Patterns':<10} {'Trades':<10} {'Win%':<10} {'PF':<10} {'Avg W/L':<15}")
    print("-" * 110)

    for r in results_sorted:
        trend = "✅ EMA" if r["use_trend"] else "❌ No"
        status = "✅" if r["profit_factor"] >= 1.0 else "❌"
        print(
            f"{r['name']:<30} {r['total_patterns']:<10} {r['total_trades']:<10} "
            f"{r['win_rate']:.1f}%{'':<5} {r['profit_factor']:<10.2f} "
            f"${r['avg_win']:.2f} / ${r['avg_loss']:.2f} {status}"
        )

    print("\n" + "=" * 110)
    print("💡 RECOMMENDATIONS:")
    print("=" * 110)

    best = results_sorted[0]
    if best["profit_factor"] >= 1.0:
        print(f"""
✅ FOUND PROFITABLE CONFIGURATION!

Use these hammer pattern parameters in your code:

def is_bearish_hammer(row):
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if c >= o:
        return False
    body = o - c
    upper_shadow = h - o
    lower_shadow = c - l
    if lower_shadow > {best['max_lower']} * body:  # ← {best['max_lower']}
        return False
    if upper_shadow < {best['min_upper']} * body:  # ← {best['min_upper']}
        return False
    return True

def is_bullish_hammer(row):
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if c <= o:
        return False
    body = c - o
    upper_shadow = h - c
    lower_shadow = o - l
    if upper_shadow > {best['max_lower']} * body:  # ← {best['max_lower']}
        return False
    if lower_shadow < {best['min_upper']} * body:  # ← {best['min_upper']}
        return False
    return True

Performance: {best['win_rate']:.1f}% win rate, {best['profit_factor']:.2f}x profit factor
""")
    else:
        print(f"""
⚠️ NO PROFITABLE CONFIGURATION FOUND YET

Best attempt:
- Win Rate: {best['win_rate']:.1f}%
- Profit Factor: {best['profit_factor']:.2f}x
- Patterns Detected: {best['total_patterns']}
- Trades Executed: {best['total_trades']}

Next steps:
1. Try different EMA periods (fast=7, slow=14 instead of 9, 15)
2. Add additional confirmation (volume, RSI, MACD)
3. Use multiple timeframe confirmation
4. Consider using a different pattern (not just hammers)
5. Test on SELL signals separately from BUY signals
""")

    print("=" * 110)


if __name__ == "__main__":
    optimize_hammer_pattern()
