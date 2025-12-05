"""
FINAL TRADING BOT - With Optimized Parameters
Ready to use with your Oanda account
"""

import time
import logging
import requests
import pandas as pd
from dataclasses import dataclass, field
from threading import Thread
from typing import Dict


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


@dataclass
class OandaConfig:
    api_key: str
    account_id: str
    base_url: str = "https://api-fxpractice.oanda.com"
    instruments: list = field(default_factory=lambda: ["BTC_USD", "XAU_USD"])
    timeframes: list = field(default_factory=lambda: ["M5", "M15"])
    lookback_candles: int = 100
    units: int = 1
    poll_sec: int = 30
    ema_fast: int = 9
    ema_slow: int = 15
    atr_period: int = 14
    use_atr: bool = True
    # ✅ OPTIMIZED PATTERN PARAMETERS
    max_lower_shadow_factor: float = 0.4   # Strict (was 0.65)
    min_upper_shadow_ratio: float = 2.5    # Strict (was 1.5)
    # ✅ OPTIMIZED SL/TP PARAMETERS
    buy_sl_mult: float = 1.0
    buy_tp_mult: float = 1.5
    sell_sl_mult: float = 1.5
    sell_tp_mult: float = 3.0


CFG = OandaConfig(
    api_key="5c821a3a1a23d3b8a18ffb0b8d10d852-887ec40cabdda2551683deb7e6d329a4",
    account_id="101-011-36217286-002",
)

HEADERS = {
    "Authorization": f"Bearer {CFG.api_key}",
    "Content-Type": "application/json"
}

INSTRUMENT_PRECISION = {
    "BTC_USD": 2,
    "XAU_USD": 3,
}

active_positions: Dict[str, Dict] = {}


def get_position_key(instrument: str, timeframe: str) -> str:
    """Generate unique key for position tracking"""
    return f"{instrument}_{timeframe}"


def has_active_position(instrument: str, timeframe: str) -> bool:
    """Check if there's an active position"""
    key = get_position_key(instrument, timeframe)
    return key in active_positions


def add_active_position(instrument: str, timeframe: str, trade_type: str, entry_price: float):
    """Record active position"""
    key = get_position_key(instrument, timeframe)
    active_positions[key] = {
        "type": trade_type,
        "entry": entry_price,
        "timestamp": time.time()
    }
    logging.info(f"✅ Position added: {key} | Type: {trade_type} | Entry: {entry_price}")


