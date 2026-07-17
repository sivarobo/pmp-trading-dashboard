"""
strategy.py
Module 5 (Hedged Option Selling): payoff calculation for defined-risk spreads.
Same-expiry structures only in this version -- Calendar/Diagonal (different
expiries) are a natural next addition once multi-expiry chain fetching is wired in.
"""

import numpy as np


# ---------------------------------------------------------------------------
# Strategy templates -- leg offsets are in "number of strikes away from ATM"
# ---------------------------------------------------------------------------
STRATEGY_TEMPLATES = {
    "Bull Put Spread": {
        "description": "Sell OTM PE + Buy further OTM PE. Bullish/neutral, defined risk, net credit.",
        "legs": [
            {"offset": -2, "type": "PE", "txn": "SELL"},
            {"offset": -4, "type": "PE", "txn": "BUY"},
        ],
    },
    "Bear Call Spread": {
        "description": "Sell OTM CE + Buy further OTM CE. Bearish/neutral, defined risk, net credit.",
        "legs": [
            {"offset": 2, "type": "CE", "txn": "SELL"},
            {"offset": 4, "type": "CE", "txn": "BUY"},
        ],
    },
    "Iron Condor": {
        "description": "Bull Put Spread + Bear Call Spread combined. Range-bound, defined risk both sides.",
        "legs": [
            {"offset": -2, "type": "PE", "txn": "SELL"},
            {"offset": -4, "type": "PE", "txn": "BUY"},
            {"offset": 2, "type": "CE", "txn": "SELL"},
            {"offset": 4, "type": "CE", "txn": "BUY"},
        ],
    },
    "Broken Wing Butterfly (Bullish, Puts)": {
        "description": "Buy 1 near ITM/ATM PE + Sell 2 ATM-ish PE + Buy 1 further OTM PE (unequal wings). "
                        "Directional bias with defined risk, often net credit.",
        "legs": [
            {"offset": -1, "type": "PE", "txn": "BUY"},
            {"offset": -3, "type": "PE", "txn": "SELL", "qty_multiplier": 2},
            {"offset": -6, "type": "PE", "txn": "BUY"},
        ],
    },
}


def build_legs_from_template(template_name: str, strikes: list, atm_index: int) -> list:
    """
    Resolves a template's relative offsets into actual strikes from the live chain's
    sorted strike list, given the ATM strike's index in that list.
    """
    template = STRATEGY_TEMPLATES[template_name]
    return _resolve_offsets(template["legs"], strikes, atm_index)


def build_scaled_legs(template_name: str, strikes: list, atm_index: int, wing_width: int) -> list:
    """
    Same as build_legs_from_template but scales every leg's offset by wing_width first,
    without mutating the shared STRATEGY_TEMPLATES dict (safe for concurrent sessions).
    """
    template = STRATEGY_TEMPLATES[template_name]
    scaled_leg_specs = [{**leg, "offset": leg["offset"] * wing_width} for leg in template["legs"]]
    return _resolve_offsets(scaled_leg_specs, strikes, atm_index)


def _resolve_offsets(leg_specs: list, strikes: list, atm_index: int) -> list:
    legs = []
    for leg in leg_specs:
        idx = atm_index + leg["offset"]
        idx = max(0, min(len(strikes) - 1, idx))  # clamp to available strikes
        legs.append({
            "strike": strikes[idx],
            "type": leg["type"],
            "txn": leg["txn"],
            "qty_multiplier": leg.get("qty_multiplier", 1),
        })
    return legs


# ---------------------------------------------------------------------------
# Payoff calculation
# ---------------------------------------------------------------------------
def leg_payoff_at_expiry(underlying_price: float, strike: float, option_type: str,
                          txn: str, premium: float, qty: int) -> float:
    """P&L for one leg at a given underlying expiry price."""
    if option_type == "CE":
        intrinsic = max(0, underlying_price - strike)
    else:  # PE
        intrinsic = max(0, strike - underlying_price)

    if txn == "BUY":
        return (intrinsic - premium) * qty
    else:  # SELL
        return (premium - intrinsic) * qty


def compute_payoff_curve(legs: list, lot_size: int, price_range: np.ndarray) -> np.ndarray:
    """
    legs: list of dicts with keys strike, type, txn, premium, qty_multiplier
    Returns an array of total P&L aligned to price_range.
    """
    total = np.zeros_like(price_range, dtype=float)
    for leg in legs:
        qty = lot_size * leg.get("qty_multiplier", 1)
        leg_pnl = np.array([
            leg_payoff_at_expiry(p, leg["strike"], leg["type"], leg["txn"], leg["premium"], qty)
            for p in price_range
        ])
        total += leg_pnl
    return total


