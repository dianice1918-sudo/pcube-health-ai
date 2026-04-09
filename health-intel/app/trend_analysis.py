from typing import List
from statistics import mean


def risk_trend(scores: List[float]) -> str:
    """
    Determines risk trend direction from historical scores.
    """
    if len(scores) < 2:
        return "INSUFFICIENT_DATA"

    # With two points, a single upward movement is enough to classify trend.
    if len(scores) == 2:
        if scores[1] > scores[0]:
            return "WORSENING"
        if scores[1] < scores[0]:
            return "IMPROVING"
        return "STABLE"

    first_half = mean(scores[: len(scores)//2])
    second_half = mean(scores[len(scores)//2 :])

    if second_half > first_half + 0.05:
        return "WORSENING"
    elif second_half < first_half - 0.05:
        return "IMPROVING"
    return "STABLE"
