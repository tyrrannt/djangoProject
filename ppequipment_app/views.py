import os
import subprocess
import csv
import io
import json
from datetime import datetime
from io import BytesIO

import qrcode
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import CircleModuleDrawer
from PIL import Image, ImageDraw, ImageFont

from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse, JsonResponse

from administration_app.utils import format_name_initials
from .models import (
    Equipment, Location, Verification, VerificationDate,
    DestLit, LocationRef, AircraftType, ContractorStatus,
)
from .forms import (
    EquipmentForm, LocationForm, VerificationForm, VerificationDateForm,
    DestLitForm, LocationRefForm, AircraftTypeForm, ContractorStatusForm,
    VerificationLabelForm, BulkLocationMoveForm, BulkVerificationUpdateForm,
)

MDB_FILE = os.path.join(os.path.dirname(__file__), "inventory.mdb")


def _parse_date(value):
    """Конвертирует даты из MDB формата в YYYY-MM-DD"""
    if not value or not value.strip():
        return None
    value = value.strip()
    for fmt in ("%m/%d/%y %H:%M:%S", "%m/%d/%y", "%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _run_mdb_table(table_name: str) -> list[dict]:
    """Извлекает данные из таблицы MDB через mdb-export"""
    result = subprocess.run(
        ["mdb-export", MDB_FILE, table_name],
        capture_output=True, text=True, check=True,
    )
    reader = csv.DictReader(io.StringIO(result.stdout))
    return list(reader)


# ─── Equipment ───────────────────────────────────────────────────────────────
@login_required
@permission_required('ppequipment_app.view_equipment', raise_exception=True)
def equipment_list(request):
    qs = Equipment.objects.select_related("aircraft_type", "dest_lit").exclude(locations__location_ref__name='АРХИВ')
    search = request.GET.get("q", "")
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(number__icontains=search))
    return render(request, "ppequipment_app/equipment_list.html", {
        "object_list": qs, "search": search, "title": "Производственно-техническая документация",
    })


@login_required
@permission_required('ppequipment_app.view_equipment', raise_exception=True)
def equipment_detail(request, pk):
    obj = get_object_or_404(Equipment.objects.select_related("aircraft_type", "dest_lit"), pk=pk)
    return render(request, "ppequipment_app/equipment_detail.html",
                  {"object": obj, "title": f"Производственно-техническая документация #{obj.number}"})


@login_required
@permission_required('ppequipment_app.add_equipment', raise_exception=True)
def equipment_create(request):
    if request.method == "POST":
        form = EquipmentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "ПТД создано")
            return redirect("ppequipment_app:equipment_list")
    else:
        form = EquipmentForm()
    return render(request, "ppequipment_app/equipment_form.html", {"form": form, "title": "Создать ПТД"})


@login_required
@permission_required('ppequipment_app.change_equipment', raise_exception=True)
def equipment_update(request, pk):
    obj = get_object_or_404(Equipment, pk=pk)
    if request.method == "POST":
        form = EquipmentForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "ПТД обновлено")
            return redirect("ppequipment_app:equipment_list")
    else:
        form = EquipmentForm(instance=obj)
    return render(request, "ppequipment_app/equipment_form.html", {"form": form, "title": "Редактировать ПТД"})


@login_required
@permission_required('ppequipment_app.delete_equipment', raise_exception=True)
def equipment_delete(request, pk):
    obj = get_object_or_404(Equipment, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "ПТД удалено")
        return redirect("ppequipment_app:equipment_list")
    return render(request, "ppequipment_app/confirm_delete.html", {"object": obj})


# ─── Verification ────────────────────────────────────────────────────────────
@login_required
@permission_required('ppequipment_app.view_verification', raise_exception=True)
def verification_list(request):
    archived_equipment = Location.objects.filter(
        location_ref__name='АРХИВ'
    ).values_list('equipment_id', flat=True)

    qs = Verification.objects.select_related("equipment", "location_ref", "contractor_status").exclude(
        equipment__in=archived_equipment
    ).all()
    search = request.GET.get("q", "")
    if search:
        qs = qs.filter(
            Q(inventory_number__icontains=search) |
            Q(equipment__name__icontains=search) |
            Q(location_ref__name__icontains=search)
        )

    # Сохраняем параметры фильтрации в сессии
    request.session['verification_filters'] = request.GET.urlencode()

    return render(request, "ppequipment_app/verification_list.html", {
        "object_list": qs, "search": search, "title": "Сверки",
    })


