import time
import logging
import requests
import pandas as pd
from dataclasses import dataclass, field
from threading import Thread
from typing import Dict, Set


# Setup logging
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
    max_lower_shadow_factor: float = 0.65
    min_upper_shadow_ratio: float = 1.5
    risk_percent: float = 1.0  # Risk per trade as % of account (for dynamic SL/TP)
    risk_reward: float = 2.0  # Risk-reward ratio
    poll_sec: int = 30
    ema_fast: int = 9
    ema_slow: int = 15
    atr_period: int = 14  # ATR period for dynamic SL/TP
    use_atr: bool = True  # Use ATR for SL/TP calculation


CFG = OandaConfig(
    api_key="5c821a3a1a23d3b8a18ffb0b8d10d852-887ec40cabdda2551683deb7e6d329a4",
    account_id="101-011-36217286-002",
    use_atr=True  # Enable ATR-based SL/TP
)


HEADERS = {
    "Authorization": f"Bearer {CFG.api_key}",
    "Content-Type": "application/json"
}


INSTRUMENT_PRECISION = {
    "BTC_USD": 2,
    "XAU_USD": 3,
}


TICK_SIZE = {
    "BTC_USD": 0.01,
    "XAU_USD": 0.001,
}


# ✅ OPTIMIZATION 2: Position tracking to prevent multiple entries
active_positions: Dict[str, Dict] = {}  # {instrument_timeframe: {"type": "BUY/SELL", "entry": price}}
position_lock = Thread().Lock if hasattr(Thread, 'Lock') else __import__('threading').Lock


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


# ✅ OPTIMIZATION 1: ATR calculation for dynamic SL/TP
def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """
    Calculate Average True Range for dynamic SL/TP calculation
    ATR = average of TR over period
    TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
    """
    if len(df) < period + 1:
        return 0.0
    
    df = df.copy()
    
    # Calculate True Range
    df['hl'] = df['high'] - df['low']
    df['hc'] = abs(df['high'] - df['close'].shift(1))
    df['lc'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['hl', 'hc', 'lc']].max(axis=1)
    
    # Calculate ATR
    atr = df['tr'].rolling(window=period).mean().iloc[-1]
    return atr if atr > 0 else 1.0


def calculate_dynamic_sl_tp(entry: float, atr: float, precision: int, trade_type: str = "BUY") -> tuple:
    """
    Calculate SL/TP dynamically using ATR multipliers
    
    BUY:  SL = entry - (2 * ATR), TP = entry + (4 * ATR)  [1:2 R:R]
    SELL: SL = entry + (2 * ATR), TP = entry - (4 * ATR)  [1:2 R:R]
    """
    sl_distance = round(1.0 * atr, precision)
    tp_distance = round(2.0 * atr, precision)
    
    if trade_type == "BUY":
        sl_price = round(entry - sl_distance, precision)
        tp_price = round(entry + tp_distance, precision)
    else:  # SELL
        sl_price = round(entry + sl_distance, precision)
        tp_price = round(entry - tp_distance, precision)
    
    return sl_price, tp_price, sl_distance, tp_distance


def fetch_ohlc(instrument: str, granularity: str, count: int) -> pd.DataFrame:
    url = f"{CFG.base_url}/v3/instruments/{instrument}/candles"
    params = {"count": count, "granularity": granularity, "price": "M"}
    for attempt in range(3):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                params=params,
                timeout=20  # more generous
            )
            response.raise_for_status()
            break
        except requests.exceptions.Timeout:
            logging.warning(f"Timeout fetching {instrument} {granularity}, attempt {attempt+1}/3")
            if attempt == 2:
                raise
            time.sleep(2)

    response.raise_for_status()
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
    df = df.copy()
    df["EMA_fast"] = df["close"].ewm(span=fast_period, adjust=False).mean()
    df["EMA_slow"] = df["close"].ewm(span=slow_period, adjust=False).mean()
    df["EMA_lower"] = df[["EMA_fast", "EMA_slow"]].min(axis=1)
    df["EMA_upper"] = df[["EMA_fast", "EMA_slow"]].max(axis=1)
    return df


