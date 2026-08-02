import time
from typing import Any

import pandas as pd
import requests


# ============================================================
# API SETTINGS
# ============================================================

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"

REQUEST_TIMEOUT = 15

# Current prices and Hyperliquid data refresh every 5 minutes.
LIVE_DATA_CACHE_SECONDS = 300

# Historical candles refresh every hour.
HISTORICAL_DATA_CACHE_SECONDS = 3600


# CoinGecko IDs used by the dashboard.
COINGECKO_ASSETS = {
    "bitcoin": "bitcoin",
    "solana": "solana",
    "pax-gold": "pax-gold",
}


# Reuse one HTTP connection pool instead of opening a new
# connection for every request.
session = requests.Session()

session.headers.update({
    "Accept": "application/json",
    "User-Agent": "TradingOperatingSystem/1.0",
})


# ============================================================
# SIMPLE IN-MEMORY CACHE
# ============================================================

_cache: dict[str, dict[str, Any]] = {}


def _get_cached(cache_key: str, max_age: int) -> Any | None:
    """
    Return cached data if it exists and has not expired.
    """

    cached_item = _cache.get(cache_key)

    if cached_item is None:
        return None

    age = time.time() - cached_item["timestamp"]

    if age >= max_age:
        _cache.pop(cache_key, None)
        return None

    return cached_item["data"]


def _set_cached(cache_key: str, data: Any) -> None:
    """
    Store data in the in-memory cache.
    """

    _cache[cache_key] = {
        "timestamp": time.time(),
        "data": data,
    }


def clear_market_data_cache() -> None:
    """
    Manually clear all cached market data.

    This can later be connected to a dashboard refresh button.
    """

    _cache.clear()


# ============================================================
# REQUEST HELPER
# ============================================================

