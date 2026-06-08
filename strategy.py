from market_data import fetch_coingecko_market_chart, fetch_coingecko_ohlc

def evaluate_trade(asset_name, price, levels):
    if price is None:
        return "NO DATA"

    long_zone = levels["long_entry"]
    short_zone = levels["short_entry"]

    if long_zone and long_zone[0] <= price <= long_zone[1]:
        return "LONG ZONE"

    if short_zone and short_zone[0] <= price <= short_zone[1]:
        return "SHORT ZONE"

    if long_zone and price < long_zone[0]:
        return "APPROACHING LONG"

    if short_zone and price > short_zone[1]:
        return "BREAKOUT / HOLD"

    return "WAIT"


def get_alert(price, levels):
    if price is None:
        return "NO DATA"

    long_zone = levels.get("long_entry")
    short_zone = levels.get("short_entry")

    if long_zone and long_zone[0] <= price <= long_zone[1]:
        return "🚨 BUY ZONE"

    if short_zone and short_zone[0] <= price <= short_zone[1]:
        return "🚨 SELL / SHORT ZONE"

    return "No alert"


def get_trend(price, levels):
    if price is None:
        return ("NO DATA", 0)

    long_zone = levels.get("long_entry")

    if long_zone and price > long_zone[1]:
        return ("BULLISH", 2)

    if long_zone and price < long_zone[0]:
        return ("PULLBACK", 1)

    return ("NEUTRAL", 0)


def get_location_score(price, levels):
    if price is None:
        return ("NO DATA", 0)

    long_zone = levels.get("long_entry")
    short_zone = levels.get("short_entry")

    if long_zone and long_zone[0] <= price <= long_zone[1]:
        return ("AT SUPPORT", 2)

    if short_zone and short_zone[0] <= price <= short_zone[1]:
        return ("AT RESISTANCE", -2)

    return ("MID RANGE", 0)


def get_funding_score(funding):
    if funding < 0:
        return ("HEALTHY", 1)

    if funding > 0.02:
        return ("OVERHEATED", -1)

    return ("NORMAL", 0)


def calculate_confluence(price, levels, funding):
    trend_text, trend_score = get_trend(price, levels)
    location_text, location_score = get_location_score(price, levels)
    funding_text, funding_score = get_funding_score(funding)

    raw_score = trend_score + location_score + funding_score

    score_out_of_10 = max(0, min(10, raw_score + 4))

    return {
        "trend": trend_text,
        "location": location_text,
        "funding": funding_text,
        "score": score_out_of_10
    }

def calculate_ema_trend(coin_id):
    if not coin_id:
        return {
            "ema_5": None,
            "ema_10": None,
            "ema_20": None,
            "ema_50": None,
            "trend": "NO DATA",
            "score": 0
        }

    try:
        df = fetch_coingecko_market_chart(coin_id, days=120)

        if df.empty or len(df) < 60:
            return {
                "ema_5": None,
                "ema_10": None,
                "ema_20": None,
                "ema_50": None,
                "trend": "NO DATA",
                "score": 0
            }

        df["ema_5"] = df["close"].ewm(span=5, adjust=False).mean()
        df["ema_10"] = df["close"].ewm(span=10, adjust=False).mean()
        df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()

        latest = df.iloc[-1]

        ema_5 = latest["ema_5"]
        ema_10 = latest["ema_10"]
        ema_20 = latest["ema_20"]
        ema_50 = latest["ema_50"]

        if ema_5 > ema_10 > ema_20 > ema_50:
            trend = "BULLISH EMA STACK"
            score = 2
        elif ema_5 < ema_10 < ema_20 < ema_50:
            trend = "BEARISH EMA STACK"
            score = -2
        elif ema_5 > ema_20 and ema_10 > ema_50:
            trend = "BULLISH MIXED"
            score = 1
        elif ema_5 < ema_20 and ema_10 < ema_50:
            trend = "BEARISH MIXED"
            score = -1
        else:
            trend = "NEUTRAL / CHOP"
            score = 0

        return {
            "ema_5": round(ema_5, 4),
            "ema_10": round(ema_10, 4),
            "ema_20": round(ema_20, 4),
            "ema_50": round(ema_50, 4),
            "trend": trend,
            "score": score
        }

    except Exception as e:
        return {
            "ema_5": None,
            "ema_10": None,
            "ema_20": None,
            "ema_50": None,
            "trend": f"ERROR",
            "score": 0
        }
    

