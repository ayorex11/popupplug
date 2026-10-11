import re

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Vendor

User = get_user_model()

NG_PHONE_RE = re.compile(r"^(?:\+?234|0)[789][01]\d{8}$")


def clean_handle(value):
    return (value or "").strip().lstrip("@")


class EmailAuthenticationForm(AuthenticationForm):
    """Login with email (stored as the username). Admin accounts with a plain username still work."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"

    def clean_username(self):
        value = self.cleaned_data["username"].strip()
        return value.lower() if "@" in value else value


class VendorSignupForm(UserCreationForm):
    """Creates the User and the linked Vendor in one step."""

    email = forms.EmailField(required=True)
    name = forms.CharField(label="Business name", max_length=120)
    phone = forms.CharField(max_length=20, help_text="e.g. 08012345678")
    instagram = forms.CharField(max_length=60, required=False, help_text="Handle without the @")
    twitter = forms.CharField(label="Twitter/X", max_length=60, required=False, help_text="Handle without the @")

    class Meta:
        model = User
        fields = ("email",)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_phone(self):
        phone = re.sub(r"[\s\-]", "", self.cleaned_data["phone"])
        if not NG_PHONE_RE.match(phone):
            raise forms.ValidationError("Enter a valid Nigerian phone number.")
        return phone

    def clean_instagram(self):
        return clean_handle(self.cleaned_data.get("instagram"))

    def clean_twitter(self):
        return clean_handle(self.cleaned_data.get("twitter"))

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = user.email  # people log in with their email
        if commit:
            user.save()
            Vendor.objects.create(
                user=user,
                name=self.cleaned_data["name"],
                phone=self.cleaned_data["phone"],
                instagram=self.cleaned_data["instagram"],
                twitter=self.cleaned_data["twitter"],
            )
        return user


class VendorProfileForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = ("name", "bio", "phone", "instagram", "twitter")

    def clean_phone(self):
        phone = re.sub(r"[\s\-]", "", self.cleaned_data["phone"])
        if not NG_PHONE_RE.match(phone):
            raise forms.ValidationError("Enter a valid Nigerian phone number.")
        return phone

    def clean_instagram(self):
        return clean_handle(self.cleaned_data.get("instagram"))

    def clean_twitter(self):
        return clean_handle(self.cleaned_data.get("twitter"))
