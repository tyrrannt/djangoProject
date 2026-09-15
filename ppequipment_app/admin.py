from typing import Optional, Tuple
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django import forms
from django.db import models
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import (
    Equipment,
    Location,
    Verification,
    VerificationDate,
    DestLit,
    LocationRef,
    AircraftType,
    ContractorStatus,
)
from .utils import replace_reference
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from unfold.contrib.filters.admin import RangeDateFilter


# ─── Inline для Equipment ─────────────────────────────────────────────────────

class LocationInline(TabularInline):
    model = Location
    extra = 1
    autocomplete_fields = ["location_ref"]


class VerificationInline(TabularInline):
    model = Verification
    extra = 1
    readonly_fields = ["inventory_number"]
    autocomplete_fields = ["location_ref", "contractor_status"]


# ─── Форма для замены справочника ─────────────────────────────────────────────

class ReplaceForm(forms.Form):
    """Форма для выбора элемента, на который заменить"""
    new_item = forms.ModelChoiceField(
        queryset=None,
        label="Заменить на",
        help_text="Выберите элемент, на который нужно заменить выбранный",
        widget=forms.Select(attrs={"class": "vTextField"}),
    )

    def __init__(self, *args, **kwargs):
        model_class = kwargs.pop("model_class", None)
        super().__init__(*args, **kwargs)
        if model_class:
            self.fields["new_item"].queryset = model_class.objects.all()


# ─── Миксин для админки справочников с функцией замены ────────────────────────

class ReplaceReferenceAdminMixin:
    """Миксин добавляет действие 'Заменить на другой элемент' для справочников"""

    def get_urls(self):
        """Добавляем URL для view замены"""
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom_urls = [
            path(
                "<int:pk>/replace/",
                self.admin_site.admin_view(self.replace_view),
                name=f"{info[0]}_{info[1]}_replace",
            ),
        ]
        return custom_urls + urls

    def replace_view(self, request, pk):
        """View для замены одного элемента на другой"""
        obj = self.get_object(request, pk)
        if obj is None:
            self.message_user(request, "Объект не найден", messages.ERROR)
            return redirect(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist")

        if request.method == "POST":
            form = ReplaceForm(request.POST, model_class=self.model)
            if form.is_valid():
                new_item = form.cleaned_data["new_item"]
                if new_item.pk == obj.pk:
                    self.message_user(request, "Нельзя заменить элемент на самого себя", messages.ERROR)
                else:
                    try:
                        stats = replace_reference(self.model, obj, new_item)
                        replaced_count = sum(stats.get("replaced", {}).values())
                        self.message_user(
                            request,
                            f'Элемент "{obj}" заменён на "{new_item}". Обновлено записей: {replaced_count}',
                            messages.SUCCESS,
                        )
                    except Exception as e:
                        self.message_user(request, f"Ошибка: {e}", messages.ERROR)
                    return redirect(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist")
        else:
            form = ReplaceForm(model_class=self.model)

        # Получаем связанные модели для отображения
        related_info = self._get_related_info()

        context = {
            **self.admin_site.each_context(request),
            "title": f'Заменить "{obj}" на другой элемент',
            "object": obj,
            "form": form,
            "related_info": related_info,
            "opts": self.model._meta,
        }
        return render(request, "admin/ppequipment_app/replace_reference.html", context)

    def _get_related_info(self):
        """Получаем информацию о связанных моделях"""
        related = []
        for rel in self.model._meta.related_objects:
            if isinstance(rel.field, models.ForeignKey):
                count = rel.related_model.objects.filter(**{rel.field.name + "__isnull": False}).count()
                related.append({
                    "model": rel.related_model._meta.verbose_name,
                    "field": rel.field.name,
                    "count": count,
                })
        return related

    def replace_link(self, obj):
        """Ссылка на страницу замены в списке - для django-unfold"""
        url = reverse(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_replace", args=[obj.pk])
        return format_html(
            '<a href="{}" class="flex items-center text-xs cursor-pointer transition hover:text-primary">'
            '<span class="material-symbols-outlined mr-1 text-sm">swap_horiz</span>Заменить</a>',
            url,
        )

    replace_link.short_description = _("Действие")

    def get_list_display(self, request):
        """Добавляем колонку с действием замены"""
        base_display = super().get_list_display(request)
        return list(base_display) + ["replace_link"]


# ─── Справочники ──────────────────────────────────────────────────────────────

@admin.register(DestLit)
class DestLitAdmin(ReplaceReferenceAdminMixin, ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(LocationRef)
class LocationRefAdmin(ReplaceReferenceAdminMixin, ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(AircraftType)
class AircraftTypeAdmin(ReplaceReferenceAdminMixin, ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(ContractorStatus)
class ContractorStatusAdmin(ReplaceReferenceAdminMixin, ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
    compressed_fields = True
    warn_unsaved_form = True


# ─── Основные модели ──────────────────────────────────────────────────────────

@admin.register(Equipment)
class EquipmentAdmin(ModelAdmin):
    list_display = ["display_equipment_header", "aircraft_type", "priority", "dest_lit"]
    list_filter = (
        "aircraft_type",
        "dest_lit",
    )
    search_fields = ["name", "number"]
    autocomplete_fields = ["aircraft_type", "dest_lit"]
    inlines = [LocationInline, VerificationInline]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Оборудование", header=True)
    def display_equipment_header(self, obj: Equipment) -> Tuple[str, str]:
        """Возвращает номер и наименование оборудования."""
        return f"№ {obj.number}", obj.name


@admin.register(Location)
class LocationAdmin(ModelAdmin):
    list_display = ["equipment", "location_ref"]
    list_filter = ("location_ref",)
    search_fields = ["location_ref__name", "equipment__name", "equipment__number"]
    autocomplete_fields = ["equipment", "location_ref"]
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(Verification)
class VerificationAdmin(ModelAdmin):
    list_display = [
        "display_verification_header",
        "location_ref",
        "contractor_status",
        "last_verification_date",
        "display_destroyed",
    ]
    list_filter = (
        "is_destroyed",
        "contractor_status",
        ("last_verification_date", RangeDateFilter),
    )
    search_fields = ["inventory_number", "equipment__name", "location_ref__name", "slug"]
    autocomplete_fields = ["equipment", "location_ref", "contractor_status"]
    date_hierarchy = "last_verification_date"
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Поверка", header=True)
    def display_verification_header(self, obj: Verification) -> Tuple[str, str]:
        """Возвращает инвентарный номер и оборудование."""
        equip_name = obj.equipment.name if obj.equipment else "Оборудование не указано"
        return f"Инв. № {obj.inventory_number}", equip_name

    @display(description="Списано", boolean=True)
    def display_destroyed(self, obj: Verification) -> bool:
        """Флаг списания оборудования."""
        return obj.is_destroyed


@admin.register(VerificationDate)
class VerificationDateAdmin(ModelAdmin):
    list_display = ["verification_date"]
    list_filter = (("verification_date", RangeDateFilter),)
    date_hierarchy = "verification_date"
    compressed_fields = True
    warn_unsaved_form = True
