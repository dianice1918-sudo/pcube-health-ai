from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


SYMPTOM_TOPICS = {
    "Headache or migraine": ("headache", "migraine"),
    "Fever or infection signals": ("fever", "chills", "temperature"),
    "Cough or throat symptoms": ("cough", "sore throat", "congestion", "cold"),
    "Stomach or nausea symptoms": ("stomach", "abdominal", "nausea", "vomiting", "diarrhea", "reflux"),
    "Fatigue or dizziness": ("fatigue", "tired", "weakness", "dizziness"),
    "Sleep concerns": ("sleep", "insomnia", "restless"),
    "Blood sugar questions": ("glucose", "blood sugar"),
}

GOAL_TOPICS = {
    "Hydration focus": ("hydration", "water", "thirst"),
    "Weight balance": ("weight", "fat loss", "lose weight", "gain weight"),
    "Energy support": ("energy", "fatigue", "focus"),
    "Heart health": ("heart", "cholesterol", "blood pressure"),
    "Blood sugar balance": ("glucose", "blood sugar", "a1c"),
    "Muscle and protein support": ("protein", "strength", "recovery"),
}

MEAL_PATTERNS = {
    "lighter soups or broth-style meals": ("soup", "broth"),
    "fiber-first breakfasts like oats or fruit": ("oats", "oatmeal", "fruit", "fiber"),
    "protein-forward meals": ("protein", "eggs", "beans", "fish", "chicken", "yogurt"),
    "vegetable-rich plates": ("vegetable", "greens", "salad"),
    "simple stomach-friendly foods": ("banana", "rice", "toast", "cracker", "bland"),
}


def _flatten_texts(items: Iterable[Any], fields: Iterable[str]) -> list[str]:
    values: list[str] = []
    for item in items:
        for field in fields:
            value = getattr(item, field, None)
            clean = " ".join(str(value or "").split()).strip().lower()
            if clean:
                values.append(clean)
    return values


