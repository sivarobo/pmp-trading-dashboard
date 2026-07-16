"""
risk.py
Module 7 (Professional Risk Management) + Module 8 (Daily SOP checklist) logic.
"""

import json
import pandas as pd
from datetime import date
from modules.db import get_connection


# ---------------------------------------------------------------------------
# Risk settings (single-row config table)
# ---------------------------------------------------------------------------
def get_risk_settings() -> dict:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT capital, max_daily_loss_pct, max_weekly_loss_pct, max_monthly_loss_pct,
                   max_deployment_pct, risk_per_trade_pct
            FROM risk_settings WHERE id = 1
        """)
        row = cur.fetchone()
    if not row:
        return {}
    keys = ["capital", "max_daily_loss_pct", "max_weekly_loss_pct", "max_monthly_loss_pct",
            "max_deployment_pct", "risk_per_trade_pct"]
    return dict(zip(keys, [float(v) for v in row]))


def update_risk_settings(settings: dict):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE risk_settings SET
                capital = %(capital)s,
                max_daily_loss_pct = %(max_daily_loss_pct)s,
                max_weekly_loss_pct = %(max_weekly_loss_pct)s,
                max_monthly_loss_pct = %(max_monthly_loss_pct)s,
                max_deployment_pct = %(max_deployment_pct)s,
                risk_per_trade_pct = %(risk_per_trade_pct)s,
                updated_at = NOW()
            WHERE id = 1
        """, settings)


# ---------------------------------------------------------------------------
# Position sizing calculator -- Module 7.2
# ---------------------------------------------------------------------------
def calculate_position_size(capital: float, risk_pct: float, entry_price: float,
                             stop_loss_price: float, lot_size: int = 1) -> dict:
    """
    Returns max lots/quantity such that a stop-loss hit loses no more than
    `risk_pct`% of capital.
    """
    max_risk_amount = capital * (risk_pct / 100)
    per_unit_risk = abs(entry_price - stop_loss_price)

    if per_unit_risk <= 0:
        return {"max_risk_amount": max_risk_amount, "per_unit_risk": 0,
                "max_quantity": 0, "max_lots": 0, "actual_risk_amount": 0}

    max_quantity = int(max_risk_amount / per_unit_risk)
    max_lots = max_quantity // lot_size if lot_size > 0 else 0
    actual_quantity = max_lots * lot_size
    actual_risk_amount = actual_quantity * per_unit_risk

    return {
        "max_risk_amount": round(max_risk_amount, 2),
        "per_unit_risk": round(per_unit_risk, 2),
        "max_quantity": max_quantity,
        "max_lots": max_lots,
        "actual_quantity": actual_quantity,
        "actual_risk_amount": round(actual_risk_amount, 2),
    }


# ---------------------------------------------------------------------------
# Drawdown tracking -- Module 7.3 (reads from journal P&L)
# ---------------------------------------------------------------------------
def compute_drawdown(journal_df: pd.DataFrame, capital: float) -> dict:
    if journal_df.empty or capital <= 0:
        return {"daily_pnl_pct": 0, "weekly_pnl_pct": 0, "monthly_pnl_pct": 0}

    df = journal_df.copy()
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce").fillna(0)

    today = pd.Timestamp.now().normalize()
    week_start = today - pd.Timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    daily_pnl = df[df["entry_date"] == today]["pnl"].sum()
    weekly_pnl = df[df["entry_date"] >= week_start]["pnl"].sum()
    monthly_pnl = df[df["entry_date"] >= month_start]["pnl"].sum()

    return {
        "daily_pnl": round(daily_pnl, 2),
        "weekly_pnl": round(weekly_pnl, 2),
        "monthly_pnl": round(monthly_pnl, 2),
        "daily_pnl_pct": round(daily_pnl / capital * 100, 2),
        "weekly_pnl_pct": round(weekly_pnl / capital * 100, 2),
        "monthly_pnl_pct": round(monthly_pnl / capital * 100, 2),
    }


def check_drawdown_limits(drawdown: dict, settings: dict) -> list:
    """Module 7.3 circuit-breaker checks. Returns a list of (level, message) alerts."""
    alerts = []
    if drawdown["daily_pnl_pct"] <= -settings.get("max_daily_loss_pct", 1.5):
        alerts.append(("danger", f"Daily loss limit hit ({drawdown['daily_pnl_pct']}%) "
                                   f"— Module 7.3 rule: stop trading for today."))
    if drawdown["weekly_pnl_pct"] <= -settings.get("max_weekly_loss_pct", 3.0):
        alerts.append(("danger", f"Weekly loss limit hit ({drawdown['weekly_pnl_pct']}%) "
                                   f"— no new positions this week."))
    if drawdown["monthly_pnl_pct"] <= -settings.get("max_monthly_loss_pct", 5.0):
        alerts.append(("danger", f"Monthly loss limit hit ({drawdown['monthly_pnl_pct']}%) "
                                   f"— full stop, review strategy before resuming."))
    return alerts


# ---------------------------------------------------------------------------
# Daily SOP Checklist -- Module 8
# ---------------------------------------------------------------------------
PREMARKET_ITEMS = [
    "Global cues checked (US close, GIFT Nifty, Asian markets, crude, USDINR)",
    "Event calendar checked (RBI/Fed/data/results today?)",
    "India VIX level + yesterday's IV trend noted",
    "Levels marked (PDH, PDL, CPR, weekly open, major OI strikes)",
    "Reviewed open positions from yesterday",
    "Today's plan written (gap up / flat / gap down scenarios)",
]

OPEN_RULES_ITEMS = [
    "No trades in first 15 minutes (observation only)",
    "Regime hypothesis formed by 10:00 AM",
]

EOD_ITEMS = [
    "All trades logged in journal",
    "Regime call reviewed (was it correct?)",
    "SOP violations checked",
    "Overnight risk assessed",
]


def get_checklist_state(check_date: date) -> dict:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT items FROM daily_checklist WHERE check_date = %s", (check_date,))
        row = cur.fetchone()
    return row[0] if row else {}


def save_checklist_state(check_date: date, items: dict):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO daily_checklist (check_date, items, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (check_date) DO UPDATE SET items = %s, updated_at = NOW()
        """, (check_date, json.dumps(items), json.dumps(items)))


def get_checklist_streak() -> int:
    """Consecutive days (ending today or the most recent day) with 100% checklist completion."""
    conn = get_connection()
    total_items = len(PREMARKET_ITEMS) + len(OPEN_RULES_ITEMS) + len(EOD_ITEMS)
    with conn.cursor() as cur:
        cur.execute("SELECT check_date, items FROM daily_checklist ORDER BY check_date DESC LIMIT 60")
        rows = cur.fetchall()

    streak = 0
    for _, items in rows:
        checked = sum(1 for v in items.values() if v) if items else 0
        if checked >= total_items:
            streak += 1
        else:
            break
    return streak
