"""
Slide- and reading-level rules, on top of the project rules in
apps/projects/permissions.py.

Blinding (FR-12): while a slide still needs readings (awaiting reader 2,
or discordant and awaiting a tie-breaker), a reading's result is visible
only to the person who read it, reviewers and system admins. Once the slide
has a final result, every member can see all readings.
"""

from apps.projects import permissions
from apps.smears.models import Slide

BLIND_STATUSES = {Slide.Status.READING, Slide.Status.DISCORDANT}


def is_blind(slide):
    return slide.status in BLIND_STATUSES


def can_see_reading(user, slide, reading):
    if not is_blind(slide):
        return True
    return reading.reader_id == user.pk or permissions.sees_blinded_results(user, slide.project)


def next_reader_number(slide):
    """2 while awaiting a second reading, 3 while awaiting a tie-breaker, else None."""
    return {Slide.Status.READING: 2, Slide.Status.DISCORDANT: 3}.get(slide.status)


def can_add_reading(user, slide):
    return (
        next_reader_number(slide) is not None
        and not slide.is_locked
        and permissions.can_enter_data(user, slide.project)
    )


def can_edit_reading(user, slide, reading):
    return (
        not slide.is_locked
        and permissions.can_enter_data(user, slide.project)
        and can_see_reading(user, slide, reading)
    )


def can_edit_slide(user, slide):
    return not slide.is_locked and permissions.can_enter_data(user, slide.project)


def can_lock(user, slide):
    final = slide.final
    return bool(final and not final.locked and permissions.can_review(user, slide.project))


def can_unlock(user, slide):
    return slide.is_locked and permissions.can_review(user, slide.project)