@login_required
@permission_required('ppequipment_app.view_verification', raise_exception=True)
def verification_detail(request, slug):
    obj = get_object_or_404(Verification.objects.select_related("equipment", "location_ref", "contractor_status"),
                            slug=slug)
    return render(request, "ppequipment_app/verification_detail.html",
                  {"object": obj, "title": f"Сверка {obj.inventory_number}"})


@login_required
@permission_required('ppequipment_app.add_verification', raise_exception=True)
def verification_create(request):
    if request.method == "POST":
        form = VerificationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Сверка создана")
            return redirect("ppequipment_app:verification_list")
    else:
        form = VerificationForm()
    return render(request, "ppequipment_app/verification_form.html", {"form": form, "title": "Создать сверку"})


@login_required
@permission_required('ppequipment_app.change_verification', raise_exception=True)
def verification_update(request, slug):
    obj = get_object_or_404(Verification, slug=slug)
    if request.method == "POST":
        form = VerificationForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Сверка обновлена")
            # Получаем сохраненные фильтры из сессии
            filters = request.session.get('verification_filters', '')

            # Формируем URL для возврата
            if filters:
                return redirect(f"{reverse('ppequipment_app:verification_list')}?{filters}")
            else:
                return redirect("ppequipment_app:verification_list")
    else:
        form = VerificationForm(instance=obj)
    return render(request, "ppequipment_app/verification_form.html", {
        "form": form,
        "title": "Редактировать сверку",
        "return_url": request.META.get('HTTP_REFERER', reverse('ppequipment_app:verification_list'))
    })


@login_required
@permission_required('ppequipment_app.delete_verification', raise_exception=True)
def verification_delete(request, slug):
    obj = get_object_or_404(Verification, slug=slug)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Сверка удалена")
        return redirect("ppequipment_app:verification_list")
    return render(request, "ppequipment_app/confirm_delete.html", {"object": obj})


# ─── Location ────────────────────────────────────────────────────────────────
@login_required
@permission_required('ppequipment_app.view_location', raise_exception=True)
def location_list(request):
    # Исключаем все оборудования, у которых есть хотя бы одно местоположение "АРХИВ"
    archived_equipment = Location.objects.filter(
        location_ref__name='АРХИВ'
    ).values_list('equipment_id', flat=True)

    qs = Location.objects.select_related("equipment", "location_ref").exclude(
        equipment_id__in=archived_equipment
    ).all()
    return render(request, "ppequipment_app/location_list.html",
                  {"object_list": qs, "title": "Местоположения ПТД"})


@login_required
@permission_required('ppequipment_app.add_location', raise_exception=True)
def location_create(request):
    if request.method == "POST":
        form = LocationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Местоположение создано")
            return redirect("ppequipment_app:location_list")
    else:
        form = LocationForm()
    return render(request, "ppequipment_app/location_form.html", {"form": form, "title": "Создать местоположение"})


@login_required
@permission_required('ppequipment_app.change_location', raise_exception=True)
def bulk_location_move(request):
    """Массовое перемещение оборудования"""
    if request.method == "POST":
        form = BulkLocationMoveForm(request.POST)
        if form.is_valid():
            equipment_ids = form.cleaned_data['equipment_ids']
            new_location = form.cleaned_data['new_location']
            location_date = form.cleaned_data.get('location_date')

            moved_count = 0
            errors = []

            with transaction.atomic():
                for equipment in equipment_ids:
                    try:
                        # Проверяем, есть ли уже такая связь
                        location, created = Location.objects.update_or_create(
                            equipment=equipment,
                            location_ref=new_location,
                            defaults={'location_date': location_date or timezone.now().date()}
                        )

                        if created:
                            moved_count += 1

                    except Exception as e:
                        errors.append(f"{equipment.number}: {str(e)}")

            if errors:
                messages.warning(request, f"Перемещено {moved_count} позиций. Ошибки: {', '.join(errors[:5])}")
            else:
                messages.success(request, f"Успешно перемещено {moved_count} позиций в '{new_location.name}'")

            return redirect("ppequipment_app:location_list")
        else:
            # Если форма не валидна, выводим ошибки
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = BulkLocationMoveForm()

    return render(request, "ppequipment_app/bulk_location_move.html", {
        "form": form,
        "title": "Массовое перемещение ПТД"
    })


