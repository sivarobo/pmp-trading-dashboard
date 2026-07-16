# PMP Trading Suite — Phase 1: Regime Dashboard

Personal signal terminal built on the Module 1 (Market Regime) and Module 4
(Institutional Entries) framework. **Signals only — no order execution.**
You watch, you decide, you place orders manually in Zerodha Kite.

## What's in Phase 1

- Live 15-min candlestick chart with VWAP, CPR (Pivot/TC/BC), PDH/PDL, and
  Initial Balance overlays
- Automatic Gap classification (Flat / Moderate / Big / Extreme)
- Regime Detection engine — counts bullish/bearish/range signals and gives a
  verdict (Trend Day Bullish / Trend Day Bearish / Range Day / Unclear)
- Confluence panel — flags when you have 3+ aligned factors (Module 4.5 rule)

## Quick Start (works fully offline, no API key needed yet)

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`. Runs on **mock data** by default so you can
test the UI and indicator logic right now, before the Kite key arrives.

## Switching to live data — Upstox (recommended, free) or Zerodha Kite

### Option A: Upstox API (free — recommended default)

1. Open a free Upstox account (zero-balance is fine — this is for market
   data access only, no trades are placed from this app)
2. Create an app at https://developer.upstox.com to get your API key/secret
3. Complete the daily OAuth login flow to get an access token (Upstox
   tokens expire every day — ask me for a login helper script when you get here)
4. Verify the correct `instrument_key` for your symbols against Upstox's
   instrument master CSV (https://assets.upstox.com/market-quote/instruments/exchange/NSE.csv.gz)
   and update `SYMBOL_MAP` in `modules/data_source.py` if needed
5. Set environment variables and run:
   ```bash
   export DATA_SOURCE=upstox
   export UPSTOX_ACCESS_TOKEN="your_daily_access_token"
   streamlit run app.py
   ```

### Option B: Zerodha Kite Connect (₹2,000/month)

1. Get API key + secret from https://developers.kite.trade
2. Install the SDK: `pip install kiteconnect` (uncomment it in `requirements.txt`)
3. Generate a daily access token (Kite tokens also expire every day)
4. Set environment variables and run:
   ```bash
   export DATA_SOURCE=kite
   export KITE_API_KEY="your_api_key"
   export KITE_ACCESS_TOKEN="your_daily_access_token"
   streamlit run app.py
   ```

Either way — **no other code changes needed.** `modules/data_source.py` already
implements both `UpstoxDataSource` and `KiteDataSource`; the app switches
automatically based on the `DATA_SOURCE` env var.

## Project Structure

```
pmp_trading_dashboard/
├── app.py                  # Main Streamlit app (Phase 1 UI)
├── requirements.txt
├── modules/
│   ├── data_source.py      # Data abstraction: Mock (now) / Kite (later)
│   ├── mock_data.py        # Synthetic candle generator for offline testing
│   ├── indicators.py       # VWAP, CPR, PDH/PDL, Gap, Regime Detection
│   └── chart.py            # Plotly candlestick chart with overlays
└── README.md
```

## Coming in Phase 2 & 3

- Option Chain Reader (Change in OI, OI Shift, Writing/Covering flags)
- Greeks Panel (live delta/theta/vega per position)
- Risk Manager (position sizing calculator, drawdown tracker)
- Trading Journal (entry form, screenshots, rule-adherence tracking)
- Daily SOP checklist

## Disclaimer

This tool provides technical signals for personal decision-making only. It
does not place orders, does not manage anyone else's capital, and is not
investment advice. Not SEBI-registered.