CALENDAR_DIAGONAL_TEMPLATES = {
    "Calendar Spread": {
        "description": "Sell near-expiry ATM option + Buy far-expiry ATM option (same strike). "
                        "Neutral, benefits from near-leg's faster theta decay. Long vega.",
        "near_offset": 0, "far_offset": 0, "option_type": "CE",
    },
    "Diagonal Spread": {
        "description": "Sell near-expiry OTM CE + Buy far-expiry ITM-ish CE (different strikes, "
                        "different expiries). Poor man's covered call — moderate bullish + income.",
        "near_offset": 2, "far_offset": -2, "option_type": "CE",
    },
}


def build_calendar_diagonal_legs(template_name: str, strikes: list, atm_index: int) -> dict:
    """Resolves a Calendar/Diagonal template into near-leg and far-leg strike specs."""
    template = CALENDAR_DIAGONAL_TEMPLATES[template_name]
    opt_type = template["option_type"]

    near_idx = max(0, min(len(strikes) - 1, atm_index + template["near_offset"]))
    far_idx = max(0, min(len(strikes) - 1, atm_index + template["far_offset"]))

    return {
        "near": {"strike": strikes[near_idx], "type": opt_type, "txn": "SELL"},
        "far": {"strike": strikes[far_idx], "type": opt_type, "txn": "BUY"},
    }


def compute_calendar_diagonal_payoff(near_leg: dict, far_leg: dict, lot_size: int,
                                      spot_price: float, near_days_to_expiry: float,
                                      far_days_to_expiry: float, risk_free_rate: float = 0.065) -> dict:
    """
    Payoff AT THE NEAR LEG'S EXPIRY. The near leg has expired (intrinsic value only);
    the far leg hasn't, so its value is estimated via Black-Scholes using its own IV
    and the remaining time left on it at that point (far_days - near_days).

    IMPORTANT SIMPLIFICATION: assumes the far leg's IV stays constant at today's quoted
    level through to the near-expiry date. Real IV can (and often does) shift, especially
    if there's an event in between -- this is a static-IV approximation, not a forecast.
    """
    from modules.options_pricing import black_scholes_price

    price_range = np.linspace(spot_price * 0.90, spot_price * 1.10, 300)
    time_left_on_far_at_near_expiry = max(0, (far_days_to_expiry - near_days_to_expiry)) / 365

    payoff = np.zeros_like(price_range, dtype=float)
    for i, p in enumerate(price_range):
        # Near leg: expired, intrinsic only, SELL side
        near_intrinsic = max(0, p - near_leg["strike"]) if near_leg["type"] == "CE" else max(0, near_leg["strike"] - p)
        near_pnl = (near_leg["premium"] - near_intrinsic) * lot_size

        # Far leg: still alive, theoretical BS value, BUY side
        far_theo_value = black_scholes_price(
            p, far_leg["strike"], time_left_on_far_at_near_expiry,
            risk_free_rate, far_leg.get("iv", 0.15), far_leg["type"]
        )
        far_pnl = (far_theo_value - far_leg["premium"]) * lot_size

        payoff[i] = near_pnl + far_pnl

    net_premium = (near_leg["premium"] - far_leg["premium"]) * lot_size  # SELL near, BUY far

    return {
        "max_profit": round(float(payoff.max()), 2),
        "max_loss": round(float(payoff.min()), 2),
        "net_premium": round(net_premium, 2),
        "is_credit": net_premium > 0,
        "price_range": price_range,
        "payoff": payoff,
        "note": "Payoff estimated at near-leg expiry using Black-Scholes for the still-alive far "
                "leg, assuming its IV stays at today's level. Real IV can shift.",
    }


def compute_strategy_stats(legs: list, lot_size: int, spot_price: float) -> dict:
    """Max profit, max loss, breakeven(s), and net credit/debit."""
    price_range = np.linspace(spot_price * 0.85, spot_price * 1.15, 500)
    payoff = compute_payoff_curve(legs, lot_size, price_range)

    max_profit = float(payoff.max())
    max_loss = float(payoff.min())

    net_premium = sum(
        (leg["premium"] if leg["txn"] == "SELL" else -leg["premium"]) * lot_size * leg.get("qty_multiplier", 1)
        for leg in legs
    )

    # breakeven(s): where payoff crosses zero
    breakevens = []
    for i in range(len(payoff) - 1):
        if (payoff[i] <= 0 <= payoff[i + 1]) or (payoff[i] >= 0 >= payoff[i + 1]):
            # linear interpolation for a cleaner estimate
            x0, x1 = price_range[i], price_range[i + 1]
            y0, y1 = payoff[i], payoff[i + 1]
            if y1 != y0:
                be = x0 + (0 - y0) * (x1 - x0) / (y1 - y0)
                breakevens.append(round(be, 1))

    return {
        "max_profit": round(max_profit, 2),
        "max_loss": round(max_loss, 2),
        "net_premium": round(net_premium, 2),
        "is_credit": net_premium > 0,
        "breakevens": breakevens,
        "price_range": price_range,
        "payoff": payoff,
    }
