"""
PMP Trading Suite — Phase 3: Risk Manager (Module 7 + Module 8)
"""

import streamlit as st
from datetime import date

from modules.env_setup import init_env
init_env()

from modules.theme import apply_theme
from modules.navbar import render_navbar, render_ticker

from modules.db import init_db
from modules.journal import get_entries
from modules.risk import (
    get_risk_settings, update_risk_settings, calculate_position_size,
    compute_drawdown, check_drawdown_limits, get_checklist_state, save_checklist_state,
    get_checklist_streak, PREMARKET_ITEMS, OPEN_RULES_ITEMS, EOD_ITEMS,
)

st.set_page_config(page_title="Risk Manager — PMP Trading Suite", layout="wide", page_icon="🛡️")
apply_theme()
render_ticker()
render_navbar(current="Risk")

try:
    init_db()
except Exception as e:
    st.error(f"Database connection failed: {e}")
    st.caption("Set DATABASE_URL (Neon Postgres connection string) in your .env file or "
               "Streamlit Cloud Secrets. See modules/db.py for setup steps.")
    st.stop()

st.sidebar.title("🛡️ Risk Manager")
st.sidebar.caption("Phase 3 — Module 7 & 8 framework")

st.title("🛡️ Risk Manager")

tab_dd, tab_sizing, tab_settings, tab_sop = st.tabs(
    ["📉 Drawdown Monitor", "🧮 Position Sizing", "⚙️ Capital Settings", "☑️ Daily SOP Checklist"]
)

settings = get_risk_settings()

# ---------------------------------------------------------------------------
# Drawdown Monitor -- Module 7.3
# ---------------------------------------------------------------------------
with tab_dd:
    journal_df = get_entries()
    dd = compute_drawdown(journal_df, settings.get("capital", 0))
    alerts = check_drawdown_limits(dd, settings)

    c1, c2, c3 = st.columns(3)
    c1.metric("Today's P&L", f"₹{dd.get('daily_pnl', 0):,.0f}", delta=f"{dd.get('daily_pnl_pct', 0)}%")
    c2.metric("This Week's P&L", f"₹{dd.get('weekly_pnl', 0):,.0f}", delta=f"{dd.get('weekly_pnl_pct', 0)}%")
    c3.metric("This Month's P&L", f"₹{dd.get('monthly_pnl', 0):,.0f}", delta=f"{dd.get('monthly_pnl_pct', 0)}%")

    st.markdown("---")
    st.caption(f"Limits: Daily -{settings.get('max_daily_loss_pct')}% · "
               f"Weekly -{settings.get('max_weekly_loss_pct')}% · "
               f"Monthly -{settings.get('max_monthly_loss_pct')}% (set in Capital Settings tab)")

    if alerts:
        for level, msg in alerts:
            st.error(f"🛑 {msg}")
    else:
        st.success("✅ Within all drawdown limits. Clear to trade per plan.")

# ---------------------------------------------------------------------------
# Position Sizing Calculator -- Module 7.2
# ---------------------------------------------------------------------------
with tab_sizing:
    st.caption("Module 7.2: risk no more than your per-trade % on any single position, "
               "sized off your actual stop-loss distance — not off margin available.")

    col1, col2 = st.columns(2)
    with col1:
        capital_input = st.number_input("Capital (₹)", value=float(settings.get("capital", 1000000)), step=10000.0)
        risk_pct_input = st.number_input("Risk per trade (%)", value=float(settings.get("risk_per_trade_pct", 1.5)),
                                          step=0.1, min_value=0.1, max_value=10.0)
        lot_size_input = st.number_input("Lot size", value=75, step=1, min_value=1)
    with col2:
        entry_price = st.number_input("Entry price (₹)", value=100.0, step=0.5)
        sl_price = st.number_input("Stop-loss price (₹)", value=95.0, step=0.5)

    if st.button("Calculate Position Size", use_container_width=True):
        result = calculate_position_size(capital_input, risk_pct_input, entry_price, sl_price, int(lot_size_input))

        r1, r2, r3 = st.columns(3)
        r1.metric("Max Risk Amount", f"₹{result['max_risk_amount']:,.0f}")
        r2.metric("Max Lots", result["max_lots"])
        r3.metric("Actual Risk (at max lots)", f"₹{result['actual_risk_amount']:,.0f}")

        if result["max_lots"] == 0:
            st.warning("Stop-loss too wide (or capital/risk % too small) for even 1 lot within your risk limit.")

