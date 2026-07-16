"""
option_chain.py
Module 2 logic: Change in OI, OI Shift, Writing/Covering, Trap detection.
Works on a flattened option-chain DataFrame with columns:
  ['strike_price', 'ce_oi', 'ce_prev_oi', 'ce_ltp', 'ce_close', 'ce_volume',
   'ce_iv', 'ce_delta', 'pe_oi', 'pe_prev_oi', 'pe_ltp', 'pe_close',
   'pe_volume', 'pe_iv', 'pe_delta', 'underlying_spot_price']
"""

import pandas as pd


# ---------------------------------------------------------------------------
# 4-Quadrant Change-in-OI classification -- Module 2.1
# ---------------------------------------------------------------------------
def classify_flow(oi_change: float, price_change: float) -> str:
    """
    Classic OI + Price quadrant, applied at the OPTION level (premium vs its
    own previous close, OI vs previous OI) rather than the underlying.
    """
    if oi_change > 0 and price_change > 0:
        return "Long Buildup"
    if oi_change > 0 and price_change < 0:
        return "Short Buildup"      # i.e. Writing
    if oi_change < 0 and price_change > 0:
        return "Short Covering"
    if oi_change < 0 and price_change < 0:
        return "Long Unwinding"
    return "Neutral"


def annotate_chain(chain_df: pd.DataFrame) -> pd.DataFrame:
    """Adds oi_change, price_change, and flow classification columns for both CE and PE."""
    df = chain_df.copy()

    df["ce_oi_change"] = df["ce_oi"] - df["ce_prev_oi"]
    df["ce_price_change"] = df["ce_ltp"] - df["ce_close"]
    df["ce_flow"] = df.apply(lambda r: classify_flow(r["ce_oi_change"], r["ce_price_change"]), axis=1)

    df["pe_oi_change"] = df["pe_oi"] - df["pe_prev_oi"]
    df["pe_price_change"] = df["pe_ltp"] - df["pe_close"]
    df["pe_flow"] = df.apply(lambda r: classify_flow(r["pe_oi_change"], r["pe_price_change"]), axis=1)

    return df


# ---------------------------------------------------------------------------
# PCR -- Put/Call Ratio
# ---------------------------------------------------------------------------
def compute_pcr(chain_df: pd.DataFrame) -> float:
    total_pe_oi = chain_df["pe_oi"].sum()
    total_ce_oi = chain_df["ce_oi"].sum()
    if total_ce_oi == 0:
        return float("nan")
    return round(total_pe_oi / total_ce_oi, 2)


# ---------------------------------------------------------------------------
# Max Pain
# ---------------------------------------------------------------------------
def compute_max_pain(chain_df: pd.DataFrame) -> float:
    """
    For each candidate expiry strike, sum the total money option writers would
    "lose" (= buyers would gain) if the index expired there. The strike with
    the MINIMUM total payout is the max pain point.
    """
    strikes = chain_df["strike_price"].values
    min_pain = None
    min_pain_strike = None

    for candidate in strikes:
        total_pain = 0.0
        for _, row in chain_df.iterrows():
            k = row["strike_price"]
            # CE writers lose (candidate - k) if candidate > k, per OI unit
            if candidate > k:
                total_pain += (candidate - k) * row["ce_oi"]
            # PE writers lose (k - candidate) if candidate < k, per OI unit
            if candidate < k:
                total_pain += (k - candidate) * row["pe_oi"]
        if min_pain is None or total_pain < min_pain:
            min_pain = total_pain
            min_pain_strike = candidate

    return min_pain_strike


# ---------------------------------------------------------------------------
# Support / Resistance walls -- highest-OI strike each side (Module 2.3)
# ---------------------------------------------------------------------------
def find_walls(chain_df: pd.DataFrame) -> dict:
    ce_wall_row = chain_df.loc[chain_df["ce_oi"].idxmax()]
    pe_wall_row = chain_df.loc[chain_df["pe_oi"].idxmax()]
    return {
        "resistance_strike": float(ce_wall_row["strike_price"]),
        "resistance_oi": float(ce_wall_row["ce_oi"]),
        "support_strike": float(pe_wall_row["strike_price"]),
        "support_oi": float(pe_wall_row["pe_oi"]),
    }


# ---------------------------------------------------------------------------
# OI Shift detection -- Module 2.2 (compares current walls to a prior snapshot)
# ---------------------------------------------------------------------------
def detect_oi_shift(current_walls: dict, previous_walls: dict) -> list:
    """
    previous_walls: dict with the same shape as find_walls()'s return,
    captured from an earlier point in the session (e.g. session_state).
    Returns a list of human-readable shift messages.
    """
    messages = []
    if not previous_walls:
        return messages

    if current_walls["resistance_strike"] != previous_walls["resistance_strike"]:
        direction = "up" if current_walls["resistance_strike"] > previous_walls["resistance_strike"] else "down"
        messages.append(
            f"CE wall (resistance) shifted {direction}: "
            f"{previous_walls['resistance_strike']:.0f} → {current_walls['resistance_strike']:.0f}"
        )

    if current_walls["support_strike"] != previous_walls["support_strike"]:
        direction = "up" if current_walls["support_strike"] > previous_walls["support_strike"] else "down"
        messages.append(
            f"PE wall (support) shifted {direction}: "
            f"{previous_walls['support_strike']:.0f} → {current_walls['support_strike']:.0f}"
        )

    return messages


# ---------------------------------------------------------------------------
# Trap detection heuristic -- Module 2.5
# ---------------------------------------------------------------------------
def detect_trap_signal(chain_df: pd.DataFrame, spot_price: float, atm_range: int = 3) -> list:
    """
    Flags a possible false-breakout trap: if spot price is near/through a
    strike but the option chain shows WRITING (OI increasing, not unwinding)
    on the side that should be giving way, the move is more likely to fail.
    """
    df = annotate_chain(chain_df)
    df["dist_from_spot"] = (df["strike_price"] - spot_price).abs()
    nearby = df.nsmallest(atm_range * 2, "dist_from_spot")

    alerts = []
    for _, row in nearby.iterrows():
        strike = row["strike_price"]
        if strike >= spot_price and row["ce_flow"] == "Short Buildup":
            alerts.append(
                f"⚠️ Spot near {strike:.0f} CE — writers ADDING (Short Buildup), "
                f"not unwinding. Upside break through this strike looks trap-prone."
            )
        if strike <= spot_price and row["pe_flow"] == "Short Buildup":
            alerts.append(
                f"⚠️ Spot near {strike:.0f} PE — writers ADDING (Short Buildup), "
                f"not unwinding. Downside break through this strike looks trap-prone."
            )
    return alerts
