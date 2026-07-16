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

from modules.env_setup import init_env
init_env()

from modules.data_source import get_data_source
from modules.indicators import (
    calculate_vwap, calculate_cpr, prev_day_high_low,
    classify_gap, initial_balance, detect_regime,
    weekly_high_low, volume_confirmation,
)
from modules.chart import build_regime_chart, build_plain_chart

st.set_page_config(page_title="PMP Trading Suite", layout="wide", page_icon="📈")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("⚙️ PMP Trading Suite")
st.sidebar.caption("Phase 1 — Regime Dashboard")

PRESET_SYMBOLS = ["NIFTY 50", "NIFTY BANK", "SENSEX"]

if "custom_symbol" not in st.session_state:
    st.session_state["custom_symbol"] = None
if "custom_symbol_label" not in st.session_state:
    st.session_state["custom_symbol_label"] = None

data_mode = os.environ.get("DATA_SOURCE", "mock")

symbol = st.sidebar.selectbox("Symbol (index presets)", PRESET_SYMBOLS, index=0)

timeframe_map = {"5 min": "5minute", "15 min": "15minute", "1 hour": "60minute",
                  "1 day": "day", "1 week": "week", "1 month": "month"}
timeframe_label = st.sidebar.selectbox("Timeframe", list(timeframe_map.keys()), index=1)
interval = timeframe_map[timeframe_label]

if interval in ("5minute", "15minute", "60minute"):
    lookback_days = st.sidebar.slider("Lookback (days)", 1, 5, 3)
elif interval == "day":
    lookback_days = st.sidebar.slider("Lookback (days)", 30, 365, 90)
else:  # week / month
    lookback_days = st.sidebar.slider("Lookback (days)", 180, 1825, 730)

if data_mode == "mock":
    st.sidebar.warning("⚠️ Running on MOCK data. Set DATA_SOURCE=kite once the API key is added.")
else:
    st.sidebar.success(f"✅ Live data source: {data_mode.upper()}")

# ---------------------------------------------------------------------------
# Search any stock or MCX commodity (Gold/Silver/Crude/etc.) -- Upstox only
# ---------------------------------------------------------------------------
if data_mode == "upstox":
    with st.sidebar.expander("🔍 Search stocks / commodities"):
        search_query = st.text_input("e.g. RELIANCE, GOLD, SILVER, CRUDEOIL", key="search_box")
        seg_choice = st.radio("Type", ["Stocks (NSE)", "Commodities (MCX)"], horizontal=True)

        if search_query:
            ds_search = get_data_source()
            segment = "NSE_EQ" if seg_choice == "Stocks (NSE)" else "MCX_FO"
            itype = "EQ" if seg_choice == "Stocks (NSE)" else "FUT"
            try:
                matches = ds_search.search_symbol(search_query, segment=segment, instrument_type=itype)
            except Exception as e:
                matches = []
                st.error(f"Search failed: {e}")

            if matches:
                labels = [f"{m['trading_symbol']} — {m['name']}" +
                          (f" (exp {m['expiry']})" if m.get("expiry") else "")
                          for m in matches]
                picked = st.selectbox("Matches (nearest expiry first for futures)", labels)
                picked_idx = labels.index(picked)

                if st.button("Use this symbol"):
                    st.session_state["custom_symbol"] = matches[picked_idx]["instrument_key"]
                    st.session_state["custom_symbol_label"] = matches[picked_idx]["trading_symbol"]
                    st.rerun()
            else:
                st.caption("No matches yet — keep typing, or check spelling.")

        if st.session_state["custom_symbol"]:
            st.success(f"Active: {st.session_state['custom_symbol_label']}")
            if st.button("Clear custom symbol"):
                st.session_state["custom_symbol"] = None
                st.session_state["custom_symbol_label"] = None
                st.rerun()

# A selected custom symbol overrides the preset dropdown
symbol_display_name = symbol
if st.session_state["custom_symbol"]:
    symbol = st.session_state["custom_symbol"]
    symbol_display_name = st.session_state["custom_symbol_label"]
    st.sidebar.info(f"Showing: **{st.session_state['custom_symbol_label']}** (custom)")

