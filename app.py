from typing import Any

from flask import Flask, render_template

from market_data import (
    fetch_asset_historical_data,
    fetch_hyperliquid_market_data,
    fetch_prices,
)

from strategy import (
    calculate_atr_volatility,
    calculate_confluence,
    calculate_donchian_structure,
    calculate_ema_trend,
    calculate_overall_rating,
    calculate_trend_signal,
    evaluate_trade,
    get_alert,
)


app = Flask(__name__)


# ============================================================
# ASSET CONFIGURATION
# ============================================================

ASSETS = {
    "bitcoin": {
        "symbol": "BTC",
        "display_name": "Bitcoin",
        "coingecko_id": "bitcoin",
        "hyperliquid_symbol": "BTC",

        # Only used if live Hyperliquid funding is unavailable.
        "fallback_funding": None,

        "levels": {
            "long_entry": (70000, 72000),
            "short_entry": (78000, 80000),
            "tp_long": [78000, 82000],
            "tp_short": [72000, 69000],
            "sl_long": 67500,
            "sl_short": 82500,
        },
    },

    "solana": {
        "symbol": "SOL",
        "display_name": "Solana",
        "coingecko_id": "solana",
        "hyperliquid_symbol": "SOL",
        "fallback_funding": None,

        "levels": {
            "long_entry": (72, 75),
            "short_entry": (92, 100),
            "tp_long": [95, 105],
            "tp_short": [78, 72],
            "sl_long": 68,
            "sl_short": 104,
        },
    },

    "pax-gold": {
        "symbol": "PAXG",
        "display_name": "PAX Gold",
        "coingecko_id": "pax-gold",
        "hyperliquid_symbol": "PAXG",
        "fallback_funding": None,

        "levels": {
            "long_entry": (4720, 4750),
            "short_entry": None,
            "tp_long": [4900, 5050, 5200],
            "tp_short": None,
            "sl_long": 4650,
            "sl_short": None,
        },
    },

    "silver": {
        "symbol": "SILVER",
        "display_name": "Silver",
        "coingecko_id": None,
        "hyperliquid_symbol": None,
        "fallback_funding": None,

        "levels": {
            "long_entry": (82.5, 83),
            "short_entry": (79, 80),
            "tp_long": [88, 92],
            "tp_short": [75, 72],
            "sl_long": 79.5,
            "sl_short": 82,
        },
    },
}


# ============================================================
# HELPERS
# ============================================================

def first_available(*values: Any) -> Any:
    """
    Return the first value that is not None.

    This is safer than using:

        live_price or fallback_price

    because zero is a valid numeric value, even though it is falsy.
    """

    for value in values:
        if value is not None:
            return value

    return None


def calculate_price_change(
    price: float | None,
    previous_price: float | None,
) -> float | None:
    """
    Calculate percentage price change from the previous-day price.
    """

    if (
        price is None
        or previous_price is None
        or previous_price == 0
    ):
        return None

    return round(
        ((price - previous_price) / previous_price) * 100,
        2,
    )


def get_empty_historical_data() -> dict:
    """
    Return empty historical datasets for unsupported assets.

    fetch_asset_historical_data already handles coin_id=None, but
    this helper makes the intended behavior explicit in app.py.
    """

    return fetch_asset_historical_data(None)


