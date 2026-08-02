from typing import Any

import pandas as pd


# ============================================================
# DEFAULT RESULT BUILDERS
# ============================================================

def _empty_ema_result(status: str = "NO DATA") -> dict[str, Any]:
    return {
        "ema_5": None,
        "ema_10": None,
        "ema_20": None,
        "ema_50": None,
        "trend": status,
        "score": 0,
        "max_score": 3,
        "available": False,
    }


def _empty_donchian_result(
    status: str = "NO DATA",
) -> dict[str, Any]:
    return {
        "high_20": None,
        "low_20": None,
        "high_55": None,
        "low_55": None,
        "structure": status,
        "score": 0,
        "max_score": 2,
        "available": False,
    }


def _empty_atr_result(status: str = "NO DATA") -> dict[str, Any]:
    return {
        "atr": None,
        "atr_pct": None,
        "volatility_state": status,
        "suggested_stop_distance": None,
        "score": 0,
        "max_score": 1,
        "available": False,
    }


def _safe_number(value: Any) -> float | None:
    """
    Safely convert a value to a float.
    """

    if value is None:
        return None

    try:
        number = float(value)

        if pd.isna(number):
            return None

        return number

    except (TypeError, ValueError):
        return None


def _valid_zone(zone: Any) -> bool:
    """
    Confirm that a trade zone contains two usable values.
    """

    return (
        isinstance(zone, (list, tuple))
        and len(zone) == 2
        and zone[0] is not None
        and zone[1] is not None
    )


# ============================================================
# MANUAL TRADE LEVELS
# ============================================================

def evaluate_trade(
    asset_name: str,
    price: float | None,
    levels: dict[str, Any],
) -> str:
    """
    Evaluate price relative to manually configured trade zones.

    asset_name is retained for compatibility and future logging.
    """

    del asset_name

    price = _safe_number(price)

    if price is None:
        return "NO DATA"

    long_zone = levels.get("long_entry")
    short_zone = levels.get("short_entry")

    if _valid_zone(long_zone):
        if long_zone[0] <= price <= long_zone[1]:
            return "LONG ZONE"

    if _valid_zone(short_zone):
        if short_zone[0] <= price <= short_zone[1]:
            return "SHORT ZONE"

    if _valid_zone(long_zone) and price < long_zone[0]:
        return "BELOW LONG ZONE"

    if _valid_zone(short_zone) and price > short_zone[1]:
        return "ABOVE SHORT ZONE"

    return "WAIT"


def get_alert(
    price: float | None,
    levels: dict[str, Any],
) -> str:
    """
    Return an alert when price enters a configured trade zone.
    """

    price = _safe_number(price)

    if price is None:
        return "NO DATA"

    long_zone = levels.get("long_entry")
    short_zone = levels.get("short_entry")

    if _valid_zone(long_zone):
        if long_zone[0] <= price <= long_zone[1]:
            return "🚨 BUY ZONE"

    if _valid_zone(short_zone):
        if short_zone[0] <= price <= short_zone[1]:
            return "🚨 SELL / SHORT ZONE"

    return "NO ALERT"


# ============================================================
# BASIC CONFLUENCE COMPONENTS
# ============================================================

def get_trend(
    price: float | None,
    levels: dict[str, Any],
) -> tuple[str, int]:
    """
    Basic price-versus-zone trend classification.

    This remains separate from the EMA trend engine.
    """

    price = _safe_number(price)

    if price is None:
        return "NO DATA", 0

    long_zone = levels.get("long_entry")

    if not _valid_zone(long_zone):
        return "NO LEVELS", 0

    if price > long_zone[1]:
        return "ABOVE LONG ZONE", 2

    if price < long_zone[0]:
        return "BELOW LONG ZONE", 0

    return "INSIDE LONG ZONE", 1


