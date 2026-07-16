"""
PMP Trading Suite — Order Preview
IMPORTANT: This page does NOT place orders. It builds a clean, reviewable order
summary that the investor manually enters into their own Upstox app. No order
execution API is used anywhere in this file, by design — see the conversation
history / README for why (SEBI's April 2026 retail algo framework restricts
"personal use" API order placement to immediate family; placing orders on an
unrelated investor's account via API falls outside that exemption).
"""

import streamlit as st
from datetime import date, datetime

from modules.env_setup import init_env
init_env()

st.set_page_config(page_title="Order Preview — PMP Trading Suite", layout="wide", page_icon="🧾")

st.sidebar.title("🧾 Order Preview")
st.sidebar.caption("Builds a clean order summary — does NOT place orders via API.")
st.sidebar.warning("⚠️ No execution happens here. Investor places the order themselves "
                     "in their own Upstox app using this summary.")

st.title("🧾 Order Preview")
st.info("This tool prepares an order summary for review — it never calls a broker's order "
        "API. Placing the order in Upstox is a manual step done by whoever owns the account.")

with st.form("order_preview_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        instrument = st.text_input("Instrument", placeholder="e.g. NIFTY 24900 PE 31 JUL")
        transaction_type = st.selectbox("Transaction", ["BUY", "SELL"])
    with col2:
        quantity = st.number_input("Quantity (total, incl. lot size)", min_value=1, value=75, step=1)
        product_type = st.selectbox("Product", ["Intraday (MIS)", "Delivery/Carryforward (NRML)"])
    with col3:
        order_type = st.selectbox("Order Type", ["MARKET", "LIMIT", "SL", "SL-M"])
        limit_price = st.number_input("Limit/Trigger Price (₹, if applicable)", min_value=0.0, value=0.0, step=0.5)

    col4, col5 = st.columns(2)
    with col4:
        stop_loss = st.number_input("Planned Stop-Loss (₹)", min_value=0.0, value=0.0, step=0.5)
    with col5:
        target = st.number_input("Planned Target (₹)", min_value=0.0, value=0.0, step=0.5)

    reasoning = st.text_area("Confluence / reasoning (for the record)", height=70,
                              placeholder="e.g. PDL sweep + VWAP reclaim + PE writing increase — Range Day setup")

    submitted = st.form_submit_button("Generate Preview", use_container_width=True)

if submitted:
    if not instrument:
        st.error("Instrument is required.")
    else:
        timestamp = datetime.now().strftime("%d %b %Y, %I:%M %p")

        summary_lines = [
            f"ORDER PREVIEW — generated {timestamp}",
            "─" * 40,
            f"Instrument     : {instrument}",
            f"Transaction    : {transaction_type}",
            f"Quantity       : {quantity}",
            f"Product        : {product_type}",
            f"Order Type     : {order_type}",
        ]
        if order_type != "MARKET" and limit_price > 0:
            summary_lines.append(f"Price/Trigger  : ₹{limit_price}")
        if stop_loss > 0:
            summary_lines.append(f"Stop-Loss      : ₹{stop_loss}")
        if target > 0:
            summary_lines.append(f"Target         : ₹{target}")
        if reasoning:
            summary_lines.append("")
            summary_lines.append(f"Reasoning: {reasoning}")
        summary_lines.append("─" * 40)
        summary_lines.append("⚠️ Not investment advice. Review before placing.")

        summary_text = "\n".join(summary_lines)

        st.subheader("📋 Copy this and place manually in Upstox")
        st.code(summary_text, language=None)

        st.caption("Click the copy icon (top-right of the box above), then paste into WhatsApp "
                   "to send to the investor, or use it directly while placing the order yourself "
                   "in the Upstox app's order screen.")

st.markdown("---")
st.caption("PMP Trading Suite · Order Preview · No orders are placed by this tool. "
           "Not investment advice.")
