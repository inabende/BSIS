"""
Reading uploaded files and turning spreadsheet cells into clean values.

Spreadsheets from different studies say the same thing in many ways
("Pos", "+", "MPS seen"; "Pf", "P. falciparum"; 15/09/2026 or 2026-09-15),
so parsing here is deliberately forgiving and every guess is explained
when it fails.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from openpyxl import load_workbook

MAX_ROWS = 20_000


class ParseError(ValueError):
    """A cell couldn't be understood; the message is shown to the user."""


def norm(text):
    """Lowercase letters and digits only, for matching names loosely."""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


# --- Reading files ------------------------------------------------------------


@dataclass
class Table:
    columns: list          # column names, in file order
    rows: list             # [(row_number_in_file, {column: value})]
    sheet_names: list = field(default_factory=list)


def read_table(fileobj, filename, sheet_name="", header_row=1):
    """Read an .xlsx or .csv file into a Table. Raises ParseError with a readable message."""
    name = filename.lower()
    if name.endswith(".xlsx"):
        raw_rows, sheets = _read_xlsx(fileobj, sheet_name)
    elif name.endswith(".csv"):
        raw_rows, sheets = _read_csv(fileobj), []
    else:
        raise ParseError("Only .xlsx and .csv files can be imported.")

    if len(raw_rows) < header_row:
        raise ParseError(f"The file has no row {header_row} to read column names from.")
    header = raw_rows[header_row - 1]
    columns, seen = [], set()
    for index, cell in enumerate(header):
        label = str(cell).strip() if cell not in (None, "") else ""
        if not label:
            continue
        if label in seen:
            raise ParseError(f"The column name '{label}' appears twice. Rename one of them and upload again.")
        seen.add(label)
        columns.append((index, label))
    if not columns:
        raise ParseError(f"Row {header_row} has no column names.")

    rows = []
    for offset, raw in enumerate(raw_rows[header_row:], start=header_row + 1):
        values = {label: (raw[index] if index < len(raw) else None) for index, label in columns}
        if all(v in (None, "") or (isinstance(v, str) and not v.strip()) for v in values.values()):
            continue  # blank line
        rows.append((offset, values))
    if len(rows) > MAX_ROWS:
        raise ParseError(f"The file has {len(rows):,} rows; the limit is {MAX_ROWS:,}. Split it into smaller files.")
    return Table(columns=[label for _, label in columns], rows=rows, sheet_names=sheets)


def _read_xlsx(fileobj, sheet_name):
    try:
        workbook = load_workbook(fileobj, read_only=True, data_only=True)
    except Exception as error:  # openpyxl raises many kinds
        raise ParseError(f"This doesn't look like a valid Excel (.xlsx) file ({error.__class__.__name__}).")
    sheets = workbook.sheetnames
    if sheet_name:
        if sheet_name not in sheets:
            raise ParseError(f"There's no sheet called '{sheet_name}'. Sheets in this file: {', '.join(sheets)}.")
        sheet = workbook[sheet_name]
    else:
        sheet = workbook[sheets[0]]
    rows = [list(row) for row in sheet.iter_rows(values_only=True)]
    workbook.close()
    return rows, sheets


def _read_csv(fileobj):
    data = fileobj.read()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(text[:5000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect)]


# --- Cell values --------------------------------------------------------------


def is_blank(value):
    return value is None or (isinstance(value, str) and value.strip() in ("", "-", "—", "NA", "N/A", "n/a", "na", "."))


