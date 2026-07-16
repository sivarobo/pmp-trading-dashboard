"""
instrument_search.py
Downloads and caches Upstox's complete instrument master file so any
stock (NSE_EQ) or MCX commodity future (Gold/Silver/Crude etc.) can be
searched by name instead of hardcoding instrument keys that go stale
(commodity futures roll to a new expiry contract every month).

Source: https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz
"""

import gzip
import json
import os
import time
from datetime import datetime

import requests

CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", ".instrument_cache.json")
CACHE_MAX_AGE_SECONDS = 24 * 60 * 60  # refresh once a day (commodity contracts roll monthly, this is plenty fresh)

MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"


def _cache_is_fresh() -> bool:
    if not os.path.exists(CACHE_PATH):
        return False
    age = time.time() - os.path.getmtime(CACHE_PATH)
    return age < CACHE_MAX_AGE_SECONDS


def _download_and_cache() -> list:
    resp = requests.get(MASTER_URL, timeout=60)
    resp.raise_for_status()
    raw = gzip.decompress(resp.content)
    data = json.loads(raw)

    with open(CACHE_PATH, "w") as f:
        json.dump(data, f)

    return data


def load_instrument_master(force_refresh: bool = False) -> list:
    """Returns the full list of instrument dicts, using a 24h local cache."""
    if not force_refresh and _cache_is_fresh():
        with open(CACHE_PATH, "r") as f:
            return json.load(f)
    return _download_and_cache()


def search_instruments(query: str, segment: str = None, instrument_type: str = None,
                        limit: int = 15) -> list:
    """
    Case-insensitive search over trading_symbol and name fields.
    segment examples: 'NSE_EQ', 'NSE_INDEX', 'MCX_FO'
    instrument_type examples: 'EQ', 'FUT', 'INDEX'
    Returns a list of matching instrument dicts (trimmed to the useful fields).
    """
    data = load_instrument_master()
    q = query.strip().upper()
    if not q:
        return []

    results = []
    for inst in data:
        if segment and inst.get("segment") != segment:
            continue
        if instrument_type and inst.get("instrument_type") != instrument_type:
            continue

        trading_symbol = (inst.get("trading_symbol") or "").upper()
        name = (inst.get("name") or "").upper()

        if q in trading_symbol or q in name:
            results.append({
                "trading_symbol": inst.get("trading_symbol"),
                "name": inst.get("name"),
                "instrument_key": inst.get("instrument_key"),
                "segment": inst.get("segment"),
                "instrument_type": inst.get("instrument_type"),
                "expiry": inst.get("expiry"),
            })
        if len(results) >= limit * 5:  # collect a bit extra before trimming/sorting
            break

    # For futures/commodities, prefer the nearest (soonest) expiry first
    def sort_key(r):
        return r["expiry"] if r.get("expiry") else "9999-99-99"

    results.sort(key=sort_key)
    return results[:limit]


def get_nearest_mcx_future(commodity_name: str) -> dict:
    """
    Convenience helper for commodities like GOLD / SILVER / CRUDEOIL / NATURALGAS.
    Returns the nearest-expiry MCX futures contract match, or None.
    """
    matches = search_instruments(commodity_name, segment="MCX_FO", instrument_type="FUT", limit=5)
    return matches[0] if matches else None