def _request_json(
    method: str,
    url: str,
    *,
    params: dict | None = None,
    json: dict | None = None,
) -> Any:
    """
    Send an API request and safely return decoded JSON.

    Raises a requests exception when the API request fails.
    """

    response = session.request(
        method=method,
        url=url,
        params=params,
        json=json,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# CURRENT COINGECKO PRICES
# ============================================================

def fetch_prices(force_refresh: bool = False) -> dict[str, float | None]:
    """
    Fetch current prices for BTC, SOL and PAXG.

    Results are cached for five minutes to prevent every dashboard
    refresh from creating another CoinGecko request.
    """

    cache_key = "coingecko_current_prices"

    if not force_refresh:
        cached_data = _get_cached(
            cache_key,
            LIVE_DATA_CACHE_SECONDS,
        )

        if cached_data is not None:
            return cached_data

    coin_ids = list(COINGECKO_ASSETS.values())

    url = f"{COINGECKO_BASE_URL}/simple/price"

    params = {
        "ids": ",".join(coin_ids),
        "vs_currencies": "usd",
        "include_24hr_change": "true",
    }

    prices: dict[str, float | None] = {
        "bitcoin": None,
        "solana": None,
        "pax-gold": None,

        # Temporary manual value until a proper silver API is added.
        "silver": 80.70,
    }

    try:
        data = _request_json(
            "GET",
            url,
            params=params,
        )

        for coin_id in coin_ids:
            value = data.get(coin_id, {}).get("usd")

            prices[coin_id] = (
                float(value)
                if value is not None
                else None
            )

        _set_cached(cache_key, prices)

    except (requests.RequestException, ValueError, TypeError) as error:
        print(f"CoinGecko price error: {error}")

    return prices


# ============================================================
# HYPERLIQUID MARKET DATA
# ============================================================

def fetch_hyperliquid_market_data(
    force_refresh: bool = False,
) -> dict[str, dict[str, float | None]]:
    """
    Fetch funding, open interest, volume and mark prices from
    Hyperliquid.

    The entire Hyperliquid market is returned by one request, so this
    function should only be called once in the Flask route—not once
    for every asset card.
    """

    cache_key = "hyperliquid_market_data"

    if not force_refresh:
        cached_data = _get_cached(
            cache_key,
            LIVE_DATA_CACHE_SECONDS,
        )

        if cached_data is not None:
            return cached_data

    payload = {
        "type": "metaAndAssetCtxs",
    }

    market_data: dict[str, dict[str, float | None]] = {}

    try:
        data = _request_json(
            "POST",
            HYPERLIQUID_INFO_URL,
            json=payload,
        )

        if (
            not isinstance(data, list)
            or len(data) < 2
            or "universe" not in data[0]
        ):
            raise ValueError(
                "Unexpected Hyperliquid response format."
            )

        universe = data[0]["universe"]
        asset_contexts = data[1]

        for asset_info, context in zip(
            universe,
            asset_contexts,
        ):
            symbol = asset_info.get("name")

            if not symbol:
                continue

            market_data[symbol] = {
                "mark_price": _safe_float(
                    context.get("markPx")
                ),
                "funding": _safe_float(
                    context.get("funding")
                ),
                "open_interest": _safe_float(
                    context.get("openInterest")
                ),
                "volume_24h": _safe_float(
                    context.get("dayNtlVlm")
                ),
                "prev_day_price": _safe_float(
                    context.get("prevDayPx")
                ),
            }

        _set_cached(cache_key, market_data)

    except (requests.RequestException, ValueError, TypeError) as error:
        print(f"Hyperliquid market-data error: {error}")

    return market_data


# ============================================================
# DAILY MARKET CHART
# ============================================================

def fetch_coingecko_market_chart(
    coin_id: str | None,
    days: int = 120,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Fetch historical daily closing prices.

    This data is suitable for calculations that only require closing
    prices, such as EMA calculations.

    Each asset and day range is cached separately.
    """

    empty_dataframe = pd.DataFrame(
        columns=["timestamp", "close"]
    )

    if not coin_id:
        return empty_dataframe

    cache_key = f"market_chart:{coin_id}:{days}"

    if not force_refresh:
        cached_data = _get_cached(
            cache_key,
            HISTORICAL_DATA_CACHE_SECONDS,
        )

        if cached_data is not None:
            return cached_data.copy()

    url = (
        f"{COINGECKO_BASE_URL}/coins/"
        f"{coin_id}/market_chart"
    )

    params = {
        "vs_currency": "usd",
        "days": days,
        "interval": "daily",
    }

    try:
        data = _request_json(
            "GET",
            url,
            params=params,
        )

        prices = data.get("prices", [])

        if not prices:
            print(
                f"No market-chart data returned for {coin_id}."
            )
            return empty_dataframe

        dataframe = pd.DataFrame(
            prices,
            columns=["timestamp", "close"],
        )

        dataframe["timestamp"] = pd.to_datetime(
            dataframe["timestamp"],
            unit="ms",
            utc=True,
        )

        dataframe["close"] = pd.to_numeric(
            dataframe["close"],
            errors="coerce",
        )

        dataframe = (
            dataframe
            .dropna(subset=["timestamp", "close"])
            .drop_duplicates(subset=["timestamp"])
            .sort_values("timestamp")
            .reset_index(drop=True)
        )

        _set_cached(cache_key, dataframe)

        return dataframe.copy()

    except (requests.RequestException, ValueError, TypeError) as error:
        print(
            f"CoinGecko market-chart error "
            f"for {coin_id}: {error}"
        )

        return empty_dataframe


# ============================================================
# OHLC DATA
# ============================================================

def fetch_coingecko_ohlc(
    coin_id: str | None,
    days: int = 90,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Fetch Open, High, Low and Close candle data.

    Use this dataset for ATR and other calculations requiring candle
    highs and lows.

    CoinGecko automatically chooses candle granularity based on the
    requested day range.
    """

    columns = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
    ]

    empty_dataframe = pd.DataFrame(columns=columns)

    if not coin_id:
        return empty_dataframe

    cache_key = f"ohlc:{coin_id}:{days}"

    if not force_refresh:
        cached_data = _get_cached(
            cache_key,
            HISTORICAL_DATA_CACHE_SECONDS,
        )

        if cached_data is not None:
            return cached_data.copy()

    url = f"{COINGECKO_BASE_URL}/coins/{coin_id}/ohlc"

    params = {
        "vs_currency": "usd",
        "days": days,
    }

    try:
        data = _request_json(
            "GET",
            url,
            params=params,
        )

        if not data:
            print(f"No OHLC data returned for {coin_id}.")
            return empty_dataframe

        dataframe = pd.DataFrame(
            data,
            columns=columns,
        )

        dataframe["timestamp"] = pd.to_datetime(
            dataframe["timestamp"],
            unit="ms",
            utc=True,
        )

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
        ]

        for column in numeric_columns:
            dataframe[column] = pd.to_numeric(
                dataframe[column],
                errors="coerce",
            )

        dataframe = (
            dataframe
            .dropna(subset=columns)
            .drop_duplicates(subset=["timestamp"])
            .sort_values("timestamp")
            .reset_index(drop=True)
        )

        _set_cached(cache_key, dataframe)

        return dataframe.copy()

    except (requests.RequestException, ValueError, TypeError) as error:
        print(
            f"CoinGecko OHLC error "
            f"for {coin_id}: {error}"
        )

        return empty_dataframe


# ============================================================
# COMBINED HISTORICAL DATA PACKAGE
# ============================================================

def fetch_asset_historical_data(
    coin_id: str | None,
    market_chart_days: int = 120,
    ohlc_days: int = 90,
) -> dict[str, pd.DataFrame]:
    """
    Return all historical data required by the strategy engine.

    Calling this function multiple times within the cache period does
    not create additional API requests.
    """

    if not coin_id:
        return {
            "market_chart": pd.DataFrame(
                columns=["timestamp", "close"]
            ),
            "ohlc": pd.DataFrame(
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                ]
            ),
        }

    return {
        "market_chart": fetch_coingecko_market_chart(
            coin_id=coin_id,
            days=market_chart_days,
        ),
        "ohlc": fetch_coingecko_ohlc(
            coin_id=coin_id,
            days=ohlc_days,
        ),
    }


# ============================================================
# UTILITY
# ============================================================

def _safe_float(value: Any) -> float | None:
    """
    Safely convert an API value to a float.
    """

    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None
