from django.contrib import admin
from contracts_app.models import TypeProperty, TypeContract, Estate, Contract

# Register your models here.
admin.site.register(TypeContract)
admin.site.register(TypeProperty)
admin.site.register(Estate)
admin.site.register(Contract)
