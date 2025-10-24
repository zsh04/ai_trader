import os

import alpaca_trade_api as tradeapi
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Get the API keys from the environment variables
API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")
BASE_URL = os.getenv("BASE_URL")

# --- Sanity Check (Optional but Recommended) ---
if not all([API_KEY, SECRET_KEY, BASE_URL]):
    raise ValueError("API keys or Base URL not set in .env file.")

# Connect to the Alpaca API
api = tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL, api_version="v2")

try:
    # Get and print your account information
    account = api.get_account()
    print("Connection Successful!")
    print(f"Account Status: {account.status}")
    print(f"Buying Power: ${account.buying_power}")

except Exception as e:
    print(f"Connection failed: {e}")
