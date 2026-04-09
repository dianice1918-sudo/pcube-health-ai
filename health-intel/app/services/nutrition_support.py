from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Iterable


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def calorie_goal_for_context(latest_record: Any) -> int:
    goal = 2000
    bmi = _as_float(getattr(latest_record, "bmi", None))
    steps = _as_int(getattr(latest_record, "steps_count", None))
    activity_level = str(getattr(latest_record, "activity_level", "") or "").strip().lower()
    glucose = _as_float(getattr(latest_record, "blood_glucose", None))
    cholesterol = _as_float(getattr(latest_record, "cholesterol", None))

    if bmi is not None:
        if bmi >= 30:
            goal -= 250
        elif bmi < 18.5:
            goal += 250

    if activity_level in {"high", "active"} or (steps is not None and steps >= 9000):
        goal += 150
    elif activity_level in {"low", "sedentary"} or (steps is not None and steps < 3500):
        goal -= 100

    if glucose is not None and glucose >= 126:
        goal -= 50
    if cholesterol is not None and cholesterol >= 220:
        goal -= 50

    return int(min(max(goal, 1600), 2600))


def water_goal_for_context(latest_record: Any) -> float:
    goal = 2.0
    temperature_c = _as_float(getattr(latest_record, "temperature_c", None))
    activity_minutes = _as_int(getattr(latest_record, "activity_minutes", None))
    steps = _as_int(getattr(latest_record, "steps_count", None))

    if temperature_c is not None and temperature_c >= 32:
        goal += 0.5
    if activity_minutes is not None and activity_minutes >= 45:
        goal += 0.3
    elif steps is not None and steps >= 9000:
        goal += 0.2

    return round(min(max(goal, 1.8), 4.0), 1)


def health_context_notes(latest_record: Any) -> list[str]:
    if latest_record is None:
        return [
            "No recent health record is available yet, so calorie and hydration goals use a general wellness baseline.",
        ]

    notes: list[str] = []
    bmi = _as_float(getattr(latest_record, "bmi", None))
    glucose = _as_float(getattr(latest_record, "blood_glucose", None))
    cholesterol = _as_float(getattr(latest_record, "cholesterol", None))
    hydration = _as_float(getattr(latest_record, "hydration_liters", None))
    steps = _as_int(getattr(latest_record, "steps_count", None))
    weather = str(getattr(latest_record, "weather_condition", "") or "").strip()

    if bmi is not None and bmi >= 30:
        notes.append("Recent BMI is elevated, so the meal target leans slightly lighter and more fiber-forward.")
    elif bmi is not None and bmi < 18.5:
        notes.append("Recent BMI is on the lower side, so the meal target leans toward extra calorie density and protein.")

    if glucose is not None and glucose >= 126:
        notes.append("Recent glucose is above the normal range, so steady meals with less sugar load are recommended.")
    elif glucose is not None and glucose >= 100:
        notes.append("Recent glucose is borderline high, so balanced meals and avoiding large sugar spikes may help.")

    if cholesterol is not None and cholesterol >= 220:
        notes.append("Recent cholesterol is elevated, so fiber, beans, oats, and lower saturated fat choices are emphasized.")

    if hydration is not None and hydration < 1.5:
        notes.append("Recent hydration looks low, so the daily water goal has been nudged upward.")

    if steps is not None and steps < 4000:
        notes.append("Recent activity is modest, so calorie guidance stays conservative unless your goals say otherwise.")
    elif steps is not None and steps >= 9000:
        notes.append("Recent activity is strong, so calorie guidance allows a bit more fuel for recovery and movement.")

    if weather:
        notes.append(f"Local conditions were recently logged as {weather.lower()}, which can affect hydration and meal comfort choices.")

    if not notes:
        notes.append("Recent health signals look fairly stable, so the nutrition guidance uses a balanced maintenance target.")
    return notes


def summarize_logs(logs: Iterable[Any], *, today: date | None = None) -> dict[str, Any]:
    current_day = today or date.today()
    daily_totals: dict[date, dict[str, float]] = defaultdict(lambda: {"calories": 0.0, "water": 0.0})

    for item in logs:
        entry_day = getattr(item, "entry_date", None) or current_day
        calories = _as_int(getattr(item, "calories", None))
        water = _as_float(getattr(item, "water_liters", None))
        if calories is not None:
            daily_totals[entry_day]["calories"] += float(calories)
        if water is not None:
            daily_totals[entry_day]["water"] += water

    today_totals = daily_totals.get(current_day, {"calories": 0.0, "water": 0.0})
    calorie_days = [int(round(values["calories"])) for values in daily_totals.values() if values["calories"] > 0]
    water_days = [values["water"] for values in daily_totals.values() if values["water"] > 0]

    avg_calories = None
    avg_water = None
    if calorie_days:
        avg_calories = int(round(sum(calorie_days) / len(calorie_days)))
    if water_days:
        avg_water = round(sum(water_days) / len(water_days), 1)

    return {
        "today_calories": int(round(today_totals["calories"])),
        "today_water_liters": round(today_totals["water"], 1),
        "avg_daily_calories_7d": avg_calories,
        "avg_daily_water_liters_7d": avg_water,
    }


def build_nutrition_summary(*, plan_tier: str, latest_record: Any, logs: Iterable[Any]) -> dict[str, Any]:
    log_summary = summarize_logs(logs)
    tier = str(plan_tier or "FREE").strip().upper() or "FREE"
    unlock_copy = (
        "Your plan includes Nutrition AI meal planning with personalized meal ideas and recipe starters."
        if tier in {"PRO", "ENTERPRISE"}
        else "Free includes calorie and water tracking. Upgrade to Pro for Nutrition AI meal plans based on symptoms, goals, and preferences."
    )
    return {
        "plan_tier": tier,
        "calorie_goal": calorie_goal_for_context(latest_record),
        "water_goal_liters": water_goal_for_context(latest_record),
        "health_context": health_context_notes(latest_record),
        "pro_unlock_message": unlock_copy,
        **log_summary,
    }
