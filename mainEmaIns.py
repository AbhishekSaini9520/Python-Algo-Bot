import time
import logging
import requests
import pandas as pd
from dataclasses import dataclass, field
from threading import Thread
from decimal import Decimal, ROUND_DOWN  # For precision calculations

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
    ema_fast_period: int = 9
    ema_slow_period: int = 15
    sl_buffer: float = 5.0  # Buffer in price units
    risk_reward: float = 2.5  # Updated from 2.0 to 2.5 as per requirement
    poll_sec: int = 30

# Replace with actual credentials
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

def fetch_ohlc(instrument: str, granularity: str, count: int) -> pd.DataFrame:
    url = f"{CFG.base_url}/v3/instruments/{instrument}/candles"
    params = {
        "count": count,
        "granularity": granularity,
        "price": "M"
    }
    response = requests.get(url, headers=HEADERS, params=params, timeout=10)
    response.raise_for_status()
    data = response.json().get("candles", [])
    if not data:
        return pd.DataFrame()
    records = []
    for c in data:
        records.append({
            "time": c["time"],
            "open": float(c["mid"]["o"]),
            "high": float(c["mid"]["h"]),
            "low": float(c["mid"]["l"]),
            "close": float(c["mid"]["c"]),
            "volume": c["volume"],
            "complete": c["complete"]
        })
    df = pd.DataFrame(records)
    df["time"] = pd.to_datetime(df["time"], format="%Y-%m-%dT%H:%M:%S.%f000Z", errors='coerce')

    df.set_index("time", inplace=True)
    return df

def compute_emas(df: pd.DataFrame, fast_period: int, slow_period: int) -> pd.DataFrame:
    df["EMA_fast"] = df["close"].ewm(span=fast_period, adjust=False).mean()
    df["EMA_slow"] = df["close"].ewm(span=slow_period, adjust=False).mean()
    df["EMA_lower"] = df[["EMA_fast", "EMA_slow"]].min(axis=1)
    return df

def is_bullish_hammer(row, min_ratio=1.5, max_upper_shadow_factor=0.65) -> bool:
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if c < o:
        return False
    body = c - o
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    if h - l <= 0 or body <= 0:
        return False
    cond_lower = lower_shadow >= min_ratio * body
    cond_upper = upper_shadow <= max_upper_shadow_factor * body
    return cond_lower and cond_upper

def place_market_buy(instrument: str, units: int, sl_price: float, tp_price: float):
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
    try:
        response = requests.post(url, headers=HEADERS, json=order, timeout=10)
        if response.status_code == 201:
            logging.info(f"Order placed for {instrument}: {response.json()}")
        else:
            error_data = response.json()
            reason = error_data.get("orderRejectTransaction", {}).get("reason", "Unknown error")
            logging.error(f"Order failed for {instrument}: {response.status_code} {reason}")
            if reason == "MARKET_HALTED":
                logging.warning(f"Market is halted for {instrument}. Retrying later.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Request failed for {instrument}: {e}")

def run_timeframe(instrument: str, timeframe: str):
    logging.info(f"Starting {instrument} bot for {timeframe}")
    last_time = None
    while True:
        try:
            precision = INSTRUMENT_PRECISION.get(instrument, 2)
            precision_format = '1.' + '0' * precision

            df = fetch_ohlc(instrument, timeframe, CFG.lookback_candles)
            if df.empty or len(df) < CFG.ema_slow_period + 1:
                logging.warning(f"Not enough data for {instrument} {timeframe}; retrying...")
                time.sleep(CFG.poll_sec)
                continue

            df_completed = df[df["complete"] == True].copy()
            if df_completed.empty:
                logging.info(f"No completed candle yet for {instrument} {timeframe}")
                time.sleep(CFG.poll_sec)
                continue

            df_completed = compute_emas(df_completed, CFG.ema_fast_period, CFG.ema_slow_period)

            last = df_completed.iloc[-1]
            time_stamp = last.name

            if time_stamp == last_time:
                time.sleep(CFG.poll_sec)
                continue
            last_time = time_stamp

            logging.info(f"{instrument} {timeframe} Candle @ {time_stamp} | "
                         f"O:{last['open']:.2f} H:{last['high']:.2f} L:{last['low']:.2f} "
                         f"C:{last['close']:.2f} EMA_lower:{last['EMA_lower']:.2f}")

            if is_bullish_hammer(last) and last["open"] > last["EMA_lower"]:
                entry = Decimal(str(last["close"]))
                precision_format = '1.' + '0' * precision

                # Fixed SL and TP
                sl = (entry - Decimal('100')).quantize(Decimal(precision_format), rounding=ROUND_DOWN)
                tp = (entry + Decimal('200')).quantize(Decimal(precision_format), rounding=ROUND_DOWN)

                if sl >= entry:
                    logging.warning(f"Invalid SL {sl} >= entry {entry} for {instrument} {timeframe}, skipping trade.")
                    continue

                logging.info(f"{instrument} {timeframe} BUY signal! Entry={entry:.{precision}f}, SL={sl:.{precision}f}, TP={tp:.{precision}f}")

                place_market_buy(instrument, CFG.units, float(sl), float(tp))
            else:
                logging.info(f"No valid bullish hammer for {instrument} {timeframe}")

            time.sleep(CFG.poll_sec)

        except Exception as e:
            logging.exception(f"Error in {instrument} {timeframe}: {e}")
            time.sleep(CFG.poll_sec)

def run_all():
    threads = []
    for instrument in CFG.instruments:
        for timeframe in CFG.timeframes:
            t = Thread(target=run_timeframe, args=(instrument, timeframe), daemon=True)
            threads.append(t)
            t.start()
    for t in threads:
        t.join()

if __name__ == "__main__":
    run_all()
