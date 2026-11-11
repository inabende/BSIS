"""Turns django-simple-history records into readable 'who changed what' rows."""

HISTORY_TYPES = {"+": "Created", "~": "Changed", "-": "Deleted"}
HIDDEN_FIELDS = {"updated_at", "created_at", "password", "last_login"}


def _display(record, field_name, value):
    """Show choice labels and related object names instead of raw values."""
    try:
        field = record.instance_type._meta.get_field(field_name)
    except Exception:
        return value
    if field.many_to_many:
        # Values arrive as [{"project": 1, "site": 2}, ...]; show the related names.
        key = field.m2m_reverse_field_name()
        ids = [row.get(key) for row in value or []]
        return ", ".join(str(o) for o in field.related_model.objects.filter(pk__in=ids)) or None
    if field.choices:
        return dict(field.flatchoices).get(value, value)
    if field.is_relation and value is not None:
        related = field.related_model.objects.filter(pk=value).first()
        return str(related) if related else value
    return value


def history_rows(obj, limit=50):
    """Newest first: date, user, action, and a list of (field label, old, new)."""
    rows = []
    records = list(obj.history.select_related("history_user").all()[: limit + 1])
    for index, record in enumerate(records[:limit]):
        changes = []
        previous = records[index + 1] if index + 1 < len(records) else None
        if record.history_type == "~" and previous is not None:
            delta = record.diff_against(previous)
            for change in delta.changes:
                if change.field in HIDDEN_FIELDS:
                    continue
                try:
                    label = record.instance_type._meta.get_field(change.field).verbose_name
                except Exception:
                    label = change.field
                changes.append(
                    (
                        str(label).capitalize(),
                        _display(record, change.field, change.old),
                        _display(record, change.field, change.new),
                    )
                )
        rows.append(
            {
                "date": record.history_date,
                "user": record.history_user,
                "action": HISTORY_TYPES.get(record.history_type, record.history_type),
                "changes": changes,
                "reason": record.history_change_reason,
            }
        )
    return rows
