"""
PMP Trading Suite — Phase 1: Regime Dashboard
Run: streamlit run app.py

Data source defaults to MOCK (fully offline). Once the Zerodha Kite Connect
API key is available, set DATA_SOURCE=kite and KITE_API_KEY / KITE_ACCESS_TOKEN
in your environment (see README.md) — no code changes needed anywhere else.
"""

import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # picks up .env created by scripts/get_upstox_token.py, if present

# Bridge Streamlit Cloud's "Secrets" into os.environ so modules/data_source.py
# (which reads os.environ) behaves identically locally and when deployed.
try:
    for _key, _value in st.secrets.items():
        os.environ.setdefault(_key, str(_value))
except Exception:
    pass  # no secrets.toml / Cloud Secrets configured yet -- fine, defaults to mock

from modules.data_source import get_data_source
from modules.indicators import (
    calculate_vwap, calculate_cpr, prev_day_high_low,
    classify_gap, initial_balance, detect_regime,
)
from modules.chart import build_regime_chart

st.set_page_config(page_title="PMP Trading Suite", layout="wide", page_icon="📈")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("⚙️ PMP Trading Suite")
st.sidebar.caption("Phase 1 — Regime Dashboard")

symbol = st.sidebar.selectbox("Symbol", ["NIFTY 50", "NIFTY BANK", "SENSEX"], index=0)
lookback_days = st.sidebar.slider("Intraday history (days)", 1, 5, 3)

data_mode = os.environ.get("DATA_SOURCE", "mock")
if data_mode == "mock":
    st.sidebar.warning("⚠️ Running on MOCK data. Set DATA_SOURCE=kite once the API key is added.")
else:
    st.sidebar.success(f"✅ Live data source: {data_mode.upper()}")

st.sidebar.markdown("---")
st.sidebar.caption("Modules 2-9 (Option Chain, Greeks, Journal, Risk Manager) ship in Phase 2 & 3.")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def load_data(symbol: str, days: int):
    ds = get_data_source()
    intraday = ds.get_intraday_candles(symbol, interval="15minute", days=days)
    daily = ds.get_daily_candles(symbol, days=15)
    return intraday, daily

intraday_df, daily_df = load_data(symbol, lookback_days)
intraday_df["date_only"] = pd.to_datetime(intraday_df["datetime"]).dt.date

available_dates = sorted(intraday_df["date_only"].unique())
selected_date = st.sidebar.selectbox("Session date", available_dates, index=len(available_dates) - 1)

day_df_raw = intraday_df[intraday_df["date_only"] == selected_date]

# ---------------------------------------------------------------------------
# Compute indicators
# ---------------------------------------------------------------------------
vwap_full = calculate_vwap(intraday_df)
day_vwap = vwap_full.loc[day_df_raw.index].reset_index(drop=True)  # align BEFORE resetting day_df's index
day_df = day_df_raw.reset_index(drop=True)

ib = initial_balance(intraday_df, selected_date)

prev_row_lookup = daily_df[pd.to_datetime(daily_df["date"]) < pd.Timestamp(selected_date)]
if not prev_row_lookup.empty:
    prev_row = prev_row_lookup.iloc[-1]
    cpr = calculate_cpr(prev_row["high"], prev_row["low"], prev_row["close"])
    gap = classify_gap(day_df.iloc[0]["open"], prev_row["close"])
else:
    cpr, gap, prev_row = {}, {}, None

pdh_pdl = prev_day_high_low(daily_df, pd.Timestamp(selected_date))
regime = detect_regime(day_df, day_vwap, ib, cpr)

# ---------------------------------------------------------------------------
# Header row — key badges
# ---------------------------------------------------------------------------
st.title("📊 Regime Dashboard")

badge_cols = st.columns(5)

verdict_color = {
    "Trend Day (Bullish)": "🟢",
    "Trend Day (Bearish)": "🔴",
    "Range Day": "🟡",
    "Unclear": "⚪",
}
with badge_cols[0]:
    st.metric("Regime Verdict", f"{verdict_color.get(regime['verdict'],'⚪')} {regime['verdict']}")

with badge_cols[1]:
    if gap:
        st.metric("Gap", gap["category"], delta=f"{gap['gap_pct']}%")
    else:
        st.metric("Gap", "—")

with badge_cols[2]:
    st.metric("CPR Width", f"{cpr.get('width_pct','—')}%",
               delta="Narrow (trend bias)" if cpr.get("is_narrow") else "Wide (range bias)")

with badge_cols[3]:
    st.metric("Last Price", f"{day_df.iloc[-1]['close']:.2f}")

with badge_cols[4]:
    st.metric("Session VWAP", f"{day_vwap.iloc[-1]:.2f}")

st.markdown("---")

# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------
chart_col, signal_col = st.columns([3, 1])

with chart_col:
    fig = build_regime_chart(day_df, day_vwap, cpr, pdh_pdl, ib,
                              title=f"{symbol} — 15 Min — {selected_date}")
    st.plotly_chart(fig, use_container_width=True)

with signal_col:
    st.subheader("🎯 Confluence Signals")

    if regime["bullish_signals"]:
        st.markdown("**Bullish factors**")
        for s in regime["bullish_signals"]:
            st.success(s, icon="🟢")

    if regime["bearish_signals"]:
        st.markdown("**Bearish factors**")
        for s in regime["bearish_signals"]:
            st.error(s, icon="🔴")

    if regime["range_signals"]:
        st.markdown("**Range factors**")
        for s in regime["range_signals"]:
            st.warning(s, icon="🟡")

    total_signals = (len(regime["bullish_signals"]) + len(regime["bearish_signals"])
                      + len(regime["range_signals"]))
    if regime["verdict"] == "Unclear":
        st.info(f"Signals mixed ({len(regime['bullish_signals'])} bullish, "
                 f"{len(regime['bearish_signals'])} bearish, {len(regime['range_signals'])} range) "
                 f"— no majority. Module 4.5 rule: **No regime = No trade.**")
    else:
        st.success(f"{total_signals} factors counted, pointing to **{regime['verdict']}** "
                    f"— sufficient confluence to act on.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Levels table
# ---------------------------------------------------------------------------
st.subheader("📐 Key Levels")
level_cols = st.columns(6)
level_data = [
    ("CPR Pivot", cpr.get("pivot", "—")),
    ("CPR TC", cpr.get("tc", "—")),
    ("CPR BC", cpr.get("bc", "—")),
    ("PDH", pdh_pdl.get("pdh", "—")),
    ("PDL", pdh_pdl.get("pdl", "—")),
    ("IB Range", f"{ib.get('ib_low','—')} – {ib.get('ib_high','—')}"),
]
for col, (label, val) in zip(level_cols, level_data):
    col.metric(label, val)

st.caption("PMP Trading Suite · Phase 1 · For personal signal use only — no order execution. "
           "Not investment advice.")
