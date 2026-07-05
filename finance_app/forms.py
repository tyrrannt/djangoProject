from django import forms
from finance_app.models import CreditTranche, CentralBankKeyRate, CreditAgreement, CreditPaymentFact
from administration_app.utils import make_custom_field

class CreditTrancheForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])

    class Meta:
        model = CreditTranche
        fields = ['date', 'amount']


class CentralBankKeyRateForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])

    class Meta:
        model = CentralBankKeyRate
        fields = ['date_from', 'rate']


class CreditAgreementForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])

    class Meta:
        model = CreditAgreement
        fields = ['bank', 'contract_number', 'contract_date', 'amount', 'interest_rate', 'has_unused_limit_commission', 'unused_limit_commission_rate', 'term_months', 'tranche_repayment_days', 'employee']


class CreditPaymentFactForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])

    class Meta:
        model = CreditPaymentFact
        fields = ['payment_date', 'payment_type', 'amount', 'payment_doc_number']
