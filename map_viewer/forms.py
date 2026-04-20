from django import forms
from .models import MapSource

class MapSourceForm(forms.ModelForm):
    class Meta:
        model = MapSource
        fields = ['name', 'db_file_path', 'is_active']