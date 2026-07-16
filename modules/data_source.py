"""
data_source.py
Data-source abstraction so the rest of the app never cares WHERE candles come from.

Today   : MockDataSource (synthetic data, works offline, for building/testing UI)
Tomorrow: KiteDataSource (Zerodha Kite Connect) -- stub included below, ready to
          fill in the moment the API key arrives. No other file needs to change.

Usage in app.py:
    from modules.data_source import get_data_source
    ds = get_data_source()          # reads DATA_SOURCE env var: "mock" | "kite"
    candles = ds.get_intraday_candles("NIFTY 50", interval="15minute", days=3)
    daily   = ds.get_daily_candles("NIFTY 50", days=10)
"""

import os
import pandas as pd
from abc import ABC, abstractmethod

from modules.mock_data import generate_mock_intraday, generate_mock_daily, generate_mock_option_chain


class BaseDataSource(ABC):
    @abstractmethod
    def get_intraday_candles(self, symbol: str, interval: str = "15minute", days: int = 3) -> pd.DataFrame:
        """Returns columns: ['datetime','open','high','low','close','volume']"""
        ...

    @abstractmethod
    def get_daily_candles(self, symbol: str, days: int = 30) -> pd.DataFrame:
        """Returns columns: ['date','open','high','low','close','volume']"""
        ...

    @abstractmethod
    def get_ltp(self, symbol: str) -> float:
        """Last traded price."""
        ...

    @abstractmethod
    def get_option_chain(self, symbol: str, expiry_date: str = None) -> pd.DataFrame:
        """
        Returns a flattened option chain DataFrame with columns:
        ['strike_price','underlying_spot_price',
         'ce_oi','ce_prev_oi','ce_ltp','ce_close','ce_volume','ce_iv','ce_delta',
         'pe_oi','pe_prev_oi','pe_ltp','pe_close','pe_volume','pe_iv','pe_delta']
        """
        ...


# ---------------------------------------------------------------------------
# MOCK DATA SOURCE  (works fully offline — use this until Kite key arrives)
# ---------------------------------------------------------------------------
class MockDataSource(BaseDataSource):
    def get_intraday_candles(self, symbol: str, interval: str = "15minute", days: int = 3) -> pd.DataFrame:
        return generate_mock_intraday(days=days)

    def get_daily_candles(self, symbol: str, days: int = 30) -> pd.DataFrame:
        return generate_mock_daily(days=days)

    def get_ltp(self, symbol: str) -> float:
        intraday = self.get_intraday_candles(symbol, days=1)
        return float(intraday.iloc[-1]["close"])

    def get_option_chain(self, symbol: str, expiry_date: str = None) -> pd.DataFrame:
        spot = self.get_ltp(symbol)
        return generate_mock_option_chain(spot_price=spot)


