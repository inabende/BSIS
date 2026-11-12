"""
Checking and importing rows of an uploaded file.

Each row becomes (at most) one participant, one sample, one slide with a
single reading, and that slide's final result. Imported history is treated
as already complete: slides are single-reader and final, but not locked, so
a reviewer still approves them.

check(batch) reads the file, applies the column mapping and returns a report
without saving anything. run_import(batch, user) repeats the check and saves
the valid rows in one transaction.
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.projects.models import ProjectMembership
from apps.qc.services import evaluate_slide
from apps.samples.models import Participant, Sample
from apps.smears.calculations import calculate
from apps.smears.models import READING_SPECIES_CHOICES, FieldDefinition, Reading, Slide

from . import parsing
from .parsing import ParseError, norm

Role = ProjectMembership.Role
DT = FieldDefinition.DataType
SPECIES_LABELS = dict(READING_SPECIES_CHOICES)


# --- What a column can be mapped to --------------------------------------------


@dataclass
class Target:
    key: str
    label: str
    group: str                 # "Participant & sample", "Slide & reading", "Result"
    required: bool = False
    help: str = ""
    aliases: tuple = ()
    definition: FieldDefinition = None


COMMON_TARGETS = [
    Target("participant_id", "Participant ID", "Participant & sample", required=True,
           aliases=("participant", "participantid", "ptid", "pid", "subjectid", "subject", "studyid", "studyno",
                    "studynumber", "participantno", "screeningid")),
    Target("sex", "Sex", "Participant & sample", aliases=("sex", "gender")),
    Target("year_of_birth", "Year of birth", "Participant & sample", aliases=("yearofbirth", "yob", "birthyear")),
    Target("sample_id", "Sample ID", "Participant & sample",
           help="If not mapped or blank, made from participant ID + collection date (e.g. PT-001-20260915).",
           aliases=("sampleid", "sample", "specimenid", "specimen", "barcode", "labid", "labno", "sampleno")),
    Target("collected_date", "Collection date", "Participant & sample", required=True,
           aliases=("collectiondate", "datecollected", "collected", "sampledate", "date", "visitdate",
                    "dateofcollection", "collectedat", "datesampled")),
    Target("collected_time", "Collection time", "Participant & sample",
           help="Optional. Without it, collection time is recorded as 00:00.",
           aliases=("collectiontime", "timecollected", "time", "timeofcollection")),
    Target("visit", "Visit", "Participant & sample", aliases=("visit", "timepoint", "visitday", "day", "visitname")),
    Target("site", "Site", "Participant & sample", help="Site code or name; must be one of the project's sites.",
           aliases=("site", "sitecode", "clinic", "facility", "studysite")),
    Target("slide_id", "Slide ID", "Slide & reading",
           help="If not mapped or blank, made from sample ID + the smear type suffix.",
           aliases=("slideid", "slide", "slideno", "slidenumber")),
    Target("reader", "Reader", "Slide & reading",
           help="Username or full name of a project reader/lead. Others are recorded as you, "
                "with the name from the file kept on the reading.",
           aliases=("reader", "microscopist", "readby", "readername", "reader1")),
    Target("read_date", "Date read", "Slide & reading", help="If not mapped, the collection date is used.",
           aliases=("readdate", "dateread", "readingdate", "dateofreading")),
    Target("comments", "Comments", "Slide & reading", aliases=("comments", "comment", "remarks", "notes", "note")),
]

# Extra column names for built-in smear fields, beyond their key and label.
FIELD_ALIASES = {
    "result": ("bsresult", "malariaresult", "mps", "bs", "outcome", "bloodsmear", "bsforMPs", "smearresult"),
    "species": ("plasmodiumspecies", "parasitespecies", "spp"),
    "asexual_parasites_counted": ("parasites", "parasitecount", "asexual", "asexualcount", "parasitescounted",
                                  "asexualparasites", "trophozoites"),
    "wbc_counted": ("wbc", "wbcs", "wbccount", "whitecellscounted", "wbcscounted"),
    "gametocytes_counted": ("gametocytes", "gametocytecount", "gamcount"),
    "gametocytes_present": ("gametocytesseen", "gametocytespresent", "gams"),
    "rbc_counted": ("rbc", "rbcs", "rbccount", "rbcscounted"),
    "infected_rbc": ("infected", "infectedrbcs", "parasitizedrbc", "parasitisedrbc", "irbc"),
}


def targets_for(smear_type):
    targets = list(COMMON_TARGETS)
    for definition in smear_type.active_fields():
        aliases = (norm(definition.key), norm(definition.label)) + FIELD_ALIASES.get(definition.key, ())
        targets.append(Target(
            f"field:{definition.key}", definition.label, "Result",
            required=definition.required, help=definition.help_text, aliases=aliases, definition=definition,
        ))
    if smear_type.calculation == "thick_density":
        targets.append(Target(
            "density_reported", "Parasite density as recorded (/µL)", "Result",
            help="For files that only record the density. If counts are also mapped, the density is "
                 "calculated from the counts and compared with this.",
            aliases=("density", "parasitedensity", "parasitesul", "parasitesperul", "parasitespermicrolitre",
                     "pd", "asexualdensity", "densityul"),
        ))
    if smear_type.calculation == "thin_parasitaemia":
        targets.append(Target(
            "parasitaemia_reported", "Parasitaemia as recorded (%)", "Result",
            help="For files that only record parasitaemia.",
            aliases=("parasitaemia", "parasitemia", "parasitaemiapct", "pct", "percentparasitaemia"),
        ))
    return targets


def auto_map(columns, targets):
    """Guess target → column from column names. Each column is used at most once."""
    mapping, used = {}, set()
    by_norm = {norm(c): c for c in columns}
    for target in targets:
        for alias in (norm(target.key.replace("field:", "")), norm(target.label)) + tuple(norm(a) for a in target.aliases):
            column = by_norm.get(alias)
            if column and column not in used:
                mapping[target.key] = column
                used.add(column)
                break
    return mapping


# --- Checking rows ---------------------------------------------------------------


@dataclass
class RowPlan:
    row: int
    participant_id: str = ""
    participant: dict = field(default_factory=dict)
    sample_id: str = ""
    sample: dict = field(default_factory=dict)
    slide_id: str = ""
    reading: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    skipped: str = ""


class Checker:
    def __init__(self, batch, user):
        self.batch = batch
        self.user = user
        self.project = batch.project
        self.smear_type = batch.smear_type
        self.targets = {t.key: t for t in targets_for(self.smear_type)}
        self.mapping = {k: v for k, v in (batch.mapping or {}).items() if k in self.targets and v}
        self.sites = list(self.project.sites.all())
        readers = (
            ProjectMembership.objects.filter(project=self.project, role__in=[Role.LEAD, Role.READER],
                                             user__is_active=True)
            .select_related("user")
        )
        self.readers = {}
        for m in readers:
            self.readers[m.user.username.lower()] = m.user
            if m.user.get_full_name():
                self.readers[norm(m.user.get_full_name())] = m.user
        # State from the database and from earlier rows in this file.
        self.existing_participants = dict(
            Participant.objects.filter(project=self.project).values_list("study_participant_id", "pk")
        )
        self.existing_participants_ci = {k.lower(): k for k in self.existing_participants}
        self.existing_samples = {
            sid.lower(): pid for sid, pid in
            Sample.objects.filter(project=self.project).values_list("sample_id", "participant__study_participant_id")
        }
        self.existing_slides = {s.lower() for s in Slide.objects.filter(project=self.project).values_list("slide_id", flat=True)}
        self.file_samples = {}
        self.file_slides = set()

    def cell(self, values, key):
        column = self.mapping.get(key)
        return values.get(column) if column else None

    def check_all(self, table):
        return [self.check_row(row_number, values) for row_number, values in table.rows]

    def check_row(self, row_number, values):
        plan = RowPlan(row=row_number)
        order = self.batch.date_order

        def parse(key, fn, *args):
            try:
                return fn(self.cell(values, key), *args)
            except ParseError as error:
                plan.errors.append(f"{self.targets[key].label}: {error}")
                return None

        # Participant
        pid = parsing.as_text(self.cell(values, "participant_id"))
        if not pid:
            plan.errors.append("Participant ID is blank.")
        plan.participant_id = self.existing_participants_ci.get(pid.lower(), pid)
        plan.participant["sex"] = parse("sex", parsing.as_choice, Participant.Sex.choices, "sex") or "U"
        yob = parse("year_of_birth", parsing.as_number)
        if yob is not None:
            if yob != int(yob) or not (1900 <= int(yob) <= timezone.now().year):
                plan.errors.append(f"Year of birth: '{yob}' isn't a valid year.")
            else:
                plan.participant["year_of_birth"] = int(yob)

        # Sample
        collected_date = parse("collected_date", parsing.as_date, order)
        if collected_date is None and not any(e.startswith("Collection date") for e in plan.errors):
            plan.errors.append("Collection date is blank.")
        collected_time = parse("collected_time", parsing.as_time) or time(0, 0)
        collected_at = None
        if collected_date:
            collected_at = timezone.make_aware(datetime.combine(collected_date, collected_time))
            if collected_at > timezone.now():
                plan.errors.append(f"Collection date {collected_date:%d/%m/%Y} is in the future.")
        sample_id = parsing.as_text(self.cell(values, "sample_id"))
        if not sample_id and pid and collected_date:
            sample_id = f"{pid}-{collected_date:%Y%m%d}"
        plan.sample_id = sample_id
        site = None
        site_text = parsing.as_text(self.cell(values, "site"))
        if site_text:
            site = next((s for s in self.sites if norm(site_text) in (norm(s.code), norm(s.name))), None)
            if site is None:
                plan.errors.append(f"Site: '{site_text}' isn't one of this project's sites "
                                   f"({', '.join(s.code for s in self.sites) or 'none set up'}).")
        plan.sample = {"visit": parsing.as_text(self.cell(values, "visit")), "collected_at": collected_at,
                       "site": site}
        if sample_id and pid:
            owner = self.existing_samples.get(sample_id.lower()) or self.file_samples.get(sample_id.lower())
            if owner and owner.lower() != pid.lower():
                plan.errors.append(f"Sample {sample_id} already belongs to participant {owner}, not {pid}.")

        # Slide
        slide_id = parsing.as_text(self.cell(values, "slide_id"))
        if not slide_id and sample_id:
            slide_id = f"{sample_id}-{self.smear_type.slide_suffix}"
        plan.slide_id = slide_id
        if slide_id.lower() in self.file_slides:
            plan.errors.append(f"Slide {slide_id} appears more than once in this file.")
        elif slide_id.lower() in self.existing_slides:
            if self.batch.on_existing_slide == "skip":
                plan.skipped = f"Slide {slide_id} already exists in this project."
            else:
                plan.errors.append(f"Slide {slide_id} already exists in this project.")

        # Reading
        reader_text = parsing.as_text(self.cell(values, "reader"))
        reader = None
        if reader_text:
            reader = self.readers.get(reader_text.lower()) or self.readers.get(norm(reader_text))
            if reader is None:
                plan.warnings.append(f"Reader '{reader_text}' isn't a reader in this project; recorded as "
                                     f"{self.user}, with the original name kept.")
        read_date = parse("read_date", parsing.as_date, order)
        read_at = timezone.make_aware(datetime.combine(read_date, time(12, 0))) if read_date else collected_at
        if read_at and collected_at and read_at < collected_at.replace(hour=0, minute=0):
            plan.errors.append("Date read is before the collection date.")
        plan.reading = {"reader": reader or self.user, "read_at": read_at, "site": site,
                        "comments": parsing.as_text(self.cell(values, "comments")),
                        "original_reader": reader_text if reader is None and reader_text else ""}

        # Result fields
        values_json = self.field_values(values, plan)
        if not plan.errors:
            try:
                plan.results = calculate(self.smear_type, values_json, self.project)
            except ValidationError as error:
                for key, messages in error.message_dict.items():
                    label = self.targets.get(f"field:{key}") or self.targets.get(key)
                    for message in messages:
                        plan.errors.append(f"{label.label}: {message}" if label else message)
        if plan.results:
            reported = values_json.get("density_reported")
            calc = plan.results.get("density_per_ul")
            if reported and calc is not None and values_json.get("wbc_counted"):
                if abs(Decimal(str(reported)) - calc) > max(Decimal("1"), calc * Decimal("0.05")):
                    plan.warnings.append(f"Density in the file ({reported:,.0f}/µL) differs from the one "
                                         f"calculated from the counts ({calc:,.0f}/µL); the calculated one is used.")
            plan.reading["values"] = {**values_json, **_json_safe(plan.results["derived"])}
            if plan.reading["original_reader"]:
                plan.reading["values"]["original_reader"] = plan.reading["original_reader"]

        if not plan.errors and not plan.skipped:
            self.file_slides.add(slide_id.lower())
            if sample_id:
                self.file_samples.setdefault(sample_id.lower(), pid)
        return plan

    def field_values(self, values, plan):
        out = {}
        positive = None
        for key, target in self.targets.items():
            definition = target.definition
            raw = self.cell(values, key)
            try:
                if definition is None:
                    if key in ("density_reported", "parasitaemia_reported"):
                        number = parsing.as_number(raw)
                        if number is not None:
                            if number < 0:
                                raise ParseError("can't be negative.")
                            out[key] = float(number)
                    continue
                value = self.convert(definition, raw)
            except ParseError as error:
                plan.errors.append(f"{target.label}: {error}")
                continue
            if value in (None, "", []):
                if definition.required:
                    plan.errors.append(f"{target.label} is blank (required).")
                continue
            out[definition.key] = value
            if definition.key == "result":
                positive = value == "positive"
        if positive:
            has_reported = "density_reported" in out or "parasitaemia_reported" in out
            for target in self.targets.values():
                d = target.definition
                if d and d.required_if_positive and out.get(d.key) in (None, "", []):
                    if has_reported and d.key in ("wbc_counted", "rbc_counted", "infected_rbc"):
                        continue  # density/parasitaemia given directly instead of counts
                    plan.errors.append(f"{target.label} is required for a positive slide.")
        return out

    @staticmethod
    def convert(definition, raw):
        if parsing.is_blank(raw):
            return None
        kind = definition.data_type
        if kind in (DT.INTEGER, DT.DECIMAL):
            number = parsing.as_number(raw)
            if kind == DT.INTEGER and number != int(number):
                raise ParseError(f"'{parsing.as_text(raw)}' should be a whole number.")
            if definition.min_value is not None and number < definition.min_value:
                raise ParseError(f"{number} is below the minimum of {definition.min_value.normalize()}.")
            if definition.max_value is not None and number > definition.max_value:
                raise ParseError(f"{number} is above the maximum of {definition.max_value.normalize()}.")
            return int(number) if kind == DT.INTEGER else float(number)
        if kind == DT.CHOICE:
            return parsing.as_choice(raw, definition.parsed_choices(), definition.key)
        if kind == DT.MULTICHOICE:
            return parsing.as_multichoice(raw, definition.parsed_choices(), definition.key)
        if kind == DT.BOOLEAN:
            return parsing.as_bool(raw)
        if kind == DT.DATE:
            return parsing.as_date(raw).isoformat()
        return parsing.as_text(raw)


def _json_safe(data):
    return {k: float(v) if isinstance(v, Decimal) else v for k, v in data.items()}


# --- Running a check / an import -----------------------------------------------


def load_table(batch):
    batch.file.open("rb")
    try:
        return parsing.read_table(batch.file, batch.original_name, batch.sheet_name, batch.header_row)
    finally:
        batch.file.close()


PREVIEW_ROWS = 15


def check(batch, user):
    """Check every row; store a report on the batch. Nothing else is saved."""
    table = load_table(batch)
    plans = Checker(batch, user).check_all(table)
    valid = [p for p in plans if not p.errors and not p.skipped]
    batch.rows_total = len(plans)
    batch.rows_valid = len(valid)
    batch.rows_skipped = sum(1 for p in plans if p.skipped and not p.errors)
    batch.report = {
        "errors": [{"row": p.row, "messages": p.errors} for p in plans if p.errors],
        "warnings": [{"row": p.row, "messages": p.warnings} for p in plans if p.warnings and not p.errors],
        "skipped": [{"row": p.row, "message": p.skipped} for p in plans if p.skipped and not p.errors],
        "preview": [_preview(p) for p in valid[:PREVIEW_ROWS]],
    }
    existing = set(Participant.objects.filter(project=batch.project).values_list("study_participant_id", flat=True))
    batch.report["new_participants"] = len({p.participant_id for p in valid} - existing)
    batch.status = batch.Status.CHECKED
    batch.save()
    return plans


def _preview(plan):
    r = plan.results
    return {
        "row": plan.row,
        "participant": plan.participant_id,
        "sample": plan.sample_id,
        "collected": plan.sample["collected_at"].strftime("%d %b %Y") if plan.sample.get("collected_at") else "",
        "slide": plan.slide_id,
        "result": {True: "Positive", False: "Negative"}.get(r.get("is_positive"), "Recorded"),
        "species": SPECIES_LABELS.get(r.get("species", ""), ""),
        "density": float(r["density_per_ul"]) if r.get("density_per_ul") is not None else None,
        "parasitaemia": float(r["parasitaemia_pct"]) if r.get("parasitaemia_pct") is not None else None,
        "reader": str(plan.reading.get("reader", "")),
    }


@transaction.atomic
def run_import(batch, user):
    """Re-check the file and save every valid row. Returns the number of slides created."""
    plans = check(batch, user)
    reason = f"Imported from {batch.original_name} (import #{batch.pk})"
    participants = {p.study_participant_id.lower(): p for p in Participant.objects.filter(project=batch.project)}
    samples = {s.sample_id.lower(): s for s in Sample.objects.filter(project=batch.project)}
    created = []
    for plan in plans:
        if plan.errors or plan.skipped:
            continue
        participant = participants.get(plan.participant_id.lower())
        if participant is None:
            participant = Participant(project=batch.project, study_participant_id=plan.participant_id,
                                      created_by=user, **plan.participant)
            participant._change_reason = reason
            participant.save()
            participants[plan.participant_id.lower()] = participant
        sample = samples.get(plan.sample_id.lower())
        if sample is None:
            sample = Sample(participant=participant, sample_id=plan.sample_id, created_by=user, **plan.sample)
            sample._change_reason = reason
            sample.save()
            samples[plan.sample_id.lower()] = sample
        slide = Slide(sample=sample, smear_type=batch.smear_type, slide_id=plan.slide_id, readers_required=1,
                      created_by=user, notes=f"Imported from {batch.original_name}, row {plan.row}.")
        slide._change_reason = reason
        slide.save()
        reading_data = plan.reading
        reading = Reading(
            slide=slide, reader_number=1, reader=reading_data["reader"], read_at=reading_data["read_at"],
            site=reading_data["site"], comments=reading_data["comments"], values=reading_data["values"],
            is_positive=plan.results["is_positive"], species=plan.results["species"],
            density_per_ul=plan.results["density_per_ul"], parasitaemia_pct=plan.results["parasitaemia_pct"],
            created_by=user,
        )
        reading._change_reason = reason
        reading.save()
        final = evaluate_slide(slide)
        if final:
            final.rule_applied = f"Imported from {batch.original_name} (import #{batch.pk})"
            final.save(update_fields=["rule_applied", "decided_at"])
        created.append(slide)
    batch.slides.add(*created)
    batch.rows_imported = len(created)
    batch.status = batch.Status.IMPORTED
    batch.imported_at = timezone.now()
    batch.save()
    return len(created)
