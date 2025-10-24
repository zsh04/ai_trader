import os
from datetime import datetime, timedelta

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API keys from environment variables
API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")

# Use the StockHistoricalDataClient for fetching market data
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# --- 1. Define the Stock and Fetch Data ---
symbol = "OKLO"
timeframe = TimeFrame.Day

# Calculate the date range
end_date = datetime.now()
start_date = end_date - timedelta(days=200)

try:
    request_params = StockBarsRequest(
        symbol_or_symbols=[symbol], timeframe=timeframe, start=start_date, end=end_date
    )

    bars = data_client.get_stock_bars(request_params).df

    # --- THIS IS THE FIRST FIX ---
    # Convert the MultiIndex to regular columns
    bars = bars.reset_index()

    print(f"Successfully fetched {len(bars)} bars for {symbol}")

    # --- 2. Calculate Technical Indicators ---
    bars.ta.rsi(append=True)
    bars.ta.macd(append=True)
    print("Successfully calculated technical indicators.")

    # --- 3. Define the Trading Signal Logic ---
    latest_data = bars.iloc[-1]

    macd_line = latest_data["MACD_12_26_9"]
    macd_signal_line = latest_data["MACDs_12_26_9"]
    rsi = latest_data["RSI_14"]

    # --- THIS IS THE SECOND FIX ---
    # Access the date from the 'timestamp' column
    print(f"\nChecking signal for {symbol} on {bars['timestamp'].iloc[-1].date()}:")
    print(f"  - MACD Line: {macd_line:.2f}")
    print(f"  - MACD Signal Line: {macd_signal_line:.2f}")
    print(f"  - RSI: {rsi:.2f}")

    if macd_line > macd_signal_line and rsi < 80:
        print("\nDecision: ✅ BUY SIGNAL DETECTED")
    else:
        print("\nDecision: ❌ NO SIGNAL")

except Exception as e:
    print(f"An error occurred: {e}")