def calculate_donchian_structure(coin_id):
    if not coin_id:
        return {
            "high_20": None,
            "low_20": None,
            "high_55": None,
            "low_55": None,
            "structure": "NO DATA",
            "score": 0
        }

    try:
        df = fetch_coingecko_market_chart(coin_id, days=120)

        if df.empty or len(df) < 60:
            return {
                "high_20": None,
                "low_20": None,
                "high_55": None,
                "low_55": None,
                "structure": "NO DATA",
                "score": 0
            }

        latest_close = df.iloc[-1]["close"]

        high_20 = df["close"].tail(20).max()
        low_20 = df["close"].tail(20).min()
        high_55 = df["close"].tail(55).max()
        low_55 = df["close"].tail(55).min()

        if latest_close >= high_55:
            structure = "MAJOR BREAKOUT"
            score = 3
        elif latest_close >= high_20:
            structure = "20D BREAKOUT"
            score = 2
        elif latest_close <= low_55:
            structure = "MAJOR BREAKDOWN"
            score = -3
        elif latest_close <= low_20:
            structure = "20D BREAKDOWN"
            score = -2
        else:
            structure = "RANGE / INSIDE CHANNEL"
            score = 0

        return {
            "high_20": round(high_20, 4),
            "low_20": round(low_20, 4),
            "high_55": round(high_55, 4),
            "low_55": round(low_55, 4),
            "structure": structure,
            "score": score
        }

    except Exception:
        return {
            "high_20": None,
            "low_20": None,
            "high_55": None,
            "low_55": None,
            "structure": "ERROR",
            "score": 0
        }
    


def calculate_trend_signal(ema_trend, donchian_structure):
    ema_score = ema_trend.get("score", 0)
    structure_score = donchian_structure.get("score", 0)

    total_score = ema_score + structure_score

    ema_text = ema_trend.get("trend", "NO DATA")
    structure_text = donchian_structure.get("structure", "NO DATA")

    if total_score >= 4:
        signal = "BULLISH BREAKOUT"
        action = "LOOK FOR LONG SETUP"
    elif total_score >= 2:
        signal = "BULLISH WATCH"
        action = "WAIT FOR CLEAN ENTRY"
    elif total_score <= -4:
        signal = "BEARISH BREAKDOWN"
        action = "LOOK FOR SHORT SETUP"
    elif total_score <= -2:
        signal = "BEARISH WATCH"
        action = "WAIT FOR REJECTION"
    else:
        signal = "WAIT"
        action = "NO CLEAN EDGE"

    return {
        "signal": signal,
        "action": action,
        "ema": ema_text,
        "structure": structure_text,
        "score": total_score
    }


def calculate_atr_volatility(coin_id, period=14):
    if not coin_id:
        return {
            "atr": None,
            "atr_pct": None,
            "volatility_state": "NO DATA",
            "suggested_stop_distance": None,
            "score": 0
        }

    try:
        df = fetch_coingecko_ohlc(coin_id, days=90)

        if df.empty or len(df) < period + 2:
            return {
                "atr": None,
                "atr_pct": None,
                "volatility_state": "NO DATA",
                "suggested_stop_distance": None,
                "score": 0
            }

        df["prev_close"] = df["close"].shift(1)

        df["tr1"] = df["high"] - df["low"]
        df["tr2"] = (df["high"] - df["prev_close"]).abs()
        df["tr3"] = (df["low"] - df["prev_close"]).abs()

        df["true_range"] = df[["tr1", "tr2", "tr3"]].max(axis=1)
        df["atr"] = df["true_range"].rolling(period).mean()

        latest = df.iloc[-1]
        atr = latest["atr"]
        close = latest["close"]

        atr_pct = (atr / close) * 100 if close else None

        if atr_pct is None:
            volatility_state = "NO DATA"
            score = 0
        elif atr_pct < 2:
            volatility_state = "LOW VOLATILITY"
            score = 0
        elif atr_pct <= 5:
            volatility_state = "HEALTHY VOLATILITY"
            score = 1
        else:
            volatility_state = "HIGH VOLATILITY"
            score = -1

        suggested_stop_distance = atr * 1.5 if atr else None

        return {
            "atr": round(atr, 4),
            "atr_pct": round(atr_pct, 2) if atr_pct is not None else None,
            "volatility_state": volatility_state,
            "suggested_stop_distance": round(suggested_stop_distance, 4) if suggested_stop_distance else None,
            "score": score
        }

    except Exception:
        return {
            "atr": None,
            "atr_pct": None,
            "volatility_state": "ERROR",
            "suggested_stop_distance": None,
            "score": 0
        }