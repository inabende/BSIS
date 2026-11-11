"""Keeps each slide's status and final result up to date as readings change."""

from django.db import transaction

from .models import FinalResult, qc_settings_for
from .rules import decide


@transaction.atomic
def evaluate_slide(slide):
    """Recompute status and final result from the slide's readings. Locked results are left alone."""
    final = slide.final
    if final and final.locked:
        return final

    settings = qc_settings_for(slide.project)
    readings = list(slide.readings.all())
    status, values, reasons = decide(
        readings, slide.readers_required, settings.density_threshold_pct, settings.final_rule
    )

    if values is None:
        if final:
            final.delete()
        final = None
    else:
        final = final or FinalResult(slide=slide)
        for key, value in values.items():
            setattr(final, key, value)
        final.had_discordance = bool(reasons)
        final.discordance_reasons = reasons
        final.save()

    if slide.status != status:
        slide.status = status
        slide.save(update_fields=["status", "updated_at"])
    # Forget the cached final result so callers see the new state.
    slide._state.fields_cache.pop("final_result", None)
    return final


def discordance_for(slide):
    """Current disagreement between readers 1 and 2 (for slides awaiting a tie-breaker)."""
    from .rules import discordance_reasons

    by_number = {r.reader_number: r for r in slide.readings.all()}
    if 1 in by_number and 2 in by_number:
        return discordance_reasons(by_number[1], by_number[2], qc_settings_for(slide.project).density_threshold_pct)
    return []