def get_location_score(
    price: float | None,
    levels: dict[str, Any],
) -> tuple[str, int]:
    """
    Score price location relative to manual support/resistance zones.
    """

    price = _safe_number(price)

    if price is None:
        return "NO DATA", 0

    long_zone = levels.get("long_entry")
    short_zone = levels.get("short_entry")

    if _valid_zone(long_zone):
        if long_zone[0] <= price <= long_zone[1]:
            return "AT SUPPORT", 2

    if _valid_zone(short_zone):
        if short_zone[0] <= price <= short_zone[1]:
            return "AT RESISTANCE", -2

    return "MID RANGE", 0


def get_funding_score(
    funding: float | None,
) -> tuple[str, int]:
    """
    Score funding as a sentiment indicator.

    Hyperliquid funding values are normally decimal rates, so:

        0.0001 = 0.01%

    The thresholds below therefore use decimal values rather than
    whole percentage values.
    """

    funding = _safe_number(funding)

    if funding is None:
        return "NO DATA", 0

    if funding < -0.0001:
        return "SHORTS CROWDED", 1

    if funding > 0.0005:
        return "LONGS CROWDED", -1

    return "BALANCED", 0


def calculate_confluence(
    price: float | None,
    levels: dict[str, Any],
    funding: float | None,
) -> dict[str, Any]:
    """
    Preserve the existing confluence calculation for dashboard
    compatibility.

    This is separate from the new overall rating.
    """

    trend_text, trend_score = get_trend(price, levels)
    location_text, location_score = get_location_score(
        price,
        levels,
    )
    funding_text, funding_score = get_funding_score(funding)

    raw_score = (
        trend_score
        + location_score
        + funding_score
    )

    score_out_of_10 = max(
        0,
        min(10, raw_score + 4),
    )

    return {
        "trend": trend_text,
        "location": location_text,
        "funding": funding_text,
        "raw_score": raw_score,
        "score": score_out_of_10,
    }


# ============================================================
# EMA TREND ENGINE
# ============================================================

def calculate_ema_trend(
    market_chart_df: pd.DataFrame | None,
) -> dict[str, Any]:
    """
    Calculate the EMA 5, 10, 20 and 50 trend state.

    This function does not fetch data. It receives a DataFrame from
    market_data.py.

    Expected columns:

        timestamp
        close
    """

    if market_chart_df is None or market_chart_df.empty:
        return _empty_ema_result()

    if "close" not in market_chart_df.columns:
        return _empty_ema_result("INVALID DATA")

    try:
        df = market_chart_df[["close"]].copy()

        df["close"] = pd.to_numeric(
            df["close"],
            errors="coerce",
        )

        df = df.dropna(subset=["close"])

        if len(df) < 50:
            return _empty_ema_result("INSUFFICIENT DATA")

        df["ema_5"] = (
            df["close"]
            .ewm(span=5, adjust=False)
            .mean()
        )

        df["ema_10"] = (
            df["close"]
            .ewm(span=10, adjust=False)
            .mean()
        )

        df["ema_20"] = (
            df["close"]
            .ewm(span=20, adjust=False)
            .mean()
        )

        df["ema_50"] = (
            df["close"]
            .ewm(span=50, adjust=False)
            .mean()
        )

        latest = df.iloc[-1]

        close = float(latest["close"])
        ema_5 = float(latest["ema_5"])
        ema_10 = float(latest["ema_10"])
        ema_20 = float(latest["ema_20"])
        ema_50 = float(latest["ema_50"])

        # Trend category has a maximum bullish score of 3.
        if (
            close > ema_5
            and ema_5 > ema_10 > ema_20 > ema_50
        ):
            trend = "STRONG BULLISH STACK"
            score = 3

        elif ema_5 > ema_10 > ema_20 > ema_50:
            trend = "BULLISH EMA STACK"
            score = 2

        elif close > ema_20 and ema_10 > ema_50:
            trend = "BULLISH MIXED"
            score = 1

        elif (
            close < ema_5
            and ema_5 < ema_10 < ema_20 < ema_50
        ):
            trend = "STRONG BEARISH STACK"
            score = -3

        elif ema_5 < ema_10 < ema_20 < ema_50:
            trend = "BEARISH EMA STACK"
            score = -2

        elif close < ema_20 and ema_10 < ema_50:
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
            "score": score,
            "max_score": 3,
            "available": True,
        }

    except (
        KeyError,
        TypeError,
        ValueError,
        IndexError,
    ) as error:
        print(f"EMA calculation error: {error}")
        return _empty_ema_result("CALCULATION ERROR")


