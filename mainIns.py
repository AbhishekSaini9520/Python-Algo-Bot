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
    instruments: list = field(default_factory=lambda: ["BTC_USD", "XAU_USD"])  # Instruments
    timeframes: list = field(default_factory=lambda: ["M1", "M5" , "M15"])  # Timeframes
    lookback_candles: int = 100
    units: int = 1
    max_lower_shadow_factor: float = 0.65
    min_upper_shadow_ratio: float = 1.5
    sl_buffer_ticks: float = 5.0   # Number of ticks for SL buffer
    risk_reward: float = 2.5       # Risk-to-reward ratio
    poll_sec: int = 30

# Replace with your actual credentials
CFG = OandaConfig(
    api_key="d31f754aa36da34dc378e510d0a39274-1e2774154dffbdaf4ec40a5b48eb8b6a",
    account_id="101-011-36217286-002"
)

HEADERS = {
    "Authorization": f"Bearer {CFG.api_key}",
    "Content-Type": "application/json"
}

# Define precision for each instrument
INSTRUMENT_PRECISION = {
    "BTC_USD": 2,
    "XAU_USD": 3,
}

# Define tick size (minimum price movement) per instrument
TICK_SIZE = {
    "BTC_USD": 0.01,
    "XAU_USD": 0.001,
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
            "volume": c["volume"]
        })
    df = pd.DataFrame(records)
    df["time"] = pd.to_datetime(df["time"], format="%Y-%m-%dT%H:%M:%S.%f000Z", errors='coerce')

    df.set_index("time", inplace=True)
    return df

def is_bullish_hammer(row) -> bool:
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if c <= o:  # bullish candle: close should be greater than open
        return False
    body = c - o
    upper_shadow = h - c  # upper wick
    lower_shadow = o - l  # lower wick
    if upper_shadow > CFG.max_lower_shadow_factor * body:
        return False
    if lower_shadow < CFG.min_upper_shadow_ratio * body:
        return False
    return True

def place_market_buy(instrument: str, units: int, sl_price: float = None, tp_price: float = None):
    precision = INSTRUMENT_PRECISION.get(instrument, 2)  # default 2 decimals if unknown
    url = f"{CFG.base_url}/v3/accounts/{CFG.account_id}/orders"
    order = {
        "units": str(units),
        "instrument": instrument,
        "timeInForce": "FOK",
        "type": "MARKET",
        "positionFill": "DEFAULT"
    }
    if sl_price is not None:
        sl_price = round(sl_price, precision)
        order["stopLossOnFill"] = {"price": f"{sl_price:.{precision}f}"}
    if tp_price is not None:
        tp_price = round(tp_price, precision)
        order["takeProfitOnFill"] = {"price": f"{tp_price:.{precision}f}"}
    payload = {"order": order}
    response = requests.post(url, headers=HEADERS, json=payload, timeout=10)
    if response.status_code == 201:
        logging.info(f"Order for {instrument} placed successfully: {response.json()}")
        return response.json()
    else:
        logging.error(f"Failed to place order for {instrument}: {response.status_code} {response.text}")
        return None

def run_timeframe(instrument: str, timeframe: str):
    logging.info(f"Starting bot for {instrument} on {timeframe}")
    last_time = None
    precision = INSTRUMENT_PRECISION.get(instrument, 2)  # fallback precision

    while True:
        try:
            df = fetch_ohlc(instrument, timeframe, CFG.lookback_candles)
            if df.empty or len(df) < 2:
                logging.warning(f"Not enough data for {instrument} {timeframe}; retrying...")
                time.sleep(CFG.poll_sec)
                continue

            df_complete = df[df['volume'] > 0]
            if len(df_complete) < 2:
                logging.warning(f"Not enough completed data for {instrument} {timeframe}; retrying...")
                time.sleep(CFG.poll_sec)
                continue

            row = df_complete.iloc[-2]  # second-last completed candle
            time_stamp = df_complete.index[-2]

            if time_stamp == last_time:
                time.sleep(CFG.poll_sec)
                continue
            last_time = time_stamp

            logging.info(f"{instrument} {timeframe} Completed Candle @ {time_stamp} | "
                         f"O:{row['open']} H:{row['high']} L:{row['low']} C:{row['close']}")

            if is_bullish_hammer(row):
                entry_price = row["close"]

                # Fixed SL and TP
                sl_price = entry_price - 100  # SL $100 below entry
                tp_price = entry_price + 200  # TP $200 above entry

                # Round SL and TP according to the instrument precision
                sl_price = round(sl_price, precision)
                tp_price = round(tp_price, precision)

                logging.info(f"{instrument} {timeframe} BUY signal: Entry={entry_price:.{precision}f}, SL={sl_price:.{precision}f}, TP={tp_price:.{precision}f}")

                place_market_buy(instrument, CFG.units, sl_price=sl_price, tp_price=tp_price)
            else:
                logging.info(f"No bullish hammer detected for {instrument} {timeframe}")

            time.sleep(CFG.poll_sec)

        except Exception as e:
            logging.exception(f"Unexpected error in {instrument} {timeframe}: {e}")
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
