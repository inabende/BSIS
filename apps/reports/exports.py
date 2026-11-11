"""
Excel and CSV exports of search results.

Excel workbook:
- "Final results": one row per slide with its final result and QC details.
- One "<smear type> readings" sheet per smear type: one row per reading, with
  every field of that type as its own column.
- "About": who exported, when, with which filters, and what the columns mean.

CSV: the "Final results" table only.

Blinding: readings of slides still being read blind are left out, unless the
user is allowed to see them (reviewers / system admins of that project).
"""

import csv
from collections import defaultdict
from decimal import Decimal

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from apps.projects import permissions
from apps.qc.access import BLIND_STATUSES
from apps.smears.dynamic import DERIVED_LABELS
from apps.smears.models import FieldDefinition, Reading

FINAL_COLUMNS = [
    "Project code", "Project name", "Participant ID", "Sex", "Year of birth", "Sample ID", "Visit",
    "Collected at", "Collection site", "Slide ID", "Smear type", "Stain", "Prepared on", "Readers required",
    "Status", "Result", "Species", "Parasite density (/µL)", "Parasitaemia (%)", "How decided",
    "Readings used", "Readers disagreed", "Disagreement details", "Approved and locked", "Approved by",
    "Approved at",
]

READING_BASE_COLUMNS = [
    "Project code", "Participant ID", "Sample ID", "Visit", "Collected at", "Slide ID", "Reader number",
    "Reader", "Read at", "Reading site", "Microscope", "Result", "Species", "Parasite density (/µL)",
    "Parasitaemia (%)",
]

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe(value):
    """Stop spreadsheet programs treating typed text as a formula (CSV/formula injection)."""
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def _local(dt):
    return timezone.localtime(dt).replace(tzinfo=None) if dt else None


def _num(value):
    return float(value) if isinstance(value, Decimal) else value


def _result(obj):
    if obj is None or obj.is_positive is None:
        return ""
    return "Positive" if obj.is_positive else "Negative"


def final_row(slide):
    sample, participant, final = slide.sample, slide.sample.participant, slide.final
    return [
        slide.project.code,
        slide.project.name,
        participant.study_participant_id,
        participant.get_sex_display(),
        participant.year_of_birth,
        sample.sample_id,
        sample.visit,
        _local(sample.collected_at),
        sample.site.name if sample.site else "",
        slide.slide_id,
        slide.smear_type.name,
        slide.get_stain_display(),
        slide.prepared_on,
        slide.readers_required,
        "Approved and locked" if final and final.locked else slide.get_status_display(),
        _result(final),
        final.get_species_display() if final and final.species else "",
        _num(final.density_per_ul) if final else None,
        _num(final.parasitaemia_pct) if final else None,
        final.rule_applied if final else "",
        final.readings_used if final else "",
        ("Yes" if final.had_discordance else "No") if final else "",
        "; ".join(final.discordance_reasons) if final else "",
        ("Yes" if final.locked else "No") if final else "",
        str(final.locked_by) if final and final.locked_by else "",
        _local(final.locked_at) if final else None,
    ]


def readings_for_export(slides, user):
    """Readings the user may see for these slides, grouped by smear type."""
    if not slides:
        return []
    projects = {s.project_id: s.project for s in slides}
    sees_blind = {pk for pk, project in projects.items() if permissions.sees_blinded_results(user, project)}
    allowed_ids = [s.pk for s in slides if s.status not in BLIND_STATUSES or s.project_id in sees_blind]
    return list(
        Reading.objects.filter(slide_id__in=allowed_ids)
        .select_related("slide__project", "slide__smear_type", "slide__sample__participant", "reader", "site")
        .order_by("slide__project__code", "slide__slide_id", "reader_number")
    )


def build_csv(response, slides):
    response.write("﻿")  # BOM so Excel opens UTF-8 (µ, accents) correctly
    writer = csv.writer(response)
    writer.writerow(FINAL_COLUMNS)
    for slide in slides:
        row = final_row(slide)
        writer.writerow(["" if v is None else _safe(v) for v in row])


HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="7A1F2B")


