import time
import logging
import requests
import pandas as pd
from dataclasses import dataclass, field
from threading import Thread

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

@dataclass
class OandaConfig:
    api_key: str
    account_id: str
    base_url: str = "https://api-fxpractice.oanda.com"
    instruments: list = field(default_factory=lambda: ["BTC_USD", "XAU_USD"])
    timeframes: list = field(default_factory=lambda: ["M1", "M5", "M15"])
    lookback_candles: int = 100
    units: int = 1
    max_lower_shadow_factor: float = 0.65
    min_upper_shadow_ratio: float = 1.5
    sl_buffer_ticks: float = 5.0
    risk_reward: float = 2.0  # For SELL, ratio is 1:2
    poll_sec: int = 30
    ema_fast: int = 9
    ema_slow: int = 15

CFG = OandaConfig(
    api_key="5c821a3a1a23d3b8a18ffb0b8d10d852-887ec40cabdda2551683deb7e6d329a4",
    account_id="101-011-36217286-002"
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

def fetch_ohlc(instrument: str, granularity: str, count: int) -> pd.DataFrame:
    url = f"{CFG.base_url}/v3/instruments/{instrument}/candles"
    params = {"count": count, "granularity": granularity, "price": "M"}
    response = requests.get(url, headers=HEADERS, params=params, timeout=10)
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

def place_market_sell_with_sl_tp(instrument: str, units: int, sl_price: float, tp_price: float):
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
        logging.info(f"Sell order placed for {instrument}: {response.json()}")
    else:
        logging.error(f"Failed to place sell order for {instrument}: {response.status_code} {response.text}")

def run_for_instrument_and_timeframe(instrument: str, timeframe: str):
    logging.info(f"Starting {instrument} bot for {timeframe}")
    last_time = None
    precision = INSTRUMENT_PRECISION.get(instrument, 2)
    while True:
        try:
            df = fetch_ohlc(instrument, timeframe, CFG.lookback_candles)
            if df.empty or len(df) < CFG.ema_slow + 1:
                logging.warning(f"Not enough data for {instrument} {timeframe}; retrying...")
                time.sleep(CFG.poll_sec)
                continue

            df = df[df["complete"] == True].copy()
            if df.empty:
                logging.info(f"No completed candle yet for {instrument} {timeframe}")
                time.sleep(CFG.poll_sec)
                continue

            df = compute_emas(df, CFG.ema_fast, CFG.ema_slow)
            last = df.iloc[-1]
            time_stamp = df.index[-1]

            if time_stamp == last_time:
                time.sleep(CFG.poll_sec)
                continue
            last_time = time_stamp

            logging.info(f"{instrument} {timeframe} Candle @ {time_stamp} | "
                         f"O:{last['open']:.2f} H:{last['high']:.2f} L:{last['low']:.2f} C:{last['close']:.2f} EMA_lower:{last['EMA_lower']:.2f}")

            if is_bearish_hammer(last):
                entry = last["close"]

                # Fixed SL and TP
                sl_price = round(entry + 100, precision)
                tp_price = round(entry - 200, precision)

                if sl_price <= entry:
                    logging.warning(f"Invalid SL {sl_price} <= entry {entry} for {instrument} {timeframe}, skipping trade.")
                    continue
                if tp_price >= entry:
                    logging.warning(f"Invalid TP {tp_price} >= entry {entry} for {instrument} {timeframe}, skipping trade.")
                    continue

                logging.info(f"{instrument} {timeframe} SELL signal! Entry={entry:.{precision}f}, SL={sl_price:.{precision}f}, TP={tp_price:.{precision}f}")

                place_market_sell_with_sl_tp(instrument, CFG.units, sl_price=sl_price, tp_price=tp_price)
            else:
                logging.info(f"No valid bearish hammer for {instrument} {timeframe}")

            time.sleep(CFG.poll_sec)

        except Exception as e:
            logging.exception(f"Error in {instrument} {timeframe}: {e}")
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
