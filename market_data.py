import requests
import pandas as pd

def fetch_prices():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": "bitcoin,solana,paxos-gold",
        "vs_currencies": "usd",
        "include_24hr_change": "true"
    }

    response = requests.get(url, params=params)
    data = response.json()

    prices = {}

    for coin in ["bitcoin", "solana", "paxos-gold"]:
        prices[coin] = data.get(coin, {}).get("usd", None)

    # Hardcoded metals for now
    prices["silver"] = 80.7

    return prices


def fetch_hyperliquid_market_data():
    url = "https://api.hyperliquid.xyz/info"

    payload = {
        "type": "metaAndAssetCtxs"
    }

    response = requests.post(url, json=payload, timeout=15)
    response.raise_for_status()

    data = response.json()

    universe = data[0]["universe"]
    asset_contexts = data[1]

    market_data = {}

    for asset_info, ctx in zip(universe, asset_contexts):
        symbol = asset_info["name"]

        market_data[symbol] = {
            "mark_price": float(ctx["markPx"]) if ctx.get("markPx") else None,
            "funding": float(ctx["funding"]) if ctx.get("funding") else None,
            "open_interest": float(ctx["openInterest"]) if ctx.get("openInterest") else None,
            "volume_24h": float(ctx["dayNtlVlm"]) if ctx.get("dayNtlVlm") else None,
            "prev_day_price": float(ctx["prevDayPx"]) if ctx.get("prevDayPx") else None,
        }

    return market_data


def fetch_coingecko_market_chart(coin_id, days=120):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": days,
        "interval": "daily"
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    data = response.json()
    prices = data.get("prices", [])

    df = pd.DataFrame(prices, columns=["timestamp", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

    return df


def fetch_coingecko_ohlc(coin_id, days=90):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {
        "vs_currency": "usd",
        "days": days
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    data = response.json()

    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

    return df