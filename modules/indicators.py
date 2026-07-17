"""
indicators.py
Core indicator calculations for the PMP Trading Suite.
Implements: VWAP, CPR, PDH/PDL, Gap Classification, Regime Detection (Module 1 & 4).
All functions take/return pandas objects and are data-source agnostic.
"""

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# VWAP
# ---------------------------------------------------------------------------
def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Session VWAP (resets each trading day).
    df must have columns: ['datetime','high','low','close','volume']
    Returns a Series aligned to df.index.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["datetime"]).dt.date
    typical_price = (df["high"] + df["low"] + df["close"]) / 3

    vwap = pd.Series(index=df.index, dtype=float)
    for _, day_idx in df.groupby("date").groups.items():
        day_slice = df.loc[day_idx]
        tp = typical_price.loc[day_idx]
        cum_vol = day_slice["volume"].cumsum().astype(float)
        cum_vol_price = (tp * day_slice["volume"]).cumsum().astype(float)

        # np.where evaluates BOTH branches eagerly, so cum_vol_price/cum_vol still runs
        # even on rows where cum_vol is 0 (e.g. the very first tick of an illiquid
        # instrument before any volume prints) -- that raised ZeroDivisionError in
        # production. Replacing 0 with NaN first makes the division always safe
        # (NaN result, no exception), then fillna() supplies the typical-price fallback.
        safe_cum_vol = cum_vol.replace(0, np.nan)
        computed = cum_vol_price / safe_cum_vol
        vwap.loc[day_idx] = computed.fillna(tp).values

    return vwap


