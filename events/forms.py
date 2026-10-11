from datetime import timedelta

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from .images import process_cover_image
from .models import Area, Category, Event

DT_FORMAT = "%Y-%m-%dT%H:%M"


class EventForm(forms.ModelForm):
    start_at = forms.DateTimeField(
        label="Starts",
        input_formats=[DT_FORMAT],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DT_FORMAT),
    )
    end_at = forms.DateTimeField(
        label="Ends",
        input_formats=[DT_FORMAT],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DT_FORMAT),
    )

    class Meta:
        model = Event
        fields = (
            "title", "category", "area", "venue", "description",
            "cover_image", "start_at", "end_at", "is_free_entry", "entry_note",
        )
        widgets = {"description": forms.Textarea(attrs={"rows": 6})}

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.vendor = vendor
        self.fields["area"].queryset = Area.objects.filter(city__is_active=True).select_related("city")
        self.fields["category"].queryset = Category.objects.all()
        self.fields["cover_image"].widget.attrs["accept"] = "image/jpeg,image/png,image/webp"
        self.fields["cover_image"].required = self.instance.pk is None

    def clean_cover_image(self):
        image = self.cleaned_data.get("cover_image")
        # On edit with no new upload, Django hands back the existing FieldFile; only
        # freshly uploaded files need validating and compressing.
        if isinstance(image, UploadedFile):
            return process_cover_image(image)
        return image

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_at"), cleaned.get("end_at")
        if start and end:
            if end <= start:
                self.add_error("end_at", "End time must be after the start time.")
            if end - start > timedelta(days=14):
                self.add_error("end_at", "Pop-ups longer than 14 days aren't supported.")
        if start and not self.instance.pk and start < timezone.now() - timedelta(hours=1):
            self.add_error("start_at", "Start time can't be in the past.")
        if self.instance.pk is None and self.vendor is not None:
            since = timezone.now() - timedelta(days=1)
            recent = Event.objects.filter(vendor=self.vendor, created_at__gte=since).count()
            if recent >= settings.MAX_EVENTS_PER_DAY:
                raise ValidationError(
                    f"You can post up to {settings.MAX_EVENTS_PER_DAY} events per day. Try again tomorrow."
                )
        return cleaned
