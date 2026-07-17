"""
PMP Trading Suite — Phase 2: Option Chain Reader
Implements Module 2 (Professional Option Chain Reading):
  - Change in OI (4-quadrant flow classification)
  - OI Shift tracking (support/resistance wall migration within the session)
  - Writing vs Covering flags
  - Trap detection heuristic
"""

import streamlit as st
import pandas as pd

from modules.env_setup import init_env
init_env()

from modules.theme import apply_theme

from modules.data_source import get_data_source
from modules.option_chain import (
    annotate_chain, compute_pcr, compute_max_pain,
    find_walls, detect_oi_shift, detect_trap_signal,
)

st.set_page_config(page_title="Option Chain Reader — PMP Trading Suite", layout="wide", page_icon="🔗")
apply_theme()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("🔗 Option Chain Reader")
st.sidebar.caption("Phase 2 — Module 2 framework")

symbol = st.sidebar.selectbox("Symbol", ["NIFTY 50", "NIFTY BANK", "SENSEX"], index=0)

import os
data_mode = os.environ.get("DATA_SOURCE", "mock")
if data_mode == "mock":
    st.sidebar.warning("⚠️ Running on MOCK data.")
else:
    st.sidebar.success(f"✅ Live data source: {data_mode.upper()}")

strike_window = st.sidebar.slider("Strikes around ATM (each side)", 5, 30, 12)

auto_refresh = st.sidebar.checkbox("Auto-refresh every 60s", value=False)
if auto_refresh:
    st.sidebar.caption("Re-run the page (R key / rerun button) to refresh manually if auto-refresh isn't wired to a timer in this environment.")

# ---------------------------------------------------------------------------
# Load option chain
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def load_chain(symbol: str):
    ds = get_data_source()
    chain = ds.get_option_chain(symbol)
    spot = chain["underlying_spot_price"].iloc[0] if "underlying_spot_price" in chain.columns and not chain.empty else None
    return chain, spot

try:
    chain_df, spot_price = load_chain(symbol)
except Exception as e:
    st.error(f"Could not load option chain: {e}")
    st.stop()

if chain_df.empty:
    st.warning("Empty option chain returned. Check symbol/expiry or data source connection.")
    st.stop()

annotated = annotate_chain(chain_df)
pcr = compute_pcr(chain_df)
max_pain = compute_max_pain(chain_df)
walls = find_walls(chain_df)

# Track wall shifts across reruns within the same session
if "prev_walls" not in st.session_state:
    st.session_state["prev_walls"] = None

shift_messages = detect_oi_shift(walls, st.session_state["prev_walls"])
st.session_state["prev_walls"] = walls

trap_alerts = detect_trap_signal(chain_df, spot_price) if spot_price else []

# ---------------------------------------------------------------------------
# Header metrics
# ---------------------------------------------------------------------------
st.title("🔗 Option Chain Reader")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Spot Price", f"{spot_price:,.2f}" if spot_price else "—")
m2.metric("PCR", f"{pcr}")
m3.metric("Max Pain", f"{max_pain:,.0f}" if max_pain else "—")
m4.metric("Resistance (CE wall)", f"{walls['resistance_strike']:,.0f}",
          help=f"OI: {walls['resistance_oi']:,.0f}")
m5.metric("Support (PE wall)", f"{walls['support_strike']:,.0f}",
          help=f"OI: {walls['support_oi']:,.0f}")

st.markdown("---")

# ---------------------------------------------------------------------------
# Alerts row
# ---------------------------------------------------------------------------
alert_col1, alert_col2 = st.columns(2)

with alert_col1:
    st.subheader("🔄 OI Shift (this session)")
    if shift_messages:
        for msg in shift_messages:
            st.info(msg)
    else:
        st.caption("No wall migration detected yet vs the last refresh. "
                   "Reload the page after some time to compare against a fresh snapshot.")

with alert_col2:
    st.subheader("⚠️ Trap Signals")
    if trap_alerts:
        for msg in trap_alerts:
            st.warning(msg)
    else:
        st.caption("No trap signals near spot right now — writers are unwinding "
                   "(or flat) at nearby strikes.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Change-in-OI table
# ---------------------------------------------------------------------------
st.subheader("📊 Change in OI — Strike-wise")

flow_color = {
    "Long Buildup": "🟢",
    "Short Buildup": "🔴",
    "Short Covering": "🟡",
    "Long Unwinding": "⚪",
    "Neutral": "—",
}

display_df = annotated.copy()
display_df["CE Flow"] = display_df["ce_flow"].map(lambda f: f"{flow_color.get(f,'')} {f}")
display_df["PE Flow"] = display_df["pe_flow"].map(lambda f: f"{flow_color.get(f,'')} {f}")

# Highlight the ATM strike (closest to spot) and trim to the selected window around it
if spot_price:
    display_df["dist"] = (display_df["strike_price"] - spot_price).abs()
    atm_strike = display_df.loc[display_df["dist"].idxmin(), "strike_price"]
    sorted_strikes = sorted(display_df["strike_price"].unique())
    atm_idx = sorted_strikes.index(atm_strike)
    lo = sorted_strikes[max(0, atm_idx - strike_window)]
    hi = sorted_strikes[min(len(sorted_strikes) - 1, atm_idx + strike_window)]
    display_df = display_df[(display_df["strike_price"] >= lo) & (display_df["strike_price"] <= hi)]
else:
    atm_strike = None

table_cols = [
    "strike_price", "ce_oi", "ce_oi_change", "CE Flow", "ce_ltp", "ce_iv",
    "PE Flow", "pe_oi_change", "pe_oi", "pe_ltp", "pe_iv",
]
table_view = display_df[table_cols].rename(columns={
    "strike_price": "Strike", "ce_oi": "CE OI", "ce_oi_change": "CE ΔOI",
    "ce_ltp": "CE LTP", "ce_iv": "CE IV", "pe_oi_change": "PE ΔOI",
    "pe_oi": "PE OI", "pe_ltp": "PE LTP", "pe_iv": "PE IV",
})

def highlight_atm(row):
    if atm_strike is not None and row["Strike"] == atm_strike:
        return ["background-color: #3d4451; color: #ffffff; font-weight: 600"] * len(row)
    return [""] * len(row)

st.dataframe(
    table_view.style.apply(highlight_atm, axis=1).format({
        "CE OI": "{:,.0f}", "CE ΔOI": "{:+,.0f}", "CE LTP": "{:.2f}", "CE IV": "{:.1f}",
        "PE ΔOI": "{:+,.0f}", "PE OI": "{:,.0f}", "PE LTP": "{:.2f}", "PE IV": "{:.1f}",
        "Strike": "{:,.0f}",
    }),
    use_container_width=True,
    height=420,
)

st.caption("💡 The header freezes automatically **inside this table's own scroll area** — "
           "hover your cursor directly over the rows (not the page's right-edge scrollbar) and scroll there.")

st.caption(
    "🟢 Long Buildup (OI↑ price↑) · 🔴 Short Buildup / Writing (OI↑ price↓) · "
    "🟡 Short Covering (OI↓ price↑) · ⚪ Long Unwinding (OI↓ price↓) — Module 2.1"
)

st.markdown("---")
st.caption("PMP Trading Suite · Phase 2 · For personal signal use only — no order execution. "
           "Not investment advice.")
