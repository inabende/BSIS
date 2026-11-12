import io
import shutil
import tempfile
from datetime import date, datetime
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from apps.imports import parsing
from apps.imports.engine import auto_map, targets_for
from apps.imports.models import ImportBatch
from apps.projects.models import ProjectMembership, Site
from apps.projects.tests.factories import PASSWORD, add_member, make_participant, make_project, make_sample, make_user
from apps.samples.models import Participant, Sample
from apps.smears.models import ProjectSmearType, SmearType, Slide

Role = ProjectMembership.Role
MEDIA = tempfile.mkdtemp()


def xlsx_file(rows, name="legacy.xlsx"):
    wb = Workbook()
    for row in rows:
        wb.active.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return SimpleUploadedFile(name, buffer.getvalue())


def csv_file(text, name="legacy.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"))


class ParsingTests(TestCase):
    def test_dates(self):
        self.assertEqual(parsing.as_date("15/09/2026"), date(2026, 9, 15))
        self.assertEqual(parsing.as_date("09/15/2026", "mdy"), date(2026, 9, 15))
        self.assertEqual(parsing.as_date("2026-09-15"), date(2026, 9, 15))
        self.assertEqual(parsing.as_date("15-Sep-2026"), date(2026, 9, 15))
        self.assertEqual(parsing.as_date(datetime(2026, 9, 15, 8, 0)), date(2026, 9, 15))
        with self.assertRaises(parsing.ParseError):
            parsing.as_date("31/02/2026")

    def test_result_and_species_shorthand(self):
        thick = SmearType.objects.get(code="malaria_thick")
        result = thick.fields.get(key="result").parsed_choices()
        species = thick.fields.get(key="species").parsed_choices()
        for text, expected in [("Pos", "positive"), ("+", "positive"), ("MPS seen", "positive"),
                               ("NMPS", "negative"), ("No MPS seen", "negative"), ("neg", "negative")]:
            self.assertEqual(parsing.as_choice(text, result, "result"), expected, text)
        self.assertEqual(parsing.as_multichoice("Pf + P. malariae", species, "species"), ["pf", "pm"])
        self.assertEqual(parsing.as_multichoice("P. falciparum", species, "species"), ["pf"])
        self.assertEqual(parsing.as_multichoice("nil", species, "species"), [])
        with self.assertRaises(parsing.ParseError):
            parsing.as_multichoice("Mixed", species, "species")

    def test_numbers_and_ids(self):
        self.assertEqual(parsing.as_text(1001.0), "1001")
        self.assertEqual(parsing.as_number("1,200"), Decimal("1200"))
        with self.assertRaises(parsing.ParseError):
            parsing.as_number("lots")

    def test_auto_map_common_names(self):
        thick = SmearType.objects.get(code="malaria_thick")
        mapping = auto_map(["PTID", "Date Collected", "BS Result", "Species", "Parasites", "WBC", "Density"],
                           targets_for(thick))
        self.assertEqual(mapping["participant_id"], "PTID")
        self.assertEqual(mapping["collected_date"], "Date Collected")
        self.assertEqual(mapping["field:result"], "BS Result")
        self.assertEqual(mapping["field:asexual_parasites_counted"], "Parasites")
        self.assertEqual(mapping["field:wbc_counted"], "WBC")
        self.assertEqual(mapping["density_reported"], "Density")


