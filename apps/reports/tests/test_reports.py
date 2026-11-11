import csv
import io
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.projects.models import ProjectMembership
from apps.projects.tests.factories import PASSWORD, add_member, make_participant, make_project, make_sample, make_user
from apps.qc.services import evaluate_slide
from apps.reports.models import ExportLog
from apps.smears.models import Reading, SmearType, Slide

Role = ProjectMembership.Role


def add_slide(sample, smear_type, slide_id, reader, positive=True, density=1000, species="pf",
              readers_required=1, values=None, second=None):
    """A slide with reader 1 (and optionally reader 2) readings, evaluated into a final result."""
    slide = Slide.objects.create(sample=sample, smear_type=smear_type, slide_id=slide_id,
                                 readers_required=readers_required)
    Reading.objects.create(
        slide=slide, reader=reader, reader_number=1, is_positive=positive,
        species=species if positive else "", density_per_ul=Decimal(density) if positive else Decimal(0),
        values=values or {"result": "positive" if positive else "negative"},
    )
    if second is not None:
        Reading.objects.create(slide=slide, reader_number=2, **second)
    evaluate_slide(slide)
    slide.refresh_from_db()
    return slide


class ReportsTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.thick = SmearType.objects.get(code="malaria_thick")
        cls.p1 = make_project("P1")
        cls.p2 = make_project("P2")
        cls.secret = make_project("SECRET")
        cls.reader = make_user("reader")
        cls.reader2 = make_user("reader2")
        cls.reviewer = make_user("reviewer")
        cls.viewer = make_user("viewer")
        for project in (cls.p1, cls.p2):
            add_member(project, cls.reader, Role.READER)
            add_member(project, cls.reader2, Role.READER)
            add_member(project, cls.reviewer, Role.REVIEWER)
            add_member(project, cls.viewer, Role.VIEWER)
        now = timezone.now()
        s1 = make_sample(make_participant(cls.p1, "A-1"), "A-1-D0")
        s2 = make_sample(make_participant(cls.p2, "B-1"), "B-1-D0")
        s_old = make_sample(make_participant(cls.p1, "A-2"), "A-2-D0")
        s_old.collected_at = now - timedelta(days=90)
        s_old.save()
        s_secret = make_sample(make_participant(cls.secret, "S-1"), "S-1-D0")

        cls.pos_p1 = add_slide(s1, cls.thick, "A-1-TK", cls.reader, density=1000,
                               values={"result": "positive", "species": ["pf"], "asexual_parasites_counted": 25,
                                       "wbc_counted": 200, "comments_note": "=cmd()"})
        cls.neg_p1 = add_slide(s_old, cls.thick, "A-2-TK", cls.reader, positive=False)
        cls.pos_p2 = add_slide(s2, cls.thick, "B-1-TK", cls.reader, density=100000, species="pv")
        cls.secret_slide = add_slide(s_secret, cls.thick, "S-1-TK", cls.reader, density=5)
        # A double-read slide still awaiting reader 2 (blind).
        cls.blind = add_slide(make_sample(make_participant(cls.p1, "A-3"), "A-3-D0"), cls.thick, "A-3-TK",
                              cls.reader, density=4321, readers_required=2,
                              values={"result": "positive", "species": ["pf"], "asexual_parasites_counted": 999})

    def login(self, user):
        self.client.login(username=user.username, password=PASSWORD)


class SearchTests(ReportsTestBase):
    def search(self, **params):
        return self.client.get(reverse("reports:search"), params)

    def test_search_only_covers_member_projects(self):
        self.login(self.viewer)
        response = self.search()
        self.assertContains(response, "A-1-TK")
        self.assertContains(response, "B-1-TK")
        self.assertNotContains(response, "S-1-TK")

    def test_filter_by_result_and_project(self):
        self.login(self.viewer)
        response = self.search(result="positive", project=[self.p1.pk])
        self.assertContains(response, "A-1-TK")
        self.assertNotContains(response, "A-2-TK")
        self.assertNotContains(response, "B-1-TK")

    def test_cannot_search_other_project_by_id(self):
        self.login(self.viewer)
        response = self.search(project=[self.secret.pk])
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "S-1-TK")

    def test_date_and_density_filters(self):
        self.login(self.viewer)
        since = (timezone.localdate() - timedelta(days=30)).isoformat()
        response = self.search(collected_from=since)
        self.assertNotContains(response, "A-2-TK")
        response = self.search(density_min=50000)
        self.assertContains(response, "B-1-TK")
        self.assertNotContains(response, "A-1-TK")

    def test_invalid_range_shows_error(self):
        self.login(self.viewer)
        response = self.search(density_min=10, density_max=1)
        self.assertContains(response, "Must be at least")

    def test_blind_slide_shows_status_not_result(self):
        self.login(self.reader2)
        response = self.search(q="A-3")
        self.assertContains(response, "Awaiting reader 2")
        self.assertNotContains(response, "4,321")

    def test_login_required(self):
        response = self.search()
        self.assertEqual(response.status_code, 302)


