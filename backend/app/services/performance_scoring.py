"""Authoritative decimal scoring, independent of persistence and the UI."""
from decimal import Decimal, ROUND_HALF_UP

D = Decimal
CENT = D("0.01")


def rating_for(score, levels):
    score = D(str(score)).quantize(CENT, rounding=ROUND_HALF_UP)
    for level in levels:
        if D(level["minimum"]) <= score <= D(level["maximum"]):
            return level["label"]
    raise ValueError("Score falls outside the configured rating ranges")


def validate_rating(value, levels):
    value = D(str(value))
    if not D(levels[0]["minimum"]) <= value <= D(levels[-1]["maximum"]):
        raise ValueError("Rating outside the configured scale")
    rating_for(value, levels)
    return value


def automatic_rating(definition, actual, progress, levels):
    """Achievement is linearly mapped across the entire scale up to the goal's cap.
    Zero targets use distance from zero (one unit tolerance); zero lower actual
    meets the cap for positive targets. Negative lower/higher targets require
    manual assessment; target-is-best supports negative and zero targets.
    """
    kind, direction = definition["measurement"], definition["direction"]
    cap = D(str(definition.get("scoring_cap", 120)))
    if kind == "QUALITATIVE":
        raise ValueError("Qualitative goals require a manual rating")
    target = D(str(definition.get("target") or 0))
    if direction == "MILESTONE" or kind == "MILESTONE":
        achievement = D(str(progress))
    elif kind == "BOOLEAN":
        if actual is None or D(str(actual)) not in (0, 1):
            raise ValueError("Boolean actual must be 0 or 1")
        achievement = D(100) if D(str(actual)) == target else D(0)
    else:
        if actual is None:
            raise ValueError("Actual is required for automatic scoring")
        actual = D(str(actual))
        if direction == "TARGET_IS_BEST":
            achievement = max(D(0), D(100) * (1 - abs(actual - target) / (abs(target) or 1)))
        elif target < 0 or actual < 0:
            raise ValueError("Negative targets/actuals require target-is-best or manual scoring")
        elif direction == "LOWER_IS_BETTER":
            achievement = cap if actual == 0 else (target / actual * 100 if target else max(D(0), 100 * (1 - actual)))
        else:
            achievement = actual / target * 100 if target else (D(100) if actual == 0 else cap)
    low, high = D(levels[0]["minimum"]), D(levels[-1]["maximum"])
    return (low + (high - low) * min(cap, max(D(0), achievement)) / cap).quantize(CENT, rounding=ROUND_HALF_UP)


def weighted(items):
    total = sum((D(str(weight)) for _, weight in items), D(0))
    if not total:
        raise ValueError("At least one positive weight is required")
    return sum((D(str(value)) * D(str(weight)) for value, weight in items), D(0)) / total


def calculate(goals, competencies, manager, config):
    levels = config["rating_scale"]["levels"]
    goal_ratings = {item["id"]: item["rating"] for item in manager.get("goals", [])}
    competency_ratings = {item["id"]: item["rating"] for item in manager.get("competencies", [])}
    kpi, competency = D(0), D(0)
    if D(config["kpi_weight"]) > 0:
        if sum((D(str(goal.weight)) for goal in goals), D(0)) != 100:
            raise ValueError("Active KPI weights must total 100")
        values = []
        for goal in goals:
            value = goal_ratings.get(str(goal.id))
            if value is None and config["auto_scoring"]:
                value = automatic_rating(goal.definition, goal.actual, goal.progress, levels)
            if value is None:
                raise ValueError(f"Manager rating required for {goal.title}")
            values.append((validate_rating(value, levels), goal.weight))
        kpi = weighted(values)
    if D(config["competency_weight"]) > 0:
        values = []
        for item in competencies:
            value = competency_ratings.get(item["id"])
            if value is None:
                raise ValueError(f"Manager rating required for {item['name']}")
            values.append((validate_rating(value, levels), item["weight"]))
        competency = weighted(values)
    final = (kpi * D(config["kpi_weight"]) / 100 + competency * D(config["competency_weight"]) / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    return {"kpi": str(kpi.quantize(CENT, rounding=ROUND_HALF_UP)), "competency": str(competency.quantize(CENT, rounding=ROUND_HALF_UP)), "pre_calibration": str(final), "pre_calibration_rating": rating_for(final, levels)}