def is_bearish_hammer(row, min_upper_shadow_ratio=1.5, max_lower_shadow_factor=0.65) -> bool:
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


def is_bullish_hammer(row, min_ratio=1.5, max_upper_shadow_factor=0.65) -> bool:
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if c <= o:
        return False
    body = c - o
    upper_shadow = h - c
    lower_shadow = o - l
    if upper_shadow > max_upper_shadow_factor * body:
        return False
    if lower_shadow < min_ratio * body:
        return False
    return True


# ✅ OPTIMIZATION 3: Trend filter using EMA
def is_uptrend(row) -> bool:
    """Check if price is in uptrend (close > EMA_lower)"""
    return row["close"] > row["EMA_lower"]


def is_downtrend(row) -> bool:
    """Check if price is in downtrend (close < EMA_upper)"""
    return row["close"] < row["EMA_upper"]


def place_market_buy_with_sl_tp(instrument: str, units: int, sl_price: float, tp_price: float, entry: float, atr: float, timeframe: str):
    """Place a BUY market order with SL and TP"""
    precision = INSTRUMENT_PRECISION.get(instrument, 2)
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


# def place_market_sell_with_sl_tp(instrument: str, units: int, sl_price: float, tp_price: float, entry: float, atr: float, timeframe: str):
    """Place a SELL market order with SL and TP"""
    precision = INSTRUMENT_PRECISION.get(instrument, 2)
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

def place_market_buy_with_sl_tp(instrument: str, units: int, sl_price: float, tp_price: float, entry: float, atr: float, timeframe: str):
    """Place a BUY market order with SL and TP"""
    precision = INSTRUMENT_PRECISION.get(instrument, 2)
    
    # Round twice for absolute safety
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
            "stopLossOnFill": {"price": f"{round(sl_price, precision):.{precision}f}"},  # ← extra round
            "takeProfitOnFill": {"price": f"{round(tp_price, precision):.{precision}f}"}  # ← extra round
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


