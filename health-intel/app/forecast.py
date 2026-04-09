from typing import List


def linear_forecast(scores: List[float], steps: int = 1) -> float:
    """
    Simple linear trend projection.
    """
    if len(scores) < 2:
        return scores[-1] if scores else 0.0

    deltas = [
        scores[i + 1] - scores[i]
        for i in range(len(scores) - 1)
    ]

    avg_delta = sum(deltas) / len(deltas)
    return round(scores[-1] + avg_delta * steps, 3)
