from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.projects.models import ProjectMembership
from apps.projects.tests.factories import (
    PASSWORD,
    add_member,
    make_participant,
    make_project,
    make_sample,
    make_user,
)
from apps.smears.models import FieldDefinition, ProjectSmearType, Reading, SmearType, Slide

Role = ProjectMembership.Role


def now_str(hours_ago=1):
    return (timezone.localtime() - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M")


class SmearViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.project = make_project("P1")
        cls.thick = SmearType.objects.get(code="malaria_thick")
        cls.thin = SmearType.objects.get(code="malaria_thin")
        cls.hema = SmearType.objects.get(code="hematology")
        for t in (cls.thick, cls.thin):
            ProjectSmearType.objects.create(project=cls.project, smear_type=t)
        cls.reader = make_user("reader")
        cls.viewer = make_user("viewer")
        add_member(cls.project, cls.reader, Role.READER)
        add_member(cls.project, cls.viewer, Role.VIEWER)
        cls.participant = make_participant(cls.project)
        cls.sample = make_sample(cls.participant, "SM-1")

    def setUp(self):
        self.client.login(username="reader", password=PASSWORD)

    def record_url(self):
        return reverse("smears:smear_record", args=["P1", self.sample.pk])

    def post_thick(self, **values):
        data = {
            "smear_type": self.thick.pk,
            "slide_id": "",
            "stain": "giemsa",
            "reader": self.reader.pk,
            "read_at": now_str(),
            "v-result": "positive",
            "v-species": ["pf"],
            "v-asexual_parasites_counted": 120,
            "v-wbc_counted": 200,
        }
        data.update(values)
        return self.client.post(self.record_url(), data)

    def test_record_thick_result(self):
        response = self.post_thick()
        slide = Slide.objects.get()
        self.assertRedirects(response, reverse("smears:slide_detail", args=["P1", slide.pk]))
        self.assertEqual(slide.slide_id, "SM-1-TK")  # suggested from sample ID + suffix
        self.assertEqual(slide.status, Slide.Status.FINAL)
        self.assertEqual(slide.created_by, self.reader)
        reading = slide.readings.get()
        self.assertEqual(reading.density_per_ul, Decimal("4800.00"))
        self.assertTrue(reading.is_positive)
        self.assertEqual(reading.species, "pf")
        self.assertEqual(reading.values["asexual_parasites_counted"], 120)
        self.assertEqual(reading.values["wbc_per_ul_used"], 8000)

    def test_slide_detail_shows_density(self):
        self.post_thick()
        slide = Slide.objects.get()
        response = self.client.get(reverse("smears:slide_detail", args=["P1", slide.pk]))
        self.assertContains(response, "4,800")
        self.assertContains(response, "P. falciparum")
        self.assertContains(response, "Asexual parasites counted")

    def test_second_slide_gets_numbered_id(self):
        self.post_thick()
        self.post_thick()
        self.assertEqual(
            sorted(Slide.objects.values_list("slide_id", flat=True)), ["SM-1-TK", "SM-1-TK-2"]
        )

    def test_duplicate_slide_id_rejected(self):
        self.post_thick(slide_id="X1")
        response = self.post_thick(slide_id="x1")
        self.assertContains(response, "already exists")
        self.assertEqual(Slide.objects.count(), 1)

    def test_logic_error_shown_on_field_and_nothing_saved(self):
        response = self.post_thick(**{"v-result": "negative", "v-species": []})
        self.assertContains(response, "A negative slide can&#x27;t have parasites counted.")
        self.assertEqual(Slide.objects.count(), 0)

    def test_required_if_positive(self):
        response = self.post_thick(**{"v-species": []})
        self.assertContains(response, "Required for a positive slide.")
        self.assertEqual(Slide.objects.count(), 0)

    def test_record_thin_result(self):
        self.client.post(
            self.record_url(),
            {
                "smear_type": self.thin.pk,
                "stain": "giemsa",
                "reader": self.reader.pk,
                "read_at": now_str(),
                "v-result": "positive",
                "v-species": ["pv"],
                "v-rbc_counted": 1000,
                "v-infected_rbc": 25,
                "v-stages": ["rings", "trophozoites"],
            },
        )
        reading = Reading.objects.get()
        self.assertEqual(reading.parasitaemia_pct, Decimal("2.5000"))
        self.assertEqual(reading.slide.slide_id, "SM-1-TN")
        self.assertEqual(reading.values["stages"], ["rings", "trophozoites"])

    def test_type_not_allowed_in_project_rejected(self):
        response = self.client.post(
            self.record_url(),
            {"smear_type": self.hema.pk, "stain": "wright", "reader": self.reader.pk, "read_at": now_str()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Slide.objects.count(), 0)

    def test_htmx_fields_partial(self):
        url = reverse("smears:smear_fields", args=["P1"])
        response = self.client.get(url, {"smear_type": self.thin.pk})
        self.assertContains(response, "Infected RBCs")
        self.assertNotContains(response, "<html")
        # A type the project doesn't use returns no fields.
        response = self.client.get(url, {"smear_type": self.hema.pk})
        self.assertContains(response, "Choose a smear type")

    def test_viewer_cannot_record(self):
        self.client.login(username="viewer", password=PASSWORD)
        self.assertEqual(self.client.get(self.record_url()).status_code, 403)
        self.assertEqual(self.client.get(reverse("smears:smear_fields", args=["P1"])).status_code, 403)

    def test_edit_reading_recalculates_and_keeps_history(self):
        self.post_thick()
        slide = Slide.objects.get()
        reading = slide.readings.get()
        self.client.post(
            reverse("smears:reading_update", args=["P1", slide.pk, reading.pk]),
            {
                "reader": self.reader.pk,
                "read_at": now_str(),
                "v-result": "positive",
                "v-species": ["pf"],
                "v-asexual_parasites_counted": 60,
                "v-wbc_counted": 200,
            },
        )
        reading.refresh_from_db()
        self.assertEqual(reading.density_per_ul, Decimal("2400.00"))
        response = self.client.get(reverse("smears:slide_history", args=["P1", slide.pk]))
        self.assertContains(response, "Asexual parasites counted")
        self.assertContains(response, "Reading (reader 1)")

    def test_results_list_filters(self):
        self.post_thick()
        self.post_thick(**{"v-result": "negative", "v-species": [], "v-asexual_parasites_counted": "",
                           "v-wbc_counted": ""})
        url = reverse("smears:results", args=["P1"])
        self.assertContains(self.client.get(url), "SM-1-TK-2")
        response = self.client.get(url, {"result": "positive"})
        self.assertContains(response, "SM-1-TK<")
        self.assertNotContains(response, "SM-1-TK-2")

    def test_slide_from_other_project_not_reachable(self):
        other = make_project("P2")
        ProjectSmearType.objects.create(project=other, smear_type=self.thick)
        add_member(other, self.reader, Role.READER)
        sample = make_sample(make_participant(other, "X"), "OTHER")
        slide = Slide.objects.create(sample=sample, smear_type=self.thick, slide_id="O-1")
        self.assertEqual(self.client.get(reverse("smears:slide_detail", args=["P1", slide.pk])).status_code, 404)

    def test_custom_smear_type_works_without_code(self):
        custom = SmearType.objects.create(code="borrelia", name="Borrelia smear", slide_suffix="BO")
        FieldDefinition.objects.create(smear_type=custom, key="result", label="Result", data_type="choice",
                                       choices="positive = Positive\nnegative = Negative", required=True)
        FieldDefinition.objects.create(smear_type=custom, key="spirochetes_per_field", label="Spirochetes per field",
                                       data_type="decimal", min_value=0)
        ProjectSmearType.objects.create(project=self.project, smear_type=custom)
        self.client.post(
            self.record_url(),
            {"smear_type": custom.pk, "stain": "giemsa", "reader": self.reader.pk, "read_at": now_str(),
             "v-result": "positive", "v-spirochetes_per_field": "2.5"},
        )
        reading = Reading.objects.get()
        self.assertTrue(reading.is_positive)
        self.assertEqual(reading.values["spirochetes_per_field"], 2.5)
        self.assertEqual(reading.slide.slide_id, "SM-1-BO")


class ProjectSmearTypeSettingsTests(TestCase):
    def test_new_project_gets_builtin_types_and_lead_can_change(self):
        lead = make_user("lead", can_create_projects=True)
        self.client.login(username="lead", password=PASSWORD)
        thick = SmearType.objects.get(code="malaria_thick")
        response = self.client.get(reverse("projects:create"))
        self.assertEqual(
            set(response.context["form"].initial["smear_types"]),
            set(SmearType.objects.filter(is_builtin=True).values_list("pk", flat=True)),
        )
        self.client.post(
            reverse("projects:create"),
            {"code": "NEW-1", "name": "New", "principal_investigator": "Dr", "default_wbc_per_ul": 8000,
             "smear_types": [thick.pk]},
        )
        links = ProjectSmearType.objects.filter(project__code="NEW-1")
        self.assertEqual([link.smear_type for link in links], [thick])
        self.assertEqual(lead.memberships.get().role, Role.LEAD)
