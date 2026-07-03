from django import forms
from finance_app.models import CreditTranche, CentralBankKeyRate, CreditAgreement, CreditPaymentFact

class CreditTrancheForm(forms.ModelForm):
    class Meta:
        model = CreditTranche
        fields = ['date', 'amount']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

class CentralBankKeyRateForm(forms.ModelForm):
    class Meta:
        model = CentralBankKeyRate
        fields = ['date_from', 'rate']
        widgets = {
            'date_from': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

from finance_app.models import CreditAgreement

class CreditAgreementForm(forms.ModelForm):
    class Meta:
        model = CreditAgreement
        fields = ['bank', 'contract_number', 'contract_date', 'amount', 'interest_rate', 'term_months', 'tranche_repayment_days', 'employee']
        widgets = {
            'contract_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'bank': forms.Select(attrs={'class': 'form-control'}),
            'contract_number': forms.TextInput(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'interest_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'term_months': forms.NumberInput(attrs={'class': 'form-control'}),
            'tranche_repayment_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'employee': forms.Select(attrs={'class': 'form-control'}),
        }

class CreditPaymentFactForm(forms.ModelForm):
    class Meta:
        model = CreditPaymentFact
        fields = ['payment_date', 'payment_type', 'amount', 'payment_doc_number']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'payment_type': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'payment_doc_number': forms.TextInput(attrs={'class': 'form-control'}),
        }
