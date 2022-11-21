from django.contrib import admin

from hrdepartment_app.models import Medical, Purpose, OfficialMemo

# Register your models here.
admin.site.register(Medical)
admin.site.register(Purpose)
admin.site.register(OfficialMemo)

