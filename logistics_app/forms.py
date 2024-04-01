from django import forms

from administration_app.utils import make_custom_field
from logistics_app.models import WayBill


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


class WayBillUpdateForm(forms.ModelForm):
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