def _match_counter(texts: Iterable[str], keyword_map: dict[str, tuple[str, ...]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for text in texts:
        for label, keywords in keyword_map.items():
            if any(keyword in text for keyword in keywords):
                counter[label] += 1
    return counter


def _to_peer_item(title: str, detail: str, evidence: str | None = None) -> dict[str, str]:
    item = {"title": title, "detail": detail}
    if evidence:
        item["evidence"] = evidence
    return item


def build_peer_insights(
    *,
    cohort_size: int,
    latest_peer_records: Iterable[Any],
    peer_messages: Iterable[Any],
    peer_logs: Iterable[Any],
    current_messages: Iterable[Any],
    current_logs: Iterable[Any],
) -> dict[str, Any]:
    privacy_note = (
        "Peer Insights only shows anonymized group patterns. No names, exact records, or raw messages from other users are exposed."
    )
    if cohort_size < 3:
        return {
            "cohort_size": int(cohort_size),
            "overview": "Not enough anonymized peer activity is available yet. Insights will appear once at least 3 peers have recent records or logs.",
            "matched_topics": [],
            "habit_trends": [],
            "symptom_patterns": [],
            "nutrition_patterns": [],
            "privacy_note": privacy_note,
        }

    peer_records = list(latest_peer_records)
    peer_message_list = list(peer_messages)
    peer_log_list = list(peer_logs)
    current_topics_source = _flatten_texts(current_messages, ("question",)) + _flatten_texts(
        current_logs,
        ("symptoms", "goals", "notes"),
    )
    peer_symptom_source = _flatten_texts(peer_message_list, ("question",)) + _flatten_texts(
        peer_log_list,
        ("symptoms",),
    )
    peer_goal_source = _flatten_texts(peer_log_list, ("goals", "notes", "meal_type"))

    current_symptom_topics = _match_counter(current_topics_source, SYMPTOM_TOPICS)
    current_goal_topics = _match_counter(current_topics_source, GOAL_TOPICS)
    peer_symptom_topics = _match_counter(peer_symptom_source, SYMPTOM_TOPICS)
    peer_goal_topics = _match_counter(peer_goal_source, GOAL_TOPICS)
    peer_meal_topics = _match_counter(peer_goal_source, MEAL_PATTERNS)

    matched_topics: list[str] = []
    for label, _count in current_symptom_topics.most_common(3):
        if peer_symptom_topics.get(label):
            matched_topics.append(label)
    for label, _count in current_goal_topics.most_common(2):
        if peer_goal_topics.get(label) and label not in matched_topics:
            matched_topics.append(label)

    hydration_values = [
        float(value)
        for value in (getattr(record, "hydration_liters", None) for record in peer_records)
        if value is not None
    ]
    step_values = [
        int(value)
        for value in (getattr(record, "steps_count", None) for record in peer_records)
        if value is not None
    ]
    glucose_values = [
        float(value)
        for value in (getattr(record, "blood_glucose", None) for record in peer_records)
        if value is not None
    ]

    habit_trends: list[dict[str, str]] = []
    if hydration_values:
        avg_hydration = round(sum(hydration_values) / len(hydration_values), 1)
        detail = (
            "Peers in your cohort are averaging solid daily hydration."
            if avg_hydration >= 2.0
            else "Peer hydration is below the ideal daily target, so water consistency remains a common improvement area."
        )
        habit_trends.append(
            _to_peer_item(
                "Hydration trend",
                detail,
                f"Average logged hydration across peers: {avg_hydration} L.",
            )
        )

    if step_values:
        avg_steps = int(round(sum(step_values) / len(step_values)))
        detail = (
            "Movement patterns are strong across the cohort."
            if avg_steps >= 7000
            else "Many peers are still below the daily walking target, so activity remains a frequent focus."
        )
        habit_trends.append(
            _to_peer_item(
                "Movement trend",
                detail,
                f"Average latest steps across peers: {avg_steps}.",
            )
        )

    if glucose_values:
        elevated = sum(1 for value in glucose_values if value >= 100)
        habit_trends.append(
            _to_peer_item(
                "Blood sugar watch",
                "A meaningful share of peers are tracking meal balance around glucose-sensitive patterns.",
                f"{elevated} of {len(glucose_values)} peers had latest glucose at or above 100 mg/dL.",
            )
        )

    if not habit_trends:
        habit_trends.append(
            _to_peer_item(
                "Emerging cohort",
                "There is peer activity in the workspace, but not enough structured wellness data yet for stronger habit comparisons.",
            )
        )

    symptom_patterns: list[dict[str, str]] = []
    for label, count in peer_symptom_topics.most_common(3):
        detail = "This topic appears often in anonymized peer symptom check-ins."
        if label in matched_topics:
            detail = "This aligns with topics showing up in your own recent activity, so it is likely more relevant to you."
        symptom_patterns.append(
            _to_peer_item(
                label,
                detail,
                f"{count} peer entries matched this theme.",
            )
        )
    if not symptom_patterns:
        symptom_patterns.append(
            _to_peer_item(
                "No strong symptom cluster yet",
                "Recent peer activity is still too varied to show a reliable symptom theme.",
            )
        )

    nutrition_patterns: list[dict[str, str]] = []
    combined_nutrition = Counter(peer_goal_topics)
    for label, count in peer_meal_topics.items():
        combined_nutrition[label] += count
    for label, count in combined_nutrition.most_common(3):
        detail = "This meal or goal pattern shows up repeatedly in anonymized peer logs."
        if label in matched_topics:
            detail = "This also overlaps with themes from your recent activity, so it may be especially relevant."
        nutrition_patterns.append(
            _to_peer_item(
                label,
                detail,
                f"{count} anonymized nutrition entries matched this theme.",
            )
        )
    if not nutrition_patterns:
        nutrition_patterns.append(
            _to_peer_item(
                "Nutrition logging is still growing",
                "Peers have not logged enough meal notes yet to surface a reliable pattern.",
            )
        )

    overview = (
        f"These anonymized insights are based on {cohort_size} peers with recent activity in your workspace. "
        "They are meant to show group-level patterns you can compare against your own habits, not medical advice."
    )
    if matched_topics:
        overview += f" The topics closest to your recent activity are: {', '.join(matched_topics[:3])}."

    return {
        "cohort_size": int(cohort_size),
        "overview": overview,
        "matched_topics": matched_topics[:4],
        "habit_trends": habit_trends[:3],
        "symptom_patterns": symptom_patterns[:3],
        "nutrition_patterns": nutrition_patterns[:3],
        "privacy_note": privacy_note,
    }
