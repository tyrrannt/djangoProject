from django.contrib import admin

from administration_app.utils import format_name_initials
from logistics_app.models import WayBill, Package

# Register your models here.
admin.site.register(WayBill)


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ("date_of_dispatch", "number_of_dispatch", "place_of_dispatch", "get_executor", "type_of_dispatch")
    list_filter = (
        "type_of_dispatch",
    )

    def get_executor(self, obj: Package):
        return format_name_initials(obj.executor.title) if obj.executor else ''

    search_fields = ["number_of_dispatch", ]
