"""
PMP Trading Suite — Pro Chart (TradingView Lightweight Charts + Custom Indicators)

Chart engine: TradingView's open-source Lightweight Charts library (same
rendering family as tradingview.com, free, no approval needed) via the
streamlit-lightweight-charts component.

Custom indicators: write Python code in the editor (the "Pine Script
equivalent" — see modules/custom_indicators.py), it plots instantly.
"""

import streamlit as st
import pandas as pd

from modules.env_setup import init_env
init_env()

from modules.theme import apply_theme
from modules.navbar import render_navbar, render_ticker

from modules.data_source import get_data_source
from modules.indicators import calculate_vwap, calculate_cpr, prev_day_high_low
from modules.custom_indicators import (
    run_indicator, save_indicator, list_indicators, delete_indicator, STARTER_TEMPLATES,
)

try:
    from streamlit_lightweight_charts import renderLightweightCharts
    LWC_AVAILABLE = True
except ImportError:
    LWC_AVAILABLE = False

st.set_page_config(page_title="Pro Chart — PMP Trading Suite", layout="wide", page_icon="📉")
apply_theme()
render_ticker()
render_navbar(current="Pro Chart")

st.sidebar.title("📉 Pro Chart")
st.sidebar.caption("TradingView Lightweight Charts + Custom Indicators")

if not LWC_AVAILABLE:
    st.error("`streamlit-lightweight-charts` is not installed. "
             "Add it to requirements.txt and run: pip install streamlit-lightweight-charts")
    st.stop()

symbol = st.sidebar.selectbox("Symbol", ["NIFTY 50", "NIFTY BANK", "SENSEX"], index=0)
timeframe_map = {"5 min": "5minute", "15 min": "15minute", "1 hour": "60minute", "1 day": "day"}
timeframe_label = st.sidebar.selectbox("Timeframe", list(timeframe_map.keys()), index=1)
interval = timeframe_map[timeframe_label]
lookback_days = st.sidebar.slider("Lookback (days)", 1, 30, 3)

show_vwap = st.sidebar.checkbox("VWAP", value=True)
show_cpr = st.sidebar.checkbox("CPR lines", value=True)
show_pdh_pdl = st.sidebar.checkbox("PDH / PDL", value=True)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def load_data(symbol: str, days: int, interval: str):
    ds = get_data_source()
    intraday = ds.get_intraday_candles(symbol, interval=interval, days=days)
    daily = ds.get_daily_candles(symbol, days=15)
    return intraday, daily

try:
    df, daily_df = load_data(symbol, lookback_days, interval)
except Exception as e:
    st.error(f"Could not load data: {e}")
    st.stop()

if df.empty:
    st.warning("No candle data returned.")
    st.stop()

df = df.sort_values("datetime").reset_index(drop=True)
df["time"] = pd.to_datetime(df["datetime"]).astype("int64") // 10**9  # unix seconds for LWC

st.title("📉 Pro Chart")

# ---------------------------------------------------------------------------
# Custom Indicator Editor
# ---------------------------------------------------------------------------
with st.expander("🧪 Custom Indicator Editor (Python — your Pine Script equivalent)", expanded=False):
    st.caption("Write indicator logic in Python. `df` (candles), `pd`, `np` are available. "
               "Assign your output to `result` — a Series, or a dict of name → Series for multiple lines.")

    col_t1, col_t2 = st.columns([1, 2])
    with col_t1:
        template_choice = st.selectbox("Load a starter template", ["(blank)"] + list(STARTER_TEMPLATES.keys()))

    default_code = STARTER_TEMPLATES.get(template_choice, "# your indicator here\nresult = df['close'].rolling(20).mean()")
    code = st.text_area("Indicator code", value=default_code, height=180, key="indicator_code")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        apply_clicked = st.button("▶️ Apply to chart", use_container_width=True)
    with col_b:
        save_name = st.text_input("Save as", placeholder="e.g. My EMA Cross")
        if st.button("💾 Save indicator", use_container_width=True):
            if save_name.strip():
                try:
                    save_indicator(save_name.strip(), code)
                    st.success(f"Saved '{save_name}'.")
                except Exception as e:
                    st.error(f"Save failed (DB): {e}")
            else:
                st.warning("Give it a name first.")
    with col_c:
        try:
            saved = list_indicators()
        except Exception:
            saved = pd.DataFrame()
        if not saved.empty:
            load_choice = st.selectbox("Load saved", ["(none)"] + saved["name"].tolist())
            if load_choice != "(none)":
                loaded_code = saved[saved["name"] == load_choice]["code"].iloc[0]
                st.session_state["loaded_indicator_code"] = loaded_code
                st.code(loaded_code, language="python")
                if st.button("🗑️ Delete this saved indicator"):
                    delete_indicator(load_choice)
                    st.rerun()