class ExportTests(ReportsTestBase):
    def export(self, fmt, **params):
        return self.client.get(reverse("reports:export", args=[fmt]), params)

    def workbook(self, response):
        return load_workbook(io.BytesIO(response.content))

    def test_excel_export_sheets_and_rows(self):
        self.login(self.reviewer)
        response = self.export("xlsx")
        self.assertEqual(response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        wb = self.workbook(response)
        self.assertEqual(wb.sheetnames, ["Final results", "Malaria – thick smear readings", "About"])
        final = wb["Final results"]
        slide_ids = [row[9] for row in final.iter_rows(min_row=2, values_only=True)]
        self.assertEqual(sorted(slide_ids), ["A-1-TK", "A-2-TK", "A-3-TK", "B-1-TK"])
        headers = [c.value for c in final[1]]
        row = {h: v for h, v in zip(headers, next(r for r in final.iter_rows(min_row=2, values_only=True) if r[9] == "B-1-TK"))}
        self.assertEqual(row["Parasite density (/µL)"], 100000)
        self.assertEqual(row["Species"], "P. vivax")

    def test_reader_export_leaves_out_blind_readings(self):
        self.login(self.reader2)
        wb = self.workbook(self.export("xlsx"))
        readings = wb["Malaria – thick smear readings"]
        ids = [row[5] for row in readings.iter_rows(min_row=2, values_only=True)]
        self.assertNotIn("A-3-TK", ids)
        self.assertIn("A-1-TK", ids)

    def test_reviewer_export_includes_blind_readings(self):
        self.login(self.reviewer)
        wb = self.workbook(self.export("xlsx"))
        ids = [row[5] for row in wb["Malaria – thick smear readings"].iter_rows(min_row=2, values_only=True)]
        self.assertIn("A-3-TK", ids)

    def test_readings_sheet_has_type_fields(self):
        self.login(self.viewer)
        sheet = self.workbook(self.export("xlsx"))["Malaria – thick smear readings"]
        headers = [c.value for c in sheet[1]]
        self.assertIn("Asexual parasites counted", headers)
        self.assertIn("Species seen", headers)

    def test_csv_export_filtered(self):
        self.login(self.viewer)
        response = self.export("csv", project=[self.p2.pk])
        text = response.content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(rows[0][0], "Project code")
        self.assertEqual([r[9] for r in rows[1:]], ["B-1-TK"])

    def test_export_never_includes_other_projects(self):
        self.login(self.viewer)
        response = self.export("csv", project=[self.secret.pk])
        self.assertNotIn("S-1-TK", response.content.decode("utf-8-sig"))

    def test_formula_text_is_neutralised(self):
        from apps.reports.exports import _safe

        self.assertEqual(_safe("=HYPERLINK(1)"), "'=HYPERLINK(1)")
        self.assertEqual(_safe("-5"), "'-5")
        self.assertEqual(_safe(-5), -5)
        self.assertEqual(_safe("Normal text"), "Normal text")

    def test_export_is_logged(self):
        self.login(self.viewer)
        self.export("xlsx", result="positive")
        log = ExportLog.objects.get()
        self.assertEqual(log.user, self.viewer)
        self.assertEqual(log.format, "xlsx")
        self.assertEqual(log.filters, {"Result": "Positive"})
        self.assertEqual(log.project_codes, ["P1", "P2"])
        self.assertEqual(log.slide_count, 2)


class DashboardTests(ReportsTestBase):
    def test_dashboard_stats(self):
        self.login(self.viewer)
        response = self.client.get(reverse("reports:dashboard"))
        stats = response.context["stats"]
        totals = stats["totals"]
        self.assertEqual(response.context["smear_type"], self.thick)
        self.assertEqual(totals["final"], 3)          # blind slide has no final result yet
        self.assertEqual(totals["awaiting"], 1)
        self.assertEqual(totals["positive"], 2)
        self.assertEqual(totals["positivity"], 66.7)
        self.assertEqual(totals["geo_mean_density"], 10000)  # √(1,000 × 100,000)
        self.assertEqual({s["label"] for s in stats["species"]}, {"P. falciparum", "P. vivax"})
        self.assertEqual([b["count"] for b in stats["density"]], [0, 0, 1, 0, 1])
        self.assertNotIn("SECRET", [p["project__code"] for p in stats["by_project"]])

    def test_dashboard_project_filter(self):
        self.login(self.viewer)
        response = self.client.get(reverse("reports:dashboard"), {"project": [self.p2.pk]})
        self.assertEqual(response.context["stats"]["totals"]["final"], 1)

    def test_discordance_rate(self):
        sample = make_sample(make_participant(self.p2, "B-2"), "B-2-D0")
        add_slide(sample, self.thick, "B-2-TK", self.reader, density=1000, readers_required=2,
                  second={"reader": self.reader2, "is_positive": False, "values": {"result": "negative"}})
        sample = make_sample(make_participant(self.p2, "B-3"), "B-3-D0")
        add_slide(sample, self.thick, "B-3-TK", self.reader, density=1000, readers_required=2,
                  second={"reader": self.reader2, "is_positive": True, "species": "pf",
                          "density_per_ul": Decimal(1100), "values": {"result": "positive"}})
        self.login(self.viewer)
        totals = self.client.get(reverse("reports:dashboard")).context["stats"]["totals"]
        self.assertEqual(totals["double_read"], 1)    # only the agreeing one has a final result
        self.assertEqual(totals["awaiting"], 2)       # the blind A-3 slide + the discordant B-2 slide

    def test_dashboard_renders_chart_data(self):
        self.login(self.viewer)
        response = self.client.get(reverse("reports:dashboard"))
        self.assertContains(response, 'id="report-data"')
        self.assertContains(response, "chart-positivity")
