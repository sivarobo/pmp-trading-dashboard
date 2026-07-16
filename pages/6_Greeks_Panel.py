"""
PMP Trading Suite — Phase 3+: Greeks Panel (Module 3)
"""

import streamlit as st
import pandas as pd
from datetime import date

from modules.env_setup import init_env
init_env()

from modules.db import init_db
from modules.data_source import get_data_source
from modules.greeks import (
    add_position, get_positions, delete_position, clear_all_positions,
    compute_portfolio_greeks, gamma_risk_warning, delta_neutral_check,
)

st.set_page_config(page_title="Greeks Panel — PMP Trading Suite", layout="wide", page_icon="🧮")

try:
    init_db()
except Exception as e:
    st.error(f"Database connection failed: {e}")
    st.caption("Set DATABASE_URL (Neon Postgres connection string) in your .env file or "
               "Streamlit Cloud Secrets.")
    st.stop()

st.sidebar.title("🧮 Greeks Panel")
st.sidebar.caption("Phase 3+ — Module 3 framework")

symbol = st.sidebar.selectbox("Symbol", ["NIFTY 50", "NIFTY BANK", "SENSEX"], index=0)

data_mode_ok = True
try:
    ds = get_data_source()
    chain_df = ds.get_option_chain(symbol)
    spot_price = chain_df["underlying_spot_price"].iloc[0] if not chain_df.empty else None
except Exception as e:
    st.sidebar.error(f"Chain load failed: {e}")
    chain_df = pd.DataFrame()
    spot_price = None
    data_mode_ok = False

st.title("🧮 Greeks Panel")

tab_positions, tab_portfolio, tab_add = st.tabs(["📋 Positions", "📊 Portfolio Greeks", "➕ Add Position"])

# ---------------------------------------------------------------------------
# Add Position
# ---------------------------------------------------------------------------
with tab_add:
    st.caption("Add each leg of your current position. Strike must exist in the live "
               "option chain to compute Greeks against it.")

    with st.form("add_position_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            strike = st.number_input("Strike", min_value=0.0, step=50.0)
            option_type = st.selectbox("Type", ["CE", "PE"])
        with col2:
            transaction = st.selectbox("Transaction", ["SELL", "BUY"])
            quantity = st.number_input("Quantity (total)", min_value=1, value=75, step=1)
        with col3:
            entry_premium = st.number_input("Entry premium (₹)", min_value=0.0, step=0.5)
            expiry = st.date_input("Expiry", value=date.today())

        if st.form_submit_button("Add Leg", use_container_width=True):
            add_position(strike, option_type, transaction, int(quantity),
                         entry_premium or None, expiry, symbol)
            st.success(f"Added {transaction} {option_type} {strike:.0f}")
            st.rerun()

# ---------------------------------------------------------------------------
# Positions List
# ---------------------------------------------------------------------------
with tab_positions:
    positions_df = get_positions()

    if positions_df.empty:
        st.info("No positions added yet — use the 'Add Position' tab.")
    else:
        display_cols = ["id", "symbol", "strike", "option_type", "transaction", "quantity",
                         "entry_premium", "expiry"]
        available = [c for c in display_cols if c in positions_df.columns]
        st.dataframe(positions_df[available], use_container_width=True, height=300)

        col1, col2 = st.columns(2)
        with col1:
            with st.expander("🗑️ Delete a position"):
                pos_id = st.number_input("Position ID to delete", min_value=1, step=1)
                if st.button("Delete Position"):
                    delete_position(int(pos_id))
                    st.success(f"Deleted position {pos_id}.")
                    st.rerun()
        with col2:
            with st.expander("🧹 Clear all positions"):
                st.warning("This removes every tracked leg.")
                if st.button("Clear All", type="primary"):
                    clear_all_positions()
                    st.success("All positions cleared.")
                    st.rerun()

# ---------------------------------------------------------------------------
# Portfolio Greeks
# ---------------------------------------------------------------------------
with tab_portfolio:
    positions_df = get_positions()

    if not data_mode_ok or chain_df.empty:
        st.warning("Live option chain unavailable — cannot compute current Greeks.")
    elif positions_df.empty:
        st.info("Add positions first to see portfolio-level Greeks.")
    else:
        result = compute_portfolio_greeks(positions_df, chain_df)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Net Delta", result["net_delta"],
                   help="Directional exposure. Near 0 = delta-neutral.")
        c2.metric("Net Gamma", result["net_gamma"],
                   help="Rate of change of delta. High = position risk changes fast near expiry.")
        c3.metric("Net Theta (₹/day)", result["net_theta"],
                   help="Positive = you earn time decay daily (net seller). Negative = you pay it (net buyer).")
        c4.metric("Net Vega", result["net_vega"],
                   help="Sensitivity to IV changes. Positive = benefits from IV rise.")

        st.markdown("---")

        # Days to expiry (using the earliest expiry among positions, if set)
        days_to_expiry = None
        if "expiry" in positions_df.columns and positions_df["expiry"].notna().any():
            nearest_expiry = pd.to_datetime(positions_df["expiry"]).min()
            days_to_expiry = (nearest_expiry.date() - date.today()).days

        if days_to_expiry is not None:
            st.caption(f"Nearest expiry: {days_to_expiry} day(s) away")
            gw = gamma_risk_warning(days_to_expiry, positions_df, spot_price)
            if gw:
                for msg in gw:
                    st.error(msg)
            else:
                st.success("✅ No elevated expiry-gamma risk detected on current legs.")

        st.markdown("---")
        dn = delta_neutral_check(result["net_delta"], result["net_theta"])
        if dn["trigger"]:
            st.warning(f"🔔 {dn['message']}")
        else:
            st.success(f"✅ {dn['message']}")

        st.markdown("---")
        st.subheader("Per-leg contribution")
        legs_df = pd.DataFrame(result["legs"])
        if not legs_df.empty:
            st.dataframe(legs_df, use_container_width=True)

st.caption("PMP Trading Suite · Module 3 · Personal Greeks tracking — data stored in Neon Postgres. "
           "Not investment advice.")
