import os
from datetime import date


def _parse_outbreak_bulletins() -> list[tuple[str, str]]:
    """
    OUTBREAK_BULLETINS format:
    YYYY-MM-DD|message;YYYY-MM-DD|message
    """
    raw = os.getenv("OUTBREAK_BULLETINS", "").strip()
    if not raw:
        return []
    rows = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk or "|" not in chunk:
            continue
        d, msg = chunk.split("|", 1)
        rows.append((d.strip(), msg.strip()))
    return rows


def hydration_tip(hydration_liters: float | None) -> str | None:
    if hydration_liters is None:
        return None
    if hydration_liters >= 2.0:
        return "Hydration level looks okay today. Keep sipping water consistently."
    if hydration_liters >= 1.5:
        return (
            "Hydration is slightly low. Drink about 2 cups of water over the next 1-2 hours "
            "to stay adequately hydrated."
        )
    if hydration_liters >= 1.0:
        return (
            "Hydration level is low and may cause fatigue or headache. Drink 2-3 cups of clean water now, "
            "then continue with regular water intake."
        )
    return (
        "Hydration level is very low and may increase fatigue risk. Drink water immediately "
        "(start with 1-2 cups) and continue frequent intake through the day."
    )


def activity_tip(steps_count: int | None, activity_minutes: int | None) -> str | None:
    if steps_count is None and activity_minutes is None:
        return None
    if steps_count is not None and steps_count < 4000:
        return "Low activity detected. Try a brisk 15-20 minute walk to improve circulation."
    if activity_minutes is not None and activity_minutes < 20:
        return "Physical activity is below target. Aim for at least 20-30 active minutes today."
    return "Good activity level today. Maintain consistent movement and short stretch breaks."


def environment_tips(
    *,
    aqi: int | None,
    uv_index: float | None,
    temperature_c: float | None,
    weather_condition: str | None,
) -> list[str]:
    tips: list[str] = []

    if aqi is not None and aqi > 100:
        tips.append(
            "Air quality is poor right now. Consider wearing a face mask outdoors and reducing prolonged exposure."
        )

    if uv_index is not None and uv_index >= 8:
        tips.append(
            "UV exposure is very high. Limit midday sun exposure, stay in shade, and use sun protection."
        )

    if temperature_c is not None and temperature_c >= 34:
        tips.append(
            "Heat level is high today. Risk of dehydration and heat stress rises, so increase water intake and avoid prolonged sun."
        )
    elif temperature_c is not None and temperature_c <= 12:
        tips.append(
            "Weather is cold. Respiratory infections may rise in cold periods; keep warm and practice hand hygiene."
        )

    cond = (weather_condition or "").strip().lower()
    if cond in {"rain", "rainy", "storm", "thunderstorm"}:
        tips.append(
            "Rainy weather can increase mosquito breeding and water-borne disease risk. Use protective measures and safe water."
        )
    if cond in {"dust", "haze", "smog"}:
        tips.append(
            "Dust/haze conditions may irritate the lungs. Use a mask and reduce outdoor exertion if sensitive."
        )

    return tips


def outbreak_alerts(today: date) -> list[str]:
    today_s = today.isoformat()
    rows = _parse_outbreak_bulletins()
    return [msg for d, msg in rows if d == today_s]
