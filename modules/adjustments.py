"""
adjustments.py
Module 6 (Adjustment Techniques): Roll Up / Roll Down / Roll Forward tracking.

Every roll CLOSES the old leg (records realized P&L) and OPENS a new leg linked
to it via parent_id, so the full adjustment history of a position is a lineage
chain, not a set of disconnected rows.
"""

import pandas as pd
import psycopg2.extras
from datetime import date, datetime
from modules.db import get_connection

MAX_ADJUSTMENTS_PER_POSITION = 2  # Module 6.4 rule


def get_open_positions() -> pd.DataFrame:
    """Thin wrapper so this module doesn't need to import from greeks.py (avoids
    a circular-ish dependency feel, keeps Module 6 self-contained)."""
    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM greek_positions WHERE status = 'OPEN' ORDER BY created_at DESC")
        rows = cur.fetchall()
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        for col in ("strike", "entry_premium", "realized_pnl"):
            if col in df.columns:
                df[col] = df[col].astype(float)
        if "quantity" in df.columns:
            df["quantity"] = df["quantity"].astype(int)
    return df


def check_roll_eligibility(position: dict) -> dict:
    """
    Module 6.4: max 2 adjustments per position lineage.
    Module 6.1: max 1 roll per day (whipsaw guard) -- checked against this leg's own created_at.
    Returns {'eligible': bool, 'warnings': [...]}
    """
    warnings = []
    eligible = True

    if position["roll_count"] >= MAX_ADJUSTMENTS_PER_POSITION:
        eligible = False
        warnings.append(
            f"🛑 This position lineage already has {position['roll_count']} adjustment(s) "
            f"— Module 6.4 limit is {MAX_ADJUSTMENTS_PER_POSITION}. Regime likely changed — "
            f"exit and redeploy fresh instead of rolling again."
        )

    created = position.get("created_at")
    if created is not None:
        created_date = created.date() if hasattr(created, "date") else created
        if created_date == date.today():
            warnings.append(
                "⚠️ This leg was opened/rolled TODAY already. Module 6.1: max one roll per "
                "position per day — rolling again now risks a whipsaw (market reverses right "
                "after you roll, hitting both sides)."
            )

    return {"eligible": eligible, "warnings": warnings}


def roll_position(old_position_id: int, new_strike: float, new_option_type: str,
                   new_transaction: str, new_premium: float, new_expiry, close_price: float,
                   roll_type: str, reason: str, quantity: int = None) -> dict:
    """
    Closes the old leg (records realized P&L) and opens a new leg linked via parent_id.
    roll_type: 'Roll Up' | 'Roll Down' | 'Roll Forward'
    """
    conn = get_connection()

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM greek_positions WHERE id = %s", (old_position_id,))
        old_pos = cur.fetchone()

    if not old_pos:
        raise ValueError(f"Position {old_position_id} not found.")
    if old_pos["status"] != "OPEN":
        raise ValueError(f"Position {old_position_id} is already {old_pos['status']}, cannot roll.")

    qty = quantity if quantity is not None else old_pos["quantity"]

    # Realized P&L on the closed leg
    entry_premium = float(old_pos["entry_premium"]) if old_pos["entry_premium"] is not None else 0.0
    if old_pos["transaction"] == "SELL":
        realized_pnl = (entry_premium - close_price) * qty
    else:
        realized_pnl = (close_price - entry_premium) * qty

    with conn.cursor() as cur:
        # Close old leg
        cur.execute("""
            UPDATE greek_positions
            SET status = 'CLOSED', closed_at = %s, realized_pnl = %s
            WHERE id = %s
        """, (datetime.now(), realized_pnl, old_position_id))

        # Open new leg, linked to the same lineage
        cur.execute("""
            INSERT INTO greek_positions
                (symbol, strike, option_type, transaction, quantity, entry_premium, expiry,
                 status, parent_id, roll_count, roll_type, roll_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'OPEN', %s, %s, %s, %s)
            RETURNING id
        """, (old_pos["symbol"], new_strike, new_option_type, new_transaction, qty, new_premium,
              new_expiry, old_position_id, old_pos["roll_count"] + 1, roll_type, reason))
        new_id = cur.fetchone()[0]

    return {"old_position_id": old_position_id, "new_position_id": new_id, "realized_pnl": round(realized_pnl, 2)}


def get_lineage_history(any_position_id: int) -> pd.DataFrame:
    """
    Walks the parent_id chain (both directions) to reconstruct the full
    roll history of a position, oldest first.
    """
    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM greek_positions WHERE id = %s", (any_position_id,))
        current = cur.fetchone()
        if not current:
            return pd.DataFrame()

        # walk back to the root (oldest ancestor)
        root = current
        while root["parent_id"] is not None:
            cur.execute("SELECT * FROM greek_positions WHERE id = %s", (root["parent_id"],))
            parent = cur.fetchone()
            if not parent:
                break
            root = parent

        # walk forward from root collecting the whole chain
        chain = [root]
        cur.execute("SELECT * FROM greek_positions WHERE parent_id = %s", (root["id"],))
        child = cur.fetchone()
        while child:
            chain.append(child)
            cur.execute("SELECT * FROM greek_positions WHERE parent_id = %s", (child["id"],))
            child = cur.fetchone()

    df = pd.DataFrame(chain)
    if not df.empty:
        for col in ("strike", "entry_premium", "realized_pnl"):
            if col in df.columns:
                df[col] = df[col].astype(float)
    return df


def get_all_lineages_summary() -> pd.DataFrame:
    """One row per position lineage (root positions), with total realized P&L
    across all rolls in that lineage plus current open-leg status."""
    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM greek_positions WHERE parent_id IS NULL ORDER BY created_at DESC")
        roots = cur.fetchall()

    summaries = []
    for root in roots:
        lineage = get_lineage_history(root["id"])
        if lineage.empty:
            continue
        total_realized = lineage[lineage["status"] == "CLOSED"]["realized_pnl"].sum()
        current_leg = lineage[lineage["status"] == "OPEN"]
        summaries.append({
            "root_id": root["id"],
            "symbol": root["symbol"],
            "total_rolls": len(lineage) - 1,
            "total_realized_pnl": round(float(total_realized), 2),
            "current_status": "OPEN" if not current_leg.empty else "FULLY CLOSED",
            "current_leg": f"{current_leg.iloc[0]['option_type']} {current_leg.iloc[0]['strike']:.0f}"
                           if not current_leg.empty else "—",
        })
    return pd.DataFrame(summaries)
