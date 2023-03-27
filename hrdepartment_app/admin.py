from django.contrib import admin

from customers_app.models import Groups
from hrdepartment_app.models import Medical, Purpose, OfficialMemo, ApprovalOficialMemoProcess, \
    BusinessProcessDirection, MedicalOrganisation, DocumentsJobDescription, DocumentsOrder, PlaceProductionActivity, \
    ReportCard

# Register your models here.

admin.site.register(DocumentsJobDescription)
admin.site.register(DocumentsOrder)
admin.site.register(PlaceProductionActivity)
admin.site.register(MedicalOrganisation)
admin.site.register(Medical)
admin.site.register(Purpose)
admin.site.register(OfficialMemo)
admin.site.register(ApprovalOficialMemoProcess)
admin.site.register(BusinessProcessDirection)
admin.site.register(Groups)
admin.site.register(ReportCard)
