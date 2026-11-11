# Administrator Guide — Smear Types

| | |
|---|---|
| **Version** | 0.1 |
| **Date** | 2026-11-11 |
| **For** | System admins |

## Built-in smear types

The system comes with three smear types. You can change their labels, help text, order and limits, and add extra fields to them. You can't change their internal names or calculations, because the formulas depend on them.

| Smear type | Slide ID suffix | Calculation |
|---|---|---|
| Malaria – thick smear | `TK` | Parasite density and gametocyte density per µL |
| Malaria – thin smear | `TN` | Parasitaemia % |
| General hematology | `HM` | Differential count must total 100% |

## Choosing smear types for a project

Project leads tick the smear types their project records under **Project → Edit → Smear types recorded in this project**. New projects start with all built-in types ticked. Only ticked types appear when staff record a result.

## Adding a new smear type

Example: a Borrelia smear with a result, a count per field, and a comment.

1. Go to **Administration → Smear types → Add smear type**.
2. Fill in:
   - **Code:** `borrelia` (lowercase, no spaces; can't be changed later without care)
   - **Name:** `Borrelia smear` (what staff see)
   - **Slide suffix:** `BO` (sample `SM-001` gets slide ID `SM-001-BO`)
   - **Calculation:** `None`
3. Under **Field definitions**, add one row per field:

   | Key | Label | Type | Settings |
   |---|---|---|---|
   | `result` | Result | Pick one | Choices: `positive = Positive` and `negative = Negative` on separate lines; tick **Required** |
   | `spirochetes_per_field` | Spirochetes per field | Decimal number | Minimum 0; tick **Required if positive** |
   | `comments_morphology` | Morphology notes | Long text | — |

4. Save. Then project leads can tick the new type for their projects.

### Field types

| Type | Shown as | Notes |
|---|---|---|
| Whole number | Number box | Use minimum/maximum to block impossible values |
| Decimal number | Number box | Up to 4 decimal places |
| Short text / Long text | Text box / text area | |
| Pick one | Radio buttons (up to 3 options) or a drop-down | Needs choices |
| Pick several | Tick boxes | Needs choices |
| Yes / no | Tick box | Unticked is saved as "No" |
| Date | Date picker | |

**Choices** go one per line, either `value = Label` (recommended) or just `Label`. The value is what's stored and exported, so keep it short and don't change it once results exist.

### Special keys

Use these keys so a custom type's results appear in result filters and, from Phase 4, in cross-project search:

- **`result`** with choices `positive` and `negative`. It also makes **Required if positive** work.
- **`species`** (Pick several) with choices `pf`, `pv`, `pm`, `po`, `pk`, `unidentified`.

## Retiring a field or smear type

Fields and smear types **can't be deleted**, because saved results refer to them. To retire one, untick **Is active**:

- An inactive **field** no longer appears on forms. Old results still show its values.
- An inactive **smear type** can't be chosen for new results. Existing slides keep it.

All changes to smear types and fields are recorded in their history (the **History** button in Administration).
