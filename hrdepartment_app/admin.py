from django.contrib import admin

from customers_app.models import Groups
from hrdepartment_app.models import Medical, Purpose, OfficialMemo, ApprovalOficialMemoProcess, \
    BusinessProcessDirection, MedicalOrganisation, DocumentsJobDescription, DocumentsOrder, PlaceProductionActivity, \
    ReportCard, ReasonForCancellation, OrderDescription, PreHolidayDay, WeekendDay, ProductionCalendar, \
    TypesUserworktime, Instructions, Provisions

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
admin.site.register(ReasonForCancellation)
admin.site.register(OrderDescription)
admin.site.register(PreHolidayDay)
admin.site.register(WeekendDay)
admin.site.register(ProductionCalendar)
admin.site.register(TypesUserworktime)
admin.site.register(Instructions)
admin.site.register(Provisions)