@override_settings(MEDIA_ROOT=MEDIA)
class ImportFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.project = make_project("P1")
        cls.site = Site.objects.get(code="S1")
        cls.thick = SmearType.objects.get(code="malaria_thick")
        ProjectSmearType.objects.create(project=cls.project, smear_type=cls.thick, readers_required=2)
        cls.lead = make_user("lead", first_name="Grace", last_name="Lead")
        cls.reader = make_user("reader", first_name="Peter", last_name="Okello")
        add_member(cls.project, cls.lead, Role.LEAD)
        add_member(cls.project, cls.reader, Role.READER)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.client.login(username="lead", password=PASSWORD)

    HEADER = ["PTID", "Sex", "Sample ID", "Date Collected", "Site", "BS Result", "Species", "Parasites", "WBC",
              "Microscopist"]

    def upload(self, file, **extra):
        data = {"smear_type": self.thick.pk, "file": file, "header_row": 1, "date_order": "dmy",
                "on_existing_slide": "skip"}
        data.update(extra)
        response = self.client.post(reverse("imports:upload", args=["P1"]), data)
        return response, ImportBatch.objects.order_by("-pk").first()

    def check(self, batch, mapping=None):
        data = mapping if mapping is not None else batch.mapping
        self.client.post(reverse("imports:map", args=["P1", batch.pk]), data)
        batch.refresh_from_db()
        return batch

    def good_rows(self):
        return [
            self.HEADER,
            ["PT-1", "F", "S-1", "15/09/2026", "S1", "Pos", "Pf", 50, 200, "Peter Okello"],
            ["PT-1", "F", "S-2", "22/09/2026", "S1", "NMPS", "", "", "", "reader"],
            ["PT-2", "M", "S-3", datetime(2026, 9, 16), "Site One", "+", "Pf + Pm", 10, 200, "Dr Unknown"],
        ]

    def test_full_import(self):
        response, batch = self.upload(xlsx_file(self.good_rows()))
        self.assertRedirects(response, reverse("imports:map", args=["P1", batch.pk]))
        self.assertEqual(batch.mapping["participant_id"], "PTID")
        self.assertEqual(batch.mapping["reader"], "Microscopist")

        batch = self.check(batch)
        self.assertEqual(batch.status, "checked")
        self.assertEqual((batch.rows_total, batch.rows_valid), (3, 3))
        self.assertEqual(Slide.objects.count(), 0)  # checking saves nothing
        self.assertEqual(len(batch.report["warnings"]), 1)  # unknown reader

        self.client.post(reverse("imports:preview", args=["P1", batch.pk]))
        batch.refresh_from_db()
        self.assertEqual((batch.status, batch.rows_imported), ("imported", 3))
        self.assertEqual(Participant.objects.filter(project=self.project).count(), 2)

        slide = Slide.objects.get(slide_id="S-1-TK")
        self.assertEqual(slide.readers_required, 1)  # imported history is single-reader, even on double-read projects
        self.assertEqual(slide.status, "final")
        self.assertEqual(slide.final.density_per_ul, Decimal("2000.00"))
        self.assertFalse(slide.final.locked)
        self.assertIn("Imported from legacy.xlsx", slide.final.rule_applied)
        self.assertEqual(slide.readings.get().reader, self.reader)       # matched by full name
        self.assertEqual(slide.sample.site, self.site)
        mixed = Slide.objects.get(slide_id="S-3-TK")
        self.assertEqual(mixed.final.species, "mixed")
        self.assertEqual(mixed.readings.get().reader, self.lead)        # unknown reader → importer
        self.assertEqual(mixed.readings.get().values["original_reader"], "Dr Unknown")
        self.assertEqual(list(batch.slides.order_by("slide_id").values_list("slide_id", flat=True)),
                         ["S-1-TK", "S-2-TK", "S-3-TK"])
        history = slide.history.first()
        self.assertIn("import #", history.history_change_reason)

    def test_row_problems_reported_and_left_out(self):
        rows = [
            self.HEADER,
            ["PT-1", "F", "S-1", "15/09/2026", "S1", "Pos", "Pf", 50, 200, ""],
            ["", "F", "S-2", "15/09/2026", "S1", "Pos", "Pf", 50, 200, ""],             # no participant
            ["PT-3", "F", "S-3", "31/02/2026", "S1", "Neg", "", "", "", ""],             # bad date
            ["PT-4", "F", "S-4", "15/09/2026", "Nowhere", "Neg", "", "", "", ""],        # unknown site
            ["PT-5", "F", "S-5", "15/09/2026", "S1", "Neg", "", 7, 200, ""],             # negative with parasites
            ["PT-6", "F", "S-6", "15/09/2026", "S1", "Pos", "", 7, 200, ""],             # positive, no species
            ["PT-7", "F", "S-1", "15/09/2026", "S1", "Neg", "", "", "", ""],             # sample of PT-1
            ["PT-8", "F", "S-8", "15/09/2099", "S1", "Neg", "", "", "", ""],             # future
        ]
        _, batch = self.upload(xlsx_file(rows))
        batch = self.check(batch)
        self.assertEqual(batch.rows_valid, 1)
        errors = {e["row"]: " ".join(e["messages"]) for e in batch.report["errors"]}
        self.assertIn("Participant ID is blank", errors[3])
        self.assertIn("isn't a date", errors[4])
        self.assertIn("isn't one of this project's sites", errors[5])
        self.assertIn("can't have parasites counted", errors[6])
        self.assertIn("Species seen is required for a positive slide", errors[7])
        self.assertIn("already belongs to participant PT-1", errors[8])
        self.assertIn("in the future", errors[9])

        # Must confirm that problem rows will be left out.
        self.client.post(reverse("imports:preview", args=["P1", batch.pk]))
        batch.refresh_from_db()
        self.assertEqual(batch.status, "checked")
        self.client.post(reverse("imports:preview", args=["P1", batch.pk]), {"accept_errors": "1"})
        self.assertEqual(Slide.objects.count(), 1)

        report = self.client.get(reverse("imports:problems", args=["P1", batch.pk])).content.decode("utf-8-sig")
        self.assertIn("isn't a date", report)

    def test_density_only_legacy_file(self):
        rows = [["Participant", "Date", "Result", "Species", "Parasite density"],
                ["PT-1", "15/09/2026", "positive", "pf", "12,400"],
                ["PT-2", "15/09/2026", "negative", "", ""]]
        _, batch = self.upload(csv_file("\n".join(",".join(f'"{c}"' for c in r) for r in rows)))
        self.assertEqual(batch.mapping["density_reported"], "Parasite density")
        batch = self.check(batch)
        self.assertEqual(batch.rows_valid, 2, batch.report)
        self.client.post(reverse("imports:preview", args=["P1", batch.pk]))
        slide = Slide.objects.get(sample__participant__study_participant_id="PT-1")
        self.assertEqual(slide.final.density_per_ul, Decimal("12400.00"))
        self.assertEqual(slide.sample.sample_id, "PT-1-20260915")  # generated
        self.assertEqual(slide.readings.get().values["density_reported"], 12400.0)

    def test_reimport_skips_existing_slides(self):
        _, batch = self.upload(xlsx_file(self.good_rows()))
        self.check(batch)
        self.client.post(reverse("imports:preview", args=["P1", batch.pk]))
        _, again = self.upload(xlsx_file(self.good_rows()))
        again = self.check(again)
        self.assertEqual((again.rows_valid, again.rows_skipped), (0, 3))

    def test_existing_slide_as_error_when_chosen(self):
        sample = make_sample(make_participant(self.project, "PT-1"), "S-1")
        Slide.objects.create(sample=sample, smear_type=self.thick, slide_id="S-1-TK")
        _, batch = self.upload(xlsx_file(self.good_rows()), on_existing_slide="error")
        batch = self.check(batch)
        self.assertIn("already exists", batch.report["errors"][0]["messages"][0])

    def test_mapping_requires_core_columns(self):
        _, batch = self.upload(xlsx_file(self.good_rows()))
        mapping = dict(batch.mapping)
        mapping.pop("participant_id")
        response = self.client.post(reverse("imports:map", args=["P1", batch.pk]), mapping)
        self.assertContains(response, "Choose the column that holds this.")

    def test_same_column_twice_rejected(self):
        _, batch = self.upload(xlsx_file(self.good_rows()))
        mapping = dict(batch.mapping, visit="PTID")
        response = self.client.post(reverse("imports:map", args=["P1", batch.pk]), mapping)
        self.assertContains(response, "already used")

    def test_bad_files_rejected_at_upload(self):
        response, _ = self.upload(SimpleUploadedFile("notes.txt", b"hello"))
        self.assertContains(response, "File extension")
        response, _ = self.upload(SimpleUploadedFile("broken.xlsx", b"not really excel"))
        self.assertContains(response, "valid Excel")
        response, _ = self.upload(xlsx_file([["A", "A"], [1, 2]]))
        self.assertContains(response, "appears twice")
        self.assertFalse(ImportBatch.objects.exists())

    def test_reader_cannot_import(self):
        self.client.login(username="reader", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("imports:upload", args=["P1"])).status_code, 403)
        self.assertEqual(self.client.get(reverse("imports:list", args=["P1"])).status_code, 403)

    def test_template_download(self):
        response = self.client.get(reverse("imports:template", args=["P1", self.thick.pk]))
        wb = load_workbook(io.BytesIO(response.content))
        self.assertEqual(wb.sheetnames, ["Results", "How to fill this in"])
        headers = [c.value for c in wb["Results"][1]]
        self.assertIn("Participant ID", headers)
        self.assertIn("Asexual parasites counted", headers)

    def test_template_round_trip(self):
        """The template's own example rows import cleanly."""
        response = self.client.get(reverse("imports:template", args=["P1", self.thick.pk]))
        _, batch = self.upload(SimpleUploadedFile("template.xlsx", response.content))
        batch = self.check(batch)
        self.assertEqual(batch.rows_valid, 2, batch.report.get("errors"))

    def test_cancel(self):
        _, batch = self.upload(xlsx_file(self.good_rows()))
        self.client.post(reverse("imports:cancel", args=["P1", batch.pk]))
        batch.refresh_from_db()
        self.assertEqual(batch.status, "cancelled")
        self.assertEqual(self.client.get(reverse("imports:map", args=["P1", batch.pk])).status_code, 403)

    def test_original_file_kept(self):
        _, batch = self.upload(xlsx_file(self.good_rows(), name="study-results.xlsx"))
        response = self.client.get(reverse("imports:file", args=["P1", batch.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("study-results.xlsx", response["Content-Disposition"])