def _write_table(sheet, headers, rows, date_columns=()):
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for row in rows:
        sheet.append([_safe(v) for v in row])
    sheet.freeze_panes = "A2"
    if rows:
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"
    for index, header in enumerate(headers, start=1):
        letter = get_column_letter(index)
        width = max(10, min(40, len(header) + 2))
        sheet.column_dimensions[letter].width = width
        if header in date_columns:
            for cell in sheet[letter][1:]:
                cell.number_format = "yyyy-mm-dd hh:mm" if header.endswith(" at") else "yyyy-mm-dd"


def _reading_value(definition, value):
    if value is None:
        return None
    if definition.data_type in FieldDefinition.CHOICE_TYPES:
        labels = dict(definition.parsed_choices())
        if isinstance(value, list):
            return ", ".join(labels.get(v, v) for v in value)
        return labels.get(value, value)
    if definition.data_type == FieldDefinition.DataType.BOOLEAN:
        return "Yes" if value else "No"
    return value


def build_xlsx(response, slides, readings, user, filters):
    workbook = Workbook()

    final_sheet = workbook.active
    final_sheet.title = "Final results"
    _write_table(
        final_sheet, FINAL_COLUMNS, [final_row(s) for s in slides],
        date_columns=("Collected at", "Prepared on", "Approved at"),
    )

    by_type = defaultdict(list)
    for reading in readings:
        by_type[reading.slide.smear_type].append(reading)
    for smear_type, type_readings in sorted(by_type.items(), key=lambda item: (item[0].order, item[0].name)):
        definitions = list(smear_type.fields.all())
        derived_keys = [k for k in DERIVED_LABELS if any(k in (r.values or {}) for r in type_readings)]
        headers = (
            READING_BASE_COLUMNS
            + [f"{d.label}{f' ({d.unit})' if d.unit else ''}" for d in definitions]
            + [DERIVED_LABELS[k][0] for k in derived_keys]
            + ["Comments"]
        )
        rows = []
        for r in type_readings:
            slide, sample = r.slide, r.slide.sample
            values = r.values or {}
            rows.append(
                [
                    slide.project.code, sample.participant.study_participant_id, sample.sample_id, sample.visit,
                    _local(sample.collected_at), slide.slide_id, r.reader_number, str(r.reader), _local(r.read_at),
                    r.site.name if r.site else "", r.microscope, _result(r),
                    r.get_species_display() if r.species else "", _num(r.density_per_ul), _num(r.parasitaemia_pct),
                ]
                + [_reading_value(d, values.get(d.key)) for d in definitions]
                + [values.get(k) for k in derived_keys]
                + [r.comments]
            )
        # Excel sheet names: max 31 characters, no / \ ? * [ ] :
        title = f"{smear_type.name} readings"
        if len(title) > 31:
            title = smear_type.name[:31]
        title = "".join("-" if ch in '/\\?*[]:' else ch for ch in title)
        _write_table(workbook.create_sheet(title), headers, rows, date_columns=("Collected at", "Read at"))

    about = workbook.create_sheet("About")
    about.column_dimensions["A"].width = 28
    about.column_dimensions["B"].width = 90
    info = [
        ("Integrated Blood Smear System – export", ""),
        ("Exported by", f"{user} ({user.username})"),
        ("Exported at", timezone.localtime().strftime("%Y-%m-%d %H:%M %Z")),
        ("Slides", len(slides)),
        ("Readings", len(readings)),
        ("", ""),
        ("Filters used", "" if filters else "None (all slides in your projects)"),
    ]
    info += [(f"  {label}", value) for label, value in filters.items()]
    info += [
        ("", ""),
        ("Notes", ""),
        ("Final results", "One row per slide. Result, species, density and parasitaemia are the slide's final "
                          "result after quality control. Blank while a slide still needs readings."),
        ("Density", "Thick smear: asexual parasites ÷ WBCs counted × WBC/µL (measured, else project default)."),
        ("Parasitaemia", "Thin smear: infected RBCs ÷ RBCs counted × 100."),
        ("Readings sheets", "One row per reading, every field as a column. Readings of slides still being read "
                            "blind are left out unless you're a reviewer or system admin for that project."),
        ("Times", "Local time of the server."),
    ]
    for row in info:
        about.append([_safe(v) for v in row])
    about["A1"].font = Font(bold=True, size=13)
    for cell in about["A"]:
        if cell.value and not str(cell.value).startswith("  "):
            cell.font = Font(bold=True)

    workbook.save(response)
