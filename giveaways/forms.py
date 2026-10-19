from django import forms

from .models import normalize_phone


class EntryForm(forms.Form):
    name = forms.CharField(max_length=80, strip=True)
    phone = forms.CharField(max_length=20, strip=True)
    attend = forms.BooleanField(required=True, error_messages={"required": "Please confirm you can attend."})
    rules = forms.BooleanField(required=True, error_messages={"required": "Please agree to the rules."})
    website = forms.CharField(required=False)  # honeypot: real people never see or fill this

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if len(name) < 2:
            raise forms.ValidationError("Please enter your name.")
        return name

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        if not phone:
            raise forms.ValidationError("Enter a Nigerian mobile number, e.g. 0801 234 5678.")
        return phone