@login_required
@permission_required('ppequipment_app.change_verification', raise_exception=True)
def bulk_verification_update(request):
    """Массовое обновление даты сверки"""
    if request.method == "POST":
        form = BulkVerificationUpdateForm(request.POST)
        if form.is_valid():
            new_v_date_obj = form.cleaned_data['new_verification_date']

            # Собираем фильтры
            qs = Verification.objects.all()

            location_refs = form.cleaned_data.get('location_ref')
            if location_refs:
                qs = qs.filter(location_ref__in=location_refs)

            contractor_statuses = form.cleaned_data.get('contractor_status')
            if contractor_statuses:
                qs = qs.filter(contractor_status__in=contractor_statuses)

            current_v_date = form.cleaned_data.get('current_verification_date')
            if current_v_date:
                qs = qs.filter(verification_date=current_v_date)

            # Обновляем
            count = qs.update(
                verification_date=new_v_date_obj,
                last_verification_date=new_v_date_obj.verification_date
            )

            messages.success(request, f"Успешно обновлено {count} записей сверки.")
            return redirect("ppequipment_app:verification_list")
    else:
        form = BulkVerificationUpdateForm()

    return render(request, "ppequipment_app/bulk_verification_update.html", {
        "form": form,
        "title": "Массовое обновление даты сверки"
    })


@login_required
@permission_required('ppequipment_app.view_equipment', raise_exception=True)
def search_equipment_ajax(request):
    """AJAX поиск оборудования для массового перемещения"""
    search = request.GET.get('q', '')
    page = int(request.GET.get('page', 1))
    page_size = 20

    equipment_list = Equipment.objects.select_related('dest_lit', 'aircraft_type')

    # Исключаем оборудование в архиве
    archived_equipment_ids = Location.objects.filter(
        location_ref__name='АРХИВ'
    ).values_list('equipment_id', flat=True)

    equipment_list = equipment_list.exclude(id__in=archived_equipment_ids)

    if search:
        equipment_list = equipment_list.filter(
            Q(number__icontains=search) |
            Q(name__icontains=search)
        )

    total = equipment_list.count()
    start = (page - 1) * page_size
    equipment_list = equipment_list[start:start + page_size]

    data = {
        'results': [
            {
                'id': eq.id,
                'number': eq.number,
                'name': eq.name,
                'dest_lit': str(eq.dest_lit) if eq.dest_lit else '',
                'aircraft_type': str(eq.aircraft_type) if eq.aircraft_type else ''
            }
            for eq in equipment_list
        ],
        'total': total,
        'page': page,
        'has_next': start + page_size < total
    }

    return JsonResponse(data)


@login_required
@permission_required('ppequipment_app.change_location', raise_exception=True)
def location_update(request, pk):
    obj = get_object_or_404(Location, pk=pk)
    if request.method == "POST":
        form = LocationForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Местоположение обновлено")
            return redirect("ppequipment_app:location_list")
    else:
        form = LocationForm(instance=obj)
    return render(request, "ppequipment_app/location_form.html",
                  {"form": form, "title": "Редактировать местоположение"})


