from datetime import timedelta

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import URLValidator
from django.utils import timezone

from .images import process_cover_image
from .models import Area, Category, Event

DT_FORMAT = "%Y-%m-%dT%H:%M"


CALL_FIELDS = (
    "seeking_vendors", "booth_price", "booth_price_max", "booth_price_on_request", "vendor_slots",
    "apply_by", "apply_link", "vendor_info", "vendor_call_closed",
)
D_FORMAT = "%Y-%m-%d"


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

    apply_by = forms.DateField(
        label="Apply by", required=False, input_formats=[D_FORMAT],
        widget=forms.DateInput(attrs={"type": "date"}, format=D_FORMAT),
        help_text="Optional. The last day vendors can apply.",
    )
    apply_link = forms.URLField(
        label="Application link", required=False, assume_scheme="https", max_length=300,
        validators=[URLValidator(schemes=["http", "https"])],
        help_text="Optional. A form or page where vendors apply. Otherwise they'll use your contact details.",
    )

    class Meta:
        model = Event
        fields = (
            "title", "category", "area", "venue", "description",
            "cover_image", "start_at", "end_at", "daily_hours", "is_free_entry", "entry_note",
        ) + CALL_FIELDS
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "vendor_info": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.vendor = vendor
        self.fields["area"].queryset = Area.objects.filter(city__is_active=True).select_related("city")
        # Only organisers get the "All categories" choice (a market can host any kind of vendor).
        organiser = bool(vendor is not None and vendor.is_organiser)
        self.fields["category"].queryset = Category.objects.all() if organiser else Category.objects.filter(is_general=False)
        if organiser:
            self.fields["category"].empty_label = "Choose a category"
        self.fields["cover_image"].widget.attrs["accept"] = "image/jpeg,image/png,image/webp"
        self.fields["cover_image"].required = self.instance.pk is None
        # Only organisers see the vendor-call section.
        self.offers_vendor_call = bool(vendor is not None and vendor.is_organiser)
        if not self.offers_vendor_call:
            for name in CALL_FIELDS:
                self.fields.pop(name, None)

    def main_fields(self):
        return [self[n] for n in self.fields if n not in CALL_FIELDS]

    def call_fields(self):
        return [self[n] for n in CALL_FIELDS if n in self.fields]

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
        if self.offers_vendor_call:
            self._clean_vendor_call(cleaned, end)
        if self.instance.pk is None and self.vendor is not None:
            since = timezone.now() - timedelta(days=1)
            recent = Event.objects.filter(vendor=self.vendor, created_at__gte=since).count()
            if recent >= settings.MAX_EVENTS_PER_DAY:
                raise ValidationError(
                    f"You can post up to {settings.MAX_EVENTS_PER_DAY} events per day. Try again tomorrow."
                )
        return cleaned

    def _clean_vendor_call(self, cleaned, end):
        if not cleaned.get("seeking_vendors"):
            # Not looking for vendors: don't keep stale booth details around.
            cleaned.update(booth_price=None, booth_price_max=None, booth_price_on_request=False, vendor_slots=None,
                           apply_by=None, apply_link="", vendor_info="", vendor_call_closed=False)
            return
        price, price_max = cleaned.get("booth_price"), cleaned.get("booth_price_max")
        ask = cleaned.get("booth_price_on_request")
        if ask and (price is not None or price_max is not None):
            self.add_error("booth_price_on_request", "Enter a price or tick \"Contact me for the booth price\", not both.")
        elif not ask and price is None and "booth_price" not in self.errors:
            self.add_error("booth_price", "Enter a booth price (0 for free), or tick \"Contact me for the booth price\".")
        if price_max is not None:
            if price is None and not ask:
                pass  # the missing starting price is already reported above
            elif price is not None and price_max < price:
                self.add_error("booth_price_max", "This must be at least the starting price.")
        apply_by = cleaned.get("apply_by")
        if apply_by:
            if end and apply_by > timezone.localtime(end).date():
                self.add_error("apply_by", "The application deadline must be on or before the last day of the event.")
            elif not self.instance.pk and apply_by < timezone.localdate():
                self.add_error("apply_by", "The application deadline can't be in the past.")