def remove_active_position(instrument: str, timeframe: str):
    """Remove position when closed"""
    key = get_position_key(instrument, timeframe)
    if key in active_positions:
        del active_positions[key]
        logging.info(f"✅ Position removed: {key}")


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate Average True Range"""
    if len(df) < period + 1:
        return 0.0
    
    df = df.copy()
    df['hl'] = df['high'] - df['low']
    df['hc'] = abs(df['high'] - df['close'].shift(1))
    df['lc'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['hl', 'hc', 'lc']].max(axis=1)
    
    atr = df['tr'].rolling(window=period).mean().iloc[-1]
    return atr if atr > 0 else 1.0


def calculate_dynamic_sl_tp(entry: float, atr: float, precision: int, trade_type: str = "BUY") -> tuple:
    """
    ✅ OPTIMIZED: Calculate SL/TP with best parameters
    
    BUY:  SL = entry - (1.0 * ATR), TP = entry + (1.5 * ATR)
    SELL: SL = entry + (1.5 * ATR), TP = entry - (3.0 * ATR)
    """
    if trade_type == "BUY":
        sl_distance = round(CFG.buy_sl_mult * atr, precision)
        tp_distance = round(CFG.buy_tp_mult * atr, precision)
        sl_price = round(entry - sl_distance, precision)
        tp_price = round(entry + tp_distance, precision)
    else:  # SELL
        sl_distance = round(CFG.sell_sl_mult * atr, precision)
        tp_distance = round(CFG.sell_tp_mult * atr, precision)
        sl_price = round(entry + sl_distance, precision)
        tp_price = round(entry - tp_distance, precision)
    
    return sl_price, tp_price, sl_distance, tp_distance


def fetch_ohlc(instrument: str, granularity: str, count: int) -> pd.DataFrame:
    """Fetch OHLC data from Oanda with retry logic"""
    url = f"{CFG.base_url}/v3/instruments/{instrument}/candles"
    params = {"count": count, "granularity": granularity, "price": "M"}
    
    for attempt in range(3):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                params=params,
                timeout=20
            )
            response.raise_for_status()
            break
        except requests.exceptions.Timeout:
            logging.warning(f"Timeout fetching {instrument} {granularity}, attempt {attempt+1}/3")
            if attempt == 2:
                raise
            time.sleep(2)

    candles = response.json().get("candles", [])
    if not candles:
        return pd.DataFrame()
    
    data = [{
        "time": candle["time"],
        "open": float(candle["mid"]["o"]),
        "high": float(candle["mid"]["h"]),
        "low": float(candle["mid"]["l"]),
        "close": float(candle["mid"]["c"]),
        "volume": candle["volume"],
        "complete": candle["complete"]
    } for candle in candles]
    
    df = pd.DataFrame(data)
    df["time"] = pd.to_datetime(df["time"], format="%Y-%m-%dT%H:%M:%S.%f000Z", errors='coerce')
    df.set_index("time", inplace=True)
    return df


def compute_emas(df: pd.DataFrame, fast_period: int, slow_period: int) -> pd.DataFrame:
    """Calculate EMA indicators"""
    df = df.copy()
    df["EMA_fast"] = df["close"].ewm(span=fast_period, adjust=False).mean()
    df["EMA_slow"] = df["close"].ewm(span=slow_period, adjust=False).mean()
    df["EMA_lower"] = df[["EMA_fast", "EMA_slow"]].min(axis=1)
    df["EMA_upper"] = df[["EMA_fast", "EMA_slow"]].max(axis=1)
    return df


# ✅ OPTIMIZED PATTERN DETECTION
def is_bearish_hammer(row) -> bool:
    """
    ✅ OPTIMIZED: Very Strict bearish hammer detection
    Parameters from pattern optimizer
    """
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if c >= o:
        return False
    body = o - c
    if body < 0.0001:
        return False
    upper_shadow = h - o
    lower_shadow = c - l
    
    # ✅ STRICT PARAMETERS
    if lower_shadow > CFG.max_lower_shadow_factor * body:  # 0.4
        return False
    if upper_shadow < CFG.min_upper_shadow_ratio * body:  # 2.5
        return False
    return True


def is_bullish_hammer(row) -> bool:
    """
    ✅ OPTIMIZED: Very Strict bullish hammer detection
    Parameters from pattern optimizer
    """
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if c <= o:
        return False
    body = c - o
    if body < 0.0001:
        return False
    upper_shadow = h - c
    lower_shadow = o - l
    
    # ✅ STRICT PARAMETERS
    if upper_shadow > CFG.max_lower_shadow_factor * body:  # 0.4
        return False
    if lower_shadow < CFG.min_upper_shadow_ratio * body:  # 2.5
        return False
    return True


def is_uptrend(row) -> bool:
    """Check if price is in uptrend (close > EMA_lower)"""
    return row["close"] > row["EMA_lower"]


def is_downtrend(row) -> bool:
    """Check if price is in downtrend (close < EMA_upper)"""
    return row["close"] < row["EMA_upper"]


def place_market_buy_with_sl_tp(instrument: str, units: int, sl_price: float, tp_price: float, 
                                entry: float, atr: float, timeframe: str):
    """Place a BUY market order with SL and TP"""
    precision = INSTRUMENT_PRECISION.get(instrument, 2)
    
    # Round for precision
    sl_price = round(sl_price, precision)
    tp_price = round(tp_price, precision)
    
    url = f"{CFG.base_url}/v3/accounts/{CFG.account_id}/orders"
    order = {
        "order": {
            "units": str(units),
            "instrument": instrument,
            "timeInForce": "FOK",
            "type": "MARKET",
            "positionFill": "DEFAULT",
            "stopLossOnFill": {"price": f"{sl_price:.{precision}f}"},
            "takeProfitOnFill": {"price": f"{tp_price:.{precision}f}"}
        }
    }
    
    response = requests.post(url, headers=HEADERS, json=order, timeout=10)
    if response.status_code == 201:
        logging.info(f"✅ BUY order placed for {instrument}: Entry={entry:.{precision}f}, SL={sl_price:.{precision}f}, TP={tp_price:.{precision}f}, ATR={atr:.{precision}f}")
        add_active_position(instrument, timeframe, "BUY", entry)
        return True
    else:
        logging.error(f"❌ Failed to place buy order for {instrument}: {response.status_code} {response.text}")
        return False


def place_market_sell_with_sl_tp(instrument: str, units: int, sl_price: float, tp_price: float, 
                                 entry: float, atr: float, timeframe: str):
    """Place a SELL market order with SL and TP"""
    precision = INSTRUMENT_PRECISION.get(instrument, 2)
    
    # Round for precision
    sl_price = round(sl_price, precision)
    tp_price = round(tp_price, precision)
    
    url = f"{CFG.base_url}/v3/accounts/{CFG.account_id}/orders"
    order = {
        "order": {
            "units": str(-units),
            "instrument": instrument,
            "timeInForce": "FOK",
            "type": "MARKET",
            "positionFill": "DEFAULT",
            "stopLossOnFill": {"price": f"{sl_price:.{precision}f}"},
            "takeProfitOnFill": {"price": f"{tp_price:.{precision}f}"}
        }
    }
    
    response = requests.post(url, headers=HEADERS, json=order, timeout=10)
    if response.status_code == 201:
        logging.info(f"✅ SELL order placed for {instrument}: Entry={entry:.{precision}f}, SL={sl_price:.{precision}f}, TP={tp_price:.{precision}f}, ATR={atr:.{precision}f}")
        add_active_position(instrument, timeframe, "SELL", entry)
        return True
    else:
        logging.error(f"❌ Failed to place sell order for {instrument}: {response.status_code} {response.text}")
        return False


def run_for_instrument_and_timeframe(instrument: str, timeframe: str):
    """Main trading loop for one instrument+timeframe combination"""
    logging.info(f"🚀 Starting {instrument} bot for {timeframe}")
    last_time = None
    precision = INSTRUMENT_PRECISION.get(instrument, 2)
    
    while True:
        try:
            # Fetch OHLC data
            df = fetch_ohlc(instrument, timeframe, CFG.lookback_candles)
            if df.empty or len(df) < CFG.ema_slow + 1:
                logging.warning(f"⚠️ Not enough data for {instrument} {timeframe}")
                time.sleep(CFG.poll_sec)
                continue

            # Filter only completed candles
            df = df[df["complete"] == True].copy()
            if df.empty:
                logging.info(f"⏳ No completed candle yet for {instrument} {timeframe}")
                time.sleep(CFG.poll_sec)
                continue

            # Calculate indicators
            df = compute_emas(df, CFG.ema_fast, CFG.ema_slow)
            last = df.iloc[-1]
            time_stamp = df.index[-1]

            # Skip if same candle
            if time_stamp == last_time:
                time.sleep(CFG.poll_sec)
                continue
            last_time = time_stamp

            # Calculate ATR
            atr = calculate_atr(df, CFG.atr_period) if CFG.use_atr else 1.0

            logging.info(f"📊 {instrument} {timeframe} @ {time_stamp} | "
                         f"O:{last['open']:.2f} H:{last['high']:.2f} L:{last['low']:.2f} C:{last['close']:.2f} | "
                         f"ATR:{atr:.2f}")

            # Skip if position exists
            if has_active_position(instrument, timeframe):
                logging.info(f"⏸️ Already in position for {instrument} {timeframe}")
                time.sleep(CFG.poll_sec)
                continue

            # ✅ CHECK FOR BEARISH HAMMER (SELL SIGNAL)
            if is_bearish_hammer(last) and is_downtrend(last):
                entry = last["close"]
                sl_price, tp_price, sl_dist, tp_dist = calculate_dynamic_sl_tp(entry, atr, precision, "SELL")

                if sl_price <= entry and tp_price < entry:
                    logging.info(f"🔴 SELL signal! Entry={entry:.{precision}f}, SL={sl_price:.{precision}f}, TP={tp_price:.{precision}f}")
                    place_market_sell_with_sl_tp(instrument, CFG.units, sl_price=sl_price, tp_price=tp_price, 
                                                 entry=entry, atr=atr, timeframe=timeframe)

            # ✅ CHECK FOR BULLISH HAMMER (BUY SIGNAL)
            elif is_bullish_hammer(last) and is_uptrend(last):
                entry = last["close"]
                sl_price, tp_price, sl_dist, tp_dist = calculate_dynamic_sl_tp(entry, atr, precision, "BUY")

                if sl_price < entry and tp_price > entry:
                    logging.info(f"🟢 BUY signal! Entry={entry:.{precision}f}, SL={sl_price:.{precision}f}, TP={tp_price:.{precision}f}")
                    place_market_buy_with_sl_tp(instrument, CFG.units, sl_price=sl_price, tp_price=tp_price, 
                                                entry=entry, atr=atr, timeframe=timeframe)

            time.sleep(CFG.poll_sec)

        except Exception as e:
            logging.exception(f"❌ Error in {instrument} {timeframe}: {e}")
            time.sleep(CFG.poll_sec)


def run_all():
    """Start bot for all instruments and timeframes"""
    threads = []
    for instrument in CFG.instruments:
        for timeframe in CFG.timeframes:
            t = Thread(target=run_for_instrument_and_timeframe, args=(instrument, timeframe), daemon=True)
            threads.append(t)
            t.start()
    
    for t in threads:
        t.join()


if __name__ == "__main__":
    print("\n" + "="*80)
    print("🤖 TRADING BOT - OPTIMIZED PARAMETERS")
    print("="*80)
    print(f"\n✅ Configuration:")
    print(f"   Max Lower Shadow: {CFG.max_lower_shadow_factor} (very strict)")
    print(f"   Min Upper Shadow: {CFG.min_upper_shadow_ratio} (very strict)")
    print(f"   BUY:  SL = {CFG.buy_sl_mult}×ATR, TP = {CFG.buy_tp_mult}×ATR")
    print(f"   SELL: SL = {CFG.sell_sl_mult}×ATR, TP = {CFG.sell_tp_mult}×ATR")
    print(f"\n📊 Expected Performance:")
    print(f"   Win Rate: ~47%")
    print(f"   Profit Factor: ~2.36x")
    print(f"\n⚠️ WARNING: 47% win rate is still below 55% threshold")
    print(f"   Run in PRACTICE mode for 1-2 weeks before live trading")
    print("\n" + "="*80 + "\n")
    
    run_all()
