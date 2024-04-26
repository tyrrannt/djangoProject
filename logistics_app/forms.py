from django import forms

from administration_app.utils import make_custom_field
from customers_app.models import Division
from logistics_app.models import WayBill, Package
import sched
from django.forms import inlineformset_factory, BaseInlineFormSet


class WayBillCreateForm(forms.ModelForm):
    class Meta:
        model = WayBill
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        # self.user = kwargs.pop("user")
        # Выбрать из списка бизнес-процессов имеющих право согласования
        super(WayBillCreateForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])
        # self.fields["content"].widget.attrs.update(
        #     {"class": "ui-widget"}
        # )

class WayBillForm(forms.ModelForm):
    class Meta:
        model = WayBill
        fields = ['document_date', 'place_of_departure', 'comment', 'place_division', 'sender', 'state', 'responsible', 'executor', 'urgency']

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        # self.user = kwargs.pop("user")
        # Выбрать из списка бизнес-процессов имеющих право согласования
        super(WayBillForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class WayBillUpdateForm(forms.ModelForm):
    place_division = forms.ModelChoiceField(
        queryset=Division.objects.filter(active=True).exclude(name__icontains='Основное подразделение'),
        label="Подразделение")
    class Meta:
        model = WayBill
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """

        # self.user = kwargs.pop("user")
        # Выбрать из списка бизнес-процессов имеющих право согласования
        super(WayBillUpdateForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class PackageCreateForm(forms.ModelForm):
    class Meta:
        model = Package
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """

        # self.user = kwargs.pop("user")
        # Выбрать из списка бизнес-процессов имеющих право согласования
        super(PackageCreateForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])

# PackageInlineFormSet = inlineformset_factory(Package, WayBill, form=PackageCreateForm, extra=1)
WayBillInlineFormSet = inlineformset_factory(Package, WayBill, form=WayBillForm, fk_name='package_number',
                                             extra=1, can_delete=True, can_delete_extra=True,
                                             formset=BaseInlineFormSet,)
