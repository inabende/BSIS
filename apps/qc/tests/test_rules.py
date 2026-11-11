from decimal import Decimal

from django.test import SimpleTestCase

from apps.qc.rules import CLOSEST_TWO, TIEBREAKER, decide, discordance_reasons, percent_difference
from apps.smears.models import READING_SPECIES_CHOICES

LABELS = dict(READING_SPECIES_CHOICES)


class R:
    """A minimal stand-in for a Reading."""

    def __init__(self, n, positive, species="", density=None, parasitaemia=None):
        self.reader_number = n
        self.is_positive = positive
        self.species = species
        self.density_per_ul = None if density is None else Decimal(density)
        self.parasitaemia_pct = None if parasitaemia is None else Decimal(parasitaemia)

    def get_species_display(self):
        return LABELS.get(self.species, self.species)


class DiscordanceTests(SimpleTestCase):
    def test_percent_difference_is_relative_to_mean(self):
        self.assertEqual(percent_difference(1000, 1400).quantize(Decimal("0.01")), Decimal("33.33"))
        self.assertEqual(percent_difference(0, 0), 0)

    def test_positive_vs_negative(self):
        reasons = discordance_reasons(R(1, True, "pf", 500), R(2, False), 50)
        self.assertEqual(reasons, ["Reader 1 positive, reader 2 negative"])

    def test_species_differ(self):
        reasons = discordance_reasons(R(1, True, "pf", 500), R(2, True, "pv", 500), 50)
        self.assertIn("Species differ", reasons[0])

    def test_density_within_threshold_agrees(self):
        self.assertEqual(discordance_reasons(R(1, True, "pf", 1000), R(2, True, "pf", 1400), 50), [])

    def test_density_beyond_threshold(self):
        reasons = discordance_reasons(R(1, True, "pf", 1000), R(2, True, "pf", 1800), 50)
        self.assertIn("Density differs by 57%", reasons[0])

    def test_threshold_is_configurable(self):
        self.assertEqual(discordance_reasons(R(1, True, "pf", 1000), R(2, True, "pf", 1800), 60), [])

    def test_parasitaemia_compared(self):
        reasons = discordance_reasons(R(1, True, "pf", parasitaemia="1.0"), R(2, True, "pf", parasitaemia="3.0"), 50)
        self.assertIn("Parasitaemia differs", reasons[0])

    def test_two_negatives_agree(self):
        self.assertEqual(discordance_reasons(R(1, False), R(2, False), 50), [])

    def test_no_result_field_not_compared(self):
        self.assertEqual(discordance_reasons(R(1, None), R(2, None), 50), [])


class DecideTests(SimpleTestCase):
    def test_no_readings_pending(self):
        self.assertEqual(decide([], 2, 50, TIEBREAKER), ("pending", None, []))

    def test_single_reader_final_immediately(self):
        status, final, _ = decide([R(1, True, "pf", 2000)], 1, 50, TIEBREAKER)
        self.assertEqual(status, "final")
        self.assertEqual(final["density_per_ul"], Decimal(2000))
        self.assertEqual(final["readings_used"], "1")

    def test_double_reading_waits_for_reader_2(self):
        self.assertEqual(decide([R(1, True, "pf", 2000)], 2, 50, TIEBREAKER)[0], "reading")

    def test_agreeing_positives_use_mean(self):
        status, final, reasons = decide([R(1, True, "pf", 1000), R(2, True, "pf", 1200)], 2, 50, TIEBREAKER)
        self.assertEqual(status, "final")
        self.assertEqual(final["density_per_ul"], Decimal("1100.00"))
        self.assertEqual(final["readings_used"], "1,2")
        self.assertEqual(reasons, [])

    def test_agreeing_negatives(self):
        status, final, _ = decide([R(1, False), R(2, False)], 2, 50, TIEBREAKER)
        self.assertEqual((status, final["is_positive"], final["readings_used"]), ("final", False, "1,2"))

    def test_discordant_waits_for_tiebreaker(self):
        status, final, reasons = decide([R(1, True, "pf", 1000), R(2, False)], 2, 50, TIEBREAKER)
        self.assertEqual((status, final), ("discordant", None))
        self.assertTrue(reasons)

    def test_tiebreaker_decides(self):
        readings = [R(1, True, "pf", 1000), R(2, False), R(3, True, "pf", 900)]
        status, final, reasons = decide(readings, 2, 50, TIEBREAKER)
        self.assertEqual(status, "final")
        self.assertEqual(final["density_per_ul"], Decimal(900))
        self.assertEqual(final["readings_used"], "3")
        self.assertTrue(reasons)  # the disagreement is still recorded

    def test_closest_two_mean_for_density(self):
        readings = [R(1, True, "pf", 1000), R(2, True, "pf", 3000), R(3, True, "pf", 1200)]
        status, final, _ = decide(readings, 2, 50, CLOSEST_TWO)
        self.assertEqual(final["density_per_ul"], Decimal("1100.00"))
        self.assertEqual(final["readings_used"], "1,3")

    def test_closest_two_majority_negative(self):
        readings = [R(1, True, "pf", 40), R(2, False), R(3, False)]
        status, final, _ = decide(readings, 2, 50, CLOSEST_TWO)
        self.assertFalse(final["is_positive"])
        self.assertEqual(final["readings_used"], "2,3")

    def test_closest_two_species_majority(self):
        readings = [R(1, True, "pf", 1000), R(2, True, "pv", 1100), R(3, True, "pf", 1050)]
        _, final, _ = decide(readings, 2, 50, CLOSEST_TWO)
        self.assertEqual(final["species"], "pf")
        self.assertEqual(final["readings_used"], "1,3")
