"""
PMP Trading Suite — Strategy Builder (Module 5)
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from modules.env_setup import init_env
init_env()

from modules.data_source import get_data_source
from modules.strategy import (
    STRATEGY_TEMPLATES, build_scaled_legs, compute_strategy_stats,
    CALENDAR_DIAGONAL_TEMPLATES, build_calendar_diagonal_legs, compute_calendar_diagonal_payoff,
)

st.set_page_config(page_title="Strategy Builder — PMP Trading Suite", layout="wide", page_icon="🏗️")

st.sidebar.title("🏗️ Strategy Builder")
st.sidebar.caption("Module 5 — Hedged Option Selling")

symbol = st.sidebar.selectbox("Symbol", ["NIFTY 50", "NIFTY BANK", "SENSEX"], index=0)
lot_size = st.sidebar.number_input("Lot size", value=75, step=1, min_value=1)

mode = st.sidebar.radio("Structure type", ["Same-Expiry Spreads", "Calendar / Diagonal (2 expiries)"])

try:
    ds = get_data_source()
except Exception as e:
    st.error(f"Could not initialize data source: {e}")
    st.stop()

st.title("🏗️ Strategy Builder")

# ===========================================================================
# MODE 1: Same-expiry spreads (Bull Put, Bear Call, Iron Condor, Broken Wing Butterfly)
# ===========================================================================
if mode == "Same-Expiry Spreads":
    try:
        chain_df = ds.get_option_chain(symbol)
        spot_price = chain_df["underlying_spot_price"].iloc[0] if not chain_df.empty else None
    except Exception as e:
        st.error(f"Could not load option chain: {e}")
        st.stop()

    if chain_df.empty or spot_price is None:
        st.warning("Empty option chain — check symbol/expiry or data source connection.")
        st.stop()

    strikes = sorted(chain_df["strike_price"].unique().tolist())
    atm_index = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot_price))

    strategy_name = st.selectbox("Strategy", list(STRATEGY_TEMPLATES.keys()))
    st.caption(STRATEGY_TEMPLATES[strategy_name]["description"])

    wing_width = st.slider("Wing width (strikes away from ATM, scales the template)", 1, 3, 1,
                            help="1 = template as designed. 2-3 widens every leg's offset proportionally "
                                 "for a wider (lower premium, lower risk) structure.")

    legs = build_scaled_legs(strategy_name, strikes, atm_index, wing_width)

    for leg in legs:
        row = chain_df[chain_df["strike_price"] == leg["strike"]]
        if not row.empty:
            prefix = "ce" if leg["type"] == "CE" else "pe"
            leg["premium"] = float(row.iloc[0][f"{prefix}_ltp"])
        else:
            leg["premium"] = 0.0

    st.markdown("---")
    st.subheader("📋 Legs")
    legs_display = pd.DataFrame([
        {"Strike": l["strike"], "Type": l["type"], "Txn": l["txn"],
         "Qty Multiplier": l.get("qty_multiplier", 1), "Premium (₹)": l["premium"]}
        for l in legs
    ])
    st.dataframe(legs_display, use_container_width=True, hide_index=True)

    stats = compute_strategy_stats(legs, lot_size, spot_price)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Max Profit", f"₹{stats['max_profit']:,.0f}")
    c2.metric("Max Loss", f"₹{stats['max_loss']:,.0f}")
    c3.metric("Net " + ("Credit" if stats["is_credit"] else "Debit"), f"₹{abs(stats['net_premium']):,.0f}")
    c4.metric("Breakeven(s)", ", ".join(f"{b:,.0f}" for b in stats["breakevens"]) if stats["breakevens"] else "—")

    st.markdown("---")
    st.subheader("📈 Payoff Diagram (at expiry)")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=stats["price_range"], y=stats["payoff"],
        mode="lines", line=dict(color="#26a69a", width=2.5),
        fill="tozeroy", fillcolor="rgba(38,166,154,0.15)",
        name="P&L at expiry",
    ))
    fig.add_hline(y=0, line_color="#787b86", line_width=1)
    fig.add_vline(x=spot_price, line_color="#ffb300", line_dash="dash",
                  annotation_text=f"Spot {spot_price:,.0f}", annotation_font_color="#ffb300")
    for be in stats["breakevens"]:
        fig.add_vline(x=be, line_color="#64b5f6", line_dash="dot",
                      annotation_text=f"BE {be:,.0f}", annotation_font_color="#64b5f6")
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#131722", plot_bgcolor="#131722",
        height=450, margin=dict(l=10, r=10, t=30, b=10),
        xaxis_title="Underlying price at expiry", yaxis_title="P&L (₹)",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Payoff calculated at expiry (no time-decay/IV path modeled between now and then).")

# ===========================================================================
# MODE 2: Calendar / Diagonal spreads (two different expiries)
# ===========================================================================
else:
    try:
        expiries = ds.get_available_expiries(symbol)
    except NotImplementedError:
        st.error("This data source doesn't support listing multiple expiries "
                 "(Calendar/Diagonal needs at least 2). Switch to Upstox live data.")
        st.stop()
    except Exception as e:
        st.error(f"Could not fetch expiries: {e}")
        st.stop()

    if len(expiries) < 2:
        st.warning("Only one expiry available right now — Calendar/Diagonal needs at least 2.")
        st.stop()

    col_e1, col_e2 = st.columns(2)
    with col_e1:
        near_expiry = st.selectbox("Near expiry (SELL leg)", expiries, index=0)
    with col_e2:
        far_options = [e for e in expiries if e > near_expiry]
        if not far_options:
            st.warning("No expiry after the selected near expiry.")
            st.stop()
        far_expiry = st.selectbox("Far expiry (BUY leg)", far_options, index=0)

    try:
        near_chain = ds.get_option_chain(symbol, near_expiry)
        far_chain = ds.get_option_chain(symbol, far_expiry)
        spot_price = near_chain["underlying_spot_price"].iloc[0] if not near_chain.empty else None
    except Exception as e:
        st.error(f"Could not load option chains: {e}")
        st.stop()

    if near_chain.empty or far_chain.empty or spot_price is None:
        st.warning("Empty option chain data.")
        st.stop()

    strikes = sorted(near_chain["strike_price"].unique().tolist())
    atm_index = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot_price))

    structure_name = st.selectbox("Structure", list(CALENDAR_DIAGONAL_TEMPLATES.keys()))
    st.caption(CALENDAR_DIAGONAL_TEMPLATES[structure_name]["description"])
    st.info("⚠️ Approximation: the far leg's payoff at near-expiry is estimated via Black-Scholes "
            "using today's IV held constant. Real IV can shift.")

    legs = build_calendar_diagonal_legs(structure_name, strikes, atm_index)

    near_row = near_chain[near_chain["strike_price"] == legs["near"]["strike"]]
    far_row = far_chain[far_chain["strike_price"] == legs["far"]["strike"]]
    prefix_near = "ce" if legs["near"]["type"] == "CE" else "pe"
    prefix_far = "ce" if legs["far"]["type"] == "CE" else "pe"

    legs["near"]["premium"] = float(near_row.iloc[0][f"{prefix_near}_ltp"]) if not near_row.empty else 0.0
    legs["far"]["premium"] = float(far_row.iloc[0][f"{prefix_far}_ltp"]) if not far_row.empty else 0.0
    far_iv_raw = float(far_row.iloc[0][f"{prefix_far}_iv"]) if not far_row.empty else 15.0
    legs["far"]["iv"] = far_iv_raw / 100 if far_iv_raw > 1 else far_iv_raw  # normalize % vs decimal

    st.markdown("---")
    st.subheader("📋 Legs")
    legs_display = pd.DataFrame([
        {"Leg": "Near (SELL)", "Expiry": near_expiry, "Strike": legs["near"]["strike"],
         "Type": legs["near"]["type"], "Premium (₹)": legs["near"]["premium"]},
        {"Leg": "Far (BUY)", "Expiry": far_expiry, "Strike": legs["far"]["strike"],
         "Type": legs["far"]["type"], "Premium (₹)": legs["far"]["premium"]},
    ])
    st.dataframe(legs_display, use_container_width=True, hide_index=True)

    near_dte = (pd.Timestamp(near_expiry) - pd.Timestamp.now().normalize()).days
    far_dte = (pd.Timestamp(far_expiry) - pd.Timestamp.now().normalize()).days

    result = compute_calendar_diagonal_payoff(legs["near"], legs["far"], lot_size, spot_price,
                                               near_dte, far_dte)

    c1, c2, c3 = st.columns(3)
    c1.metric("Max Profit (est.)", f"₹{result['max_profit']:,.0f}")
    c2.metric("Max Loss (est.)", f"₹{result['max_loss']:,.0f}")
    c3.metric("Net " + ("Credit" if result["is_credit"] else "Debit"), f"₹{abs(result['net_premium']):,.0f}")

    st.markdown("---")
    st.subheader(f"📈 Estimated Payoff at Near Expiry ({near_expiry})")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=result["price_range"], y=result["payoff"],
        mode="lines", line=dict(color="#26a69a", width=2.5),
        fill="tozeroy", fillcolor="rgba(38,166,154,0.15)",
        name="Estimated P&L",
    ))
    fig.add_hline(y=0, line_color="#787b86", line_width=1)
    fig.add_vline(x=spot_price, line_color="#ffb300", line_dash="dash",
                  annotation_text=f"Spot {spot_price:,.0f}", annotation_font_color="#ffb300")
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#131722", plot_bgcolor="#131722",
        height=450, margin=dict(l=10, r=10, t=30, b=10),
        xaxis_title="Underlying price at near expiry", yaxis_title="Estimated P&L (₹)",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(result["note"])

st.markdown("---")
st.caption("PMP Trading Suite · Module 5 · Not investment advice.")