# ---------------------------------------------------------------------------
# Capital Settings -- Module 7.1
# ---------------------------------------------------------------------------
with tab_settings:
    st.caption("Module 7.1: keep 40% capital in reserve. These limits drive the Drawdown Monitor alerts.")

    with st.form("risk_settings_form"):
        capital = st.number_input("Total Trading Capital (₹)", value=float(settings.get("capital", 1000000)), step=10000.0)
        max_deployment = st.slider("Max deployment (%)", 10, 100, int(settings.get("max_deployment_pct", 60)))
        risk_per_trade = st.slider("Risk per trade (%)", 0.5, 5.0, float(settings.get("risk_per_trade_pct", 1.5)), step=0.1)
        max_daily = st.slider("Max daily loss (%)", 0.5, 5.0, float(settings.get("max_daily_loss_pct", 1.5)), step=0.1)
        max_weekly = st.slider("Max weekly loss (%)", 1.0, 10.0, float(settings.get("max_weekly_loss_pct", 3.0)), step=0.5)
        max_monthly = st.slider("Max monthly loss (%)", 2.0, 15.0, float(settings.get("max_monthly_loss_pct", 5.0)), step=0.5)

        if st.form_submit_button("Save Settings", use_container_width=True):
            update_risk_settings({
                "capital": capital, "max_deployment_pct": max_deployment,
                "risk_per_trade_pct": risk_per_trade, "max_daily_loss_pct": max_daily,
                "max_weekly_loss_pct": max_weekly, "max_monthly_loss_pct": max_monthly,
            })
            st.success("Settings saved.")
            st.rerun()

    st.info(f"💡 Deployable capital right now: ₹{settings.get('capital', 0) * settings.get('max_deployment_pct', 60) / 100:,.0f} "
            f"({settings.get('max_deployment_pct', 60)}% of ₹{settings.get('capital', 0):,.0f})")

# ---------------------------------------------------------------------------
# Daily SOP Checklist -- Module 8
# ---------------------------------------------------------------------------
with tab_sop:
    today = date.today()
    saved_state = get_checklist_state(today)
    streak = get_checklist_streak()

    st.metric("🔥 Current 100%-adherence streak", f"{streak} day(s)")
    st.markdown("---")

    new_state = {}

    st.subheader("Pre-Market Checklist (8:45–9:10 AM)")
    for i, item in enumerate(PREMARKET_ITEMS):
        key = f"pm_{i}"
        new_state[key] = st.checkbox(item, value=saved_state.get(key, False), key=f"chk_{key}")

    st.subheader("Market Open Rules (9:15–10:00 AM)")
    for i, item in enumerate(OPEN_RULES_ITEMS):
        key = f"open_{i}"
        new_state[key] = st.checkbox(item, value=saved_state.get(key, False), key=f"chk_{key}")

    st.subheader("End-of-Day Review (3:30–4:00 PM)")
    for i, item in enumerate(EOD_ITEMS):
        key = f"eod_{i}"
        new_state[key] = st.checkbox(item, value=saved_state.get(key, False), key=f"chk_{key}")

    if st.button("Save Today's Checklist", use_container_width=True):
        save_checklist_state(today, new_state)
        completed = sum(1 for v in new_state.values() if v)
        total = len(new_state)
        if completed == total:
            st.success(f"✅ 100% complete ({completed}/{total}) — streak continues!")
        else:
            st.warning(f"{completed}/{total} complete — streak breaks if not 100% by end of day.")
        st.rerun()

st.caption("PMP Trading Suite · Phase 3 · Personal risk management — data stored in your Neon Postgres database.")