st.sidebar.markdown("---")
st.sidebar.caption("Modules 2-9 (Option Chain, Greeks, Journal, Risk Manager) ship in Phase 2 & 3.")

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
    intraday_df, daily_df = load_data(symbol, lookback_days, interval)
except Exception as e:
    st.error(f"Could not load data for '{symbol_display_name}': {e}")
    st.caption("If this is a custom (stock/commodity) symbol, the instrument_key or "
               "market hours for that segment may need checking.")
    st.stop()
intraday_df["date_only"] = pd.to_datetime(intraday_df["datetime"]).dt.date

# Daily/Weekly/Monthly views: VWAP, CPR, Initial Balance, and Regime Detection are all
# intraday-SESSION concepts (VWAP resets each day, IB = first 60 min of a session, etc.)
# and don't have a meaningful definition on multi-day bars -- show a plain chart instead
# of computing session indicators that would otherwise be silently wrong.
if interval in ("day", "week", "month"):
    st.title("📊 Regime Dashboard")
    st.info("VWAP / CPR / Regime Detection are intraday-session tools and only apply to "
             "5 min / 15 min / 1 hour timeframes. Showing plain price chart for this view.")
    fig = build_plain_chart(intraday_df, title=f"{symbol_display_name} — {timeframe_label}")
    st.plotly_chart(fig, use_container_width=True, config={
        "modeBarButtonsToAdd": ["drawline", "drawopenpath", "drawrect", "drawcircle", "eraseshape"],
        "displaylogo": False,
    })
    st.caption("PMP Trading Suite · Phase 1 · For personal signal use only — no order execution. "
               "Not investment advice.")
    st.stop()

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
weekly_hl = weekly_high_low(daily_df, pd.Timestamp(selected_date))
vol_confirm = volume_confirmation(intraday_df)
regime = detect_regime(day_df, day_vwap, ib, cpr)

# ---------------------------------------------------------------------------
# Header row — key badges
# ---------------------------------------------------------------------------
st.title("📊 Regime Dashboard")

badge_cols = st.columns(6)

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

with badge_cols[5]:
    if vol_confirm["ratio"] is not None:
        icon = "✅" if vol_confirm["confirmed"] else "⚠️"
        st.metric("Volume", f"{icon} {vol_confirm['ratio']}x avg",
                   help=f"Module 4.5: breakout needs ≥1.5x the last 20-bar average volume. "
                        f"Latest: {vol_confirm['latest_volume']:,.0f}, Avg: {vol_confirm['avg_volume']:,.0f}")
    else:
        st.metric("Volume", "—", help="Not enough bars yet for a 20-period average.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------
chart_col, signal_col = st.columns([3, 1])

with chart_col:
    fig = build_regime_chart(day_df, day_vwap, cpr, pdh_pdl, ib, weekly_hl=weekly_hl,
                              title=f"{symbol_display_name} — {timeframe_label} — {selected_date}")
    st.plotly_chart(fig, use_container_width=True, config={
        "modeBarButtonsToAdd": ["drawline", "drawopenpath", "drawrect", "drawcircle", "eraseshape"],
        "displaylogo": False,
    })

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
level_cols = st.columns(8)
level_data = [
    ("CPR Pivot", cpr.get("pivot", "—")),
    ("CPR TC", cpr.get("tc", "—")),
    ("CPR BC", cpr.get("bc", "—")),
    ("PDH", pdh_pdl.get("pdh", "—")),
    ("PDL", pdh_pdl.get("pdl", "—")),
    ("IB Range", f"{ib.get('ib_low','—')} – {ib.get('ib_high','—')}"),
    ("Weekly High", weekly_hl.get("wh", "—")),
    ("Weekly Low", weekly_hl.get("wl", "—")),
]
for col, (label, val) in zip(level_cols, level_data):
    col.metric(label, val)

st.caption("PMP Trading Suite · Phase 1 · For personal signal use only — no order execution. "
           "Not investment advice.")