def run_for_instrument_and_timeframe(instrument: str, timeframe: str):
    logging.info(f"🚀 Starting {instrument} bot for {timeframe}")
    last_time = None
    precision = INSTRUMENT_PRECISION.get(instrument, 2)
    
    while True:
        try:
            df = fetch_ohlc(instrument, timeframe, CFG.lookback_candles)
            if df.empty or len(df) < CFG.ema_slow + 1:
                logging.warning(f"⚠️ Not enough data for {instrument} {timeframe}; retrying...")
                time.sleep(CFG.poll_sec)
                continue

            df = df[df["complete"] == True].copy()
            if df.empty:
                logging.info(f"⏳ No completed candle yet for {instrument} {timeframe}")
                time.sleep(CFG.poll_sec)
                continue

            df = compute_emas(df, CFG.ema_fast, CFG.ema_slow)
            last = df.iloc[-1]
            time_stamp = df.index[-1]

            if time_stamp == last_time:
                time.sleep(CFG.poll_sec)
                continue
            last_time = time_stamp

            # ✅ OPTIMIZATION 1: Calculate ATR for dynamic SL/TP
            atr = calculate_atr(df, CFG.atr_period) if CFG.use_atr else 1.0

            logging.info(f"📊 {instrument} {timeframe} Candle @ {time_stamp} | "
                         f"O:{last['open']:.2f} H:{last['high']:.2f} L:{last['low']:.2f} C:{last['close']:.2f} | "
                         f"EMA_L:{last['EMA_lower']:.2f} ATR:{atr:.2f}")

            # ✅ OPTIMIZATION 2: Skip if position already exists
            if has_active_position(instrument, timeframe):
                logging.info(f"⏸️ Already in position for {instrument} {timeframe}, skipping new signal")
                time.sleep(CFG.poll_sec)
                continue

            # Check for BEARISH HAMMER (SELL Signal)
            if is_bearish_hammer(last):
                # ✅ OPTIMIZATION 3: Confirm with downtrend filter
                if is_downtrend(last):
                    entry = last["close"]

                    # ✅ OPTIMIZATION 1: Dynamic SL/TP using ATR
                    if CFG.use_atr:
                        sl_price, tp_price, sl_dist, tp_dist = calculate_dynamic_sl_tp(entry, atr, precision, "SELL")
                        logging.info(f"📐 SELL Signal (ATR): SL_dist={sl_dist:.{precision}f}, TP_dist={tp_dist:.{precision}f}")
                    else:
                        sl_price = round(entry + 10, precision)
                        tp_price = round(entry - 20, precision)
                        logging.info(f"📐 SELL Signal (Fixed): SL=entry+10, TP=entry-20")

                    if sl_price <= entry:
                        logging.warning(f"❌ Invalid SL {sl_price} <= entry {entry} for {instrument} {timeframe}, skipping trade.")
                    elif tp_price >= entry:
                        logging.warning(f"❌ Invalid TP {tp_price} >= entry {entry} for {instrument} {timeframe}, skipping trade.")
                    else:
                        logging.info(f"🔴 SELL signal! Entry={entry:.{precision}f}, SL={sl_price:.{precision}f}, TP={tp_price:.{precision}f}")
                        place_market_sell_with_sl_tp(instrument, CFG.units, sl_price=sl_price, tp_price=tp_price, entry=entry, atr=atr, timeframe=timeframe)
                else:
                    logging.info(f"⚠️ Bearish hammer detected but NOT in downtrend for {instrument} {timeframe} - signal filtered out")

            # Check for BULLISH HAMMER (BUY Signal)
            elif is_bullish_hammer(last):
                # ✅ OPTIMIZATION 3: Confirm with uptrend filter
                if is_uptrend(last):
                    entry = last["close"]

                    # ✅ OPTIMIZATION 1: Dynamic SL/TP using ATR
                    if CFG.use_atr:
                        sl_price, tp_price, sl_dist, tp_dist = calculate_dynamic_sl_tp(entry, atr, precision, "BUY")
                        logging.info(f"📐 BUY Signal (ATR): SL_dist={sl_dist:.{precision}f}, TP_dist={tp_dist:.{precision}f}")
                    else:
                        sl_price = round(entry - 10, precision)
                        tp_price = round(entry + 20, precision)
                        logging.info(f"📐 BUY Signal (Fixed): SL=entry-10, TP=entry+20")

                    if sl_price >= entry:
                        logging.warning(f"❌ Invalid SL {sl_price} >= entry {entry} for {instrument} {timeframe}, skipping trade.")
                    elif tp_price <= entry:
                        logging.warning(f"❌ Invalid TP {tp_price} <= entry {entry} for {instrument} {timeframe}, skipping trade.")
                    else:
                        logging.info(f"🟢 BUY signal! Entry={entry:.{precision}f}, SL={sl_price:.{precision}f}, TP={tp_price:.{precision}f}")
                        place_market_buy_with_sl_tp(instrument, CFG.units, sl_price=sl_price, tp_price=tp_price, entry=entry, atr=atr, timeframe=timeframe)
                else:
                    logging.info(f"⚠️ Bullish hammer detected but NOT in uptrend for {instrument} {timeframe} - signal filtered out")
            else:
                logging.info(f"❌ No valid hammer pattern for {instrument} {timeframe}")

            time.sleep(CFG.poll_sec)

        except Exception as e:
            logging.exception(f"❌ Error in {instrument} {timeframe}: {e}")
            time.sleep(CFG.poll_sec)


def run_all():
    threads = []
    for instrument in CFG.instruments:
        for timeframe in CFG.timeframes:
            t = Thread(target=run_for_instrument_and_timeframe, args=(instrument, timeframe), daemon=True)
            threads.append(t)
            t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    run_all()