# ============================================================
# DONCHIAN STRUCTURE ENGINE
# ============================================================

def calculate_donchian_structure(
    market_chart_df: pd.DataFrame | None,
) -> dict[str, Any]:
    """
    Calculate 20-period and 55-period close-based Donchian structure.

    Important:
    The current candle is excluded from channel calculations.

    Without excluding it, the latest close will often equal the
    channel high simply because it is included in the maximum.
    That can create false breakout signals.
    """

    if market_chart_df is None or market_chart_df.empty:
        return _empty_donchian_result()

    if "close" not in market_chart_df.columns:
        return _empty_donchian_result("INVALID DATA")

    try:
        df = market_chart_df[["close"]].copy()

        df["close"] = pd.to_numeric(
            df["close"],
            errors="coerce",
        )

        df = df.dropna(subset=["close"])

        # We need one current candle plus 55 prior candles.
        if len(df) < 56:
            return _empty_donchian_result(
                "INSUFFICIENT DATA"
            )

        latest_close = float(df.iloc[-1]["close"])

        previous_closes = df.iloc[:-1]["close"]

        high_20 = float(
            previous_closes.tail(20).max()
        )
        low_20 = float(
            previous_closes.tail(20).min()
        )
        high_55 = float(
            previous_closes.tail(55).max()
        )
        low_55 = float(
            previous_closes.tail(55).min()
        )

        # Structure category has a maximum bullish score of 2.
        if latest_close > high_55:
            structure = "55-PERIOD BREAKOUT"
            score = 2

        elif latest_close > high_20:
            structure = "20-PERIOD BREAKOUT"
            score = 1

        elif latest_close < low_55:
            structure = "55-PERIOD BREAKDOWN"
            score = -2

        elif latest_close < low_20:
            structure = "20-PERIOD BREAKDOWN"
            score = -1

        else:
            structure = "INSIDE CHANNEL"
            score = 0

        return {
            "high_20": round(high_20, 4),
            "low_20": round(low_20, 4),
            "high_55": round(high_55, 4),
            "low_55": round(low_55, 4),
            "structure": structure,
            "score": score,
            "max_score": 2,
            "available": True,
        }

    except (
        KeyError,
        TypeError,
        ValueError,
        IndexError,
    ) as error:
        print(f"Donchian calculation error: {error}")
        return _empty_donchian_result(
            "CALCULATION ERROR"
        )


# ============================================================
# ATR VOLATILITY ENGINE
# ============================================================

