"""
mock_data.py
Synthetic NIFTY-like candle generator so the dashboard is fully testable
offline, before the Zerodha Kite API key is wired in.

Produces plausible 15-min OHLCV data across trading sessions (09:15-15:30 IST),
with randomized gaps and a mix of trend/range-day behaviour so the Regime
Detection engine has something meaningful to classify.
"""

import numpy as np
import pandas as pd


def _session_timestamps(date: pd.Timestamp, interval_minutes: int = 15) -> list:
    start = pd.Timestamp(date.year, date.month, date.day, 9, 15)
    end = pd.Timestamp(date.year, date.month, date.day, 15, 30)
    ts = []
    cur = start
    while cur <= end:
        ts.append(cur)
        cur += pd.Timedelta(minutes=interval_minutes)
    return ts


def generate_mock_intraday(days: int = 3, base_price: float = 25000.0, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    all_rows = []
    prev_close = base_price

    # walk back `days` trading days (skip weekends)
    today = pd.Timestamp.now().normalize()
    trading_days = []
    d = today
    while len(trading_days) < days:
        if d.weekday() < 5:  # Mon-Fri
            trading_days.append(d)
        d -= pd.Timedelta(days=1)
    trading_days = sorted(trading_days)

    for day in trading_days:
        # randomly assign a "regime" to this day for realistic variety
        regime = rng.choice(["trend_up", "trend_down", "range", "gap_trap"], p=[0.25, 0.2, 0.4, 0.15])

        gap_pct = rng.normal(0, 0.35)  # % gap vs prev close
        day_open = prev_close * (1 + gap_pct / 100)

        timestamps = _session_timestamps(day)
        n = len(timestamps)

        prices = [day_open]
        vol_base = rng.integers(80000, 150000)

        for i in range(1, n):
            if regime == "trend_up":
                drift = rng.normal(4.5, 6)
            elif regime == "trend_down":
                drift = rng.normal(-4.5, 6)
            elif regime == "range":
                # mean-revert toward day_open
                drift = (day_open - prices[-1]) * 0.08 + rng.normal(0, 5)
            else:  # gap_trap: strong move first hour, then reversal
                if i < n * 0.3:
                    drift = rng.normal(6 if gap_pct > 0 else -6, 5)
                else:
                    drift = rng.normal(-3 if gap_pct > 0 else 3, 5)
            prices.append(prices[-1] + drift)

        # build OHLC from the walked closes
        rows = []
        for i, ts in enumerate(timestamps):
            c = prices[i]
            o = prices[i - 1] if i > 0 else day_open
            wiggle = abs(rng.normal(4, 3))
            h = max(o, c) + wiggle
            l = min(o, c) - wiggle
            vol = int(vol_base * rng.uniform(0.5, 1.8) * (1.8 if i < 4 else 1.0))
            rows.append({
                "datetime": ts,
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(c, 2),
                "volume": vol,
            })

        all_rows.extend(rows)
        prev_close = rows[-1]["close"]

    return pd.DataFrame(all_rows)


def generate_mock_daily(days: int = 30, base_price: float = 25000.0, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    today = pd.Timestamp.now().normalize()

    trading_days = []
    d = today
    while len(trading_days) < days:
        if d.weekday() < 5:
            trading_days.append(d)
        d -= pd.Timedelta(days=1)
    trading_days = sorted(trading_days)

    rows = []
    price = base_price
    for day in trading_days:
        drift = rng.normal(20, 120)
        o = price
        c = price + drift
        h = max(o, c) + abs(rng.normal(40, 25))
        l = min(o, c) - abs(rng.normal(40, 25))
        vol = int(rng.integers(4_000_000, 9_000_000))
        rows.append({
            "date": day.date(),
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": vol,
        })
        price = c

    return pd.DataFrame(rows)
