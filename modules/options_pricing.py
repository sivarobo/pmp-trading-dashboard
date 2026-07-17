"""
options_pricing.py
Lightweight Black-Scholes pricer -- needed only for Calendar/Diagonal spreads,
where the far-expiry leg is still "alive" (not expired) at the near leg's
expiry date, so its payoff can't be computed from intrinsic value alone like
same-expiry spreads. This estimates its theoretical remaining value instead.

No scipy dependency -- uses math.erf for the normal CDF.
"""

import math


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def black_scholes_price(spot: float, strike: float, time_to_expiry_years: float,
                         risk_free_rate: float, iv: float, option_type: str) -> float:
    """
    Standard Black-Scholes price. iv is annualized (e.g. 0.15 for 15%).
    Returns 0 if time_to_expiry is effectively zero (use intrinsic value instead in that case).
    """
    if time_to_expiry_years <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        # No time value left -- fall back to intrinsic value
        if option_type == "CE":
            return max(0.0, spot - strike)
        return max(0.0, strike - spot)

    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * iv ** 2) * time_to_expiry_years) / \
         (iv * math.sqrt(time_to_expiry_years))
    d2 = d1 - iv * math.sqrt(time_to_expiry_years)

    if option_type == "CE":
        price = spot * _norm_cdf(d1) - strike * math.exp(-risk_free_rate * time_to_expiry_years) * _norm_cdf(d2)
    else:  # PE
        price = strike * math.exp(-risk_free_rate * time_to_expiry_years) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)

    return max(0.0, price)
