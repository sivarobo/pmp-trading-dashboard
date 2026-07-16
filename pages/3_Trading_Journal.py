"""
PMP Trading Suite — Phase 3: Trading Journal (Module 9)
"""

import streamlit as st
import pandas as pd
from datetime import date, time

from modules.env_setup import init_env
init_env()

from modules.db import init_db
from modules.journal import add_entry, get_entries, delete_entry, compute_stats

st.set_page_config(page_title="Trading Journal — PMP Trading Suite", layout="wide", page_icon="📝")

try:
    init_db()
except Exception as e:
    st.error(f"Database connection failed: {e}")
    st.caption("Set DATABASE_URL (Neon Postgres connection string) in your .env file or "
               "Streamlit Cloud Secrets. See modules/db.py for setup steps.")
    st.stop()

st.sidebar.title("📝 Trading Journal")
st.sidebar.caption("Phase 3 — Module 9 framework")

st.title("📝 Trading Journal")

tab_new, tab_history, tab_stats = st.tabs(["➕ New Entry", "📜 History", "📊 Weekly Review"])

# ---------------------------------------------------------------------------
# New Entry
# ---------------------------------------------------------------------------
with tab_new:
    st.caption("Log every trade — entry reason, exit reason, and lesson learned are the "
               "3 fields that actually build discipline (Module 9).")

    with st.form("journal_entry_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            entry_date = st.date_input("Date", value=date.today())
            entry_time = st.time_input("Entry time", value=time(9, 30))
            instrument = st.text_input("Instrument & Structure", placeholder="e.g. Nifty Iron Condor 24700/24500 PE-25300/25500 CE")
        with col2:
            regime_call = st.selectbox("Regime Call", ["Trend Day (Bullish)", "Trend Day (Bearish)", "Range Day", "Unclear"])
            exit_time = st.time_input("Exit time", value=time(15, 15))
            structure = st.text_input("Strategy type", placeholder="e.g. Bull Put Spread, Directional Buy")
        with col3:
            planned_sl = st.number_input("Planned SL (₹)", value=0.0, step=100.0)
            planned_target = st.number_input("Planned Target (₹)", value=0.0, step=100.0)
            max_loss = st.number_input("Max Loss (₹)", value=0.0, step=100.0)

        entry_reason = st.text_area("Entry reason (confluence factors)", height=70,
                                     placeholder="e.g. PDL sweep + VWAP reclaim + PE writing increase")
        exit_reason = st.selectbox("Exit reason", ["Target hit", "SL hit", "Time stop", "Manual (discretionary)"])

        col4, col5, col6 = st.columns(3)
        with col4:
            pnl = st.number_input("P&L (₹, negative for loss)", value=0.0, step=100.0)
        with col5:
            rule_adherence = st.radio("Followed SOP rules?", ["Yes", "No"], horizontal=True)
        with col6:
            mistake_category = st.selectbox("Mistake category (if any)",
                                             ["None", "Execution error", "Analysis error", "Discipline error"])

        rule_violation = st.text_input("If rules broken, which rule?", placeholder="optional")
        lesson = st.text_area("Lesson learned (one line)", height=60)

        col7, col8 = st.columns(2)
        with col7:
            emo_entry = st.slider("Emotional state at entry (1=fear, 5=calm)", 1, 5, 3)
        with col8:
            emo_exit = st.slider("Emotional state at exit (1=fear, 5=calm)", 1, 5, 3)

        screenshot_note = st.text_input("Screenshot reference (optional)",
                                         placeholder="e.g. filename or note — image upload coming in a later pass")

        submitted = st.form_submit_button("Save Entry", use_container_width=True)

        if submitted:
            if not instrument or not entry_reason:
                st.error("Instrument and Entry reason are required — an entry without a reason isn't a journal entry.")
            else:
                add_entry({
                    "entry_date": entry_date, "entry_time": entry_time, "exit_time": exit_time,
                    "instrument": instrument, "structure": structure, "regime_call": regime_call,
                    "entry_reason": entry_reason, "planned_sl": planned_sl or None,
                    "planned_target": planned_target or None, "max_loss": max_loss or None,
                    "exit_reason": exit_reason, "pnl": pnl,
                    "rule_adherence": (rule_adherence == "Yes"), "rule_violation": rule_violation or None,
                    "mistake_category": mistake_category if mistake_category != "None" else None,
                    "lesson": lesson or None, "emotional_state_entry": emo_entry,
                    "emotional_state_exit": emo_exit, "screenshot_note": screenshot_note or None,
                })
                st.success("Entry saved.")
                st.rerun()

# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------
with tab_history:
    entries_df = get_entries()

    if entries_df.empty:
        st.info("No entries yet — log your first trade in the 'New Entry' tab.")
    else:
        display_cols = ["entry_date", "instrument", "structure", "regime_call", "exit_reason",
                         "pnl", "rule_adherence", "mistake_category", "lesson"]
        available_cols = [c for c in display_cols if c in entries_df.columns]
        st.dataframe(entries_df[available_cols], use_container_width=True, height=450)

        with st.expander("🗑️ Delete an entry"):
            entry_id_to_delete = st.number_input("Entry ID to delete", min_value=1, step=1)
            if st.button("Delete"):
                delete_entry(int(entry_id_to_delete))
                st.success(f"Deleted entry {entry_id_to_delete}.")
                st.rerun()

# ---------------------------------------------------------------------------
# Weekly Review Stats
# ---------------------------------------------------------------------------
with tab_stats:
    entries_df = get_entries()
    stats = compute_stats(entries_df)

    if stats["total_trades"] == 0:
        st.info("No data yet for stats.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Trades", stats["total_trades"])
        c2.metric("Win Rate", f"{stats['win_rate']}%" if stats["win_rate"] is not None else "—")
        c3.metric("Win/Loss Ratio", stats["win_loss_ratio"] if stats["win_loss_ratio"] is not None else "—")
        c4.metric("Total P&L", f"₹{stats['total_pnl']:,.0f}" if stats["total_pnl"] is not None else "—")

        st.markdown("---")
        c5, c6 = st.columns(2)
        c5.metric("Avg Win", f"₹{stats['avg_win']:,.0f}" if stats["avg_win"] is not None else "—")
        c6.metric("Avg Loss", f"₹{stats['avg_loss']:,.0f}" if stats["avg_loss"] is not None else "—")

        st.markdown("---")
        adherence_pct = stats["rule_adherence_pct"]
        if adherence_pct is not None:
            st.metric("Rule Adherence % (the metric that actually matters — Module 9)", f"{adherence_pct}%")
            if adherence_pct < 80:
                st.warning("Rule adherence below 80% — review your SOP checklist discipline before "
                            "worrying about win rate.")
            else:
                st.success("Rule adherence solid. Keep the process consistent.")

        if not entries_df.empty and "mistake_category" in entries_df.columns:
            mistake_counts = entries_df["mistake_category"].dropna().value_counts()
            if not mistake_counts.empty:
                st.markdown("**Most frequent mistake category**")
                st.bar_chart(mistake_counts)

st.caption("PMP Trading Suite · Phase 3 · Personal journal — data stored in your Neon Postgres database.")
