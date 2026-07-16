"""
greeks.py
Module 3 (Greeks பயன்பாடு): position tracking + portfolio-level Greeks aggregation,
expiry gamma risk warnings, and delta-neutral adjustment triggers.
"""

import pandas as pd
import psycopg2.extras
from modules.db import get_connection


# ---------------------------------------------------------------------------
# Position CRUD (stored in Postgres so it persists across sessions)
# ---------------------------------------------------------------------------
def add_position(strike: float, option_type: str, transaction: str, quantity: int,
                  entry_premium: float, expiry: str, symbol: str = "NIFTY 50"):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO greek_positions
                (symbol, strike, option_type, transaction, quantity, entry_premium, expiry)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (symbol, strike, option_type, transaction, quantity, entry_premium, expiry))


def get_positions() -> pd.DataFrame:
    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM greek_positions ORDER BY created_at DESC")
        rows = cur.fetchall()
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def delete_position(position_id: int):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM greek_positions WHERE id = %s", (position_id,))


def clear_all_positions():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM greek_positions")


# ---------------------------------------------------------------------------
# Portfolio Greeks aggregation -- Module 3.1 (position delta calc example)
# ---------------------------------------------------------------------------
def compute_portfolio_greeks(positions_df: pd.DataFrame, chain_df: pd.DataFrame) -> dict:
    """
    Looks up each leg's live Greeks from the current option chain snapshot and
    sums them into net portfolio delta / gamma / theta / vega, accounting for
    BUY (+1) vs SELL (-1) sign and quantity.
    """
    if positions_df.empty or chain_df.empty:
        return {"net_delta": 0, "net_gamma": 0, "net_theta": 0, "net_vega": 0, "legs": []}

    net_delta = net_gamma = net_theta = net_vega = 0.0
    legs = []

    for _, pos in positions_df.iterrows():
        strike_row = chain_df[chain_df["strike_price"] == float(pos["strike"])]
        if strike_row.empty:
            continue
        row = strike_row.iloc[0]
        prefix = "ce" if pos["option_type"] == "CE" else "pe"

        leg_delta = row.get(f"{prefix}_delta", 0) or 0
        leg_gamma = row.get(f"{prefix}_gamma", 0) or 0
        leg_theta = row.get(f"{prefix}_theta", 0) or 0
        leg_vega = row.get(f"{prefix}_vega", 0) or 0

        sign = 1 if pos["transaction"] == "BUY" else -1
        qty = pos["quantity"]

        net_delta += sign * qty * leg_delta
        net_gamma += sign * qty * leg_gamma
        net_theta += sign * qty * leg_theta
        net_vega += sign * qty * leg_vega

        legs.append({
            "strike": pos["strike"], "type": pos["option_type"], "transaction": pos["transaction"],
            "qty": qty, "delta": round(sign * qty * leg_delta, 2),
            "theta": round(sign * qty * leg_theta, 2),
        })

    return {
        "net_delta": round(net_delta, 2),
        "net_gamma": round(net_gamma, 5),
        "net_theta": round(net_theta, 2),
        "net_vega": round(net_vega, 2),
        "legs": legs,
    }


# ---------------------------------------------------------------------------
# Expiry Gamma Risk Warning -- Module 3.2
# ---------------------------------------------------------------------------
def gamma_risk_warning(days_to_expiry: int, positions_df: pd.DataFrame, spot_price: float) -> list:
    """
    Module 3.2: gamma accelerates sharply into expiry, especially for short
    ATM/near-ATM legs. Flags positions at elevated risk.
    """
    warnings = []
    if positions_df.empty:
        return warnings

    if days_to_expiry <= 1:
        for _, pos in positions_df.iterrows():
            dist_pct = abs(pos["strike"] - spot_price) / spot_price * 100 if spot_price else 100
            if pos["transaction"] == "SELL" and dist_pct < 2:
                warnings.append(
                    f"⚠️ {pos['option_type']} {pos['strike']:.0f} (SELL, {dist_pct:.1f}% from spot) — "
                    f"expiry day gamma risk. A small move can flip this deep ITM fast. "
                    f"Module 3.2: consider reducing size or hedging."
                )
    elif days_to_expiry <= 3:
        short_near_atm = positions_df[
            (positions_df["transaction"] == "SELL") &
            ((positions_df["strike"] - spot_price).abs() / spot_price * 100 < 3)
        ]
        if not short_near_atm.empty:
            warnings.append(
                f"⚠️ {len(short_near_atm)} short leg(s) within 3% of spot, {days_to_expiry} days to expiry — "
                f"gamma will accelerate. Monitor closely."
            )
    return warnings


# ---------------------------------------------------------------------------
# Delta-Neutral Adjustment Trigger -- Module 3.5 / Module 6.4
# ---------------------------------------------------------------------------
def delta_neutral_check(net_delta: float, net_theta: float, multiplier: float = 1.5) -> dict:
    """
    Module 6.4 rule: adjust when net delta exceeds `multiplier`x the daily theta income.
    """
    if net_theta == 0:
        return {"trigger": False, "message": "No theta income to compare against yet."}

    delta_value_estimate = abs(net_delta)  # rough proxy; theta is in ₹/day already
    threshold = abs(net_theta) * multiplier

    if delta_value_estimate > threshold:
        return {
            "trigger": True,
            "message": f"Net delta ({net_delta}) exceeds {multiplier}x daily theta (₹{net_theta}) — "
                       f"Module 6.4 rule: consider a delta-neutral adjustment (roll untested side or hedge)."
        }
    return {"trigger": False, "message": f"Net delta within {multiplier}x theta threshold — no adjustment needed."}
