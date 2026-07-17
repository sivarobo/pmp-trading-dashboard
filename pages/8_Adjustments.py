"""
PMP Trading Suite — Adjustments (Module 6)
Roll Up / Roll Down / Roll Forward tracking, built on top of the positions
tracked in the Greeks Panel (Module 3).
"""

import streamlit as st
import pandas as pd
from datetime import date

from modules.env_setup import init_env
init_env()

from modules.theme import apply_theme

from modules.db import init_db
from modules.data_source import get_data_source
from modules.adjustments import (
    get_open_positions, check_roll_eligibility, roll_position,
    get_lineage_history, get_all_lineages_summary, MAX_ADJUSTMENTS_PER_POSITION,
)

st.set_page_config(page_title="Adjustments — PMP Trading Suite", layout="wide", page_icon="🔄")
apply_theme()

try:
    init_db()
except Exception as e:
    st.error(f"Database connection failed: {e}")
    st.caption("Set DATABASE_URL (Neon Postgres connection string) in your .env file or "
               "Streamlit Cloud Secrets.")
    st.stop()

st.sidebar.title("🔄 Adjustments")
st.sidebar.caption("Module 6 — Roll Up / Down / Forward tracking")
st.sidebar.info(f"Rule: max {MAX_ADJUSTMENTS_PER_POSITION} adjustments per position lineage "
                 f"(Module 6.4). Beyond that — exit and redeploy, don't keep rolling.")

symbol = st.sidebar.selectbox("Symbol", ["NIFTY 50", "NIFTY BANK", "SENSEX"], index=0)

try:
    ds = get_data_source()
    chain_df = ds.get_option_chain(symbol)
    spot_price = chain_df["underlying_spot_price"].iloc[0] if not chain_df.empty else None
except Exception as e:
    st.sidebar.error(f"Chain load failed: {e}")
    chain_df = pd.DataFrame()
    spot_price = None

st.title("🔄 Adjustments")

tab_roll, tab_history = st.tabs(["🔀 Roll a Position", "📜 Adjustment History"])

# ---------------------------------------------------------------------------
# Roll a Position
# ---------------------------------------------------------------------------
with tab_roll:
    open_positions = get_open_positions()

    if open_positions.empty:
        st.info("No open positions to roll. Add positions in the Greeks Panel first.")
    else:
        pos_labels = [
            f"#{row['id']} — {row['transaction']} {row['option_type']} {row['strike']:.0f} "
            f"(qty {row['quantity']}, {row['roll_count']} prior roll(s))"
            for _, row in open_positions.iterrows()
        ]
        picked_label = st.selectbox("Select position to roll", pos_labels)
        picked_idx = pos_labels.index(picked_label)
        old_pos = open_positions.iloc[picked_idx].to_dict()

        eligibility = check_roll_eligibility(old_pos)
        for w in eligibility["warnings"]:
            if "🛑" in w:
                st.error(w)
            else:
                st.warning(w)

        if not eligibility["eligible"]:
            st.stop()

        st.markdown("---")
        roll_type = st.radio("Roll type", ["Roll Up", "Roll Down", "Roll Forward"], horizontal=True)
        st.caption({
            "Roll Up": "Module 6.1: move a short PE up when market rallies and it's now safe, "
                       "collecting extra credit to offset pressure on the other side.",
            "Roll Down": "Module 6.2: mirror of Roll Up — move a short CE down when market falls.",
            "Roll Forward": "Module 6.3: same strike, next expiry — only if your original thesis "
                             "is still valid. Max once; a second roll forward means the thesis was wrong.",
        }[roll_type])

        close_price = st.number_input(f"Close price for the OLD leg (₹) — what you're exiting it at",
                                       min_value=0.0, step=0.5)

        if chain_df.empty:
            st.warning("Live option chain unavailable — cannot pick a new strike right now.")
        else:
            strikes = sorted(chain_df["strike_price"].unique().tolist())

            if roll_type == "Roll Forward":
                new_strike = old_pos["strike"]
                st.caption(f"Same strike ({new_strike:.0f}), rolling to a later expiry.")
                try:
                    expiries = ds.get_available_expiries(symbol)
                    new_expiry = st.selectbox("New expiry", expiries)
                except Exception:
                    new_expiry = st.date_input("New expiry", value=date.today())
            else:
                new_strike = st.selectbox("New strike", strikes,
                                           index=min(range(len(strikes)),
                                                     key=lambda i: abs(strikes[i] - old_pos["strike"])))
                new_expiry = old_pos["expiry"] if old_pos["expiry"] else date.today()

            new_row = chain_df[chain_df["strike_price"] == new_strike]
            prefix = "ce" if old_pos["option_type"] == "CE" else "pe"
            live_new_premium = float(new_row.iloc[0][f"{prefix}_ltp"]) if not new_row.empty else 0.0

            new_premium = st.number_input("New leg premium (₹) — auto-filled from LTP, editable",
                                           min_value=0.0, value=live_new_premium, step=0.5)

            reason = st.text_input("Reason for this roll", placeholder="e.g. Market rallied, PE safe now, collecting extra credit")

            if st.button("Execute Roll", use_container_width=True, type="primary"):
                result = roll_position(
                    old_position_id=int(old_pos["id"]), new_strike=new_strike,
                    new_option_type=old_pos["option_type"], new_transaction=old_pos["transaction"],
                    new_premium=new_premium, new_expiry=new_expiry, close_price=close_price,
                    roll_type=roll_type, reason=reason, quantity=int(old_pos["quantity"]),
                )
                pnl_icon = "🟢" if result["realized_pnl"] >= 0 else "🔴"
                st.success(f"Rolled #{result['old_position_id']} → #{result['new_position_id']}. "
                          f"{pnl_icon} Realized P&L on closed leg: ₹{result['realized_pnl']:,.0f}")
                st.rerun()

# ---------------------------------------------------------------------------
# Adjustment History
# ---------------------------------------------------------------------------
with tab_history:
    summary_df = get_all_lineages_summary()

    if summary_df.empty:
        st.info("No position lineages yet.")
    else:
        st.subheader("📊 Lineage Summary")
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("🔍 View Full Roll Chain")
        root_id = st.number_input("Root position ID (from table above)", min_value=1, step=1)
        if st.button("Show Chain"):
            chain = get_lineage_history(int(root_id))
            if chain.empty:
                st.warning("No lineage found for that ID.")
            else:
                display_cols = ["id", "status", "option_type", "strike", "transaction",
                                 "entry_premium", "roll_type", "roll_reason", "realized_pnl", "created_at"]
                available = [c for c in display_cols if c in chain.columns]
                st.dataframe(chain[available], use_container_width=True, hide_index=True)

st.caption("PMP Trading Suite · Module 6 · Personal adjustment tracking — data stored in Neon Postgres. "
           "Not investment advice.")
