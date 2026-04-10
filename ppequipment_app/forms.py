from django import forms
from .models import Equipment, Location, Verification, VerificationDate, DestLit, LocationRef, AircraftType, ContractorStatus


class EquipmentForm(forms.ModelForm):
    """Форма для оборудования"""

    class Meta:
        model = Equipment
        fields = ["name", "aircraft_type", "edition", "issue", "approved_by",
                  "approval_date", "priority", "dest_lit"]
        widgets = {
            "approval_date": forms.DateInput(attrs={"type": "date"}),
            "name": forms.Textarea(attrs={"rows": 2}),
            "edition": forms.Textarea(attrs={"rows": 2}),
            "approved_by": forms.Textarea(attrs={"rows": 2}),
        }


class LocationForm(forms.ModelForm):
    """Форма для местоположения"""

    class Meta:
        model = Location
        fields = ["equipment", "location_ref"]


class VerificationForm(forms.ModelForm):
    """Форма для сверки"""

    class Meta:
        model = Verification
        fields = ["location_ref", "equipment", "contractor_status",
                  "last_verification_date", "notes", "vs_number", "end_date", "is_destroyed"]
        widgets = {
            "last_verification_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class VerificationDateForm(forms.ModelForm):
    """Форма для даты сверки"""

    class Meta:
        model = VerificationDate
        fields = ["verification_date"]
        widgets = {
            "verification_date": forms.DateInput(attrs={"type": "date"}),
        }


# Формы для справочников

class DestLitForm(forms.ModelForm):
    class Meta:
        model = DestLit
        fields = ["name"]


class LocationRefForm(forms.ModelForm):
    class Meta:
        model = LocationRef
        fields = ["name"]


class AircraftTypeForm(forms.ModelForm):
    class Meta:
        model = AircraftType
        fields = ["name"]


class ContractorStatusForm(forms.ModelForm):
    class Meta:
        model = ContractorStatus
        fields = ["name"]