@login_required
@permission_required('ppequipment_app.delete_location', raise_exception=True)
def location_delete(request, pk):
    obj = get_object_or_404(Location, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Местоположение удалено")
        return redirect("ppequipment_app:location_list")
    return render(request, "ppequipment_app/confirm_delete.html", {"object": obj})


# ─── VerificationDate ────────────────────────────────────────────────────────
@login_required
@permission_required('ppequipment_app.view_verificationdate', raise_exception=True)
def verification_date_list(request):
    qs = VerificationDate.objects.all().order_by("-verification_date")
    return render(request, "ppequipment_app/verificationdate_list.html", {"object_list": qs, "title": "Даты сверок"})


@login_required
@permission_required('ppequipment_app.add_verificationdate', raise_exception=True)
def verification_date_create(request):
    if request.method == "POST":
        form = VerificationDateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Дата сверки создана")
            return redirect("ppequipment_app:verification_date_list")
    else:
        form = VerificationDateForm()
    return render(request, "ppequipment_app/verificationdate_form.html", {"form": form, "title": "Создать дату сверки"})


@login_required
@permission_required('ppequipment_app.change_verificationdate', raise_exception=True)
def verification_date_update(request, pk):
    obj = get_object_or_404(VerificationDate, pk=pk)
    if request.method == "POST":
        form = VerificationDateForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Дата сверки обновлена")
            return redirect("ppequipment_app:verification_date_list")
    else:
        form = VerificationDateForm(instance=obj)
    return render(request, "ppequipment_app/verificationdate_form.html",
                  {"form": form, "title": "Редактировать дату сверки"})


@login_required
@permission_required('ppequipment_app.delete_verificationdate', raise_exception=True)
def verification_date_delete(request, pk):
    obj = get_object_or_404(VerificationDate, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Дата сверки удалена")
        return redirect("ppequipment_app:verification_date_list")
    return render(request, "ppequipment_app/confirm_delete.html", {"object": obj})


# ─── Справочники CRUD ────────────────────────────────────────────────────────
def _crud_list(request, model, template, context_name, search_fields=None):
    """Список для справочников - доступ только авторизованным"""
    if not request.user.is_authenticated:
        messages.error(request, "Необходимо авторизоваться для просмотра")
        return redirect('customers_app:login')

    qs = model.objects.all()
    search = request.GET.get("q", "")
    if search and search_fields:
        q_obj = Q()
        for f in search_fields:
            q_obj |= Q(**{f"{f}__icontains": search})
        qs = qs.filter(q_obj)
    return render(request, template, {"object_list": qs, context_name: True, "search": search})


def _crud_create_update(request, model, form_class, template, obj=None, title=""):
    """Создание/обновление для справочников - проверка прав внутри"""
    if not request.user.is_authenticated:
        messages.error(request, "Необходимо авторизоваться")
        return redirect('customers_app:login')

    # Определяем имя модели для проверки прав
    model_name = model._meta.model_name
    is_edit = obj is not None

    if is_edit and not request.user.has_perm(f'ppequipment_app.change_{model_name}'):
        messages.error(request, f"У вас нет прав на изменение {model._meta.verbose_name}")
        return redirect(f'ppequipment_app:{model_name}_list')
    elif not is_edit and not request.user.has_perm(f'ppequipment_app.add_{model_name}'):
        messages.error(request, f"У вас нет прав на создание {model._meta.verbose_name}")
        return redirect(f'ppequipment_app:{model_name}_list')

    if request.method == "POST":
        form = form_class(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Сохранено")
            return redirect(request.META.get("HTTP_REFERER", "ppequipment_app:index"))
    else:
        form = form_class(instance=obj)
    return render(request, template, {"form": form, "title": title})


# DestLit
def dest_lit_list(request):
    return _crud_list(request, DestLit, "ppequipment_app/ref_list.html", "is_dest_lit", search_fields=["name"])


def dest_lit_create(request):
    return _crud_create_update(request, DestLit, DestLitForm, "ppequipment_app/ref_form.html", title="Создать Назн-лит")


def dest_lit_update(request, pk):
    obj = get_object_or_404(DestLit, pk=pk)
    return _crud_create_update(request, DestLit, DestLitForm, "ppequipment_app/ref_form.html", obj=obj,
                               title="Редактировать Назн-лит")


@login_required
@permission_required('ppequipment_app.delete_destlit', raise_exception=True)
def dest_lit_delete(request, pk):
    obj = get_object_or_404(DestLit, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Запись удалена")
        return redirect("ppequipment_app:dest_lit_list")
    return render(request, "ppequipment_app/confirm_delete.html", {"object": obj})


# LocationRef
def location_ref_list(request):
    return _crud_list(request, LocationRef, "ppequipment_app/ref_list.html", "is_location_ref", search_fields=["name"])


def location_ref_create(request):
    return _crud_create_update(request, LocationRef, LocationRefForm, "ppequipment_app/ref_form.html",
                               title="Создать местоположение")


def location_ref_update(request, pk):
    obj = get_object_or_404(LocationRef, pk=pk)
    return _crud_create_update(request, LocationRef, LocationRefForm, "ppequipment_app/ref_form.html", obj=obj,
                               title="Редактировать местоположение")


@login_required
@permission_required('ppequipment_app.delete_locationref', raise_exception=True)
def location_ref_delete(request, pk):
    obj = get_object_or_404(LocationRef, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Запись удалена")
        return redirect("ppequipment_app:location_ref_list")
    return render(request, "ppequipment_app/confirm_delete.html", {"object": obj})


# AircraftType
def aircraft_type_list(request):
    return _crud_list(request, AircraftType, "ppequipment_app/ref_list.html", "is_aircraft_type",
                      search_fields=["name"])


def aircraft_type_create(request):
    return _crud_create_update(request, AircraftType, AircraftTypeForm, "ppequipment_app/ref_form.html",
                               title="Создать тип ВС")


def aircraft_type_update(request, pk):
    obj = get_object_or_404(AircraftType, pk=pk)
    return _crud_create_update(request, AircraftType, AircraftTypeForm, "ppequipment_app/ref_form.html", obj=obj,
                               title="Редактировать тип ВС")


@login_required
@permission_required('ppequipment_app.delete_aircrafttype', raise_exception=True)
def aircraft_type_delete(request, pk):
    obj = get_object_or_404(AircraftType, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Запись удалена")
        return redirect("ppequipment_app:aircraft_type_list")
    return render(request, "ppequipment_app/confirm_delete.html", {"object": obj})


# ContractorStatus
def contractor_status_list(request):
    return _crud_list(request, ContractorStatus, "ppequipment_app/ref_list.html", "is_contractor_status",
                      search_fields=["name"])


def contractor_status_create(request):
    return _crud_create_update(request, ContractorStatus, ContractorStatusForm, "ppequipment_app/ref_form.html",
                               title="Создать статус контр-раб")


def contractor_status_update(request, pk):
    obj = get_object_or_404(ContractorStatus, pk=pk)
    return _crud_create_update(request, ContractorStatus, ContractorStatusForm, "ppequipment_app/ref_form.html",
                               obj=obj, title="Редактировать статус контр-раб")


@login_required
@permission_required('ppequipment_app.delete_contractorstatus', raise_exception=True)
def contractor_status_delete(request, pk):
    obj = get_object_or_404(ContractorStatus, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Запись удалена")
        return redirect("ppequipment_app:contractor_status_list")
    return render(request, "ppequipment_app/confirm_delete.html", {"object": obj})


# ─── Import from MDB ─────────────────────────────────────────────────────────
def import_from_mdb(request):
    """Импорт данных из MDB-файла с нормализацией в справочники"""
    if request.method != "POST":
        return render(request, "ppequipment_app/import_mdb.html")

    imported = {"dest_lit": 0, "locations": 0, "aircraft_types": 0, "contractor_statuses": 0,
                "equipment": 0, "location_entries": 0, "verifications": 0, "dates": 0}
    errors = []

    try:
        # ── Шаг 0: Справочник Назн-лит ──
        rows = _run_mdb_table("наименование")
        dest_lit_set = set()
        for row in rows:
            val = (row.get("назн-лит") or "").strip()
            if val:
                dest_lit_set.add(val)
        for val in dest_lit_set:
            _, created = DestLit.objects.get_or_create(name=val)
            if created:
                imported["dest_lit"] += 1

        # ── Шаг 1: Справочник Типов ВС ──
        aircraft_type_set = set()
        for row in rows:
            val = (row.get("тип") or "").strip()
            if val:
                aircraft_type_set.add(val)
        for val in aircraft_type_set:
            _, created = AircraftType.objects.get_or_create(name=val)
            if created:
                imported["aircraft_types"] += 1

        # ── Шаг 2: Справочник Местоположений ──
        rows_loc = _run_mdb_table("где")
        rows_sverka = _run_mdb_table("сверка")
        location_name_set = set()
        for row in rows_loc:
            val = (row.get("где") or "").strip()
            if val:
                location_name_set.add(val)
        for row in rows_sverka:
            val = (row.get("где") or "").strip()
            if val:
                location_name_set.add(val)
        for val in location_name_set:
            _, created = LocationRef.objects.get_or_create(name=val)
            if created:
                imported["locations"] += 1

        # ── Шаг 3: Справочник Контр-раб статусов ──
        contractor_status_set = set()
        for row in rows_sverka:
            val = (row.get("конт-раб") or "").strip()
            if val:
                contractor_status_set.add(val)
        for val in contractor_status_set:
            _, created = ContractorStatus.objects.get_or_create(name=val)
            if created:
                imported["contractor_statuses"] += 1

        # ── Шаг 4: Оборудование (наименование) ──
        rows = _run_mdb_table("наименование")
        for row in rows:
            equip_number = int(row.get("номер", 0) or 0)
            dest_lit_val = (row.get("назн-лит") or "").strip()
            aircraft_type_val = (row.get("тип") or "").strip()

            dest_lit_obj = DestLit.objects.filter(name=dest_lit_val).first() if dest_lit_val else None
            aircraft_type_obj = AircraftType.objects.filter(
                name=aircraft_type_val).first() if aircraft_type_val else None

            _, created = Equipment.objects.update_or_create(
                number=equip_number,
                defaults={
                    "name": row.get("наимен", ""),
                    "aircraft_type": aircraft_type_obj,
                    "edition": row.get("издание") or None,
                    "issue": row.get("выпуск") or None,
                    "approved_by": row.get("кем утвержден") or None,
                    "approval_date": _parse_date(row.get("дата утверждения")),
                    "priority": int(row["приоритет"]) if row.get("приоритет") else None,
                    "dest_lit": dest_lit_obj,
                },
            )
            if created:
                imported["equipment"] += 1

        # ── Шаг 5: Местоположения оборудования (где) ──
        for row in rows_loc:
            equip_number = int(row.get("номер", 0) or 0)
            loc_val = (row.get("где") or "").strip()
            if equip_number and loc_val:
                equipment = Equipment.objects.filter(number=equip_number).first()
                location_ref = LocationRef.objects.filter(name=loc_val).first()
                if equipment and location_ref:
                    _, created = Location.objects.get_or_create(
                        equipment=equipment, location_ref=location_ref,
                    )
                    if created:
                        imported["location_entries"] += 1

        # ── Шаг 6: Сверки (сверка) ──
        for row in rows_sverka:
            inv = (row.get("инв") or "").strip()
            if not inv:
                continue
            equip_number = int(row.get("номер", 0) or 0)
            equipment = Equipment.objects.filter(number=equip_number).first() if equip_number else None

            loc_val = (row.get("где") or "").strip()
            location_ref = LocationRef.objects.filter(name=loc_val).first() if loc_val else None

            contractor_val = (row.get("конт-раб") or "").strip()
            contractor_status = ContractorStatus.objects.filter(name=contractor_val).first() if contractor_val else None

            _, created = Verification.objects.update_or_create(
                inventory_number=inv,
                defaults={
                    "equipment": equipment,
                    "location_ref": location_ref,
                    "contractor_status": contractor_status,
                    "last_verification_date": _parse_date(row.get("последняя сверка")),
                    "notes": row.get("примечание") or None,
                    "vs_number": row.get("№ вс") or None,
                    "end_date": _parse_date(row.get("дата оконч")),
                    "is_destroyed": str(row.get("уничтожен", "0")).lower() in ("1", "true", "yes", "да"),
                },
            )
            if created:
                imported["verifications"] += 1

        # ── Шаг 7: Даты сверок ──
        rows_dates = _run_mdb_table("Таблица дата сверки")
        for row in rows_dates:
            date_val = _parse_date(row.get("дата сверки"))
            if date_val:
                _, created = VerificationDate.objects.get_or_create(
                    verification_date=date_val,
                )
                if created:
                    imported["dates"] += 1

        messages.success(
            request,
            f"Импорт завершён: справочники — "
            f"назн-лит={imported['dest_lit']}, типы ВС={imported['aircraft_types']}, "
            f"местоположения={imported['locations']}, контр-раб={imported['contractor_statuses']}; "
            f"данные — оборудование={imported['equipment']}, "
            f"записи местоположений={imported['location_entries']}, "
            f"сверки={imported['verifications']}, даты={imported['dates']}"
        )
    except TypeError:
        pass
    # except Exception as e:
    #     errors.append(str(e))
    #     messages.error(request, f"Ошибка импорта: {e}")

    return render(request, "ppequipment_app/import_mdb.html", {
        "imported": imported, "errors": errors,
    })


# ─── Сверочные этикетки ──────────────────────────────────────────────────────
@login_required
def verification_labels(request):
    """Страница выбора условий для печати свёрочных этикеток"""
    if request.method == "POST":
        form = VerificationLabelForm(request.POST)
        if form.is_valid():
            # Собираем фильтры
            qs = Verification.objects.select_related(
                "equipment", "location_ref", "contractor_status", "equipment__aircraft_type", "equipment__dest_lit"
            ).all()

            # Дата сверки
            verification_date = form.cleaned_data.get("verification_date")
            if verification_date:
                qs = qs.filter(last_verification_date=verification_date.verification_date)

            # Местоположение
            location_refs = form.cleaned_data.get("location_ref")
            if location_refs:
                qs = qs.filter(location_ref__in=location_refs)

            # Статус контр-раб
            contractor_statuses = form.cleaned_data.get("contractor_status")
            if contractor_statuses:
                qs = qs.filter(contractor_status__in=contractor_statuses)

            # Назн-лит (через оборудование)
            dest_lits = form.cleaned_data.get("dest_lit")
            if dest_lits:
                qs = qs.filter(equipment__dest_lit__in=dest_lits)

            # Уничтожен
            is_destroyed = form.cleaned_data.get("is_destroyed")
            if is_destroyed == "0":
                qs = qs.filter(is_destroyed=False)
            elif is_destroyed == "1":
                qs = qs.filter(is_destroyed=True)

            # Тип ВС
            aircraft_types = form.cleaned_data.get("aircraft_type")
            if aircraft_types:
                qs = qs.filter(equipment__aircraft_type__in=aircraft_types)

            # Инвентарные номера
            inventory_numbers = form.cleaned_data.get("inventory_numbers")
            if inventory_numbers:
                # Разбиваем по запятым и новым строкам
                inv_list = [inv.strip() for inv in inventory_numbers.replace("\n", ",").split(",") if inv.strip()]
                if inv_list:
                    qs = qs.filter(inventory_number__in=inv_list)

            # Если ничего не выбрано, показываем все записи
            if not qs.exists():
                messages.warning(request, "Нет данных для печати этикеток. Измените условия фильтрации.")
                return render(request, "ppequipment_app/verification_labels.html", {"form": form})

            return render(request, "ppequipment_app/verification_labels_print.html", {
                "labels": qs,
                "count": qs.count(),
                "verification_date_label": verification_date.verification_date if verification_date else None,
            })
    else:
        form = VerificationLabelForm()

    return render(request, "ppequipment_app/verification_labels.html", {"form": form})


# ─── QR-код для этикетки ────────────────────────────────────────────────────
def generate_verification_qr(request, slug):
    """Генерирует QR-код с полными данными сверочной этикетки"""
    verification = get_object_or_404(
        Verification.objects.select_related(
            "equipment", "location_ref", "contractor_status",
            "equipment__aircraft_type", "equipment__dest_lit"
        ),
        slug=slug,
    )
    try:
        vd = verification.verification_date.verification_date.strftime('%d.%m.%Y')
    except Exception as e:
        vd = 'отсутствует'

    try:
        vr = format_name_initials(verification.verification_date.verification_responsible.title)
    except Exception as e:
        vr = 'неизвестен'


    # Формируем данные для QR-кода
    qr_data = f"""Инв. №: {verification.inventory_number}
ПТД: {verification.equipment.name if verification.equipment else "—"}
Местоположение: {verification.location_ref if verification.location_ref else "—"}
Статус: {verification.contractor_status if verification.contractor_status else "—"}
Последняя сверка: {vd}
Ответственный: {vr}
Примечание: {verification.notes if verification.notes else "—"}"""

    # Создаём QR-код
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    # Генерируем изображение с CircleModule
    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=CircleModuleDrawer(radius_factor=0.5),
        fill_color=(0, 0, 0),
        back_color=(255, 255, 255),
    )

    # Конвертируем в PNG и отдаём
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    response = HttpResponse(buffer, content_type="image/png")
    response["Cache-Control"] = "public, max-age=86400"
    return response