# ---------------------------------------------------------------------------
# UPSTOX DATA SOURCE  (free tier — recommended default)
# ---------------------------------------------------------------------------
class UpstoxDataSource(BaseDataSource):
    """
    Setup steps:
      1. Open a free Upstox account (zero-balance is fine — this is for
         market-data access only, no trades placed from here).
      2. Create an app at https://developer.upstox.com to get API key + secret.
      3. Complete the daily OAuth login flow to get an access token (Upstox
         tokens expire daily, same as Kite — a login helper script can be
         added when you reach this step).
      4. Set env vars: UPSTOX_ACCESS_TOKEN
      5. Find the correct instrument_key for your symbol:
         - Nifty 50 index is typically "NSE_INDEX|Nifty 50"
         - Bank Nifty is typically "NSE_INDEX|Nifty Bank"
         ALWAYS verify against Upstox's published instrument master CSV
         (https://assets.upstox.com/market-quote/instruments/exchange/NSE.csv.gz)
         since exact keys can change — do not hardcode blindly.

    Uses Upstox Historical Candle Data V3 API.
    """

    BASE_URL = "https://api.upstox.com/v3/historical-candle"

    # symbol -> Upstox instrument_key mapping. Verify/update from the
    # instrument master CSV before going live.
    SYMBOL_MAP = {
        "NIFTY 50": "NSE_INDEX|Nifty 50",
        "NIFTY BANK": "NSE_INDEX|Nifty Bank",
        "SENSEX": "BSE_INDEX|SENSEX",
    }

    INTERVAL_MAP = {
        "15minute": ("minutes", 15),
        "5minute": ("minutes", 5),
        "1minute": ("minutes", 1),
        "day": ("days", 1),
    }

    def __init__(self):
        import requests  # local import so the base app doesn't need `requests` unless this class is used
        self._requests = requests

        access_token = os.environ.get("UPSTOX_ACCESS_TOKEN")
        if not access_token:
            raise EnvironmentError("Set UPSTOX_ACCESS_TOKEN env var before using UpstoxDataSource.")
        self._headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        }

    def _instrument_key(self, symbol: str) -> str:
        if symbol in self.SYMBOL_MAP:
            return self.SYMBOL_MAP[symbol]
        if "|" in symbol:
            # Already looks like a raw instrument_key (e.g. from search_symbol()),
            # such as "NSE_EQ|INE002A01018" or "MCX_FO|123456" -- use it directly.
            return symbol
        raise ValueError(f"No instrument_key mapping for '{symbol}'. Add it to SYMBOL_MAP, "
                          f"or pass a raw instrument_key (use search_symbol() to find one).")

    def search_symbol(self, query: str, segment: str = None, instrument_type: str = None) -> list:
        """Search the full instrument master by name/trading_symbol (see modules/instrument_search.py)."""
        from modules.instrument_search import search_instruments
        return search_instruments(query, segment=segment, instrument_type=instrument_type)

    def _fetch_candles(self, symbol: str, unit: str, interval_value: int,
                        from_date: str, to_date: str) -> pd.DataFrame:
        instrument_key = self._instrument_key(symbol)
        url = f"{self.BASE_URL}/{instrument_key}/{unit}/{interval_value}/{to_date}/{from_date}"
        resp = self._requests.get(url, headers=self._headers, timeout=15)
        resp.raise_for_status()
        payload = resp.json()

        candles = payload.get("data", {}).get("candles", [])
        # Each candle: [timestamp, open, high, low, close, volume, oi]
        df = pd.DataFrame(candles, columns=["datetime", "open", "high", "low", "close", "volume", "oi"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime").reset_index(drop=True)
        return df[["datetime", "open", "high", "low", "close", "volume"]]

    def get_intraday_candles(self, symbol: str, interval: str = "15minute", days: int = 3) -> pd.DataFrame:
        unit, val = self.INTERVAL_MAP.get(interval, ("minutes", 15))
        to_date = pd.Timestamp.now().strftime("%Y-%m-%d")
        from_date = (pd.Timestamp.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
        return self._fetch_candles(symbol, unit, val, from_date, to_date)

    def get_daily_candles(self, symbol: str, days: int = 30) -> pd.DataFrame:
        to_date = pd.Timestamp.now().strftime("%Y-%m-%d")
        from_date = (pd.Timestamp.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
        df = self._fetch_candles(symbol, "days", 1, from_date, to_date)
        df.rename(columns={"datetime": "date"}, inplace=True)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df

    def get_ltp(self, symbol: str) -> float:
        intraday = self.get_intraday_candles(symbol, days=1)
        return float(intraday.iloc[-1]["close"])

    def get_nearest_expiry(self, symbol: str) -> str:
        """Fetches available option contracts and returns the nearest (soonest) expiry date."""
        instrument_key = self._instrument_key(symbol)
        url = "https://api.upstox.com/v2/option/contract"
        resp = self._requests.get(url, params={"instrument_key": instrument_key},
                                   headers=self._headers, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        contracts = payload.get("data", [])
        expiries = sorted({c["expiry"] for c in contracts if "expiry" in c})
        if not expiries:
            raise ValueError(f"No option contracts/expiries found for {symbol}")
        return expiries[0]

    def get_option_chain(self, symbol: str, expiry_date: str = None) -> pd.DataFrame:
        instrument_key = self._instrument_key(symbol)
        if expiry_date is None:
            expiry_date = self.get_nearest_expiry(symbol)

        url = "https://api.upstox.com/v2/option/chain"
        resp = self._requests.get(
            url,
            params={"instrument_key": instrument_key, "expiry_date": expiry_date},
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        raw = payload.get("data", [])

        rows = []
        for item in raw:
            ce = item.get("call_options", {}) or {}
            pe = item.get("put_options", {}) or {}
            ce_md = ce.get("market_data", {}) or {}
            pe_md = pe.get("market_data", {}) or {}
            ce_gr = ce.get("option_greeks", {}) or {}
            pe_gr = pe.get("option_greeks", {}) or {}

            rows.append({
                "strike_price": item.get("strike_price"),
                "underlying_spot_price": item.get("underlying_spot_price"),
                "ce_oi": ce_md.get("oi", 0),
                "ce_prev_oi": ce_md.get("prev_oi", 0),
                "ce_ltp": ce_md.get("ltp", 0),
                "ce_close": ce_md.get("close_price", 0),
                "ce_volume": ce_md.get("volume", 0),
                "ce_iv": ce_gr.get("iv", 0),
                "ce_delta": ce_gr.get("delta", 0),
                "pe_oi": pe_md.get("oi", 0),
                "pe_prev_oi": pe_md.get("prev_oi", 0),
                "pe_ltp": pe_md.get("ltp", 0),
                "pe_close": pe_md.get("close_price", 0),
                "pe_volume": pe_md.get("volume", 0),
                "pe_iv": pe_gr.get("iv", 0),
                "pe_delta": pe_gr.get("delta", 0),
            })

        return pd.DataFrame(rows).sort_values("strike_price").reset_index(drop=True)


# ---------------------------------------------------------------------------
# KITE CONNECT DATA SOURCE  (fill this in once the API key arrives)
# ---------------------------------------------------------------------------
class KiteDataSource(BaseDataSource):
    """
    Setup steps once you have the key:
      1. pip install kiteconnect
      2. Set env vars: KITE_API_KEY, KITE_ACCESS_TOKEN
      3. Instrument tokens: Kite needs numeric instrument_token, not "NIFTY 50" —
         fetch once via kite.instruments() and cache the mapping (see NOTE below).

    NOTE on instrument tokens: Nifty 50 index token is typically 256265, but
    ALWAYS confirm via kite.instruments("NSE") since tokens can change. Do not
    hardcode without verifying against the live instruments dump.
    """

    def __init__(self):
        try:
            from kiteconnect import KiteConnect
        except ImportError as e:
            raise ImportError(
                "kiteconnect not installed. Run: pip install kiteconnect"
            ) from e

        api_key = os.environ.get("KITE_API_KEY")
        access_token = os.environ.get("KITE_ACCESS_TOKEN")
        if not api_key or not access_token:
            raise EnvironmentError(
                "Set KITE_API_KEY and KITE_ACCESS_TOKEN env vars before using KiteDataSource."
            )

        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)
        self._instrument_cache = {}

    def _resolve_token(self, symbol: str) -> int:
        if symbol in self._instrument_cache:
            return self._instrument_cache[symbol]
        instruments = self.kite.instruments("NSE")
        for inst in instruments:
            if inst["tradingsymbol"] == symbol:
                self._instrument_cache[symbol] = inst["instrument_token"]
                return inst["instrument_token"]
        raise ValueError(f"Instrument token not found for symbol: {symbol}")

    def get_intraday_candles(self, symbol: str, interval: str = "15minute", days: int = 3) -> pd.DataFrame:
        token = self._resolve_token(symbol)
        from_date = pd.Timestamp.now() - pd.Timedelta(days=days)
        to_date = pd.Timestamp.now()
        data = self.kite.historical_data(token, from_date, to_date, interval)
        df = pd.DataFrame(data)
        df.rename(columns={"date": "datetime"}, inplace=True)
        return df[["datetime", "open", "high", "low", "close", "volume"]]

    def get_daily_candles(self, symbol: str, days: int = 30) -> pd.DataFrame:
        token = self._resolve_token(symbol)
        from_date = pd.Timestamp.now() - pd.Timedelta(days=days)
        to_date = pd.Timestamp.now()
        data = self.kite.historical_data(token, from_date, to_date, "day")
        df = pd.DataFrame(data)
        df.rename(columns={"date": "date"}, inplace=True)
        return df[["date", "open", "high", "low", "close", "volume"]]

    def get_ltp(self, symbol: str) -> float:
        quote = self.kite.ltp([f"NSE:{symbol}"])
        return quote[f"NSE:{symbol}"]["last_price"]

    def get_option_chain(self, symbol: str, expiry_date: str = None) -> pd.DataFrame:
        raise NotImplementedError(
            "Kite option chain requires building it from kite.instruments('NFO') "
            "(filter by name/expiry/strike) plus kite.quote() for OI/LTP per leg. "
            "Ask me to build this out if you switch to Kite as the primary data source."
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def get_data_source() -> BaseDataSource:
    """
    Reads DATA_SOURCE env var ("mock" | "upstox" | "kite"). Defaults to mock
    so the app always runs even before any broker API is set up.
    """
    mode = os.environ.get("DATA_SOURCE", "mock").lower()
    if mode == "upstox":
        return UpstoxDataSource()
    if mode == "kite":
        return KiteDataSource()
    return MockDataSource()
