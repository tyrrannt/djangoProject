from django.contrib import admin
from contracts_app.models import TypeProperty, TypeContract, Estate, Contract, Posts, TypeDocuments, CompanyProperty

# Register your models here.
admin.site.register(TypeContract)
admin.site.register(TypeProperty)
admin.site.register(TypeDocuments)
admin.site.register(Estate)
admin.site.register(Contract)
admin.site.register(Posts)
# admin.site.register(Hotel)
admin.site.register(CompanyProperty)

