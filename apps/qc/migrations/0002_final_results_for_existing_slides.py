"""
Slides recorded before Phase 3 were single-reader: give each one a final
result copied from its reader 1 reading.
"""

from django.db import migrations


def create_final_results(apps, schema_editor):
    Slide = apps.get_model("smears", "Slide")
    FinalResult = apps.get_model("qc", "FinalResult")
    for slide in Slide.objects.filter(final_result__isnull=True):
        reading = slide.readings.filter(reader_number=1).first()
        if not reading:
            continue
        FinalResult.objects.create(
            slide=slide,
            is_positive=reading.is_positive,
            species=reading.species,
            density_per_ul=reading.density_per_ul,
            parasitaemia_pct=reading.parasitaemia_pct,
            rule_applied="Single reader",
            readings_used="1",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("qc", "0001_initial"),
        ("smears", "0003_readers_required"),
    ]

    operations = [migrations.RunPython(create_final_results, migrations.RunPython.noop)]