# Determine which code to run: freshly applied, or previously loaded
active_code = None
if apply_clicked:
    active_code = code
    st.session_state["active_indicator_code"] = code
elif "active_indicator_code" in st.session_state:
    active_code = st.session_state["active_indicator_code"]

custom_series = {}
if active_code:
    outcome = run_indicator(active_code, df)
    if outcome["ok"]:
        custom_series = outcome["series"]
        st.success(f"Custom indicator active: {', '.join(custom_series.keys())}")
    else:
        st.error(f"Indicator error: {outcome['error']}")

# ---------------------------------------------------------------------------
# Build Lightweight Charts config
# ---------------------------------------------------------------------------
candle_data = [
    {"time": int(row["time"]), "open": float(row["open"]), "high": float(row["high"]),
     "low": float(row["low"]), "close": float(row["close"])}
    for _, row in df.iterrows()
]

volume_data = [
    {"time": int(row["time"]), "value": float(row["volume"]),
     "color": "rgba(38,166,154,0.5)" if row["close"] >= row["open"] else "rgba(239,83,80,0.5)"}
    for _, row in df.iterrows()
]

series = [
    {"type": "Candlestick", "data": candle_data,
     "options": {"upColor": "#26a69a", "downColor": "#ef5350",
                  "borderUpColor": "#26a69a", "borderDownColor": "#ef5350",
                  "wickUpColor": "#26a69a", "wickDownColor": "#ef5350"}},
    {"type": "Histogram", "data": volume_data,
     "options": {"priceScaleId": "volume", "priceFormat": {"type": "volume"}},
     "priceScale": {"scaleMargins": {"top": 0.85, "bottom": 0}}},
]

# VWAP overlay
if show_vwap:
    vwap = calculate_vwap(df)
    vwap_data = [{"time": int(t), "value": float(v)} for t, v in zip(df["time"], vwap) if pd.notna(v)]
    series.append({"type": "Line", "data": vwap_data,
                    "options": {"color": "#ffb300", "lineWidth": 2, "title": "VWAP"}})

# Custom indicator overlays
palette = ["#64b5f6", "#ce93d8", "#ff8a65", "#aed581", "#4dd0e1", "#f06292"]
for i, (name, s) in enumerate(custom_series.items()):
    line_data = [{"time": int(t), "value": float(v)} for t, v in zip(df["time"], s) if pd.notna(v)]
    series.append({"type": "Line", "data": line_data,
                    "options": {"color": palette[i % len(palette)], "lineWidth": 1.5, "title": name}})

chart_options = {
    "height": 560,
    "layout": {"background": {"type": "solid", "color": "#131722"},
                "textColor": "#d1d4dc"},
    "grid": {"vertLines": {"color": "#2a2e39"}, "horzLines": {"color": "#2a2e39"}},
    "timeScale": {"timeVisible": True, "secondsVisible": False},
    "crosshair": {"mode": 0},
}

renderLightweightCharts([{"chart": chart_options, "series": series}], key="prochart")

# ---------------------------------------------------------------------------
# CPR / PDH-PDL shown as a levels strip (Lightweight Charts price lines need
# per-series API access the Streamlit wrapper doesn't expose cleanly, so
# levels render as a reference strip below the chart instead)
# ---------------------------------------------------------------------------
if show_cpr or show_pdh_pdl:
    if not daily_df.empty:
        last_session = pd.to_datetime(df["datetime"]).dt.date.max()
        prev_rows = daily_df[pd.to_datetime(daily_df["date"]) < pd.Timestamp(last_session)]
        if not prev_rows.empty:
            prev_row = prev_rows.iloc[-1]
            cols = st.columns(6)
            i = 0
            if show_cpr:
                cpr = calculate_cpr(prev_row["high"], prev_row["low"], prev_row["close"])
                for label, val in [("CPR Pivot", cpr["pivot"]), ("TC", cpr["tc"]), ("BC", cpr["bc"])]:
                    cols[i].metric(label, val)
                    i += 1
            if show_pdh_pdl:
                pdh_pdl = prev_day_high_low(daily_df, pd.Timestamp(last_session))
                for label, val in [("PDH", pdh_pdl.get("pdh", "—")), ("PDL", pdh_pdl.get("pdl", "—"))]:
                    cols[i].metric(label, val)
                    i += 1

st.caption("PMP Trading Suite · Pro Chart · TradingView Lightweight Charts (open-source) · "
           "Custom indicators run YOUR code — verify logic before trading on it. Not investment advice.")
