"""
Strategy Optimization Tester
Tests multiple parameter combinations to find the most profitable settings
"""

import pandas as pd
import numpy as np
from datetime import datetime


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
    Backtest with specific parameters
    
    buy_sl_mult: SL multiplier for BUY (e.g., 0.8 = 0.8 * ATR)
    buy_tp_mult: TP multiplier for BUY (e.g., 2.0 = 2.0 * ATR)
    sell_sl_mult: SL multiplier for SELL
    sell_tp_mult: TP multiplier for SELL
    """

    required_cols = ["open", "high", "low", "close", "volume"]
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"Missing required columns. Need: {required_cols}")

    df = df.copy()
    df = compute_emas(df, 9, 15)
    df["atr"] = calculate_atr(df, 14)

    # Pattern detection with custom parameters
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

            for ts, future_row in future_data.iterrows():
                if future_row["high"] >= tp:
                    exit_idx = ts
                    profit = entry - (entry - tp)  # TP hit = positive
                    break
                if future_row["low"] <= sl:
                    exit_idx = ts
                    profit = -(entry - sl)  # SL hit = negative
                    break

            if exit_idx is not None:
                exit_pos = df.index.get_loc(exit_idx)
                trades.append({
                    "type": "BUY",
                    "profit": profit,
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

            for ts, future_row in future_data.iterrows():
                if future_row["low"] <= tp:
                    exit_idx = ts
                    profit = entry - tp  # TP hit = positive
                    break
                if future_row["high"] >= sl:
                    exit_idx = ts
                    profit = -(sl - entry)  # SL hit = negative
                    break

            if exit_idx is not None:
                exit_pos = df.index.get_loc(exit_idx)
                trades.append({
                    "type": "SELL",
                    "profit": profit,
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
    profit_factor = (
        winners["profit"].sum() / abs(losers["profit"].sum())
        if len(losers) > 0 and losers["profit"].sum() != 0
        else 0
    )

    total_return_pct = (total_profit / abs(trades_df["profit"].sum() + 1)) * 100

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
    }


def optimize_strategy():
    """Test multiple parameter combinations and find the best one"""

    print("\n" + "=" * 100)
    print("🔧 STRATEGY OPTIMIZATION - TESTING PARAMETER COMBINATIONS")
    print("=" * 100)

    # Load test data
    try:
        df = pd.read_csv("XAU_USD_M5.csv", parse_dates=["time"], index_col="time")
        df = df[["open", "high", "low", "close", "volume"]]
        print(f"\n✅ Loaded XAU_USD_M5.csv ({len(df)} candles)")
    except FileNotFoundError:
        print("❌ XAU_USD_M5.csv not found!")
        return

    # Parameters to test
    buy_sl_options = [0.5, 0.8, 1.0, 1.2]  # SL multipliers for BUY
    buy_tp_options = [1.5, 2.0, 2.5, 3.0]  # TP multipliers for BUY
    sell_sl_options = [1.5, 2.0, 2.5]      # SL multipliers for SELL
    sell_tp_options = [3.0, 4.0, 5.0]      # TP multipliers for SELL

    best_result = None
    best_score = -float('inf')
    results = []

    total_combos = (len(buy_sl_options) * len(buy_tp_options) * 
                   len(sell_sl_options) * len(sell_tp_options))
    
    print(f"\n🧪 Testing {total_combos} parameter combinations...\n")

    combo_num = 0
    for buy_sl in buy_sl_options:
        for buy_tp in buy_tp_options:
            for sell_sl in sell_sl_options:
                for sell_tp in sell_tp_options:
                    combo_num += 1
                    
                    # Skip invalid combinations (TP must be > SL distance)
                    if buy_tp <= buy_sl or sell_tp <= sell_sl:
                        continue

                    stats = backtest_with_params(
                        df, 
                        buy_sl_mult=buy_sl,
                        buy_tp_mult=buy_tp,
                        sell_sl_mult=sell_sl,
                        sell_tp_mult=sell_tp
                    )

                    # Score = (win_rate * 0.4) + (profit_factor * 0.6)
                    score = (stats["win_rate"] * 0.4) + (stats["profit_factor"] * 0.6)

                    results.append({
                        "buy_sl": buy_sl,
                        "buy_tp": buy_tp,
                        "sell_sl": sell_sl,
                        "sell_tp": sell_tp,
                        "win_rate": stats["win_rate"],
                        "profit_factor": stats["profit_factor"],
                        "total_return": stats["total_return"],
                        "total_trades": stats["total_trades"],
                        "score": score,
                    })

                    if score > best_score:
                        best_score = score
                        best_result = results[-1]

                    # Print progress every 10 combos
                    if combo_num % 10 == 0:
                        print(f"   Tested {combo_num}/{total_combos} combinations...", end='\r')

    print(f"   ✅ Tested all {total_combos} combinations!                    ")

    # Sort results by score
    results_sorted = sorted(results, key=lambda x: x["score"], reverse=True)

    # Print top 10 results
    print("\n" + "=" * 100)
    print("🏆 TOP 10 PARAMETER COMBINATIONS")
    print("=" * 100)

    for idx, result in enumerate(results_sorted[:10], 1):
        print(f"\n#{idx} - Score: {result['score']:.2f}")
        print(f"   BUY:  SL = {result['buy_sl']:.1f} * ATR,  TP = {result['buy_tp']:.1f} * ATR")
        print(f"   SELL: SL = {result['sell_sl']:.1f} * ATR,  TP = {result['sell_tp']:.1f} * ATR")
        print(f"   Win Rate:       {result['win_rate']:.1f}% {'✅' if result['win_rate'] >= 55 else '❌'}")
        print(f"   Profit Factor:  {result['profit_factor']:.2f}x {'✅' if result['profit_factor'] >= 1.5 else '❌'}")
        print(f"   Total Return:   {result['total_return']:.2f}% {'✅' if result['total_return'] > 0 else '❌'}")
        print(f"   Total Trades:   {result['total_trades']}")

    # Print best result
    print("\n" + "=" * 100)
    print("🎯 BEST PARAMETERS FOUND")
    print("=" * 100)

    if best_result:
        print(f"\n✅ Best Configuration:")
        print(f"\n   BUY Orders:")
        print(f"      SL Distance = {best_result['buy_sl']:.1f} * ATR")
        print(f"      TP Distance = {best_result['buy_tp']:.1f} * ATR")
        print(f"\n   SELL Orders:")
        print(f"      SL Distance = {best_result['sell_sl']:.1f} * ATR")
        print(f"      TP Distance = {best_result['sell_tp']:.1f} * ATR")
        print(f"\n   Performance:")
        print(f"      Win Rate:      {best_result['win_rate']:.1f}%")
        print(f"      Profit Factor: {best_result['profit_factor']:.2f}x")
        print(f"      Total Return:  {best_result['total_return']:.2f}%")
        print(f"      Total Trades:  {best_result['total_trades']}")

        # Check if it passes minimum requirements
        passes = (best_result['win_rate'] >= 55 and 
                 best_result['profit_factor'] >= 1.5 and 
                 best_result['total_return'] > 0)

        print(f"\n   Status: {'✅ READY FOR LIVE TRADING' if passes else '⚠️ STILL NEEDS WORK'}")

        print(f"\n" + "=" * 100)
        print("💾 HOW TO USE THESE PARAMETERS:")
        print("=" * 100)
        print(f"\nUpdate your calculate_dynamic_sl_tp() function:\n")
        print(f"   BUY:")
        print(f"      sl_distance = round({best_result['buy_sl']} * atr, precision)")
        print(f"      tp_distance = round({best_result['buy_tp']} * atr, precision)")
        print(f"\n   SELL:")
        print(f"      sl_distance = round({best_result['sell_sl']} * atr, precision)")
        print(f"      tp_distance = round({best_result['sell_tp']} * atr, precision)")

    print("\n" + "=" * 100)


if __name__ == "__main__":
    optimize_strategy()
