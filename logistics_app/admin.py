from django.contrib import admin

from administration_app.utils import format_name_initials
from logistics_app.models import WayBill, Package, PackageImage, Grade, Nomenclature, NomenclatureUnit, \
    NomenclatureGroup


# Register your models here.
@admin.register(WayBill)
class WayBillAdmin(admin.ModelAdmin):
    list_display = ("document_date", "place_of_departure", "place_division",
                    "sender", "state", "responsible", "date_of_creation", "executor", "urgency")

@admin.register(PackageImage)
class PackageImageAdmin(admin.ModelAdmin):
    list_display = ("date_of_creation", "package", "caption")

@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ("date_of_dispatch", "number_of_dispatch", "place_of_dispatch", "get_executor", "type_of_dispatch")
    list_filter = (
        "type_of_dispatch",
    )

    def get_executor(self, obj: Package):
        return format_name_initials(obj.executor.title) if obj.executor else ''

    search_fields = ["number_of_dispatch", ]

@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

@admin.register(NomenclatureUnit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ('name', 'short_name')
    search_fields = ('name', 'short_name')

@admin.register(NomenclatureGroup)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent')
    search_fields = ('name',)
    list_filter = ('parent',)

@admin.register(Nomenclature)
class NomenclatureAdmin(admin.ModelAdmin):
    list_display = ('name', 'group', 'price', 'quantity', 'unit', 'serial_number', 'year_of_manufacture', 'weight', 'dimensions', 'grade', 'location', 'estate')
    search_fields = ('name', 'description', 'serial_number')
    list_filter = ('group', 'unit', 'grade', 'location', 'estate')