def build_asset_card(
    asset_key: str,
    config: dict,
    prices: dict,
    hyperliquid_data: dict,
) -> dict:
    """
    Build one complete dashboard card.

    app.py orchestrates the process:
        1. Select live market data.
        2. Retrieve cached historical data.
        3. Run strategy calculations.
        4. Package results for the HTML template.
    """

    levels = config.get("levels", {})
    coin_id = config.get("coingecko_id")
    hl_symbol = config.get("hyperliquid_symbol")

    # --------------------------------------------------------
    # LIVE HYPERLIQUID DATA
    # --------------------------------------------------------

    hl_data = {}

    if hl_symbol:
        hl_data = hyperliquid_data.get(hl_symbol, {})

    live_price = hl_data.get("mark_price")
    fallback_price = prices.get(asset_key)

    price = first_available(
        live_price,
        fallback_price,
    )

    funding = first_available(
        hl_data.get("funding"),
        config.get("fallback_funding"),
    )

    open_interest = hl_data.get("open_interest")
    volume_24h = hl_data.get("volume_24h")
    previous_day_price = hl_data.get("prev_day_price")

    price_change_24h = calculate_price_change(
        price,
        previous_day_price,
    )

    # --------------------------------------------------------
    # CACHED HISTORICAL DATA
    # --------------------------------------------------------

    if coin_id:
        historical_data = fetch_asset_historical_data(
            coin_id=coin_id,
            market_chart_days=120,
            ohlc_days=90,
        )
    else:
        historical_data = get_empty_historical_data()

    market_chart_df = historical_data["market_chart"]
    ohlc_df = historical_data["ohlc"]

    # --------------------------------------------------------
    # STRATEGY CALCULATIONS
    # --------------------------------------------------------

    signal = evaluate_trade(
        asset_name=asset_key,
        price=price,
        levels=levels,
    )

    alert = get_alert(
        price=price,
        levels=levels,
    )

    confluence = calculate_confluence(
        price=price,
        levels=levels,
        funding=funding,
    )

    ema_trend = calculate_ema_trend(
        market_chart_df
    )

    donchian_structure = calculate_donchian_structure(
        market_chart_df
    )

    atr_volatility = calculate_atr_volatility(
        ohlc_df=ohlc_df,
        period=14,
        stop_multiplier=1.5,
    )

    trend_signal = calculate_trend_signal(
        ema_trend=ema_trend,
        donchian_structure=donchian_structure,
    )

    overall_rating = calculate_overall_rating(
        ema_trend=ema_trend,
        donchian_structure=donchian_structure,
        atr_volatility=atr_volatility,
        funding=funding,
    )

    # --------------------------------------------------------
    # DATA AVAILABILITY
    # --------------------------------------------------------

    historical_data_available = (
        not market_chart_df.empty
        or not ohlc_df.empty
    )

    if not coin_id:
        data_status = "LIVE PRICE ONLY"
    elif not historical_data_available:
        data_status = "HISTORICAL DATA UNAVAILABLE"
    else:
        data_status = "DATA AVAILABLE"

    # --------------------------------------------------------
    # CARD OUTPUT
    # --------------------------------------------------------

    return {
        # Identity
        "asset_key": asset_key,
        "symbol": config.get("symbol", asset_key.upper()),
        "display_name": config.get(
            "display_name",
            asset_key.title(),
        ),

        # Current market information
        "price": price,
        "price_change_24h": price_change_24h,
        "funding": funding,
        "open_interest": open_interest,
        "volume_24h": volume_24h,
        "prev_day_price": previous_day_price,

        # Existing dashboard fields
        "signal": signal,
        "alert": alert,
        "confluence": confluence,
        "ema_trend": ema_trend,
        "donchian_structure": donchian_structure,
        "trend_signal": trend_signal,
        "atr_volatility": atr_volatility,
        "levels": levels,

        # Trading Operating System fields
        "overall_rating": overall_rating,
        "recommendation": overall_rating.get(
            "recommendation",
            "WAIT FOR DATA",
        ),
        "market_status": overall_rating.get(
            "status",
            "INSUFFICIENT DATA",
        ),

        # Data-quality information
        "data_status": data_status,
        "historical_data_available": (
            historical_data_available
        ),
    }


# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def index():
    """
    Main Trading Operating System dashboard.

    Current prices and Hyperliquid market context are fetched only
    once per page request. Their internal cache prevents unnecessary
    API calls across repeated browser refreshes.
    """

    prices = fetch_prices()
    hyperliquid_data = fetch_hyperliquid_market_data()

    dashboard = []

    for asset_key, config in ASSETS.items():
        try:
            asset_card = build_asset_card(
                asset_key=asset_key,
                config=config,
                prices=prices,
                hyperliquid_data=hyperliquid_data,
            )

        except Exception as error:
            # One failed asset should not prevent every other card
            # from loading.
            app.logger.exception(
                "Failed to build dashboard card for %s",
                asset_key,
            )

            asset_card = {
                "asset_key": asset_key,
                "symbol": config.get(
                    "symbol",
                    asset_key.upper(),
                ),
                "display_name": config.get(
                    "display_name",
                    asset_key.title(),
                ),
                "price": prices.get(asset_key),
                "price_change_24h": None,
                "funding": None,
                "open_interest": None,
                "volume_24h": None,
                "prev_day_price": None,
                "signal": "NO DATA",
                "alert": "NO ALERT",
                "confluence": {
                    "trend": "NO DATA",
                    "location": "NO DATA",
                    "funding": "NO DATA",
                    "raw_score": 0,
                    "score": 0,
                },
                "ema_trend": {
                    "trend": "CALCULATION ERROR",
                    "score": 0,
                    "available": False,
                },
                "donchian_structure": {
                    "structure": "CALCULATION ERROR",
                    "score": 0,
                    "available": False,
                },
                "trend_signal": {
                    "signal": "NO DATA",
                    "action": "WAIT FOR DATA",
                    "score": 0,
                    "available": False,
                },
                "atr_volatility": {
                    "atr": None,
                    "atr_pct": None,
                    "volatility_state": "CALCULATION ERROR",
                    "suggested_stop_distance": None,
                    "score": 0,
                    "available": False,
                },
                "overall_rating": {
                    "rating": None,
                    "display_rating": "NO DATA",
                    "status": "CALCULATION ERROR",
                    "recommendation": "WAIT FOR DATA",
                    "coverage": 0,
                    "implemented_coverage": 0,
                    "components": [],
                },
                "recommendation": "WAIT FOR DATA",
                "market_status": "CALCULATION ERROR",
                "levels": config.get("levels", {}),
                "data_status": f"ERROR: {error}",
                "historical_data_available": False,
            }

        dashboard.append(asset_card)

    # Highest-rated assets appear first. Assets without a rating
    # remain at the bottom.
    dashboard.sort(
        key=lambda item: (
            item.get("overall_rating", {}).get("rating")
            is not None,
            item.get("overall_rating", {}).get("rating")
            or 0,
        ),
        reverse=True,
    )

    return render_template(
        "index.html",
        dashboard=dashboard,
    )


# ============================================================
# APPLICATION START
# ============================================================

if __name__ == "__main__":
    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000,
    )
