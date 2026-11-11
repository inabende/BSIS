"""
Comparing readings and deciding a slide's final result (FR-12 – FR-14).

Pure functions on Reading-like objects (anything with is_positive, species,
density_per_ul, parasitaemia_pct, reader_number), so they're easy to test.

Discordance — two readings disagree when any of these is true:
- one is positive and the other negative;
- both positive but the species differ;
- both positive and their density (or parasitaemia) differs by more than
  the project's threshold, measured as |a − b| ÷ mean(a, b) × 100.

Readings with no positive/negative (e.g. hematology) aren't compared
automatically; they always "agree" and the final result follows reader 1.
"""

from decimal import ROUND_HALF_UP, Decimal

TIEBREAKER = "tiebreaker"
CLOSEST_TWO = "closest_two"


def percent_difference(a, b):
    a, b = Decimal(a), Decimal(b)
    mean = (a + b) / 2
    if mean == 0:
        return Decimal(0)
    return abs(a - b) / mean * 100


def discordance_reasons(first, second, threshold_pct):
    """Human-readable reasons the two readings disagree; empty list if they agree."""
    reasons = []
    if first.is_positive is None or second.is_positive is None:
        return reasons
    if first.is_positive != second.is_positive:
        reasons.append(
            f"Reader {first.reader_number} {'positive' if first.is_positive else 'negative'}, "
            f"reader {second.reader_number} {'positive' if second.is_positive else 'negative'}"
        )
        return reasons
    if not first.is_positive:
        return reasons
    if first.species != second.species:
        reasons.append(
            f"Species differ: reader {first.reader_number} {first.get_species_display() or 'none'}, "
            f"reader {second.reader_number} {second.get_species_display() or 'none'}"
        )
    for attr, label, unit in (("density_per_ul", "Density", "/µL"), ("parasitaemia_pct", "Parasitaemia", "%")):
        a, b = getattr(first, attr), getattr(second, attr)
        if a is None or b is None:
            continue
        diff = percent_difference(a, b)
        if diff > threshold_pct:
            reasons.append(
                f"{label} differs by {diff.quantize(Decimal(1), ROUND_HALF_UP)}% "
                f"({_fmt(a)} vs {_fmt(b)}{unit}; limit {threshold_pct}%)"
            )
    return reasons


def _fmt(value):
    value = Decimal(value)
    return f"{value.normalize():,f}" if value != value.to_integral() else f"{int(value):,}"


def _mean(values):
    values = [Decimal(v) for v in values if v is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _q(value, places):
    if value is None:
        return None
    return Decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _from_one(reading, rule):
    return {
        "is_positive": reading.is_positive,
        "species": reading.species,
        "density_per_ul": reading.density_per_ul,
        "parasitaemia_pct": reading.parasitaemia_pct,
        "rule_applied": rule,
        "readings_used": str(reading.reader_number),
    }


def _mean_of(readings, rule):
    first = readings[0]
    return {
        "is_positive": first.is_positive,
        "species": first.species,
        "density_per_ul": _q(_mean(r.density_per_ul for r in readings), 2),
        "parasitaemia_pct": _q(_mean(r.parasitaemia_pct for r in readings), 4),
        "rule_applied": rule,
        "readings_used": ",".join(str(r.reader_number) for r in readings),
    }


def _closest_pair(readings, attr):
    """The two readings whose `attr` values are closest together."""
    best = None
    for i, a in enumerate(readings):
        for b in readings[i + 1:]:
            va, vb = getattr(a, attr), getattr(b, attr)
            if va is None or vb is None:
                continue
            gap = abs(Decimal(va) - Decimal(vb))
            if best is None or gap < best[0]:
                best = (gap, a, b)
    return [best[1], best[2]] if best else None


def decide(readings, readers_required, threshold_pct, final_rule):
    """
    Work out where a slide stands.

    Returns (status, final, reasons):
      status  – "pending", "reading", "discordant" or "final"
      final   – dict of final-result values, or None
      reasons – discordance reasons between readers 1 and 2 (may be non-empty even when final)
    """
    by_number = {r.reader_number: r for r in readings}
    r1, r2, r3 = by_number.get(1), by_number.get(2), by_number.get(3)

    if not r1:
        return "pending", None, []
    if readers_required <= 1:
        return "final", _from_one(r1, "Single reader"), []
    if not r2:
        return "reading", None, []

    reasons = discordance_reasons(r1, r2, threshold_pct)
    if not reasons:
        if r1.is_positive:
            return "final", _mean_of([r1, r2], "Readers 1 and 2 agree; mean of their values"), []
        return "final", _from_one(r1, "Readers 1 and 2 agree") | {"readings_used": "1,2"}, []
    if not r3:
        return "discordant", None, reasons

    if final_rule == CLOSEST_TWO:
        return "final", _closest_two(r1, r2, r3), reasons
    return "final", _from_one(r3, "Discordant; tie-breaker (reader 3) decides"), reasons


def _closest_two(r1, r2, r3):
    readings = [r1, r2, r3]
    # Positive/negative by majority (there are 3 readings, so there's always one).
    positives = [r for r in readings if r.is_positive]
    negatives = [r for r in readings if r.is_positive is False]
    if len(negatives) > len(positives):
        return _from_one(r3 if r3.is_positive is False else negatives[0], "Discordant; majority negative") | {
            "readings_used": ",".join(str(r.reader_number) for r in negatives)
        }
    # Species by majority among positives; otherwise the tie-breaker's.
    species_votes = {}
    for r in positives:
        species_votes.setdefault(r.species, []).append(r)
    majority = [group for group in species_votes.values() if len(group) >= 2]
    agreeing = majority[0] if majority else [r3] if r3.is_positive else positives
    species = agreeing[0].species

    attr = "density_per_ul" if any(r.density_per_ul is not None for r in agreeing) else "parasitaemia_pct"
    pair = _closest_pair(agreeing, attr) if len(agreeing) >= 2 else None
    if pair:
        result = _mean_of(sorted(pair, key=lambda r: r.reader_number),
                          "Discordant; majority result, mean of the two closest readings")
    else:
        result = _from_one(agreeing[0], "Discordant; majority result")
    result["species"] = species
    result["is_positive"] = True
    return result
