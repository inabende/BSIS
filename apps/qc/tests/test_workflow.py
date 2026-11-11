from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.projects.models import Project, ProjectMembership
from apps.projects.tests.factories import PASSWORD, add_member, make_participant, make_project, make_sample, make_user
from apps.qc.models import FinalResult, QCSettings
from apps.smears.models import ProjectSmearType, Reading, SmearType, Slide

Role = ProjectMembership.Role


def when():
    return (timezone.localtime() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")


class DoubleReadingWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.project = make_project("P1")
        cls.thick = SmearType.objects.get(code="malaria_thick")
        ProjectSmearType.objects.create(project=cls.project, smear_type=cls.thick, readers_required=2)
        cls.r1 = make_user("r1")
        cls.r2 = make_user("r2")
        cls.r3 = make_user("r3")
        cls.reviewer = make_user("reviewer")
        cls.lead = make_user("lead")
        for user in (cls.r1, cls.r2, cls.r3):
            add_member(cls.project, user, Role.READER)
        add_member(cls.project, cls.reviewer, Role.REVIEWER)
        add_member(cls.project, cls.lead, Role.LEAD)
        cls.sample = make_sample(make_participant(cls.project), "SM-1")

    def login(self, user):
        self.client.login(username=user.username, password=PASSWORD)

    def thick_values(self, positive=True, parasites=50, species="pf"):
        if not positive:
            return {"v-result": "negative"}
        return {"v-result": "positive", "v-species": [species], "v-asexual_parasites_counted": parasites,
                "v-wbc_counted": 200}

    def record_first(self, reader, **values):
        self.login(reader)
        data = {"smear_type": self.thick.pk, "stain": "giemsa", "reader": reader.pk, "read_at": when()}
        data.update(values or self.thick_values())
        self.client.post(reverse("smears:smear_record", args=["P1", self.sample.pk]), data)
        return Slide.objects.latest("pk")

    def add_reading(self, slide, reader, **values):
        self.login(reader)
        data = {"reader": reader.pk, "read_at": when()}
        data.update(values or self.thick_values())
        return self.client.post(reverse("smears:reading_create", args=["P1", slide.pk]), data)

    def detail(self, slide):
        return self.client.get(reverse("smears:slide_detail", args=["P1", slide.pk]))

    # --- Flow ----------------------------------------------------------------

    def test_first_reading_waits_for_second(self):
        slide = self.record_first(self.r1)
        self.assertEqual(slide.readers_required, 2)
        self.assertEqual(slide.status, Slide.Status.READING)
        self.assertFalse(FinalResult.objects.exists())

    def test_agreeing_readers_give_mean_final(self):
        slide = self.record_first(self.r1, **self.thick_values(parasites=50))   # 2,000/µL
        self.add_reading(slide, self.r2, **self.thick_values(parasites=60))     # 2,400/µL
        slide.refresh_from_db()
        self.assertEqual(slide.status, Slide.Status.FINAL)
        self.assertEqual(slide.final.density_per_ul, Decimal("2200.00"))
        self.assertFalse(slide.final.had_discordance)

    def test_discordant_then_tiebreaker(self):
        slide = self.record_first(self.r1)
        self.add_reading(slide, self.r2, **self.thick_values(positive=False))
        slide.refresh_from_db()
        self.assertEqual(slide.status, Slide.Status.DISCORDANT)

        self.add_reading(slide, self.r3, **self.thick_values(parasites=40))
        slide.refresh_from_db()
        self.assertEqual(slide.status, Slide.Status.FINAL)
        self.assertTrue(slide.final.had_discordance)
        self.assertEqual(slide.final.readings_used, "3")
        self.assertEqual(slide.final.density_per_ul, Decimal("1600.00"))

    def test_same_reader_cannot_read_twice(self):
        slide = self.record_first(self.r1)
        response = self.add_reading(slide, self.r1)
        self.assertContains(response, "Select a valid choice")
        self.assertEqual(slide.readings.count(), 1)

    def test_no_reading_slot_when_final(self):
        slide = self.record_first(self.r1)
        self.add_reading(slide, self.r2)
        self.login(self.r3)
        response = self.client.get(reverse("smears:reading_create", args=["P1", slide.pk]))
        self.assertEqual(response.status_code, 403)

    # --- Blinding --------------------------------------------------------------

    def test_reader_2_cannot_see_reader_1_result(self):
        slide = self.record_first(self.r1, **self.thick_values(parasites=77))
        self.login(self.r2)
        response = self.detail(slide)
        self.assertContains(response, "being read blind")
        self.assertNotContains(response, "3,080")  # 77 / 200 × 8000
        # ...nor through the history page or the edit page.
        history = self.client.get(reverse("smears:slide_history", args=["P1", slide.pk]))
        self.assertNotContains(history, "77")
        reading = slide.readings.get()
        self.assertEqual(
            self.client.get(reverse("smears:reading_update", args=["P1", slide.pk, reading.pk])).status_code, 403
        )

    def test_own_reader_and_reviewer_can_see(self):
        slide = self.record_first(self.r1, **self.thick_values(parasites=77))
        self.assertContains(self.detail(slide), "3,080")
        self.login(self.reviewer)
        self.assertContains(self.detail(slide), "3,080")

    def test_everyone_sees_after_final(self):
        slide = self.record_first(self.r1, **self.thick_values(parasites=77))
        self.add_reading(slide, self.r2, **self.thick_values(parasites=80))
        self.login(self.r3)
        self.assertContains(self.detail(slide), "3,080")

    def test_results_list_shows_status_not_reader_1(self):
        self.record_first(self.r1, **self.thick_values(parasites=77))
        self.login(self.r2)
        response = self.client.get(reverse("smears:results", args=["P1"]))
        self.assertContains(response, "Awaiting reader 2")
        self.assertNotContains(response, "3,080")

    def test_reviewer_sees_discordance_reasons(self):
        slide = self.record_first(self.r1)
        self.add_reading(slide, self.r2, **self.thick_values(positive=False))
        self.login(self.reviewer)
        self.assertContains(self.detail(slide), "Reader 1 positive, reader 2 negative")
        self.login(self.r3)
        self.assertNotContains(self.detail(slide), "Reader 1 positive, reader 2 negative")

    # --- Locking ----------------------------------------------------------------

    def final_slide(self):
        slide = self.record_first(self.r1)
        self.add_reading(slide, self.r2)
        return slide

    def test_reviewer_locks_and_editing_is_blocked(self):
        slide = self.final_slide()
        self.login(self.reviewer)
        self.client.post(reverse("qc:lock", args=["P1", slide.pk]))
        final = FinalResult.objects.get(slide=slide)
        self.assertTrue(final.locked)
        self.assertEqual(final.locked_by, self.reviewer)

        self.login(self.r1)
        reading = slide.readings.get(reader_number=1)
        self.assertEqual(
            self.client.get(reverse("smears:reading_update", args=["P1", slide.pk, reading.pk])).status_code, 403
        )
        self.assertEqual(self.client.get(reverse("smears:slide_update", args=["P1", slide.pk])).status_code, 403)

    def test_reader_and_lead_cannot_lock(self):
        slide = self.final_slide()
        for user in (self.r1, self.lead):
            self.login(user)
            self.assertEqual(self.client.post(reverse("qc:lock", args=["P1", slide.pk])).status_code, 403)

    def test_unlock_needs_reason_and_is_recorded(self):
        slide = self.final_slide()
        self.login(self.reviewer)
        self.client.post(reverse("qc:lock", args=["P1", slide.pk]))
        response = self.client.post(reverse("qc:unlock", args=["P1", slide.pk]), {"reason": ""})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(FinalResult.objects.get(slide=slide).locked)

        self.client.post(reverse("qc:unlock", args=["P1", slide.pk]), {"reason": "Typo in reader 2 count"})
        final = FinalResult.objects.get(slide=slide)
        self.assertFalse(final.locked)
        self.assertEqual(final.history.first().history_change_reason, "Unlocked: Typo in reader 2 count")
        history = self.client.get(reverse("smears:slide_history", args=["P1", slide.pk]))
        self.assertContains(history, "Typo in reader 2 count")

    def test_bulk_approve(self):
        first = self.final_slide()
        self.sample = make_sample(self.sample.participant, "SM-2")
        second = self.final_slide()
        self.login(self.reviewer)
        response = self.client.get(reverse("qc:review", args=["P1"]))
        self.assertContains(response, "Approve and lock selected")
        self.client.post(reverse("qc:bulk_approve", args=["P1"]), {"slide": [first.pk, second.pk]})
        self.assertEqual(FinalResult.objects.filter(locked=True).count(), 2)

    def test_editing_reading_recomputes_final(self):
        slide = self.final_slide()  # both 50 parasites → agree
        self.login(self.r2)
        reading = slide.readings.get(reader_number=2)
        self.client.post(
            reverse("smears:reading_update", args=["P1", slide.pk, reading.pk]),
            {"reader": self.r2.pk, "read_at": when(), "v-result": "negative"},
        )
        slide.refresh_from_db()
        self.assertEqual(slide.status, Slide.Status.DISCORDANT)
        self.assertFalse(FinalResult.objects.filter(slide=slide).exists())


class QCSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.project = make_project("P1")
        cls.thick = SmearType.objects.get(code="malaria_thick")
        cls.link = ProjectSmearType.objects.create(project=cls.project, smear_type=cls.thick)
        cls.lead = make_user("lead")
        cls.reader = make_user("reader")
        add_member(cls.project, cls.lead, Role.LEAD)
        add_member(cls.project, cls.reader, Role.READER)

    def test_lead_changes_settings(self):
        self.client.login(username="lead", password=PASSWORD)
        self.client.post(
            reverse("qc:settings", args=["P1"]),
            {f"readers_{self.thick.pk}": 2, "density_threshold_pct": 30, "final_rule": "closest_two"},
        )
        self.link.refresh_from_db()
        settings = QCSettings.objects.get(project=self.project)
        self.assertEqual(self.link.readers_required, 2)
        self.assertEqual((settings.density_threshold_pct, settings.final_rule), (30, "closest_two"))

    def test_reader_cannot_change_settings(self):
        self.client.login(username="reader", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("qc:settings", args=["P1"])).status_code, 403)

    def test_existing_slides_keep_reader_count(self):
        sample = make_sample(make_participant(self.project), "S")
        slide = Slide.objects.create(sample=sample, smear_type=self.thick, slide_id="S-TK", readers_required=1)
        self.link.readers_required = 2
        self.link.save()
        slide.refresh_from_db()
        self.assertEqual(slide.readers_required, 1)

    def test_closed_project_reviewer_cannot_lock(self):
        reviewer = make_user("rev")
        add_member(self.project, reviewer, Role.REVIEWER)
        sample = make_sample(make_participant(self.project), "S")
        slide = Slide.objects.create(sample=sample, smear_type=self.thick, slide_id="S-TK")
        Reading.objects.create(slide=slide, reader=self.reader, is_positive=False)
        from apps.qc.services import evaluate_slide

        evaluate_slide(slide)
        self.project.status = Project.Status.CLOSED
        self.project.save()
        self.client.login(username="rev", password=PASSWORD)
        self.assertEqual(self.client.post(reverse("qc:lock", args=["P1", slide.pk])).status_code, 403)
