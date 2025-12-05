"""
Simple Backtest Template for Optimized Trading Bot
Demonstrates how to validate strategy on historical data
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



    # REMOVED: Trend confirmation (no uptrend/downtrend filter)
    # Signals trigger on hammer pattern alone
    df["buy_signal"] = df["is_bullish"]
    df["sell_signal"] = df["is_bearish"]



    # ✅ Count all patterns detected
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
            future_data = df.iloc[i + 1 : i + 100]  # Look ahead 100 candles



            hit_tp = False
            hit_sl = False
            exit_idx = None



            for ts, future_row in future_data.iterrows():
                if future_row["high"] >= tp:
                    hit_tp = True
                    exit_idx = ts  # timestamp label
                    break
                if future_row["low"] <= sl:
                    hit_sl = True
                    exit_idx = ts  # timestamp label
                    break



            if exit_idx is not None:
                exit_price = df.loc[exit_idx, "close"]
                profit = exit_price - entry if hit_tp else -(entry - exit_price)
                profit_pct = (profit / entry) * 100



                # Convert timestamp to position for candles_held
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
                    exit_idx = ts  # timestamp label
                    break
                if future_row["high"] >= sl:
                    hit_sl = True
                    exit_idx = ts  # timestamp label
                    break



            if exit_idx is not None:
                exit_price = df.loc[exit_idx, "close"]
                profit = entry - exit_price if hit_tp else -(exit_price - entry)
                profit_pct = (profit / entry) * 100



                # Convert timestamp to position for candles_held
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
        # Pattern detection stats
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




def print_backtest_results(stats: dict):
    """Pretty print backtest results"""



    print("\n" + "=" * 80)
    print("BACKTEST RESULTS")
    print("=" * 80)


    # Pattern Detection Section
    print(f"\n🔨 Pattern Detection:")
    print(f"   Total Bullish Hammers:  {stats['total_bullish_hammers']}")
    print(f"   Total Bearish Hammers:  {stats['total_bearish_hammers']}")
    print(f"   Bullish Buy Signals:    {stats['total_bullish_buy_signals']}")
    print(f"   Bearish Sell Signals:   {stats['total_bearish_sell_signals']}")


    # Trade Type Breakdown
    print(f"\n📊 Trade Breakdown:")
    print(f"   Total BUY Trades:       {stats['buy_trades']} (Win: {stats['buy_wins']})")
    print(f"   Total SELL Trades:      {stats['sell_trades']} (Win: {stats['sell_wins']})")


    print(f"\n📊 Trade Count:")
    print(f"   Total Trades:     {stats['total_trades']}")
    print(f"   Winning Trades:   {stats['win_count']} ({stats['win_rate']:.2f}%)")
    print(f"   Losing Trades:    {stats['loss_count']} ({100 - stats['win_rate']:.2f}%)")



    print(f"\n💰 Profitability:")
    print(f"   Total P&L:        ${stats['total_profit']:.2f}")
    print(f"   Total Return:     {stats['total_return_pct']:.2f}%")
    print(f"   Avg Win:          ${stats['avg_win']:.2f}")
    print(f"   Avg Loss:         ${stats['avg_loss']:.2f}")
    print(f"   Profit Factor:    {stats['profit_factor']:.2f}x")



    print(f"\n📈 Risk Metrics:")
    print(f"   Max Win:          ${stats['max_win']:.2f}")
    print(f"   Max Loss:         ${stats['max_loss']:.2f}")
    print(f"   Avg Candles Held: {stats['avg_candles_held']:.1f}")



    # Assessment
    print(f"\n✅ Assessment:")
    if stats["win_rate"] >= 55:
        print(
            f"   Win Rate: {'✅ Good' if stats['win_rate'] >= 60 else '⚠️ Acceptable'} ({stats['win_rate']:.1f}%)"
        )
    else:
        print(f"   Win Rate: ❌ Poor ({stats['win_rate']:.1f}%)")



    if stats["profit_factor"] >= 1.5:
        print(
            f"   Profit Factor: {'✅ Good' if stats['profit_factor'] >= 2.0 else '⚠️ Acceptable'} ({stats['profit_factor']:.2f}x)"
        )
    else:
        print(f"   Profit Factor: ❌ Poor ({stats['profit_factor']:.2f}x)")



    if stats["total_return_pct"] > 0:
        print(f"   Profitability: ✅ Profitable (+{stats['total_return_pct']:.2f}%)")
    else:
        print(f"   Profitability: ❌ Loss ({stats['total_return_pct']:.2f}%)")



    print("\n" + "=" * 80)




# Example usage
if __name__ == "__main__":
    # Load your historical data
    df = pd.read_csv("BTC_USD_M5.csv", parse_dates=["time"], index_col="time")
    df = df[["open", "high", "low", "close", "volume"]]



    # Run backtest
    stats = backtest_vectorized(df, use_atr=True)



    # Print results
    print_backtest_results(stats)



    # Save trades to CSV
    stats["trades"].to_csv("backtest_results.csv")



    print("✅ Backtest template ready!")
    print("Instructions:")
    print("1. Load historical OHLC data into 'df'")
    print("2. Call: stats = backtest_vectorized(df)")
    print("3. Call: print_backtest_results(stats)")
    print("\nColumns required: ['open', 'high', 'low', 'close', 'volume']")
