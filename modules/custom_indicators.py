"""
custom_indicators.py
"Pine Script equivalent" for the PMP Trading Suite — but in Python.

The user writes a small Python function body in the dashboard's code editor.
It receives the candle DataFrame as `df` and must assign the final plot series
to a variable named `result` (a pandas Series aligned to df, or a dict of
name -> Series for multi-line indicators).

Example user code (an EMA crossover signal):

    ema_fast = df['close'].ewm(span=9).mean()
    ema_slow = df['close'].ewm(span=21).mean()
    result = {'EMA 9': ema_fast, 'EMA 21': ema_slow}

Available inside user code: df, pd (pandas), np (numpy), and nothing else.

SECURITY NOTE: exec() of user code is inherently powerful. This is acceptable
here ONLY because this is a personal single-user tool where the person writing
the indicator code and the person running the server are the same person (Siva).
Do NOT expose this page to untrusted users / multi-tenant deployments without a
proper sandbox — the __builtins__ restriction below raises the bar but is not a
true security boundary.
"""

import pandas as pd
import numpy as np
import psycopg2.extras
from modules.db import get_connection

# Builtins whitelist -- enough for normal indicator math, nothing file/network/import-y.
_SAFE_BUILTINS = {
    "abs": abs, "min": min, "max": max, "round": round, "len": len,
    "range": range, "sum": sum, "enumerate": enumerate, "zip": zip,
    "float": float, "int": int, "bool": bool, "str": str, "list": list,
    "dict": dict, "tuple": tuple, "set": set, "sorted": sorted,
    "any": any, "all": all, "print": print,
}

FORBIDDEN_TOKENS = ["import ", "__", "open(", "exec(", "eval(", "compile(",
                     "globals(", "locals(", "getattr(", "setattr(", "delattr("]


def validate_code(code: str) -> list:
    """Cheap static screen for obviously dangerous constructs. Returns list of problems."""
    problems = []
    lowered = code.lower()
    for token in FORBIDDEN_TOKENS:
        if token in lowered:
            problems.append(f"Forbidden construct: `{token.strip()}`")
    if "result" not in code:
        problems.append("Code must assign to a variable named `result` "
                         "(a Series, or a dict of name -> Series).")
    return problems


def run_indicator(code: str, df: pd.DataFrame) -> dict:
    """
    Executes user indicator code against a COPY of df.
    Returns {'ok': bool, 'series': {name: pd.Series}, 'error': str|None}
    """
    problems = validate_code(code)
    if problems:
        return {"ok": False, "series": {}, "error": "; ".join(problems)}

    env = {
        "__builtins__": _SAFE_BUILTINS,
        "df": df.copy(),
        "pd": pd,
        "np": np,
    }

    try:
        exec(code, env)  # noqa: S102 -- single-user personal tool, see module docstring
    except Exception as e:
        return {"ok": False, "series": {}, "error": f"{type(e).__name__}: {e}"}

    result = env.get("result")
    if result is None:
        return {"ok": False, "series": {}, "error": "`result` was not set by your code."}

    series_out = {}
    if isinstance(result, pd.Series):
        series_out["Custom"] = result
    elif isinstance(result, dict):
        for name, s in result.items():
            if isinstance(s, pd.Series):
                series_out[str(name)] = s
    else:
        return {"ok": False, "series": {},
                "error": f"`result` must be a pandas Series or dict of Series, got {type(result).__name__}."}

    if not series_out:
        return {"ok": False, "series": {}, "error": "No plottable Series found in `result`."}

    # Align lengths to df
    for name, s in series_out.items():
        if len(s) != len(df):
            return {"ok": False, "series": {},
                    "error": f"Series '{name}' has {len(s)} points but df has {len(df)} rows — "
                             f"they must align."}

    return {"ok": True, "series": series_out, "error": None}


# ---------------------------------------------------------------------------
# Persistence -- save named indicators to Postgres so they survive restarts
# ---------------------------------------------------------------------------
def save_indicator(name: str, code: str):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO custom_indicators (name, code, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (name) DO UPDATE SET code = EXCLUDED.code, updated_at = NOW()
        """, (name, code))


def list_indicators() -> pd.DataFrame:
    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT name, code, updated_at FROM custom_indicators ORDER BY name")
        rows = cur.fetchall()
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def delete_indicator(name: str):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM custom_indicators WHERE name = %s", (name,))


# ---------------------------------------------------------------------------
# Starter templates shown in the editor
# ---------------------------------------------------------------------------
STARTER_TEMPLATES = {
    "EMA Crossover (9/21)": """ema_fast = df['close'].ewm(span=9).mean()
ema_slow = df['close'].ewm(span=21).mean()
result = {'EMA 9': ema_fast, 'EMA 21': ema_slow}""",

    "RSI (14)": """delta = df['close'].diff()
gain = delta.clip(lower=0).rolling(14).mean()
loss = (-delta.clip(upper=0)).rolling(14).mean()
rs = gain / loss.replace(0, np.nan)
rsi = 100 - (100 / (1 + rs))
result = {'RSI 14': rsi.fillna(50)}""",

    "Supertrend-style ATR Bands": """atr = (df['high'] - df['low']).rolling(10).mean()
mid = (df['high'] + df['low']) / 2
result = {'Upper Band': mid + 2*atr, 'Lower Band': mid - 2*atr}""",

    "Bollinger Bands (20, 2)": """ma = df['close'].rolling(20).mean()
std = df['close'].rolling(20).std()
result = {'BB Mid': ma, 'BB Upper': ma + 2*std, 'BB Lower': ma - 2*std}""",
}
