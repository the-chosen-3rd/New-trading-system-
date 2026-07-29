from flask import Flask, render_template
from market_data import fetch_prices, fetch_hyperliquid_market_data
from strategy import (
    evaluate_trade,
    get_alert,
    calculate_confluence,
    calculate_ema_trend,
    calculate_donchian_structure,
    calculate_trend_signal,
    calculate_atr_volatility
)

app = Flask(__name__)

ASSETS = {
    "bitcoin": {
        "symbol": "BTC",
        "coingecko_id": "bitcoin",
        "hyperliquid_symbol": "BTC",
        "funding": 0.0060,
        "levels": {
            "long_entry": (70000, 72000),
            "short_entry": (78000, 80000),
            "tp_long": [78000, 82000],
            "tp_short": [72000, 69000],
            "sl_long": 67500,
            "sl_short": 82500
        }
    },

    "solana": {
        "symbol": "SOL",
        "coingecko_id": "solana",
        "hyperliquid_symbol": "SOL",
        "funding": 0.0071,
        "levels": {
            "long_entry": (72, 75),
            "short_entry": (92, 100),
            "tp_long": [95, 105],
            "tp_short": [78, 72],
            "sl_long": 68,
            "sl_short": 104
        }
    },

    "pax-gold": {
        "symbol": "pax-gold",
        "coingecko_id": "pax-gold",
        "hyperliquid_symbol": "PAXG",
        "funding": 0.0053,
        "levels": {
            "long_entry": (4720, 4750),
            "short_entry": None,
            "tp_long": [4900, 5050, 5200],
            "tp_short": None,
            "sl_long": 4650,
            "sl_short": None
        }
    },

    "silver": {
        "symbol": "SILVER",
        "coingecko_id": None,
        "hyperliquid_symbol": None,
        "funding": 0.0154,
        "levels": {
            "long_entry": (82.5, 83),
            "short_entry": (79, 80),
            "tp_long": [88, 92],
            "tp_short": [75, 72],
            "sl_long": 79.5,
            "sl_short": 82
        }
    }
}


@app.route("/")
def index():
    prices = fetch_prices()
    hyperliquid_data = fetch_hyperliquid_market_data()
    dashboard = []

    for asset, config in ASSETS.items():
        levels = config["levels"]
        coin_id = config.get("coingecko_id")
        atr_volatility = calculate_atr_volatility(coin_id)

        hl_symbol = config.get("hyperliquid_symbol")
        hl_data = hyperliquid_data.get(hl_symbol, {}) if hl_symbol else {}

        price = hl_data.get("mark_price") or prices.get(asset)

        funding = hl_data.get("funding", config.get("funding", 0))
        open_interest = hl_data.get("open_interest")
        volume_24h = hl_data.get("volume_24h")
        prev_day_price = hl_data.get("prev_day_price")

        signal = evaluate_trade(asset, price, levels)
        alert = get_alert(price, levels)
        confluence = calculate_confluence(price, levels, funding)

        ema_trend = calculate_ema_trend(coin_id)
        donchian_structure = calculate_donchian_structure(coin_id)
        trend_signal = calculate_trend_signal(ema_trend, donchian_structure)

        dashboard.append({
            "symbol": config["symbol"],
            "price": price,
            "signal": signal,
            "atr_volatility": atr_volatility,
            "alert": alert,
            "confluence": confluence,
            "ema_trend": ema_trend,
            "donchian_structure": donchian_structure,
            "trend_signal": trend_signal,
            "funding": funding,
            "open_interest": open_interest,
            "volume_24h": volume_24h,
            "prev_day_price": prev_day_price,
            "levels": levels
            
        })

    return render_template("index.html", dashboard=dashboard)


if __name__ == "__main__":
    app.run(debug=True)
