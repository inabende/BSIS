"""
Creates the built-in smear types (malaria thick, malaria thin, general hematology)
and their fields, and allows them on every existing project.

The field keys here are used by apps/smears/calculations.py — don't rename them.
"""

from django.db import migrations

SPECIES = "\n".join(
    [
        "pf = P. falciparum",
        "pv = P. vivax",
        "pm = P. malariae",
        "po = P. ovale",
        "pk = P. knowlesi",
        "unidentified = Plasmodium sp. (unidentified)",
    ]
)
RESULT = "positive = Positive\nnegative = Negative"

# (key, label, data_type, extra options)
THICK = [
    ("result", "Result", "choice", {"choices": RESULT, "required": True}),
    ("species", "Species seen", "multichoice", {"choices": SPECIES, "required_if_positive": True,
        "help_text": "Tick more than one for a mixed infection."}),
    ("asexual_parasites_counted", "Asexual parasites counted", "integer", {"min_value": 0,
        "help_text": "Asexual parasites counted against the WBCs below."}),
    ("wbc_counted", "WBCs counted", "integer", {"min_value": 1, "required_if_positive": True,
        "help_text": "Usually 200 (500 if fewer than 10 parasites per 200 WBCs)."}),
    ("wbc_per_ul", "Measured WBC count", "integer", {"min_value": 1, "unit": "/µL",
        "help_text": "Leave blank to use the project's default WBC/µL."}),
    ("gametocytes_present", "Gametocytes seen", "boolean", {}),
    ("gametocytes_counted", "Gametocytes counted", "integer", {"min_value": 0,
        "help_text": "Counted against the same WBCs."}),
    ("fields_examined", "High-power fields examined", "integer", {"min_value": 0,
        "help_text": "e.g. 100 fields before declaring a slide negative."}),
]

THIN = [
    ("result", "Result", "choice", {"choices": RESULT, "required": True}),
    ("species", "Species seen", "multichoice", {"choices": SPECIES, "required_if_positive": True,
        "help_text": "Tick more than one for a mixed infection."}),
    ("rbc_counted", "RBCs counted", "integer", {"min_value": 1, "required_if_positive": True}),
    ("infected_rbc", "Infected RBCs", "integer", {"min_value": 0, "required_if_positive": True}),
    ("stages", "Stages seen", "multichoice", {"choices":
        "rings = Rings\ntrophozoites = Trophozoites\nschizonts = Schizonts\ngametocytes = Gametocytes"}),
    ("fields_examined", "Fields examined", "integer", {"min_value": 0}),
]

PERCENT = {"min_value": 0, "max_value": 100, "unit": "%"}
HEMATOLOGY = [
    ("neutrophils", "Neutrophils", "integer", PERCENT),
    ("band_forms", "Band forms", "integer", PERCENT),
    ("lymphocytes", "Lymphocytes", "integer", PERCENT),
    ("monocytes", "Monocytes", "integer", PERCENT),
    ("eosinophils", "Eosinophils", "integer", PERCENT),
    ("basophils", "Basophils", "integer", PERCENT),
    ("rbc_morphology", "RBC morphology", "multichoice", {"choices": "\n".join([
        "normal = Normocytic normochromic",
        "microcytic = Microcytic",
        "macrocytic = Macrocytic",
        "hypochromic = Hypochromic",
        "anisocytosis = Anisocytosis",
        "poikilocytosis = Poikilocytosis",
        "target_cells = Target cells",
        "sickle_cells = Sickle cells",
        "spherocytes = Spherocytes",
        "schistocytes = Schistocytes",
        "nucleated_rbc = Nucleated RBCs",
        "polychromasia = Polychromasia",
    ])}),
    ("rbc_comments", "RBC comments", "longtext", {}),
    ("wbc_comments", "WBC comments", "longtext", {"help_text": "e.g. toxic granulation, atypical lymphocytes, blasts."}),
    ("platelet_estimate", "Platelet estimate", "choice", {"choices":
        "adequate = Adequate\ndecreased = Decreased\nincreased = Increased\nclumped = Clumped (can't estimate)"}),
    ("platelet_comments", "Platelet comments", "longtext", {}),
    ("parasites_seen", "Blood parasites seen incidentally", "boolean", {}),
]

TYPES = [
    # code, name, suffix, calculation, order, description, fields
    ("malaria_thick", "Malaria – thick smear", "TK", "thick_density", 10,
     "Detects parasites and estimates density against white blood cells.", THICK),
    ("malaria_thin", "Malaria – thin smear", "TN", "thin_parasitaemia", 20,
     "Identifies species and stages; parasitaemia as % of red blood cells.", THIN),
    ("hematology", "General hematology", "HM", "hematology_differential", 30,
     "Differential WBC count, RBC morphology and platelet estimate.", HEMATOLOGY),
]


def create_builtins(apps, schema_editor):
    SmearType = apps.get_model("smears", "SmearType")
    FieldDefinition = apps.get_model("smears", "FieldDefinition")
    Project = apps.get_model("projects", "Project")
    ProjectSmearType = apps.get_model("smears", "ProjectSmearType")

    for code, name, suffix, calculation, order, description, fields in TYPES:
        smear_type, _ = SmearType.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "slide_suffix": suffix,
                "calculation": calculation,
                "order": order,
                "description": description,
                "is_builtin": True,
            },
        )
        for position, (key, label, data_type, extra) in enumerate(fields, start=1):
            FieldDefinition.objects.update_or_create(
                smear_type=smear_type,
                key=key,
                defaults={"label": label, "data_type": data_type, "order": position * 10, "is_builtin": True, **extra},
            )
        for project in Project.objects.all():
            ProjectSmearType.objects.get_or_create(project=project, smear_type=smear_type)


class Migration(migrations.Migration):
    dependencies = [
        ("smears", "0001_initial"),
        ("projects", "0001_initial"),
    ]

    operations = [migrations.RunPython(create_builtins, migrations.RunPython.noop)]