def calculate_atr_volatility(
    ohlc_df: pd.DataFrame | None,
    period: int = 14,
    stop_multiplier: float = 1.5,
) -> dict[str, Any]:
    """
    Calculate ATR and volatility state.

    Expected columns:

        open
        high
        low
        close

    ATR is used as a risk measurement, not as an entry signal.
    """

    if ohlc_df is None or ohlc_df.empty:
        return _empty_atr_result()

    required_columns = {
        "high",
        "low",
        "close",
    }

    if not required_columns.issubset(ohlc_df.columns):
        return _empty_atr_result("INVALID DATA")

    if period < 2:
        return _empty_atr_result("INVALID PERIOD")

    try:
        df = ohlc_df.copy()

        for column in required_columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

        df = df.dropna(
            subset=["high", "low", "close"]
        )

        if len(df) < period + 1:
            return _empty_atr_result(
                "INSUFFICIENT DATA"
            )

        previous_close = df["close"].shift(1)

        high_low = df["high"] - df["low"]
        high_previous = (
            df["high"] - previous_close
        ).abs()
        low_previous = (
            df["low"] - previous_close
        ).abs()

        true_range = pd.concat(
            [
                high_low,
                high_previous,
                low_previous,
            ],
            axis=1,
        ).max(axis=1)

        # Wilder-style ATR smoothing.
        atr_series = true_range.ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period,
        ).mean()

        atr = _safe_number(atr_series.iloc[-1])
        close = _safe_number(df["close"].iloc[-1])

        if atr is None or close is None or close <= 0:
            return _empty_atr_result(
                "CALCULATION ERROR"
            )

        atr_pct = (atr / close) * 100

        # Volatility category contributes a maximum of one point.
        if atr_pct < 1.0:
            volatility_state = "VERY LOW VOLATILITY"
            score = 0

        elif atr_pct < 2.0:
            volatility_state = "LOW VOLATILITY"
            score = 0.5

        elif atr_pct <= 5.0:
            volatility_state = "HEALTHY VOLATILITY"
            score = 1

        elif atr_pct <= 8.0:
            volatility_state = "ELEVATED VOLATILITY"
            score = 0.5

        else:
            volatility_state = "EXTREME VOLATILITY"
            score = 0

        suggested_stop_distance = (
            atr * stop_multiplier
        )

        return {
            "atr": round(atr, 4),
            "atr_pct": round(atr_pct, 2),
            "volatility_state": volatility_state,
            "suggested_stop_distance": round(
                suggested_stop_distance,
                4,
            ),
            "score": score,
            "max_score": 1,
            "available": True,
        }

    except (
        KeyError,
        TypeError,
        ValueError,
        IndexError,
    ) as error:
        print(f"ATR calculation error: {error}")
        return _empty_atr_result(
            "CALCULATION ERROR"
        )


# ============================================================
# COMBINED TREND SIGNAL
# ============================================================

def calculate_trend_signal(
    ema_trend: dict[str, Any],
    donchian_structure: dict[str, Any],
) -> dict[str, Any]:
    """
    Combine EMA trend and Donchian market structure.

    This signal remains directional. It is not yet the complete
    overall rating.
    """

    ema_available = ema_trend.get(
        "available",
        False,
    )
    structure_available = donchian_structure.get(
        "available",
        False,
    )

    if not ema_available and not structure_available:
        return {
            "signal": "NO DATA",
            "action": "WAIT FOR DATA",
            "ema": ema_trend.get("trend", "NO DATA"),
            "structure": donchian_structure.get(
                "structure",
                "NO DATA",
            ),
            "score": 0,
            "max_score": 5,
            "available": False,
        }

    ema_score = _safe_number(
        ema_trend.get("score")
    ) or 0

    structure_score = _safe_number(
        donchian_structure.get("score")
    ) or 0

    total_score = ema_score + structure_score

    if total_score >= 4:
        signal = "STRONG BULLISH"
        action = "LOOK FOR LONG SETUP"

    elif total_score >= 2:
        signal = "BULLISH WATCH"
        action = "WAIT FOR CLEAN LONG ENTRY"

    elif total_score <= -4:
        signal = "STRONG BEARISH"
        action = "LOOK FOR SHORT SETUP"

    elif total_score <= -2:
        signal = "BEARISH WATCH"
        action = "WAIT FOR CLEAN SHORT ENTRY"

    else:
        signal = "NEUTRAL"
        action = "NO CLEAN EDGE"

    return {
        "signal": signal,
        "action": action,
        "ema": ema_trend.get(
            "trend",
            "NO DATA",
        ),
        "structure": donchian_structure.get(
            "structure",
            "NO DATA",
        ),
        "score": total_score,
        "max_score": 5,
        "available": True,
    }