def vwap_deviation_bands(df: pd.DataFrame, vwap: pd.Series, mult: float = 1.5) -> pd.DataFrame:
    """
    Standard-deviation bands around VWAP for the current session,
    used for Range-Day VWAP-fade entries (Module 4.1).
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["datetime"]).dt.date
    typical_price = (df["high"] + df["low"] + df["close"]) / 3

    upper = pd.Series(index=df.index, dtype=float)
    lower = pd.Series(index=df.index, dtype=float)

    for _, day_idx in df.groupby("date").groups.items():
        tp = typical_price.loc[day_idx]
        v = vwap.loc[day_idx]
        # rolling population std of (tp - vwap) within the session so far
        diffs_sq = (tp - v) ** 2
        cum_var = diffs_sq.expanding().mean()
        std = np.sqrt(cum_var)
        upper.loc[day_idx] = v + mult * std
        lower.loc[day_idx] = v - mult * std

    return pd.DataFrame({"vwap_upper": upper, "vwap_lower": lower})


# ---------------------------------------------------------------------------
# CPR (Central Pivot Range)  -- Module 4.2
# ---------------------------------------------------------------------------
def calculate_cpr(prev_high: float, prev_low: float, prev_close: float) -> dict:
    """
    Standard CPR formula using previous day's H, L, C.
    Returns pivot, bc (bottom central), tc (top central), and width_pct.
    """
    pivot = (prev_high + prev_low + prev_close) / 3
    bc = (prev_high + prev_low) / 2
    tc = (pivot - bc) + pivot

    # normalize so tc is always the higher value
    top = max(tc, bc)
    bottom = min(tc, bc)

    prev_range = prev_high - prev_low
    width_pct = ((top - bottom) / prev_range * 100) if prev_range > 0 else 0.0

    return {
        "pivot": round(pivot, 2),
        "tc": round(top, 2),
        "bc": round(bottom, 2),
        "width_pct": round(width_pct, 2),
        "is_narrow": width_pct < 15.0,   # Module 4.2 rule: narrow CPR -> trend day probability
    }


# ---------------------------------------------------------------------------
# PDH / PDL / Weekly High-Low -- Module 4.3 / 4.4
# ---------------------------------------------------------------------------
def prev_day_high_low(daily_df: pd.DataFrame, current_date) -> dict:
    """
    daily_df: one row per trading day with columns ['date','high','low','close','open']
    current_date: the date for which we want the *previous* day's H/L
    """
    daily_df = daily_df.copy()
    daily_df["date"] = pd.to_datetime(daily_df["date"])
    current_date = pd.Timestamp(current_date)

    daily_df = daily_df.sort_values("date")
    prior = daily_df[daily_df["date"] < current_date]
    if prior.empty:
        return {"pdh": None, "pdl": None, "pdc": None}
    last_row = prior.iloc[-1]
    return {"pdh": last_row["high"], "pdl": last_row["low"], "pdc": last_row["close"]}


def weekly_high_low(daily_df: pd.DataFrame, current_date) -> dict:
    daily_df = daily_df.copy()
    daily_df["date"] = pd.to_datetime(daily_df["date"])
    current_date = pd.to_datetime(current_date)
    week_start = current_date - pd.Timedelta(days=current_date.weekday())
    prior_week = daily_df[(daily_df["date"] >= week_start - pd.Timedelta(days=7))
                           & (daily_df["date"] < week_start)]
    if prior_week.empty:
        return {"wh": None, "wl": None}
    return {"wh": prior_week["high"].max(), "wl": prior_week["low"].min()}


# ---------------------------------------------------------------------------
# Gap Classification -- Module 1.3
# ---------------------------------------------------------------------------
def classify_gap(today_open: float, prev_close: float) -> dict:
    gap_pct = (today_open - prev_close) / prev_close * 100

    if abs(gap_pct) < 0.2:
        category = "Flat open"
    elif abs(gap_pct) < 0.5:
        category = "Moderate gap"
    elif abs(gap_pct) < 1.0:
        category = "Big gap"
    else:
        category = "Extreme gap"

    direction = "Gap Up" if gap_pct > 0 else ("Gap Down" if gap_pct < 0 else "Flat")

    return {
        "gap_pct": round(gap_pct, 2),
        "category": category,
        "direction": direction,
    }


# ---------------------------------------------------------------------------
# Initial Balance (first 60 min range) -- used in Regime Detection
# ---------------------------------------------------------------------------
def initial_balance(df: pd.DataFrame, session_date, ib_minutes: int = 60) -> dict:
    """
    df: intraday candles for a single session with ['datetime','high','low']
    Returns the IB high/low computed from the first `ib_minutes` of trade.
    """
    day_df = df[pd.to_datetime(df["datetime"]).dt.date == session_date].copy()
    if day_df.empty:
        return {"ib_high": None, "ib_low": None}

    day_df["datetime"] = pd.to_datetime(day_df["datetime"])
    session_start = day_df["datetime"].min()
    cutoff = session_start + pd.Timedelta(minutes=ib_minutes)
    ib_slice = day_df[day_df["datetime"] <= cutoff]

    return {
        "ib_high": ib_slice["high"].max(),
        "ib_low": ib_slice["low"].min(),
    }


def volume_confirmation(intraday_df: pd.DataFrame, lookback: int = 20, multiplier: float = 1.5) -> dict:
    """
    Module 4.5: breakout candle volume should exceed `multiplier`x the average
    of the preceding `lookback` candles to be considered confirmed (not a low-volume trap).
    """
    df = intraday_df.sort_values("datetime").reset_index(drop=True)
    if len(df) < lookback + 1:
        return {"confirmed": None, "latest_volume": None, "avg_volume": None, "ratio": None}

    avg_vol = df["volume"].iloc[-(lookback + 1):-1].mean()
    latest_vol = df["volume"].iloc[-1]
    ratio = (latest_vol / avg_vol) if avg_vol > 0 else None
    confirmed = ratio is not None and ratio >= multiplier

    return {
        "confirmed": confirmed,
        "latest_volume": latest_vol,
        "avg_volume": round(avg_vol, 0),
        "ratio": round(ratio, 2) if ratio is not None else None,
    }


# ---------------------------------------------------------------------------
# Regime Detection -- Module 1.1 / 1.2 (signal counting engine)
# ---------------------------------------------------------------------------
def detect_regime(day_df: pd.DataFrame, vwap: pd.Series, ib: dict, cpr: dict) -> dict:
    """
    Counts bullish / bearish / range signals per Module 1 rules and returns
    a verdict: 'Trend Day (Bullish)', 'Trend Day (Bearish)', 'Range Day', or 'Unclear'.

    day_df: intraday candles for today so far, columns
            ['datetime','open','high','low','close','volume']
    vwap:   VWAP series aligned to day_df.index
    ib:     dict from initial_balance()
    cpr:    dict from calculate_cpr()
    """
    if day_df.empty or len(day_df) < 4:
        return {"verdict": "Unclear", "bullish_signals": [], "bearish_signals": [], "range_signals": []}

    day_open = day_df.iloc[0]["open"]
    day_low_so_far = day_df["low"].min()
    day_high_so_far = day_df["high"].max()
    last_close = day_df.iloc[-1]["close"]
    last_vwap = vwap.iloc[-1]

    bullish_signals = []
    bearish_signals = []
    range_signals = []

    # 1. Open = Low / Open = High test (within small tolerance)
    tolerance = (day_high_so_far - day_low_so_far) * 0.05 if day_high_so_far > day_low_so_far else 0
    if abs(day_open - day_low_so_far) <= tolerance:
        bullish_signals.append("Open ≈ Low of day (no breakdown below open)")
    if abs(day_open - day_high_so_far) <= tolerance:
        bearish_signals.append("Open ≈ High of day (no breakup above open)")

    # 2. Price vs VWAP — one-sided session
    above_vwap_pct = (day_df["close"] > vwap.values).mean()
    below_vwap_pct = (day_df["close"] < vwap.values).mean()
    if above_vwap_pct >= 0.85:
        bullish_signals.append(f"Price stayed above VWAP {above_vwap_pct*100:.0f}% of session")
    elif below_vwap_pct >= 0.85:
        bearish_signals.append(f"Price stayed below VWAP {below_vwap_pct*100:.0f}% of session")
    else:
        range_signals.append("Price chopping around VWAP")

    # 3. IB extension
    if ib.get("ib_high") is not None:
        if last_close > ib["ib_high"]:
            bullish_signals.append("Price extended above Initial Balance high")
        elif last_close < ib["ib_low"]:
            bearish_signals.append("Price extended below Initial Balance low")
        else:
            range_signals.append("Price still inside Initial Balance range")

    # 4. CPR width
    if cpr.get("is_narrow"):
        bullish_signals.append("Narrow CPR (trend-day bias)") if last_close >= cpr["pivot"] else None
        bearish_signals.append("Narrow CPR (trend-day bias)") if last_close < cpr["pivot"] else None
    else:
        range_signals.append("Wide CPR (sideways bias)")

    # 5. VWAP chop count (crosses)
    crosses = (np.sign(day_df["close"].values - vwap.values)[:-1] !=
               np.sign(day_df["close"].values - vwap.values)[1:]).sum()
    if crosses >= 3:
        range_signals.append(f"VWAP crossed {crosses} times — no clear direction")

    # Verdict
    bull_count = len(bullish_signals)
    bear_count = len(bearish_signals)
    range_count = len(range_signals)

    if bull_count >= 3 and bull_count > bear_count and bull_count > range_count:
        verdict = "Trend Day (Bullish)"
    elif bear_count >= 3 and bear_count > bull_count and bear_count > range_count:
        verdict = "Trend Day (Bearish)"
    elif range_count >= 2 and range_count >= bull_count and range_count >= bear_count:
        verdict = "Range Day"
    else:
        verdict = "Unclear"

    return {
        "verdict": verdict,
        "bullish_signals": bullish_signals,
        "bearish_signals": bearish_signals,
        "range_signals": range_signals,
    }
