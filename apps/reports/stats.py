"""
Summary statistics for the reports dashboard, computed in the database.

Everything is based on *final* results (after quality control) for one smear
type at a time. Slides still awaiting readings are counted separately.
"""

import math

from django.db.models import Avg, Count, F, Q
from django.db.models.functions import Ln, TruncMonth

from apps.smears.models import READING_SPECIES_CHOICES, Slide

SPECIES_LABELS = dict(READING_SPECIES_CHOICES)

# Parasite density bands (/µL) for the distribution chart.
DENSITY_BANDS = [
    ("< 100", 0, 100),
    ("100 – 999", 100, 1_000),
    ("1,000 – 9,999", 1_000, 10_000),
    ("10,000 – 99,999", 10_000, 100_000),
    ("≥ 100,000", 100_000, None),
]


def _pct(part, whole):
    return round(100 * part / whole, 1) if whole else None


def dashboard_stats(slides):
    """`slides` is a Slide queryset already limited to the user's projects, the filters and one smear type."""
    finals = slides.filter(final_result__isnull=False)
    with_result = finals.filter(final_result__is_positive__isnull=False)
    positives = with_result.filter(final_result__is_positive=True)

    totals = slides.aggregate(
        slides=Count("pk"),
        awaiting=Count("pk", filter=Q(status__in=[Slide.Status.READING, Slide.Status.DISCORDANT])),
        final=Count("pk", filter=Q(final_result__isnull=False)),
        locked=Count("pk", filter=Q(final_result__locked=True)),
        positive=Count("pk", filter=Q(final_result__is_positive=True)),
        negative=Count("pk", filter=Q(final_result__is_positive=False)),
        double_read=Count("pk", filter=Q(final_result__isnull=False, readers_required=2)),
        discordant=Count("pk", filter=Q(final_result__had_discordance=True)),
    )
    totals["positivity"] = _pct(totals["positive"], totals["positive"] + totals["negative"])
    totals["discordance_rate"] = _pct(totals["discordant"], totals["double_read"])

    log_mean = positives.filter(final_result__density_per_ul__gt=0).aggregate(
        v=Avg(Ln(F("final_result__density_per_ul")))
    )["v"]
    totals["geo_mean_density"] = round(math.exp(log_mean)) if log_mean is not None else None

    by_project = []
    for row in (
        slides.values("project__code", "project__name")
        .annotate(
            final=Count("pk", filter=Q(final_result__isnull=False)),
            positive=Count("pk", filter=Q(final_result__is_positive=True)),
            negative=Count("pk", filter=Q(final_result__is_positive=False)),
            awaiting=Count("pk", filter=Q(status__in=[Slide.Status.READING, Slide.Status.DISCORDANT])),
            double_read=Count("pk", filter=Q(final_result__isnull=False, readers_required=2)),
            discordant=Count("pk", filter=Q(final_result__had_discordance=True)),
        )
        .order_by("project__code")
    ):
        row["positivity"] = _pct(row["positive"], row["positive"] + row["negative"])
        row["discordance_rate"] = _pct(row["discordant"], row["double_read"])
        by_project.append(row)

    species = [
        {"label": SPECIES_LABELS.get(row["final_result__species"]) or "Not recorded", "count": row["n"]}
        for row in positives.values("final_result__species").annotate(n=Count("pk")).order_by("-n")
    ]

    density = []
    for label, low, high in DENSITY_BANDS:
        band = positives.filter(final_result__density_per_ul__gte=low)
        if high is not None:
            band = band.filter(final_result__density_per_ul__lt=high)
        density.append({"label": label, "count": band.count()})
    has_density = any(b["count"] for b in density)

    monthly = []
    for row in (
        with_result.annotate(month=TruncMonth("sample__collected_at"))
        .values("month")
        .annotate(
            total=Count("pk"),
            positive=Count("pk", filter=Q(final_result__is_positive=True)),
        )
        .order_by("month")
    ):
        monthly.append(
            {
                "label": row["month"].strftime("%b %Y"),
                "total": row["total"],
                "positive": row["positive"],
                "positivity": _pct(row["positive"], row["total"]),
            }
        )

    return {
        "totals": totals,
        "by_project": by_project,
        "species": species,
        "density": density if has_density else [],
        "monthly": monthly,
        "has_positivity": (totals["positive"] + totals["negative"]) > 0,
    }
