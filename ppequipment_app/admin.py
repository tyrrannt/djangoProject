from django.contrib import admin
from .models import (
    Equipment, Location, Verification, VerificationDate,
    DestLit, LocationRef, AircraftType, ContractorStatus,
)


# ─── Inline для Equipment ─────────────────────────────────────────────────────

class LocationInline(admin.TabularInline):
    model = Location
    extra = 1


class VerificationInline(admin.TabularInline):
    model = Verification
    extra = 1
    readonly_fields = ["inventory_number"]


# ─── Справочники ──────────────────────────────────────────────────────────────

@admin.register(DestLit)
class DestLitAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(LocationRef)
class LocationRefAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(AircraftType)
class AircraftTypeAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(ContractorStatus)
class ContractorStatusAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


# ─── Основные модели ──────────────────────────────────────────────────────────

@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ["number", "name", "aircraft_type", "priority", "dest_lit"]
    list_filter = ["aircraft_type", "dest_lit"]
    search_fields = ["name", "number"]
    inlines = [LocationInline, VerificationInline]


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ["equipment", "location_ref"]
    list_filter = ["location_ref"]
    search_fields = ["location_ref__name", "equipment__name"]


@admin.register(Verification)
class VerificationAdmin(admin.ModelAdmin):
    list_display = ["inventory_number", "equipment", "location_ref",
                    "contractor_status", "last_verification_date", "is_destroyed"]
    list_filter = ["is_destroyed", "contractor_status", "last_verification_date"]
    search_fields = ["inventory_number", "equipment__name", "location_ref__name"]
    date_hierarchy = "last_verification_date"


@admin.register(VerificationDate)
class VerificationDateAdmin(admin.ModelAdmin):
    list_display = ["verification_date"]
    date_hierarchy = "verification_date"
