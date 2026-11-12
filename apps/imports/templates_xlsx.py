"""A ready-made Excel template for importing one smear type into a project."""

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from apps.smears.models import FieldDefinition

from .engine import targets_for

HEADER_FILL = PatternFill("solid", fgColor="7A1F2B")
REQUIRED_FILL = PatternFill("solid", fgColor="5C1720")

EXAMPLES = {
    "participant_id": ["PT-0001", "PT-0002"],
    "sex": ["F", "M"],
    "year_of_birth": [2018, 2020],
    "sample_id": ["PT-0001-D0", "PT-0002-D0"],
    "collected_date": ["15/09/2026", "15/09/2026"],
    "collected_time": ["09:30", "10:15"],
    "visit": ["Day 0", "Day 0"],
    "slide_id": ["", ""],
    "read_date": ["15/09/2026", "16/09/2026"],
    "field:result": ["Positive", "Negative"],
    "field:species": ["Pf", ""],
    "field:asexual_parasites_counted": [64, ""],
    "field:wbc_counted": [200, ""],
    "field:gametocytes_present": ["No", "No"],
    "field:fields_examined": ["", 100],
    "field:rbc_counted": [2000, ""],
    "field:infected_rbc": [15, ""],
    "field:stages": ["Rings", ""],
}


def build_template(response, project, smear_type):
    targets = [t for t in targets_for(smear_type) if t.key != "density_reported" and t.key != "parasitaemia_reported"]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Results"
    sheet.append([t.label for t in targets])
    for cell, target in zip(sheet[1], targets):
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = REQUIRED_FILL if target.required else HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.column_dimensions[cell.column_letter].width = max(14, len(target.label) + 2)
    examples = dict(EXAMPLES)
    if project.sites.exists():
        examples["site"] = [project.sites.first().code] * 2
    for i in range(2):
        sheet.append([examples.get(t.key, ["", ""])[i] for t in targets])
    for cell in list(sheet[2]) + list(sheet[3]):
        cell.font = Font(italic=True, color="888888")
    sheet.freeze_panes = "A2"

    guide = workbook.create_sheet("How to fill this in")
    guide.column_dimensions["A"].width = 32
    guide.column_dimensions["B"].width = 14
    guide.column_dimensions["C"].width = 90
    guide.append([f"Import template: {smear_type.name} for {project.code}"])
    guide["A1"].font = Font(bold=True, size=13)
    guide.append([
        "Replace the two grey example rows with your data (or delete them). Keep the first row's column names. "
        "Columns you don't have can be left empty or deleted. You can also import files in other layouts: "
        "the import page lets you match your own column names."
    ])
    guide.append([])
    guide.append(["Column", "Required?", "What to write"])
    for cell in guide[4]:
        cell.font = Font(bold=True)
    sites = ", ".join(f"{s.code} ({s.name})" for s in project.sites.all()) or "No sites set up for this project yet"
    explanations = {
        "participant_id": "The study's participant ID. No names.",
        "sex": "F, M or U (unknown).",
        "sample_id": "Optional. Blank = participant ID + collection date.",
        "collected_date": "e.g. 15/09/2026 (day/month/year), or a real Excel date.",
        "collected_time": "Optional, e.g. 09:30.",
        "site": f"One of: {sites}.",
        "slide_id": "Optional. Blank = sample ID + '-" + smear_type.slide_suffix + "'.",
        "reader": "Username or full name of a reader in this project. Other names are kept but recorded "
                  "under the person importing.",
        "read_date": "Optional. Blank = collection date.",
    }
    for target in targets:
        text = explanations.get(target.key, target.help)
        definition = target.definition
        if definition is not None:
            if definition.data_type in FieldDefinition.CHOICE_TYPES:
                options = ", ".join(label for _, label in definition.parsed_choices())
                several = " Several allowed, separated by + or commas." if definition.data_type == "multichoice" else ""
                text = f"One of: {options}.{several} {target.help}".strip()
            elif definition.data_type == FieldDefinition.DataType.BOOLEAN:
                text = "Yes or No."
            elif definition.data_type in FieldDefinition.NUMBER_TYPES:
                limits = []
                if definition.min_value is not None:
                    limits.append(f"min {definition.min_value.normalize()}")
                if definition.max_value is not None:
                    limits.append(f"max {definition.max_value.normalize()}")
                kind = "Whole number" if definition.data_type == "integer" else "Number"
                text = f"{kind}{' (' + ', '.join(limits) + ')' if limits else ''}{' ' + definition.unit if definition.unit else ''}. {target.help}".strip()
        required = "Yes" if target.required else ("If positive" if definition is not None and definition.required_if_positive else "")
        guide.append([target.label, required, text])
        guide.cell(row=guide.max_row, column=3).alignment = Alignment(wrap_text=True, vertical="top")
    workbook.save(response)