def as_text(value):
    """IDs and text. Excel often turns 1001 into 1001.0 – undo that."""
    if is_blank(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


DATE_FORMATS = {
    "dmy": ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%d %B %Y"],
    "mdy": ["%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%b %d %Y", "%b %d, %Y", "%B %d, %Y"],
    "ymd": ["%Y/%m/%d", "%Y.%m.%d"],
}


def as_date(value, order="dmy"):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = as_text(value)
    if not text:
        return None
    text = text.split(" ")[0] if re.match(r"^\d{4}-\d{2}-\d{2}[ T]", text) else text
    for fmt in ["%Y-%m-%d"] + DATE_FORMATS.get(order, []):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ParseError(f"'{text}' isn't a date I can read (expected {_example(order)}).")


def _example(order):
    return {"dmy": "e.g. 15/09/2026", "mdy": "e.g. 09/15/2026", "ymd": "e.g. 2026-09-15"}.get(order, "a date")


def as_time(value):
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, time):
        return value
    if isinstance(value, float) and 0 <= value < 1:  # Excel stores times as day fractions
        minutes = round(value * 24 * 60)
        return time(minutes // 60, minutes % 60)
    text = as_text(value)
    if not text:
        return None
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%H.%M", "%H%M"):
        try:
            return datetime.strptime(text.upper(), fmt).time()
        except ValueError:
            continue
    raise ParseError(f"'{text}' isn't a time I can read (expected e.g. 14:30).")


def as_number(value):
    if isinstance(value, bool):
        raise ParseError(f"'{value}' isn't a number.")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = as_text(value).replace(",", "").replace(" ", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        raise ParseError(f"'{as_text(value)}' isn't a number.")


TRUE_WORDS = {"yes", "y", "true", "t", "1", "x", "present", "seen", "positive", "pos", "+"}
FALSE_WORDS = {"no", "n", "false", "f", "0", "absent", "notseen", "none", "nil", "negative", "neg"}


def as_bool(value):
    if isinstance(value, bool):
        return value
    text = norm(as_text(value)) or as_text(value)
    if not text:
        return None
    if text in TRUE_WORDS:
        return True
    if text in FALSE_WORDS:
        return False
    raise ParseError(f"'{as_text(value)}' isn't yes or no.")


# Extra ways of writing particular choices. Keys are normalised (norm()).
CHOICE_SYNONYMS = {
    "sex": {
        "F": {"f", "female", "woman", "girl", "2"},
        "M": {"m", "male", "man", "boy", "1"},
        "U": {"u", "unknown", "notrecorded", "missing"},
    },
    "result": {
        "positive": {"positive", "pos", "p", "1", "yes", "y", "mps", "mpsseen", "seen", "detected"},
        "negative": {"negative", "neg", "n", "0", "no", "nmps", "nompsseen", "nompss", "notseen", "nil", "none",
                     "notdetected", "nmpsseen"},
    },
    "species": {
        "pf": {"pf", "pfal", "falciparum", "pfalciparum", "plasmodiumfalciparum"},
        "pv": {"pv", "pviv", "vivax", "pvivax", "plasmodiumvivax"},
        "pm": {"pm", "pmal", "malariae", "pmalariae", "plasmodiummalariae"},
        "po": {"po", "pov", "ovale", "povale", "plasmodiumovale"},
        "pk": {"pk", "knowlesi", "pknowlesi", "plasmodiumknowlesi"},
        "unidentified": {"unidentified", "unknown", "psp", "plasmodiumsp", "plasmodiumspp", "spp", "sp"},
    },
}
# Signs that a cell is positive even if written as a symbol.
SYMBOL_VALUES = {"result": {"+": "positive", "++": "positive", "+++": "positive", "-": "negative", "--": "negative"}}


def as_choice(value, choices, key=""):
    """Match a cell to one of [(value, label)] by value, label or known synonyms."""
    raw = as_text(value)
    if not raw:
        return None
    if raw in SYMBOL_VALUES.get(key, {}):
        return SYMBOL_VALUES[key][raw]
    wanted = norm(raw)
    for choice_value, label in choices:
        if wanted in (norm(choice_value), norm(label)):
            return choice_value
    for choice_value, words in CHOICE_SYNONYMS.get(key, {}).items():
        if wanted in words and choice_value in dict(choices):
            return choice_value
    options = ", ".join(label for _, label in choices)
    raise ParseError(f"'{raw}' isn't one of the options ({options}).")


SPLIT = re.compile(r"\s*(?:[,;/+&]|\band\b)\s*", re.IGNORECASE)


def as_multichoice(value, choices, key=""):
    raw = as_text(value)
    if not raw:
        return []
    if key == "species" and norm(raw) in {"nil", "none", "neg", "negative", "nompsseen", "nmps"}:
        return []
    if key == "species" and norm(raw) == "mixed":
        raise ParseError("'Mixed' on its own doesn't say which species. Write them out, e.g. 'Pf + Pm'.")
    picked = []
    for part in [p for p in SPLIT.split(raw) if p.strip()]:
        choice = as_choice(part, choices, key)
        if choice not in picked:
            picked.append(choice)
    return picked
