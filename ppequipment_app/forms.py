from django import forms

from administration_app.utils import make_custom_field
from .models import Equipment, Location, Verification, VerificationDate, DestLit, LocationRef, AircraftType, ContractorStatus


class EquipmentForm(forms.ModelForm):
    """Форма для оборудования"""

    class Meta:
        model = Equipment
        fields = ["name", "aircraft_type", "edition", "issue", "approved_by",
                  "approval_date", "priority", "dest_lit"]
        widgets = {
            # "approval_date": forms.DateInput(attrs={"type": "date"}),
            "name": forms.Textarea(attrs={"rows": 2}),
            "edition": forms.Textarea(attrs={"rows": 2}),
            "approved_by": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super(EquipmentForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class LocationForm(forms.ModelForm):
    """Форма для местоположения"""

    class Meta:
        model = Location
        fields = ["equipment", "location_ref"]

    def __init__(self, *args, **kwargs):
        super(LocationForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class VerificationForm(forms.ModelForm):
    """Форма для сверки"""

    class Meta:
        model = Verification
        fields = ["location_ref", "equipment", "contractor_status", 'inventory_number',
                  "last_verification_date", "notes", "vs_number", "end_date", "is_destroyed"]
        widgets = {
            # "last_verification_date": forms.DateInput(attrs={"type": "date"}),
            # "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super(VerificationForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class VerificationDateForm(forms.ModelForm):
    """Форма для даты сверки"""

    class Meta:
        model = VerificationDate
        fields = ["verification_date"]
        # widgets = {
        #     "verification_date": forms.DateInput(attrs={"type": "date"}),
        # }

    def __init__(self, *args, **kwargs):
        super(VerificationDateForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


# Формы для справочников

class DestLitForm(forms.ModelForm):
    class Meta:
        model = DestLit
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super(DestLitForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class LocationRefForm(forms.ModelForm):
    class Meta:
        model = LocationRef
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super(LocationRefForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class AircraftTypeForm(forms.ModelForm):
    class Meta:
        model = AircraftType
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super(AircraftTypeForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class ContractorStatusForm(forms.ModelForm):
    class Meta:
        model = ContractorStatus
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super(ContractorStatusForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class VerificationLabelForm(forms.Form):
    """Форма для выбора условий печати свёрочных этикеток"""
    verification_date = forms.ModelChoiceField(
        queryset=VerificationDate.objects.all().order_by("-verification_date"),
        widget=forms.Select,
        label="Дата сверки",
        required=False,
        empty_label="Все даты",
    )
    location_ref = forms.ModelMultipleChoiceField(
        queryset=LocationRef.objects.all().order_by("name"),
        widget=forms.SelectMultiple(attrs={"class": "form-control", "size": 8}),
        label="Местоположение",
        required=False,
    )
    contractor_status = forms.ModelMultipleChoiceField(
        queryset=ContractorStatus.objects.all().order_by("name"),
        widget=forms.SelectMultiple(attrs={"class": "form-control", "size": 8}),
        label="Статус контр-раб",
        required=False,
    )
    dest_lit = forms.ModelMultipleChoiceField(
        queryset=DestLit.objects.all().order_by("name"),
        widget=forms.SelectMultiple(attrs={"class": "form-control", "size": 8}),
        label="Назн-лит",
        required=False,
    )
    is_destroyed = forms.ChoiceField(
        choices=[
            ("", "Все"),
            ("0", "Не уничтожен"),
            ("1", "Уничтожен"),
        ],
        widget=forms.Select,
        label="Уничтожен",
        required=False,
    )
    aircraft_type = forms.ModelMultipleChoiceField(
        queryset=AircraftType.objects.all().order_by("name"),
        widget=forms.SelectMultiple(attrs={"class": "form-control", "size": 8}),
        label="Тип ВС",
        required=False,
    )
    inventory_numbers = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Введите инвентарные номера через запятую или каждый с новой строки"}),
        label="Инвентарные номера",
        required=False,
        help_text="Если заполнено, фильтрует по указанным номерам",
    )

    def __init__(self, *args, **kwargs):
        super(VerificationLabelForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])
