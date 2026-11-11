from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.smears.calculations import calculate
from apps.smears.models import SmearType

PROJECT = SimpleNamespace(default_wbc_per_ul=8000)


class CalculationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.thick = SmearType.objects.get(code="malaria_thick")
        cls.thin = SmearType.objects.get(code="malaria_thin")
        cls.hema = SmearType.objects.get(code="hematology")

    def errors(self, smear_type, values):
        with self.assertRaises(ValidationError) as ctx:
            calculate(smear_type, values, PROJECT)
        return ctx.exception.message_dict

    # --- Thick ---------------------------------------------------------------

    def test_thick_density_uses_project_default_wbc(self):
        r = calculate(self.thick, {"result": "positive", "species": ["pf"], "asexual_parasites_counted": 50,
                                   "wbc_counted": 200}, PROJECT)
        self.assertEqual(r["density_per_ul"], Decimal("2000.00"))
        self.assertTrue(r["is_positive"])
        self.assertEqual(r["species"], "pf")
        self.assertEqual(r["derived"]["wbc_per_ul_used"], 8000)

    def test_thick_density_uses_measured_wbc_when_given(self):
        r = calculate(self.thick, {"result": "positive", "species": ["pf"], "asexual_parasites_counted": 50,
                                   "wbc_counted": 200, "wbc_per_ul": 6000}, PROJECT)
        self.assertEqual(r["density_per_ul"], Decimal("1500.00"))

    def test_thick_project_specific_default(self):
        r = calculate(self.thick, {"result": "positive", "species": ["pf"], "asexual_parasites_counted": 10,
                                   "wbc_counted": 500}, SimpleNamespace(default_wbc_per_ul=7500))
        self.assertEqual(r["density_per_ul"], Decimal("150.00"))

    def test_thick_gametocyte_density_and_flag(self):
        r = calculate(self.thick, {"result": "positive", "species": ["pf"], "asexual_parasites_counted": 0,
                                   "gametocytes_counted": 4, "wbc_counted": 200}, PROJECT)
        self.assertEqual(r["density_per_ul"], Decimal("0.00"))
        self.assertEqual(r["derived"]["gametocyte_density_per_ul"], 160.0)
        self.assertTrue(r["derived"]["gametocytes_present"])

    def test_thick_mixed_species(self):
        r = calculate(self.thick, {"result": "positive", "species": ["pf", "pm"], "asexual_parasites_counted": 5,
                                   "wbc_counted": 200}, PROJECT)
        self.assertEqual(r["species"], "mixed")

    def test_thick_negative_is_zero_density(self):
        r = calculate(self.thick, {"result": "negative", "fields_examined": 100}, PROJECT)
        self.assertFalse(r["is_positive"])
        self.assertEqual(r["density_per_ul"], Decimal("0.00"))

    def test_thick_positive_without_parasites_rejected(self):
        errors = self.errors(self.thick, {"result": "positive", "species": ["pf"], "wbc_counted": 200})
        self.assertIn("asexual_parasites_counted", errors)

    def test_thick_negative_with_parasites_rejected(self):
        errors = self.errors(self.thick, {"result": "negative", "asexual_parasites_counted": 3, "wbc_counted": 200})
        self.assertIn("asexual_parasites_counted", errors)

    def test_negative_with_species_rejected(self):
        errors = self.errors(self.thick, {"result": "negative", "species": ["pf"]})
        self.assertIn("species", errors)

    # --- Thin ----------------------------------------------------------------

    def test_thin_parasitaemia(self):
        r = calculate(self.thin, {"result": "positive", "species": ["pf"], "rbc_counted": 2000,
                                  "infected_rbc": 30, "stages": ["rings"]}, PROJECT)
        self.assertEqual(r["parasitaemia_pct"], Decimal("1.5000"))
        self.assertIsNone(r["density_per_ul"])

    def test_thin_infected_more_than_counted_rejected(self):
        errors = self.errors(self.thin, {"result": "positive", "species": ["pf"], "rbc_counted": 10,
                                         "infected_rbc": 11})
        self.assertIn("infected_rbc", errors)

    def test_thin_negative_with_stages_rejected(self):
        errors = self.errors(self.thin, {"result": "negative", "stages": ["rings"]})
        self.assertIn("stages", errors)

    # --- Hematology ----------------------------------------------------------

    def test_hematology_differential_must_total_100(self):
        errors = self.errors(self.hema, {"neutrophils": 60, "lymphocytes": 30})
        self.assertIn("currently 90%", errors["neutrophils"][0])

    def test_hematology_valid(self):
        r = calculate(self.hema, {"neutrophils": 60, "lymphocytes": 30, "monocytes": 6, "eosinophils": 3,
                                  "basophils": 1}, PROJECT)
        self.assertIsNone(r["is_positive"])
        self.assertEqual(r["derived"]["differential_total"], 100)

    def test_hematology_without_differential_is_fine(self):
        r = calculate(self.hema, {"platelet_estimate": "adequate"}, PROJECT)
        self.assertEqual(r["derived"], {})
