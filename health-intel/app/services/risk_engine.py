def calculate_risk(record) -> float:
    """
    Normalize health metrics into a 0.0–1.0 risk score.
    Returns None if required fields are missing or non-numeric.
    """
    # Validate required fields exist and are not None
    required_fields = [record.systolic_bp, record.bmi, record.blood_glucose]
    if any(field is None for field in required_fields):
        print(f"Warning: Incomplete health record {record.id}. Missing required fields.")
        return None
    
    try:
        score = (
            (float(record.systolic_bp) / 180) +
            (float(record.bmi) / 40) +
            (float(record.blood_glucose) / 200)
        ) / 3

        return round(min(max(score, 0.0), 1.0), 2)
    except (ValueError, TypeError) as e:
        print(f"Warning: Could not calculate risk for record {record.id}: {e}")
        return None


def classify_risk(score: float) -> str:
    if score < 0.33:
        return "LOW"
    elif score < 0.66:
        return "MODERATE"
    return "HIGH"


def predict_next_risk(scores: list[float]) -> float:
    """
    Simple time-series trend prediction using linear slope.
    Keeps implementation dependency-free to avoid NumPy/OpenBLAS import failures.
    """
    if not scores:
        return 0.0

    if len(scores) < 2:
        return scores[-1]

    n = len(scores)
    x_values = list(range(n))
    x_mean = sum(x_values) / n
    y_mean = sum(scores) / n

    denominator = sum((x - x_mean) ** 2 for x in x_values)
    if denominator == 0:
        return round(min(max(scores[-1], 0.0), 1.0), 2)

    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, scores))
    slope = numerator / denominator
    prediction = scores[-1] + slope

    return round(min(max(prediction, 0.0), 1.0), 2)
