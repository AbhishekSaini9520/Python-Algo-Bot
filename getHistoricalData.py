# Use this script to download historical data from Oanda
import requests
import pandas as pd

CFG_API_KEY = "5c821a3a1a23d3b8a18ffb0b8d10d852-887ec40cabdda2551683deb7e6d329a4"
CFG_ACCOUNT_ID = "101-011-36217286-002"

HEADERS = {
    "Authorization": f"Bearer {CFG_API_KEY}",
    "Content-Type": "application/json"
}

def download_oanda_data(instrument, granularity, days_back=30):
    """Download historical candles from Oanda"""
    url = f"https://api-fxpractice.oanda.com/v3/instruments/{instrument}/candles"
    
    # Calculate how many candles we need
    # M1 = 1440 candles/day, M5 = 288 candles/day, M15 = 96 candles/day
    if granularity == "M5":
        count = 288 * days_back
    elif granularity == "M15":
        count = 96 * days_back
    else:
        count = 500
    
    params = {"count": min(count, 5000), "granularity": granularity, "price": "M"}
    
    response = requests.get(url, headers=HEADERS, params=params, timeout=10)
    candles = response.json().get("candles", [])
    
    # Convert to DataFrame
    data = [{
        "time": candle["time"],
        "open": float(candle["mid"]["o"]),
        "high": float(candle["mid"]["h"]),
        "low": float(candle["mid"]["l"]),
        "close": float(candle["mid"]["c"]),
        "volume": candle["volume"]
    } for candle in candles]
    
    df = pd.DataFrame(data)
    df["time"] = pd.to_datetime(df["time"])
    df.set_index("time", inplace=True)
    
    return df

# Download data
print("📥 Downloading BTC_USD M5 data...")
btc_data = download_oanda_data("BTC_USD", "M5", days_back=30)
btc_data.to_csv("BTC_USD_M5.csv")
print(f"✅ Saved {len(btc_data)} candles to BTC_USD_M5.csv")

print("📥 Downloading XAU_USD M5 data...")
xau_data = download_oanda_data("XAU_USD", "M5", days_back=30)
xau_data.to_csv("XAU_USD_M5.csv")
print(f"✅ Saved {len(xau_data)} candles to XAU_USD_M5.csv")
