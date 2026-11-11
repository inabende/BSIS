"""
Calculations and consistency checks run whenever a reading is saved.

``calculate(smear_type, values, project)`` returns the searchable columns
for Reading plus any derived values to store in ``Reading.values``. It raises
``ValidationError({field_key: message})`` when the entered values don't make
sense together (e.g. a negative slide with parasites counted).

Formulas (docs/01-requirements.md FR-10):
- Thick: density (/µL) = parasites counted ÷ WBCs counted × WBC/µL
  (measured WBC/µL if entered, else the project default, else 8,000)
- Thin:  parasitaemia (%) = infected RBCs ÷ RBCs counted × 100
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError

from .models import MIXED, SmearType

DEFAULT_WBC_PER_UL = 8000
Calc = SmearType.Calculation


def _dec(value, places):
    return Decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _common(values):
    """Positive/negative and species, from the 'result' and 'species' fields if the type has them."""
    result = values.get("result")
    is_positive = {"positive": True, "negative": False}.get(result)
    species_list = values.get("species") or []
    if len(species_list) > 1:
        species = MIXED
    elif species_list:
        species = species_list[0]
    else:
        species = ""
    return is_positive, species


def _thick(values, project, errors):
    out = {}
    positive = values.get("result") == "positive"
    asexual = values.get("asexual_parasites_counted")
    gametocytes = values.get("gametocytes_counted")
    wbc = values.get("wbc_counted")

    if positive:
        if not asexual and not gametocytes:
            errors["asexual_parasites_counted"] = (
                "A positive slide needs asexual parasites or gametocytes counted."
            )
    else:
        if asexual:
            errors["asexual_parasites_counted"] = "A negative slide can't have parasites counted."
        if gametocytes or values.get("gametocytes_present"):
            errors["gametocytes_counted"] = "A negative slide can't have gametocytes."

    if gametocytes and not values.get("gametocytes_present"):
        # Counting gametocytes means they were seen.
        out["gametocytes_present"] = True

    wbc_per_ul = values.get("wbc_per_ul") or getattr(project, "default_wbc_per_ul", None) or DEFAULT_WBC_PER_UL
    if wbc:
        out["wbc_per_ul_used"] = wbc_per_ul
        density = Decimal(asexual or 0) / Decimal(wbc) * Decimal(wbc_per_ul)
        out["density_per_ul"] = _dec(density, 2)
        if gametocytes is not None:
            out["gametocyte_density_per_ul"] = float(_dec(Decimal(gametocytes) / Decimal(wbc) * Decimal(wbc_per_ul), 2))
    elif not positive:
        out["density_per_ul"] = Decimal("0.00")
    return out


def _thin(values, errors):
    out = {}
    positive = values.get("result") == "positive"
    rbc = values.get("rbc_counted")
    infected = values.get("infected_rbc")
    stages = values.get("stages") or []

    if rbc and infected is not None and infected > rbc:
        errors["infected_rbc"] = "Infected RBCs can't be more than RBCs counted."
    if positive and not infected and not stages:
        errors["infected_rbc"] = "A positive slide needs infected RBCs counted or stages recorded."
    if not positive:
        if infected:
            errors["infected_rbc"] = "A negative slide can't have infected RBCs."
        if stages:
            errors["stages"] = "A negative slide can't have parasite stages."

    if rbc and infected is not None and "infected_rbc" not in errors:
        out["parasitaemia_pct"] = _dec(Decimal(infected) / Decimal(rbc) * 100, 4)
    elif not positive:
        out["parasitaemia_pct"] = Decimal("0.0000")
    return out


DIFFERENTIAL_KEYS = ["neutrophils", "band_forms", "lymphocytes", "monocytes", "eosinophils", "basophils"]


def _hematology(values, errors):
    entered = [values[k] for k in DIFFERENTIAL_KEYS if values.get(k) is not None]
    if entered:
        total = sum(entered)
        if total != 100:
            errors["neutrophils"] = f"The differential count must total 100% (currently {total}%)."
        return {"differential_total": total}
    return {}


def calculate(smear_type, values, project):
    """Return {is_positive, species, density_per_ul, parasitaemia_pct, derived} or raise ValidationError."""
    errors = {}
    is_positive, species = _common(values)

    if is_positive is False and values.get("species"):
        errors["species"] = "Don't record species for a negative slide."

    derived = {}
    if smear_type.calculation == Calc.THICK_DENSITY:
        derived = _thick(values, project, errors)
    elif smear_type.calculation == Calc.THIN_PARASITAEMIA:
        derived = _thin(values, errors)
    elif smear_type.calculation == Calc.HEMATOLOGY:
        derived = _hematology(values, errors)

    if errors:
        raise ValidationError(errors)

    return {
        "is_positive": is_positive,
        "species": species,
        "density_per_ul": derived.pop("density_per_ul", None),
        "parasitaemia_pct": derived.pop("parasitaemia_pct", None),
        "derived": derived,
    }
