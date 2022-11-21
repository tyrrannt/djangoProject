from django.contrib import admin

from hrdepartment_app.models import Medical, Purpose, OfficialMemo, ApprovalOficialMemoProcess

# Register your models here.
admin.site.register(Medical)
admin.site.register(Purpose)
admin.site.register(OfficialMemo)
admin.site.register(ApprovalOficialMemoProcess)