# ============================================================
# PROVISIONAL OVERALL RATING
# ============================================================

def calculate_overall_rating(
    ema_trend: dict[str, Any],
    donchian_structure: dict[str, Any],
    atr_volatility: dict[str, Any],
    funding: float | None = None,
) -> dict[str, Any]:
    """
    Calculate an early overall rating using currently implemented
    components.

    Current categories:

        Trend       maximum 3 points
        Structure   maximum 2 points
        Volatility  maximum 1 point
        Sentiment   maximum 1 point

    Maximum currently implemented score: 7 points.

    The result is normalized to 10 so the dashboard can display a
    familiar rating, but coverage is shown clearly. Momentum and
    liquidity will be added later.
    """

    components: list[dict[str, Any]] = []

    if ema_trend.get("available"):
        trend_score = max(
            0,
            float(ema_trend.get("score", 0)),
        )

        components.append({
            "name": "Trend",
            "score": trend_score,
            "maximum": 3,
            "status": ema_trend.get("trend"),
        })

    if donchian_structure.get("available"):
        structure_score = max(
            0,
            float(
                donchian_structure.get("score", 0)
            ),
        )

        components.append({
            "name": "Structure",
            "score": structure_score,
            "maximum": 2,
            "status": donchian_structure.get(
                "structure"
            ),
        })

    if atr_volatility.get("available"):
        components.append({
            "name": "Volatility",
            "score": float(
                atr_volatility.get("score", 0)
            ),
            "maximum": 1,
            "status": atr_volatility.get(
                "volatility_state"
            ),
        })

    funding_text, funding_raw_score = (
        get_funding_score(funding)
    )

    if funding_text != "NO DATA":
        # Convert -1, 0, 1 into a non-negative 0-to-1
        # quality score.
        if funding_raw_score > 0:
            funding_quality_score = 1
        elif funding_raw_score == 0:
            funding_quality_score = 0.75
        else:
            funding_quality_score = 0

        components.append({
            "name": "Sentiment",
            "score": funding_quality_score,
            "maximum": 1,
            "status": funding_text,
        })

    available_score = sum(
        component["score"]
        for component in components
    )

    available_maximum = sum(
        component["maximum"]
        for component in components
    )

    if available_maximum == 0:
        return {
            "rating": None,
            "display_rating": "NO DATA",
            "status": "INSUFFICIENT DATA",
            "recommendation": "WAIT FOR DATA",
            "coverage": 0,
            "implemented_coverage": 0,
            "components": components,
        }

    rating = (
        available_score / available_maximum
    ) * 10

    rating = round(
        max(0, min(10, rating)),
        1,
    )

    # Seven of the intended ten points are implemented.
    implemented_coverage = round(
        (available_maximum / 7) * 100
    )

    full_system_coverage = round(
        (available_maximum / 10) * 100
    )

    if rating >= 8.5:
        status = "STRONG CONDITIONS"
        recommendation = "LOOK FOR QUALIFIED SETUP"

    elif rating >= 7:
        status = "FAVORABLE CONDITIONS"
        recommendation = "WATCH FOR ENTRY"

    elif rating >= 5:
        status = "MIXED CONDITIONS"
        recommendation = "WAIT FOR MORE CONFIRMATION"

    elif rating >= 3:
        status = "WEAK CONDITIONS"
        recommendation = "AVOID NEW ENTRY"

    else:
        status = "UNFAVORABLE CONDITIONS"
        recommendation = "STAY OUT"

    return {
        "rating": rating,
        "display_rating": f"{rating} / 10",
        "status": status,
        "recommendation": recommendation,

        # Coverage relative to the eventual full 10-point engine.
        "coverage": full_system_coverage,

        # Coverage relative to currently implemented categories.
        "implemented_coverage": min(
            100,
            implemented_coverage,
        ),

        "components": components,
    }
