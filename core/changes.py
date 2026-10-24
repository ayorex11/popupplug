"""Plain-English record of what an edit changed, so staff can re-approve with eyes open."""
from datetime import date, datetime

from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

EMPTY = "(empty)"


def _show(field, value):
    if isinstance(field, forms.ModelChoiceField) and not isinstance(field, forms.ModelMultipleChoiceField):
        if value in (None, ""):
            return EMPTY
        if not hasattr(value, "pk"):
            value = field.queryset.filter(pk=value).first() or value
        return str(value)
    if isinstance(value, (list, tuple, set)) or hasattr(value, "all"):
        items = value.all() if hasattr(value, "all") else value
        names = [str(i) if hasattr(i, "pk") else str(field.queryset.filter(pk=i).first() or i) for i in items]
        return ", ".join(sorted(names)) or EMPTY
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, UploadedFile):
        return "new image uploaded"
    if hasattr(value, "name") and hasattr(value, "storage"):  # FieldFile
        return "previous image" if value else EMPTY
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime("%a %d %b %Y, %I:%M %p") if timezone.is_aware(value) else str(value)
    if isinstance(value, date):
        return value.strftime("%a %d %b %Y")
    if value in (None, ""):
        return EMPTY
    choices = dict(getattr(field, "choices", []) or [])
    text = str(choices.get(value, value))
    return text if len(text) <= 240 else text[:237] + "..."


def form_changes(form):
    """{label: {"old": str, "new": str}} for every field the user actually changed."""
    out = {}
    for name in form.changed_data:
        field = form.fields[name]
        old, new = _show(field, form.initial.get(name)), _show(field, form.cleaned_data.get(name))
        if old != new:
            out[str(field.label or name.replace("_", " ").title())] = {"old": old, "new": new}
    return out


def merge_changes(existing, new):
    """Keep the first old value and the latest new value across several edits before approval."""
    merged = {k: dict(v) for k, v in (existing or {}).items()}
    for label, change in new.items():
        if label in merged:
            merged[label]["new"] = change["new"]
        else:
            merged[label] = dict(change)
    return {k: v for k, v in merged.items() if v["old"] != v["new"]}
