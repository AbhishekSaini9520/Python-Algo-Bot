"""
Complete Accuracy Check - All functions included
No external imports needed from backtest module
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


def is_bearish_hammer(row) -> bool:
    """Bearish hammer pattern detection"""
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if c >= o:
        return False
    body = o - c
    upper_shadow = h - o
    lower_shadow = c - l
    if lower_shadow > 0.65 * body:
        return False
    if upper_shadow < 1.5 * body:
        return False
    return True


def is_bullish_hammer(row) -> bool:
    """Bullish hammer pattern detection"""
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if c <= o:
        return False
    body = c - o
    upper_shadow = h - c
    lower_shadow = o - l
    if upper_shadow > 0.65 * body:
        return False
    if lower_shadow < 1.5 * body:
        return False
    return True


def backtest_vectorized(df: pd.DataFrame, use_atr: bool = True) -> dict:
    """
    Vectorized backtest - process entire dataframe at once
    Returns: stats dict with all metrics
    """

    # Ensure we have required columns
    required_cols = ["open", "high", "low", "close", "volume"]
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"Missing required columns. Need: {required_cols}")

    df = df.copy()

    # Calculate indicators
    df = compute_emas(df, 9, 15)
    df["atr"] = calculate_atr(df, 14)

    # Pattern detection
    df["is_bearish"] = df.apply(is_bearish_hammer, axis=1)
    df["is_bullish"] = df.apply(is_bullish_hammer, axis=1)

    # Generate signals (no trend filter)
    df["buy_signal"] = df["is_bullish"]
    df["sell_signal"] = df["is_bearish"]

    # Count all patterns detected
    total_bullish_hammers = df["is_bullish"].sum()
    total_bearish_hammers = df["is_bearish"].sum()
    total_bullish_buy_signals = df["buy_signal"].sum()
    total_bearish_sell_signals = df["sell_signal"].sum()

    # Extract trades
    trades = []

    for i in range(100, len(df)):
        row = df.iloc[i]

        if row["buy_signal"]:
            entry = row["close"]
            atr = row["atr"]

            if use_atr and atr > 0:
                sl = entry - (1.0 * atr)
                tp = entry + (2.0 * atr)
            else:
                sl = entry - 5
                tp = entry + 10

            # Find exit (SL or TP hit)
            future_data = df.iloc[i + 1 : i + 100]

            hit_tp = False
            hit_sl = False
            exit_idx = None

            for ts, future_row in future_data.iterrows():
                if future_row["high"] >= tp:
                    hit_tp = True
                    exit_idx = ts
                    break
                if future_row["low"] <= sl:
                    hit_sl = True
                    exit_idx = ts
                    break

            if exit_idx is not None:
                exit_price = df.loc[exit_idx, "close"]
                profit = exit_price - entry if hit_tp else -(entry - exit_price)
                profit_pct = (profit / entry) * 100

                exit_pos = df.index.get_loc(exit_idx)

                trades.append(
                    {
                        "entry_time": df.index[i],
                        "entry_price": entry,
                        "exit_time": exit_idx,
                        "exit_price": exit_price,
                        "type": "BUY",
                        "profit": profit,
                        "profit_pct": profit_pct,
                        "hit_tp": hit_tp,
                        "sl": sl,
                        "tp": tp,
                        "candles_held": exit_pos - i,
                    }
                )

        elif row["sell_signal"]:
            entry = row["close"]
            atr = row["atr"]

            if use_atr and atr > 0:
                sl = entry + (2.0 * atr)
                tp = entry - (4.0 * atr)
            else:
                sl = entry + 10
                tp = entry - 20

            # Find exit
            future_data = df.iloc[i + 1 : i + 100]

            hit_tp = False
            hit_sl = False
            exit_idx = None

            for ts, future_row in future_data.iterrows():
                if future_row["low"] <= tp:
                    hit_tp = True
                    exit_idx = ts
                    break
                if future_row["high"] >= sl:
                    hit_sl = True
                    exit_idx = ts
                    break

            if exit_idx is not None:
                exit_price = df.loc[exit_idx, "close"]
                profit = entry - exit_price if hit_tp else -(exit_price - entry)
                profit_pct = (profit / entry) * 100

                exit_pos = df.index.get_loc(exit_idx)

                trades.append(
                    {
                        "entry_time": df.index[i],
                        "entry_price": entry,
                        "exit_time": exit_idx,
                        "exit_price": exit_price,
                        "type": "SELL",
                        "profit": profit,
                        "profit_pct": profit_pct,
                        "hit_tp": hit_tp,
                        "sl": sl,
                        "tp": tp,
                        "candles_held": exit_pos - i,
                    }
                )

    # Calculate statistics
    if not trades:
        print("❌ No trades generated")
        return {}

    trades_df = pd.DataFrame(trades)

    # Win/Loss metrics
    winners = trades_df[trades_df["profit"] > 0]
    losers = trades_df[trades_df["profit"] <= 0]

    # Count wins/losses by type
    buy_trades = trades_df[trades_df["type"] == "BUY"]
    sell_trades = trades_df[trades_df["type"] == "SELL"]
    buy_wins = len(buy_trades[buy_trades["profit"] > 0])
    sell_wins = len(sell_trades[sell_trades["profit"] > 0])

    win_count = len(winners)
    loss_count = len(losers)
    total_trades = len(trades_df)
    win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0

    # P&L metrics
    total_profit = trades_df["profit"].sum()
    avg_win = winners["profit"].mean() if len(winners) > 0 else 0
    avg_loss = abs(losers["profit"].mean()) if len(losers) > 0 else 0

    profit_factor = (
        winners["profit"].sum() / abs(losers["profit"].sum())
        if len(losers) > 0 and losers["profit"].sum() != 0
        else 0
    )

    # Risk metrics
    max_loss = losers["profit"].min() if len(losers) > 0 else 0
    max_gain = winners["profit"].max() if len(winners) > 0 else 0

    # Average holding time
    avg_candles = trades_df["candles_held"].mean()

    # Return metrics
    total_return_pct = (total_profit / (trades_df["entry_price"].sum() / total_trades)) * 100

    stats = {
        "total_trades": total_trades,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_rate,
        "total_profit": total_profit,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "max_win": max_gain,
        "max_loss": max_loss,
        "avg_candles_held": avg_candles,
        "total_return_pct": total_return_pct,
        "trades": trades_df,
        "total_bullish_hammers": total_bullish_hammers,
        "total_bearish_hammers": total_bearish_hammers,
        "total_bullish_buy_signals": total_bullish_buy_signals,
        "total_bearish_sell_signals": total_bearish_sell_signals,
        "buy_trades": len(buy_trades),
        "sell_trades": len(sell_trades),
        "buy_wins": buy_wins,
        "sell_wins": sell_wins,
    }

    return stats


def check_accuracy():
    """Check if strategy is ready for live trading"""

    print("\n" + "=" * 80)
    print("🔍 ACCURACY CHECK - SCANNING ALL TIMEFRAMES")
    print("=" * 80)

    # Define all timeframes and instruments to test
    test_files = [
        ("BTC_USD_M5.csv", "BTC_USD M5"),
        ("XAU_USD_M5.csv", "XAU_USD M5"),
    ]

    results = {}
    total_stats = {
        "total_files": 0,
        "files_passed": 0,
        "files_failed": 0,
        "avg_win_rate": 0,
        "avg_profit_factor": 0,
        "avg_return": 0,
    }

    for filename, label in test_files:
        try:
            print(f"\n📂 Loading {label}...")
            df = pd.read_csv(filename, parse_dates=["time"], index_col="time")
            df = df[["open", "high", "low", "close", "volume"]]

            print(f"   ✅ Loaded {len(df)} candles")

            # Run backtest
            print(f"   🧪 Running backtest...")
            stats = backtest_vectorized(df, use_atr=True)

            if not stats:
                print(f"   ❌ No trades generated for {label}")
                total_stats["files_failed"] += 1
                continue

            results[label] = {
                "win_rate": stats.get("win_rate", 0),
                "profit_factor": stats.get("profit_factor", 0),
                "total_return": stats.get("total_return_pct", 0),
                "total_trades": stats.get("total_trades", 0),
                "buy_trades": stats.get("buy_trades", 0),
                "sell_trades": stats.get("sell_trades", 0),
                "buy_wins": stats.get("buy_wins", 0),
                "sell_wins": stats.get("sell_wins", 0),
                "avg_win": stats.get("avg_win", 0),
                "avg_loss": stats.get("avg_loss", 0),
                "max_win": stats.get("max_win", 0),
                "max_loss": stats.get("max_loss", 0),
            }

            total_stats["total_files"] += 1

        except FileNotFoundError:
            print(f"   ⚠️ File {filename} not found, skipping...")
            total_stats["files_failed"] += 1
        except Exception as e:
            print(f"   ❌ Error processing {filename}: {e}")
            total_stats["files_failed"] += 1

    # Print detailed results
    print("\n" + "=" * 80)
    print("📊 DETAILED RESULTS")
    print("=" * 80)

    all_ready = True
    passed_count = 0

    for label, metrics in results.items():
        win_rate = metrics["win_rate"]
        pf = metrics["profit_factor"]
        ret = metrics["total_return"]
        trades = metrics["total_trades"]
        buy_trades = metrics["buy_trades"]
        sell_trades = metrics["sell_trades"]
        buy_wins = metrics["buy_wins"]
        sell_wins = metrics["sell_wins"]

        # Determine if this timeframe passes
        passes_win_rate = win_rate >= 55
        passes_pf = pf >= 1.5
        passes_return = ret > 0

        passes = passes_win_rate and passes_pf and passes_return

        if passes:
            passed_count += 1
        else:
            all_ready = False

        status = "✅ PASS" if passes else "❌ FAIL"

        print(f"\n{label} {status}")
        print(f"   Win Rate:        {win_rate:.1f}% {'✅' if passes_win_rate else '❌ (need ≥55%)'}")
        print(f"   Profit Factor:   {pf:.2f}x {'✅' if passes_pf else '❌ (need ≥1.5x)'}")
        print(f"   Total Return:    {ret:.2f}% {'✅' if passes_return else '❌ (need >0%)'}")
        print(f"   ---")
        print(f"   Total Trades:    {trades}")
        print(f"   BUY Trades:      {buy_trades} (Won: {buy_wins})")
        print(f"   SELL Trades:     {sell_trades} (Won: {sell_wins})")
        print(f"   Avg Win:         ${metrics['avg_win']:.2f}")
        print(f"   Avg Loss:        ${metrics['avg_loss']:.2f}")
        print(f"   Max Win:         ${metrics['max_win']:.2f}")
        print(f"   Max Loss:        ${metrics['max_loss']:.2f}")

    # Calculate averages
    if results:
        total_stats["avg_win_rate"] = sum(r["win_rate"] for r in results.values()) / len(results)
        total_stats["avg_profit_factor"] = sum(r["profit_factor"] for r in results.values()) / len(results)
        total_stats["avg_return"] = sum(r["total_return"] for r in results.values()) / len(results)
        total_stats["files_passed"] = passed_count

    # Print summary
    print("\n" + "=" * 80)
    print("📈 SUMMARY")
    print("=" * 80)
    print(f"\nFiles Tested:        {total_stats['total_files']}")
    print(f"Files Passed:        {total_stats['files_passed']} ✅")
    print(f"Files Failed:        {total_stats['files_failed']} ❌")
    print(f"\nAverage Win Rate:    {total_stats['avg_win_rate']:.1f}%")
    print(f"Average Profit Factor: {total_stats['avg_profit_factor']:.2f}x")
    print(f"Average Return:      {total_stats['avg_return']:.2f}%")

    print("\n" + "=" * 80)
    if all_ready and total_stats['files_passed'] == total_stats['total_files']:
        print("✅ STRATEGY READY FOR LIVE TRADING")
        print("All timeframes profitable and above thresholds!")
    else:
        print("❌ STRATEGY NOT READY - NEEDS OPTIMIZATION")
        print("\n🔧 Recommendations:")
        print("1. Adjust ATR multipliers:")
        print("   - BUY: Try SL 0.8 * ATR, TP 2.0 * ATR")
        print("   - SELL: Try SL 1.5 * ATR, TP 3.0 * ATR")
        print("\n2. Tighten hammer pattern detection:")
        print("   - Reduce upper_shadow threshold (currently 1.5)")
        print("   - Increase lower_shadow threshold (currently 0.65)")
        print("\n3. Adjust EMA periods:")
        print("   - Try fast=7, slow=14 instead of 9, 15")
        print("\n4. Add position sizing based on account balance")
        print("\n5. Test multiple timeframe combinations")
    print("=" * 80)


if __name__ == "__main__":
    check_accuracy()
