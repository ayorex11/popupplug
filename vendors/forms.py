import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.forms import PasswordResetForm, AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.models import Q

from .models import Vendor

User = get_user_model()

NG_PHONE_RE = re.compile(r"^(?:\+?234|0)[789][01]\d{8}$")
HANDLE_RE = re.compile(r"^[A-Za-z0-9._]{1,60}$")
SOCIAL_FIELDS = ("instagram", "tiktok", "twitter")
CONTACT_FIELDS = ("phone", "instagram", "tiktok", "twitter", "website")
ROLE_CHOICES = [
    ("vendor", "I sell at pop-ups (vendor)"),
    ("organiser", "I organise pop-ups or markets (organiser)"),
    ("both", "Both"),
]


def clean_handle(value):
    """Accept 'name', '@name' or a pasted profile link, and return just the handle."""
    value = (value or "").strip()
    if not value:
        return ""
    value = value.split("?")[0].split("#")[0].rstrip("/")
    if "/" in value:
        value = value.rsplit("/", 1)[-1]
    value = value.lstrip("@")
    if not HANDLE_RE.match(value):
        raise ValidationError("Enter just your handle, like yourbrand (letters, numbers, dots and underscores).")
    return value


def clean_website(value):
    value = (value or "").strip()
    if not value:
        return ""
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    try:
        URLValidator(schemes=["http", "https"])(value)
    except ValidationError:
        raise ValidationError("Enter a valid website address, like https://yourbrand.com.") from None
    return value


class EmailAuthenticationForm(AuthenticationForm):
    """Login with email (stored as the username). Admin accounts with a plain username still work."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"

    def clean_username(self):
        value = self.cleaned_data["username"].strip()
        return value.lower() if "@" in value else value


class ProfileFieldsMixin:
    """Shared cleaning for the signup and profile forms: handles, links, phone and the role rules."""

    def clean_role(self):
        return self.cleaned_data.get("role") or Vendor.Role.VENDOR

    def clean_phone(self):
        phone = re.sub(r"[\s\-]", "", self.cleaned_data.get("phone") or "")
        if not phone:
            return ""
        if not NG_PHONE_RE.match(phone):
            raise ValidationError("Enter a valid Nigerian phone number.")
        return phone

    def clean_instagram(self):
        return clean_handle(self.cleaned_data.get("instagram"))

    def clean_tiktok(self):
        return clean_handle(self.cleaned_data.get("tiktok"))

    def clean_twitter(self):
        return clean_handle(self.cleaned_data.get("twitter"))

    def clean_website(self):
        return clean_website(self.cleaned_data.get("website"))

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        if role in (Vendor.Role.VENDOR, Vendor.Role.BOTH) and not cleaned.get("phone") and "phone" not in self.errors:
            self.add_error("phone", "Vendors need a WhatsApp number so shoppers can reach them.")
        # Everyone needs a social account too: a phone number alone isn't enough for us to check who you are.
        if not any(cleaned.get(f) for f in SOCIAL_FIELDS) and not any(f in self.errors for f in SOCIAL_FIELDS):
            self.add_error("instagram", "Add at least one social account (Instagram, TikTok or X). A phone number alone isn't enough.")
        return cleaned


class VendorSignupForm(ProfileFieldsMixin, UserCreationForm):
    """Creates the User and the linked profile (vendor, organiser or both) in one step."""

    role = forms.ChoiceField(label="I am a", choices=ROLE_CHOICES, initial="vendor", widget=forms.RadioSelect, required=False)
    email = forms.EmailField(required=True)
    name = forms.CharField(label="Business / brand name", max_length=120)
    phone = forms.CharField(label="WhatsApp number", max_length=20, required=False, help_text="e.g. 08012345678. Required for vendors, optional for organisers.")
    instagram = forms.CharField(max_length=200, required=False, help_text="Handle without the @. Add at least one of Instagram, TikTok or X.")
    tiktok = forms.CharField(label="TikTok", max_length=200, required=False, help_text="Handle without the @")
    twitter = forms.CharField(label="Twitter/X", max_length=200, required=False, help_text="Handle without the @")
    website = forms.CharField(max_length=200, required=False, help_text="Optional")

    class Meta:
        model = User
        fields = ("email",)

    field_order = ["role", "name", "email", "phone", "instagram", "tiktok", "twitter", "website"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = user.email  # people log in with their email
        if commit:
            user.save()
            Vendor.objects.create(
                user=user,
                role=self.cleaned_data["role"],
                name=self.cleaned_data["name"],
                phone=self.cleaned_data["phone"],
                instagram=self.cleaned_data["instagram"],
                tiktok=self.cleaned_data["tiktok"],
                twitter=self.cleaned_data["twitter"],
                website=self.cleaned_data["website"],
            )
        return user


class VendorProfileForm(ProfileFieldsMixin, forms.ModelForm):
    role = forms.ChoiceField(label="I am a", choices=ROLE_CHOICES, widget=forms.RadioSelect, required=False)
    instagram = forms.CharField(max_length=200, required=False, help_text="Handle without the @")
    tiktok = forms.CharField(label="TikTok", max_length=200, required=False, help_text="Handle without the @")
    twitter = forms.CharField(label="Twitter/X", max_length=200, required=False, help_text="Handle without the @")
    website = forms.CharField(max_length=200, required=False, help_text="Optional")

    class Meta:
        model = Vendor
        fields = ("role", "name", "bio", "phone", "instagram", "tiktok", "twitter", "website")


class BrandedPasswordResetForm(PasswordResetForm):
    """Sends the reset link through our branded email path.

    Links are built from SITE_URL (never the request's Host header) and each address is
    throttled so the form can't be used to spam someone's inbox.
    """

    def save(self, domain_override=None, request=None, token_generator=default_token_generator, **kwargs):
        from django.core.cache import cache
        from django.urls import reverse
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        from core.notifications import notify_password_reset

        for user in self.get_users(self.cleaned_data["email"]):
            key = f"pwreset:{user.pk}"
            if cache.get(key):
                continue
            cache.set(key, 1, 60)
            path = reverse("password_reset_confirm", kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": token_generator.make_token(user),
            })
            notify_password_reset(user, path)
