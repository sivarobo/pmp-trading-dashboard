"""
journal.py
CRUD + stats for the Trading Journal (Module 9).
"""

import pandas as pd
import psycopg2.extras
from modules.db import get_connection


def add_entry(entry: dict):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO journal_entries
                (entry_date, entry_time, exit_time, instrument, structure, regime_call,
                 entry_reason, planned_sl, planned_target, max_loss, exit_reason, pnl,
                 rule_adherence, rule_violation, mistake_category, lesson,
                 emotional_state_entry, emotional_state_exit, screenshot_note)
            VALUES
                (%(entry_date)s, %(entry_time)s, %(exit_time)s, %(instrument)s, %(structure)s,
                 %(regime_call)s, %(entry_reason)s, %(planned_sl)s, %(planned_target)s,
                 %(max_loss)s, %(exit_reason)s, %(pnl)s, %(rule_adherence)s, %(rule_violation)s,
                 %(mistake_category)s, %(lesson)s, %(emotional_state_entry)s,
                 %(emotional_state_exit)s, %(screenshot_note)s)
        """, entry)


def get_entries(limit: int = 200) -> pd.DataFrame:
    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT * FROM journal_entries
            ORDER BY entry_date DESC, entry_time DESC NULLS LAST
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def delete_entry(entry_id: int):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM journal_entries WHERE id = %s", (entry_id,))


def compute_stats(df: pd.DataFrame) -> dict:
    """Weekly-review metrics per Module 9."""
    if df.empty:
        return {
            "total_trades": 0, "win_rate": None, "avg_win": None, "avg_loss": None,
            "win_loss_ratio": None, "rule_adherence_pct": None, "total_pnl": None,
        }

    total_trades = len(df)
    pnl = pd.to_numeric(df["pnl"], errors="coerce").dropna()

    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    win_rate = (len(wins) / len(pnl) * 100) if len(pnl) > 0 else None
    avg_win = wins.mean() if len(wins) > 0 else None
    avg_loss = losses.mean() if len(losses) > 0 else None
    win_loss_ratio = (avg_win / abs(avg_loss)) if avg_win and avg_loss else None

    adherence = df["rule_adherence"].dropna()
    rule_adherence_pct = (adherence.sum() / len(adherence) * 100) if len(adherence) > 0 else None

    return {
        "total_trades": total_trades,
        "win_rate": round(win_rate, 1) if win_rate is not None else None,
        "avg_win": round(avg_win, 2) if avg_win is not None else None,
        "avg_loss": round(avg_loss, 2) if avg_loss is not None else None,
        "win_loss_ratio": round(win_loss_ratio, 2) if win_loss_ratio is not None else None,
        "rule_adherence_pct": round(rule_adherence_pct, 1) if rule_adherence_pct is not None else None,
        "total_pnl": round(pnl.sum(), 2) if len(pnl) > 0 else None,
    }
