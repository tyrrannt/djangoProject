# flight_planning/views.py
import json
from datetime import datetime, timedelta

from django.db.models import Q
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import transaction
from django.contrib.auth.decorators import login_required

from customers_app.models import DataBaseUser
from hrdepartment_app.models import PlaceProductionActivity
from contracts_app.models import Estate, TypeProperty
from .models import PilotAssignment, AircraftMovement, FlightCrew, CrewMember, FlightCrewNote, CREW_ROLES
from .forms import AircraftMovementForm
from .selectors import (
    get_pilot_assignments_for_month,
    get_active_aircraft,
    get_latest_aircraft_locations,
    get_aircraft_movement_history,
    get_mpd_aircraft_map,
    get_crews_for_month,
    get_mpd_crew_map,
    get_available_aircraft_for_mpd,
    get_personnel_utilization_report_data,
    get_aircraft_basing_report_data
)
from .services import (
    get_grouped_pilot_schedule,
    record_aircraft_movement,
    validate_crew_composition,
    check_crew_member_conflicts,
    create_or_update_flight_crew_range,
    update_flight_crew,
    delete_flight_crew
)

# Должности летного состава для планирования
ALLOWED_JOBS = ['командир', 'пилот', 'бортмеханик', 'Командир', 'Бортмеханик', 'инструктор', 'Бортовой']


def get_pilot_allowed_roles(job_name: str) -> list:
    """
    Возвращает список допустимых ролей в экипаже на основе должности сотрудника:
    - commander: КВС (командир ВС, пилот-инструктор, командир летного отряда, летный директор, пилот-инспектор)
    - copilot: Второй пилот (второй пилот, командир ВС, пилот-инструктор, командир отряда)
    - pilot_instructor: Пилот-инструктор (пилот-инструктор, пилот-инспектор, командир отряда, летный директор)
    - flight_engineer: Бортмеханик (бортовой механик, бортмеханик-инструктор, старший бортмеханик)
    - flight_engineer_instructor: Бортмеханик-инструктор (бортмеханик-инструктор, старший бортмеханик)
    """
    j = (job_name or "").lower()
    roles = []
    
    # 1. КВС
    if any(k in j for k in ['командир воздушного судна', 'командир летного', 'заместитель командира летного', 'пилот-инструктор', 'пилот-инспектор', 'летный директор']) and not any(x in j for x in ['бортмеханик', 'врач', 'штаб', 'водитель']):
        roles.append('commander')
    
    # 2. Второй пилот
    if any(k in j for k in ['второй пилот', 'командир воздушного судна', 'командир летного', 'заместитель командира летного', 'пилот-инструктор', 'пилот-инспектор', 'летный директор']) and not any(x in j for x in ['бортмеханик', 'врач', 'штаб', 'водитель']):
        roles.append('copilot')
    
    # 3. Пилот-инструктор
    if any(k in j for k in ['пилот-инструктор', 'пилот-инспектор', 'командир летного', 'заместитель командира летного', 'летный директор']) and not any(x in j for x in ['бортмеханик', 'врач', 'штаб', 'водитель']):
        roles.append('pilot_instructor')
    
    # 4. Бортмеханик
    if any(k in j for k in ['бортмеханик', 'бортовой механик', 'старший бортмеханик']):
        roles.append('flight_engineer')
    
    # 5. Бортмеханик-инструктор
    if any(k in j for k in ['бортмеханик-инструктор', 'старший бортмеханик']):
        roles.append('flight_engineer_instructor')
    
    return roles


@login_required
def my_schedule_view(request):
    """
    Отображает страницу личного графика для текущего пилота.

    Args:
        request: Объект HttpRequest.

    Returns:
        Объект HttpResponse с отрендеренным шаблоном.
    """
    year = request.GET.get('year', timezone.now().year)
    month = request.GET.get('month', timezone.now().month)

    try:
        year = int(year)
        month = int(month)
    except ValueError:
        year = timezone.now().year
        month = timezone.now().month

    assignments = get_pilot_assignments_for_month(
        pilot_id=request.user.id,
        year=year,
        month=month
    )

    grouped_schedule = get_grouped_pilot_schedule(list(assignments), year, month)

    # Генерируем даты выбранного месяца для навигации
    first_day = datetime(year, month, 1).date()
    prev_month_date = first_day - timedelta(days=1)
    if month == 12:
        next_month_date = datetime(year + 1, 1, 1).date()
    else:
        next_month_date = datetime(year, month + 1, 1).date()

    context = {
        'grouped_schedule': grouped_schedule,
        'year': year,
        'month': month,
        'prev_year': prev_month_date.year,
        'prev_month': prev_month_date.month,
        'next_year': next_month_date.year,
        'next_month': next_month_date.month,
        'month_name': first_day.strftime('%B %Y'),
    }

    return render(request, 'flight_planning/my_schedule.html', context)


@login_required
@require_http_methods(["GET"])
def get_my_assignments_api(request):
    """
    Возвращает назначения текущего пользователя за указанный месяц в формате JSON.

    Args:
        request: Объект HttpRequest с параметрами year и month.

    Returns:
        JsonResponse со списком назначений.
    """
    year = request.GET.get('year')
    month = request.GET.get('month')

    if not year or not month:
        now = timezone.now()
        year = now.year
        month = now.month

    try:
        year = int(year)
        month = int(month)
    except ValueError:
        return JsonResponse({'error': 'Invalid year or month'}, status=400)

    assignments = get_pilot_assignments_for_month(
        pilot_id=request.user.id,
        year=year,
        month=month
    )

    data = [
        {
            'id': a.id,
            'date': a.date.isoformat(),
            'mpd_id': a.mpd_id,
            'mpd_name': a.mpd.name
        }
        for a in assignments
    ]

    return JsonResponse({'assignments': data})


@login_required
def planning_table(request):
    """
    Главная страница с таблицей планирования
    """
    # Получаем год и месяц из GET параметров, либо текущие
    year = request.GET.get('year', timezone.now().year)
    month = request.GET.get('month', timezone.now().month)

    try:
        year = int(year)
        month = int(month)
    except ValueError:
        year = timezone.now().year
        month = timezone.now().month

    # Получаем все МПД
    mpds = PlaceProductionActivity.objects.filter(in_planning=True).order_by('name')

    # Создаём динамические условия Q
    q_conditions = Q()
    for keyword in ALLOWED_JOBS:
        q_conditions |= Q(user_work_profile__job__name__icontains=keyword)
    # Получаем всех активных пилотов (пользователей)
    pilots = DataBaseUser.objects.filter(
        is_active=True,
        user_work_profile__isnull=False
    ).filter(q_conditions).select_related('user_work_profile__job').order_by('last_name', 'first_name').distinct()

    # Генерируем даты выбранного месяца
    first_day = datetime(year, month, 1).date()
    if month == 12:
        last_day = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1).date() - timedelta(days=1)

    dates = []
    current = first_day
    while current <= last_day:
        dates.append(current)
        current += timedelta(days=1)

    # Загружаем существующие назначения за месяц с подгрузкой экипажей
    assignments = PilotAssignment.objects.filter(
        date__year=year,
        date__month=month
    ).select_related('pilot', 'mpd', 'crew', 'crew__aircraft', 'crew__aircraft__type_property')

    # Строим карту назначений для быстрого доступа в шаблоне
    assignment_map = {}
    for a in assignments:
        mpd_id = a.mpd_id
        date_str = a.date.isoformat()

        if mpd_id not in assignment_map:
            assignment_map[mpd_id] = {}

        if date_str not in assignment_map[mpd_id]:
            assignment_map[mpd_id][date_str] = []

        # Получаем должность пилота
        job_name = None
        is_commander = False
        is_instructor = False
        try:
            if hasattr(a.pilot, 'user_work_profile') and a.pilot.user_work_profile:
                if hasattr(a.pilot.user_work_profile, 'job') and a.pilot.user_work_profile.job:
                    job_name = a.pilot.user_work_profile.job.name
                    if job_name:
                        job_lower = job_name.lower()
                        is_commander = 'командир' in job_lower
                        is_instructor = 'инструктор' in job_lower
        except Exception as e:
            print(f"Error getting job info for pilot {a.pilot_id}: {e}")

        assignment_map[mpd_id][date_str].append({
            'pilot_id': a.pilot_id,
            'pilot_name': a.pilot.title or a.pilot.username,
            'pilot_job': job_name or 'Должность не указана',
            'is_commander': is_commander,
            'is_instructor': is_instructor,
            'assignment_id': a.id,
            'crew_id': a.crew_id,
            'role_in_crew': a.role_in_crew,
            'role_in_crew_label': a.get_role_in_crew_display() if a.role_in_crew else '',
            'aircraft_number': a.crew.aircraft.registration_number if (a.crew and a.crew.aircraft) else ('Резерв' if a.crew else ''),
            'flight_type': a.crew.flight_type if a.crew else ''
        })

    # Получаем карту экипажей за месяц
    crew_map = get_mpd_crew_map(year, month)

    # Карта актуального распределения ВС по МПД
    mpd_aircraft_map = get_mpd_aircraft_map()

    # Сериализуемый список всех пилотов для JavaScript модальных окон
    pilots_js_list = []
    for p in pilots:
        job_title = p.user_work_profile.job.name if (hasattr(p, 'user_work_profile') and p.user_work_profile and p.user_work_profile.job) else ''
        job_lower = job_title.lower()
        allowed_roles = get_pilot_allowed_roles(job_title)
        suggested_role = 'copilot'
        if 'commander' in allowed_roles:
            suggested_role = 'commander'
        elif 'flight_engineer_instructor' in allowed_roles:
            suggested_role = 'flight_engineer_instructor'
        elif 'flight_engineer' in allowed_roles:
            suggested_role = 'flight_engineer'
        elif 'pilot_instructor' in allowed_roles:
            suggested_role = 'pilot_instructor'

        pilots_js_list.append({
            'id': p.id,
            'name': p.title or p.username,
            'job': job_title,
            'is_commander': 'командир' in job_lower,
            'is_instructor': 'инструктор' in job_lower,
            'suggested_role': suggested_role,
            'allowed_roles': allowed_roles
        })

    # Данные для навигации по месяцам
    prev_month_date = first_day - timedelta(days=1)
    next_month_date = last_day + timedelta(days=1)

    context = {
        'mpds': mpds,
        'pilots': pilots,
        'dates': dates,
        'year': year,
        'month': month,
        'prev_year': prev_month_date.year,
        'prev_month': prev_month_date.month,
        'next_year': next_month_date.year,
        'next_month': next_month_date.month,
        'month_name': first_day.strftime('%B %Y'),
        'assignment_map': assignment_map,
        'crew_map': crew_map,
        'crew_map_json': json.dumps(crew_map),
        'mpd_aircraft_json': json.dumps(mpd_aircraft_map),
        'pilots_js_json': json.dumps(pilots_js_list),
    }

    return render(request, 'flight_planning/table.html', context)


@login_required
@require_http_methods(["GET"])
def get_assignments_api(request):
    """
    Получить назначения за месяц в формате JSON
    """
    year = request.GET.get('year')
    month = request.GET.get('month')

    if not year or not month:
        return JsonResponse({'error': 'year and month required'}, status=400)

    assignments = PilotAssignment.objects.filter(
        date__year=year,
        date__month=month
    ).values('id', 'pilot_id', 'mpd_id', 'date')

    return JsonResponse({'assignments': list(assignments)}, safe=False)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def assign_pilot_api(request):
    """
    Назначить пилота на диапазон дат для МПД
    """
    try:
        data = json.loads(request.body)
        pilot_id = data.get('pilot_id')
        mpd_id = data.get('mpd_id')
        start_date = data.get('start_date')
        end_date = data.get('end_date')

        # Валидация
        if not all([pilot_id, mpd_id, start_date, end_date]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        pilot = get_object_or_404(DataBaseUser, id=pilot_id, is_active=True)
        mpd = get_object_or_404(PlaceProductionActivity, id=mpd_id)

        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()

        if start > end:
            return JsonResponse({'error': 'Start date must be before end date'}, status=400)

        # Проверяем конфликты
        conflicts = []
        current = start
        while current <= end:
            existing = PilotAssignment.objects.filter(
                pilot=pilot,
                date=current
            ).select_related('mpd').first()

            if existing and existing.mpd_id != mpd_id:
                conflicts.append({
                    'date': current.isoformat(),
                    'old_mpd_id': existing.mpd_id,
                    'old_mpd_name': existing.mpd.name,
                    'assignment_id': existing.id
                })
            current += timedelta(days=1)

        # Получаем информацию о должности пилота
        job_name = None
        is_commander = False
        is_instructor = False
        try:
            if hasattr(pilot, 'user_work_profile') and pilot.user_work_profile:
                if hasattr(pilot.user_work_profile, 'job') and pilot.user_work_profile.job:
                    job_name = pilot.user_work_profile.job.name
                    if job_name:
                        job_lower = job_name.lower()
                        is_commander = 'командир' in job_lower
                        is_instructor = 'пилот-инструктор' in job_lower
        except:
            pass

        # Если есть конфликты, возвращаем их для подтверждения
        if conflicts:
            return JsonResponse({
                'status': 'conflict',
                'conflicts': conflicts,
                'pilot_id': pilot_id,
                'mpd_id': mpd_id,
                'start_date': start_date,
                'end_date': end_date
            }, status=409)

        # Нет конфликтов — создаём назначения
        assignments_created = []
        with transaction.atomic():
            current = start
            while current <= end:
                assignment, created = PilotAssignment.objects.get_or_create(
                    pilot=pilot,
                    date=current,
                    defaults={'mpd': mpd, 'created_by': request.user}
                )
                if not created and assignment.mpd_id != mpd_id:
                    assignment.mpd = mpd
                    assignment.save()
                assignments_created.append({
                    'date': current.isoformat(),
                    'assignment_id': assignment.id
                })
                current += timedelta(days=1)

        return JsonResponse({
            'status': 'success',
            'assignments': assignments_created,
            'mpd_id': mpd_id,
            'pilot_id': pilot_id,
            'pilot_name': pilot.title or pilot.username,
            'pilot_job': job_name or 'Должность не указана',
            'is_commander': is_commander,
            'is_instructor': is_instructor
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def resolve_conflict_api(request):
    """
    Разрешить конфликт — удалить старые назначения и создать новые
    """
    try:
        data = json.loads(request.body)
        conflicts = data.get('conflicts', [])
        pilot_id = data.get('pilot_id')
        mpd_id = data.get('mpd_id')
        start_date = data.get('start_date')
        end_date = data.get('end_date')

        if not all([pilot_id, mpd_id, start_date, end_date]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        pilot = get_object_or_404(DataBaseUser, id=pilot_id)
        mpd = get_object_or_404(PlaceProductionActivity, id=mpd_id)
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()

        with transaction.atomic():
            # Удаляем конфликтующие назначения
            conflict_ids = [c['assignment_id'] for c in conflicts if c.get('assignment_id')]
            if conflict_ids:
                PilotAssignment.objects.filter(id__in=conflict_ids).delete()

            # Создаём новые назначения
            assignments_created = []
            current = start
            while current <= end:
                # Проверяем, не создали ли уже (на случай частичного конфликта)
                existing = PilotAssignment.objects.filter(pilot=pilot, date=current).first()
                if existing:
                    existing.mpd = mpd
                    existing.save()
                    assignments_created.append({
                        'date': current.isoformat(),
                        'assignment_id': existing.id
                    })
                else:
                    assignment = PilotAssignment.objects.create(
                        pilot=pilot,
                        mpd=mpd,
                        date=current,
                        created_by=request.user
                    )
                    assignments_created.append({
                        'date': current.isoformat(),
                        'assignment_id': assignment.id
                    })
                current += timedelta(days=1)

        return JsonResponse({
            'status': 'success',
            'assignments': assignments_created
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def remove_assignments_api(request):
    """
    Удалить назначения по списку ID
    """
    try:
        data = json.loads(request.body)
        assignment_ids = data.get('assignment_ids', [])

        if not assignment_ids:
            return JsonResponse({'error': 'No assignment IDs provided'}, status=400)

        deleted_count, _ = PilotAssignment.objects.filter(
            id__in=assignment_ids
        ).delete()

        return JsonResponse({
            'status': 'success',
            'deleted': deleted_count
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def get_pilot_job_info(request):
    """
    Получить должность пилота и статус командира/инструктора
    """
    pilot_id = request.GET.get('pilot_id')
    if not pilot_id:
        return JsonResponse({'error': 'pilot_id required'}, status=400)

    try:
        pilot = get_object_or_404(DataBaseUser, id=pilot_id)
        job_name = None
        is_commander = False
        is_instructor = False

        if hasattr(pilot, 'user_work_profile') and pilot.user_work_profile:
            if pilot.user_work_profile.job:
                job_name = pilot.user_work_profile.job.name
                if job_name:
                    job_lower = job_name.lower()
                    is_commander = 'командир' in job_lower
                    is_instructor = 'пилот-инструктор' in job_lower

        return JsonResponse({
            'job_name': job_name or 'Должность не указана',
            'is_commander': is_commander,
            'is_instructor': is_instructor
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def aircraft_movement_list_view(request):
    """
    Отображает страницу журнала перемещений воздушных судов (ВС) по МПД.
    Включает сводную информацию о текущей дислокации бортов и фильтрацию истории.
    """
    aircraft_id = request.GET.get('aircraft')
    mpd_id = request.GET.get('mpd')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    movements_qs = AircraftMovement.objects.select_related(
        'aircraft', 'aircraft__type_property', 'mpd', 'created_by'
    )

    if aircraft_id:
        movements_qs = movements_qs.filter(aircraft_id=aircraft_id)
    if mpd_id:
        movements_qs = movements_qs.filter(mpd_id=mpd_id)
    if date_from:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            movements_qs = movements_qs.filter(date__gte=d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            movements_qs = movements_qs.filter(date__lte=d_to)
        except ValueError:
            pass

    movements = movements_qs.order_by('-date', '-created_at')

    # Текущее распределение активных бортов по МПД
    mpd_aircraft_map = get_mpd_aircraft_map()
    all_mpds_in_planning = PlaceProductionActivity.objects.filter(in_planning=True).order_by('name')

    # Формируем структуру сводки по всем МПД в планировании
    mpd_summary = []
    for mpd_obj in all_mpds_in_planning:
        mpd_summary.append({
            'mpd': mpd_obj,
            'aircrafts': mpd_aircraft_map.get(mpd_obj.id, [])
        })

    # Справочники для фильтров формы
    aircrafts = Estate.objects.select_related('type_property').order_by('registration_number')
    mpds = all_mpds_in_planning

    # Если запрос через Ajax/DataTable
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.GET.get('format') == 'json':
        data = [
            {
                'id': m.id,
                'aircraft_number': m.aircraft.registration_number,
                'aircraft_type': m.aircraft.type_property.type_property if m.aircraft.type_property else '',
                'is_decommissioned': m.aircraft.is_decommissioned,
                'mpd_name': m.mpd.name,
                'mpd_id': m.mpd_id,
                'date': m.date.strftime('%d.%m.%Y'),
                'raw_date': m.date.isoformat(),
                'comment': m.comment,
                'created_by': m.created_by.title or m.created_by.username if m.created_by else 'Система',
                'created_at': m.created_at.strftime('%d.%m.%Y %H:%M'),
            }
            for m in movements
        ]
        return JsonResponse({'data': data})

    context = {
        'title': 'Журнал перемещения воздушных судов по МПД',
        'movements': movements,
        'mpd_summary': mpd_summary,
        'aircrafts': aircrafts,
        'mpds': mpds,
        'selected_aircraft_id': int(aircraft_id) if aircraft_id and aircraft_id.isdigit() else None,
        'selected_mpd_id': int(mpd_id) if mpd_id and mpd_id.isdigit() else None,
        'selected_date_from': date_from or '',
        'selected_date_to': date_to or '',
    }
    return render(request, 'flight_planning/aircraft_movement_list.html', context)


@login_required
def aircraft_movement_create_view(request):
    """
    Создание новой записи в журнале перемещения ВС.
    """
    if request.method == 'POST':
        form = AircraftMovementForm(request.POST)
        if form.is_valid():
            movement = form.save(commit=False)
            movement.created_by = request.user
            movement.save()
            messages.success(
                request,
                f"Перемещение борта {movement.aircraft.registration_number} на МПД '{movement.mpd.name}' успешно зарегистрировано."
            )
            return redirect('flight_planning:aircraft_movement_list')
    else:
        initial = {}
        if request.GET.get('aircraft_id'):
            initial['aircraft'] = request.GET.get('aircraft_id')
        if request.GET.get('mpd_id'):
            initial['mpd'] = request.GET.get('mpd_id')
        form = AircraftMovementForm(initial=initial)

    context = {
        'title': 'Добавить перемещение воздушного судна',
        'form': form,
        'is_edit': False,
    }
    return render(request, 'flight_planning/aircraft_movement_form.html', context)


@login_required
def aircraft_movement_update_view(request, pk):
    """
    Редактирование существующей записи журнала перемещения ВС.
    """
    movement = get_object_or_404(AircraftMovement, pk=pk)

    if request.method == 'POST':
        form = AircraftMovementForm(request.POST, instance=movement)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Запись о перемещении борта {movement.aircraft.registration_number} успешно обновлена."
            )
            return redirect('flight_planning:aircraft_movement_list')
    else:
        form = AircraftMovementForm(instance=movement)

    context = {
        'title': f'Редактирование перемещения: {movement.aircraft.registration_number}',
        'form': form,
        'movement': movement,
        'is_edit': True,
    }
    return render(request, 'flight_planning/aircraft_movement_form.html', context)


@login_required
@require_http_methods(["POST"])
def aircraft_movement_delete_view(request, pk):
    """
    Удаление записи о перемещении ВС. Поддерживает как стандартный POST, так и AJAX запрос.
    """
    movement = get_object_or_404(AircraftMovement, pk=pk)
    aircraft_reg = movement.aircraft.registration_number
    mpd_name = movement.mpd.name
    movement.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'message': 'Запись успешно удалена'})

    messages.success(request, f"Запись о перемещении борта {aircraft_reg} на {mpd_name} удалена.")
    return redirect('flight_planning:aircraft_movement_list')


@login_required
@require_http_methods(["GET"])
def get_aircraft_locations_api(request):
    """
    API эндпоинт для получения текущего местоположения всех активных ВС по МПД.
    """
    date_str = request.GET.get('date')
    target_date = None
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'error': 'Invalid date format, expected YYYY-MM-DD'}, status=400)

    mpd_map = get_mpd_aircraft_map(target_date)
    return JsonResponse({'status': 'success', 'locations': mpd_map})


@login_required
@require_http_methods(["POST"])
def save_crew_api(request):
    """
    API эндпоинт для создания или обновления летного экипажа (на день или диапазон дат).
    """
    try:
        data = json.loads(request.body)
        crew_id = data.get('crew_id')
        mpd_id = data.get('mpd_id')
        aircraft_id = data.get('aircraft_id')
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date') or start_date_str
        flight_type = data.get('flight_type', 'standard')
        members = data.get('members', [])
        name = data.get('name', '')
        comment = data.get('comment', '')

        if not mpd_id or not start_date_str:
            return JsonResponse({'error': 'Не заполнены обязательные параметры (МПД, даты).'}, status=400)

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'error': 'Некорректный формат даты (ожидается YYYY-MM-DD).'}, status=400)

        if start_date > end_date:
            return JsonResponse({'error': 'Начальная дата не может быть позже конечной.'}, status=400)

        if aircraft_id:
            try:
                aircraft_id = int(aircraft_id)
            except (ValueError, TypeError):
                aircraft_id = None

        force_override = data.get('force_override', False)

        if crew_id and start_date == end_date:
            # Редактирование конкретного экипажа на выбранную дату
            result = update_flight_crew(
                crew_id=int(crew_id),
                mpd_id=int(mpd_id),
                aircraft_id=aircraft_id,
                target_date=start_date,
                flight_type=flight_type,
                members=members,
                comment=comment,
                crew_name=name,
                force_override=force_override
            )
        else:
            result = create_or_update_flight_crew_range(
                mpd_id=int(mpd_id),
                aircraft_id=aircraft_id,
                start_date=start_date,
                end_date=end_date,
                flight_type=flight_type,
                members=members,
                created_by=request.user,
                comment=comment,
                crew_name=name,
                force_override=force_override
            )

        if result.get('status') == 'error':
            return JsonResponse({'error': ' '.join(result.get('errors', [])), 'errors': result.get('errors')}, status=400)
        elif result.get('status') == 'conflict':
            return JsonResponse({
                'status': 'conflict',
                'conflict_type': result.get('conflict_type', 'unknown'),
                'conflicts': result.get('conflicts', []),
                'can_override': result.get('can_override', False),
                'errors': result.get('errors', []),
                'error': ' '.join(result.get('errors', []))
            }, status=409)

        return JsonResponse({
            'status': 'success',
            'message': f"Экипаж успешно сохранен ({start_date_str} — {end_date_str})",
            'created_crews_count': result.get('created_crews_count', 1),
            'aircraft_name': result.get('aircraft_name', 'Резерв')
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def get_crew_detail_api(request, crew_id: int):
    """
    API получения детальной информации по конкретному экипажу для редактирования.
    """
    try:
        crew = FlightCrew.objects.select_related('aircraft', 'mpd').prefetch_related('members__member').get(id=crew_id)
        members_data = []
        for m in crew.members.all():
            job_name = ''
            try:
                if hasattr(m.member, 'user_work_profile') and m.member.user_work_profile and m.member.user_work_profile.job:
                    job_name = m.member.user_work_profile.job.name
            except Exception:
                pass

            members_data.append({
                'member_id': m.member_id,
                'name': m.member.title or m.member.username,
                'role': m.role,
                'role_label': m.get_role_display(),
                'job': job_name,
                'allowed_roles': get_pilot_allowed_roles(job_name)
            })

        return JsonResponse({
            'status': 'success',
            'crew': {
                'id': crew.id,
                'mpd_id': crew.mpd_id,
                'mpd_name': crew.mpd.name,
                'aircraft_id': crew.aircraft_id,
                'aircraft_number': crew.aircraft.registration_number if crew.aircraft else 'Резерв',
                'date': crew.date.isoformat(),
                'flight_type': crew.flight_type,
                'flight_type_label': crew.get_flight_type_display(),
                'name': crew.name,
                'comment': crew.comment,
                'members': members_data
            }
        })
    except FlightCrew.DoesNotExist:
        return JsonResponse({'error': 'Экипаж не найден.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def validate_crew_api(request):
    """
    API валидации состава экипажа на лету.
    """
    try:
        data = json.loads(request.body)
        flight_type = data.get('flight_type', 'standard')
        members = data.get('members', [])
        is_valid, errors = validate_crew_composition(flight_type, members)
        return JsonResponse({
            'status': 'success',
            'is_valid': is_valid,
            'errors': errors
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def delete_crew_api(request):
    """
    API удаления экипажа по ID.
    """
    try:
        data = json.loads(request.body)
        crew_id = data.get('crew_id')
        if not crew_id:
            return JsonResponse({'error': 'Параметр crew_id обязателен.'}, status=400)

        success = delete_flight_crew(int(crew_id))
        if success:
            return JsonResponse({'status': 'success', 'message': 'Экипаж успешно удален.'})
        return JsonResponse({'error': 'Экипаж не найден.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def get_day_crew_info_api(request):
    """
    Возвращает полную информацию по МПД на выбранную дату:
    - Доступные воздушные суда на этом МПД
    - Существующие экипажи на этом МПД
    - Индивидуальные назначения вне экипажа
    """
    mpd_id = request.GET.get('mpd_id')
    date_str = request.GET.get('date')

    if not mpd_id or not date_str:
        return JsonResponse({'error': 'Параметры mpd_id и date обязательны.'}, status=400)

    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        mpd_id = int(mpd_id)
    except ValueError:
        return JsonResponse({'error': 'Некорректные параметры.'}, status=400)

    # 1. Воздушные суда на МПД
    available_aircraft = get_available_aircraft_for_mpd(mpd_id, target_date)
    aircraft_list = [
        {
            'id': ac.id,
            'registration_number': ac.registration_number,
            'type_property': ac.type_property.type_property if ac.type_property else 'ВС',
            'is_decommissioned': ac.is_decommissioned
        }
        for ac in available_aircraft
    ]

    # 2. Существующие экипажи на МПД на эту дату
    crews = FlightCrew.objects.filter(
        mpd_id=mpd_id,
        date=target_date
    ).select_related('aircraft', 'aircraft__type_property').prefetch_related('members__member')

    crews_data = []
    for c in crews:
        members_data = [
            {
                'member_id': m.member_id,
                'name': m.member.title or m.member.username,
                'role': m.role,
                'role_label': m.get_role_display()
            }
            for m in c.members.all()
        ]
        crews_data.append({
            'id': c.id,
            'aircraft_id': c.aircraft_id,
            'aircraft_number': c.aircraft.registration_number if c.aircraft else 'Резерв',
            'aircraft_type': c.aircraft.type_property.type_property if (c.aircraft and c.aircraft.type_property) else '',
            'flight_type': c.flight_type,
            'flight_type_label': c.get_flight_type_display(),
            'name': c.name,
            'comment': c.comment,
            'members': members_data
        })

    # 3. Индивидуальные назначения вне экипажей
    standalone_assignments = PilotAssignment.objects.filter(
        mpd_id=mpd_id,
        date=target_date,
        crew__isnull=True
    ).select_related('pilot')

    standalone_data = [
        {
            'assignment_id': a.id,
            'pilot_id': a.pilot_id,
            'pilot_name': a.pilot.title or a.pilot.username,
        }
        for a in standalone_assignments
    ]

    return JsonResponse({
        'status': 'success',
        'mpd_id': mpd_id,
        'date': date_str,
        'aircraft_count': len(aircraft_list),
        'aircraft_list': aircraft_list,
        'crews_count': len(crews_data),
        'crews': crews_data,
        'standalone_assignments': standalone_data
    })


@login_required
@require_http_methods(["POST"])
def add_member_to_crew_api(request):
    """
    API добавления сотрудника в существующий экипаж с проверкой занятости на других МПД/экипажах.
    """
    try:
        data = json.loads(request.body)
        crew_id = data.get('crew_id')
        pilot_id = data.get('pilot_id')
        role = data.get('role')
        force_override = data.get('force_override', False)

        if not crew_id or not pilot_id or not role:
            return JsonResponse({'error': 'Не заполнены обязательные параметры (crew_id, pilot_id, role).'}, status=400)

        crew = get_object_or_404(FlightCrew, id=crew_id)
        pilot = get_object_or_404(DataBaseUser, id=pilot_id)

        # Проверка конфликтов занятости
        conflicts = check_crew_member_conflicts(
            mpd_id=crew.mpd_id,
            start_date=crew.date,
            end_date=crew.date,
            members=[{'member_id': int(pilot_id), 'role': role}],
            current_crew_id=crew.id
        )

        if conflicts and not force_override:
            return JsonResponse({
                'status': 'conflict',
                'conflict_type': 'members',
                'conflicts': conflicts,
                'can_override': True,
                'errors': [c['description'] for c in conflicts],
                'error': ' '.join([c['description'] for c in conflicts])
            }, status=409)

        with transaction.atomic():
            # Если сотрудник состоял в другом экипаже на эту дату, удаляем
            old_crews = FlightCrew.objects.filter(
                date=crew.date,
                members__member=pilot
            ).exclude(id=crew.id)
            for oc in old_crews:
                CrewMember.objects.filter(crew=oc, member=pilot).delete()

            CrewMember.objects.update_or_create(
                crew=crew,
                member=pilot,
                defaults={'role': role}
            )
            assignment, created = PilotAssignment.objects.get_or_create(
                pilot=pilot,
                date=crew.date,
                defaults={
                    'mpd': crew.mpd,
                    'crew': crew,
                    'role_in_crew': role,
                    'created_by': request.user
                }
            )
            if not created:
                assignment.mpd = crew.mpd
                assignment.crew = crew
                assignment.role_in_crew = role
                assignment.save()

        return JsonResponse({
            'status': 'success',
            'message': f"Сотрудник {pilot.title or pilot.username} успешно добавлен в экипаж."
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def get_crew_notes_api(request, crew_id: int):
    """
    API получения списка пометок и сообщений к экипажу/полету.
    """
    try:
        crew = FlightCrew.objects.select_related('aircraft', 'mpd').prefetch_related('notes__author', 'members__member').get(id=crew_id)
        today = timezone.now().date()
        min_editable_date = today - timedelta(days=1)
        max_editable_date = today + timedelta(days=1)
        is_date_allowed = (min_editable_date <= crew.date <= max_editable_date)

        # Проверка прав: только назначенный член экипажа (второй пилот/участник) или администратор/диспетчер
        membership = crew.members.filter(member=request.user).first()
        is_crew_member = membership is not None
        is_admin = request.user.is_superuser or request.user.is_staff or request.user.has_perm('flight_planning.change_flightcrew')
        can_user_add_note = is_date_allowed and (is_crew_member or is_admin)

        roles_dict = dict(CREW_ROLES)
        notes_data = [
            {
                'id': n.id,
                'author_id': n.author_id,
                'author_name': n.author.title if (n.author and n.author.title) else (n.author.username if n.author else 'Неизвестно'),
                'author_role': n.author_role,
                'author_role_label': roles_dict.get(n.author_role, n.author_role),
                'message': n.message,
                'created_at': n.created_at.strftime('%d.%m.%Y %H:%M'),
                'created_at_time': n.created_at.strftime('%H:%M'),
                'can_delete': (is_admin or (n.author_id == request.user.id))
            }
            for n in crew.notes.all()
        ]

        # Находим второго пилота (или членов экипажа)
        copilot_member = crew.members.filter(role='copilot').first()
        copilot_name = (copilot_member.member.title or copilot_member.member.username) if copilot_member else ""

        return JsonResponse({
            'status': 'success',
            'crew_id': crew.id,
            'mpd_name': crew.mpd.name,
            'aircraft_number': crew.aircraft.registration_number if crew.aircraft else 'Резерв',
            'date': crew.date.isoformat(),
            'date_formatted': crew.date.strftime('%d.%m.%Y'),
            'copilot_name': copilot_name,
            'is_date_allowed': is_date_allowed,
            'is_crew_member': is_crew_member,
            'is_admin': is_admin,
            'can_user_add_note': can_user_add_note,
            'min_editable_date': min_editable_date.strftime('%d.%m.%Y'),
            'max_editable_date': max_editable_date.strftime('%d.%m.%Y'),
            'notes': notes_data
        })
    except FlightCrew.DoesNotExist:
        return JsonResponse({'error': 'Экипаж не найден.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def save_crew_note_api(request, crew_id: int):
    """
    API добавления пометки к полету.
    Ограничение 1: разрешено только для рейсов на вчера, сегодня и завтра (сегодня +- 1 день).
    Ограничение 2: разрешено только назначенному в этот экипаж сотруднику (второму пилоту / члену экипажа) или администратору.
    """
    try:
        crew = FlightCrew.objects.select_related('aircraft', 'mpd').prefetch_related('members').get(id=crew_id)
        today = timezone.now().date()
        min_editable_date = today - timedelta(days=1)
        max_editable_date = today + timedelta(days=1)

        if not (min_editable_date <= crew.date <= max_editable_date):
            return JsonResponse({
                'error': f'Ввод пометок разрешен только для рейсов на вчера ({min_editable_date.strftime("%d.%m.%Y")}), сегодня ({today.strftime("%d.%m.%Y")}) и завтра ({max_editable_date.strftime("%d.%m.%Y")}).'
            }, status=403)

        # Проверка принадлежности к экипажу
        membership = crew.members.filter(member=request.user).first()
        is_crew_member = membership is not None
        is_admin = request.user.is_superuser or request.user.is_staff or request.user.has_perm('flight_planning.change_flightcrew')

        if not (is_crew_member or is_admin):
            return JsonResponse({
                'error': 'Вы не назначены в данный экипаж. Оставлять пометки к полету разрешено только назначенному второму пилоту (членам экипажа).'
            }, status=403)

        data = json.loads(request.body)
        message = data.get('message', '').strip()
        if not message:
            return JsonResponse({'error': 'Текст пометки не может быть пустым.'}, status=400)

        author_role = membership.role if membership else 'dispatcher'

        note = FlightCrewNote.objects.create(
            crew=crew,
            author=request.user,
            author_role=author_role,
            message=message
        )

        roles_dict = dict(CREW_ROLES)
        return JsonResponse({
            'status': 'success',
            'message': 'Пометка к полету успешно добавлена.',
            'note': {
                'id': note.id,
                'author_id': note.author_id,
                'author_name': note.author.title if (note.author and note.author.title) else (note.author.username if note.author else 'Неизвестно'),
                'author_role': note.author_role,
                'author_role_label': roles_dict.get(note.author_role, note.author_role),
                'message': note.message,
                'created_at': note.created_at.strftime('%d.%m.%Y %H:%M'),
                'created_at_time': note.created_at.strftime('%H:%M'),
                'can_delete': True
            }
        })
    except FlightCrew.DoesNotExist:
        return JsonResponse({'error': 'Экипаж не найден.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def delete_crew_note_api(request, note_id: int):
    """
    API удаления пометки к полету (доступно автору или администратору).
    """
    try:
        note = FlightCrewNote.objects.select_related('crew').get(id=note_id)
        if not (request.user.is_superuser or request.user.is_staff or note.author_id == request.user.id):
            return JsonResponse({'error': 'У вас нет прав на удаление этой пометки.'}, status=403)

        crew_id = note.crew_id
        note.delete()
        remaining_notes_count = FlightCrewNote.objects.filter(crew_id=crew_id).count()

        return JsonResponse({
            'status': 'success',
            'message': 'Пометка удалена.',
            'crew_id': crew_id,
            'remaining_notes_count': remaining_notes_count
        })
    except FlightCrewNote.DoesNotExist:
        return JsonResponse({'error': 'Пометка не найдена.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def personnel_utilization_report_view(request):
    """
    Отображает аналитический отчет по производственной загрузке летного состава
    с распределением по 4 авиационно-кадровым группам:
    1. Оперативный резерв и нераспределенный состав (0%)
    2. Минимальная производственная нагрузка (1–30%)
    3. Штатная производственная загрузка (31–70%)
    4. Интенсивная летная нагрузка (свыше 70%)
    """
    now = timezone.now()
    year = request.GET.get('year', now.year)
    month = request.GET.get('month', now.month)
    job_category = request.GET.get('job_category', '').strip()

    try:
        year = int(year)
        month = int(month)
    except (ValueError, TypeError):
        year = now.year
        month = now.month

    if month < 1:
        month = 1
    elif month > 12:
        month = 12

    # Получаем сгруппированные данные отчета
    report_data = get_personnel_utilization_report_data(year=year, month=month, job_category=job_category or None)

    # Навигация по месяцам
    first_day = datetime(year, month, 1).date()
    prev_month_date = first_day - timedelta(days=1)
    if month == 12:
        next_month_date = datetime(year + 1, 1, 1).date()
    else:
        next_month_date = datetime(year, month + 1, 1).date()

    MONTHS_LIST = [
        (1, 'Январь'), (2, 'Февраль'), (3, 'Март'), (4, 'Апрель'),
        (5, 'Май'), (6, 'Июнь'), (7, 'Июль'), (8, 'Август'),
        (9, 'Сентябрь'), (10, 'Октябрь'), (11, 'Ноябрь'), (12, 'Декабрь')
    ]

    JOB_CATEGORIES = [
        ('', 'Все должности летного состава'),
        ('commander', 'КВС (Командиры воздушных судов)'),
        ('copilot', 'Вторые пилоты'),
        ('instructor', 'Пилоты-инструкторы / Инспекторы'),
        ('flight_engineer', 'Бортмеханики / Бортинженеры'),
    ]

    years_list = list(range(now.year - 2, now.year + 3))

    user_division = ""
    try:
        if hasattr(request.user, 'user_work_profile') and request.user.user_work_profile and request.user.user_work_profile.divisions:
            user_division = request.user.user_work_profile.divisions.name or str(request.user.user_work_profile.divisions)
    except Exception:
        pass

    if not user_division:
        user_division = "Служба планирования и организации полетов"

    context = {
        'report': report_data,
        'year': year,
        'month': month,
        'job_category': job_category,
        'prev_year': prev_month_date.year,
        'prev_month': prev_month_date.month,
        'next_year': next_month_date.year,
        'next_month': next_month_date.month,
        'months_list': MONTHS_LIST,
        'years_list': years_list,
        'job_categories': JOB_CATEGORIES,
        'generation_time': now.strftime('%d.%m.%Y %H:%M'),
        'current_user': request.user,
        'user_division': user_division,
    }

    return render(request, 'flight_planning/utilization_report.html', context)


def generate_basing_excel_response(report_data: dict, company_name: str, user_division: str, author_name: str) -> HttpResponse:
    """
    Генерирует официальный файл Excel (.xlsx) с отчетом «Базирование ВС на дату»
    со строгим табличным оформлением и автоподбором ширины столбцов.
    """
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Базирование {report_data['target_date_short']}"
    ws.views.sheetView[0].showGridLines = True

    # Стили
    company_font = Font(name="Calibri", size=11, bold=True, color="1E293B")
    division_font = Font(name="Calibri", size=10, italic=True, color="475569")
    title_font = Font(name="Calibri", size=14, bold=True, color="0F172A")
    header_font = Font(name="Calibri", size=11, bold=True, color="0F172A")
    data_font = Font(name="Calibri", size=10, color="000000")
    bold_data_font = Font(name="Calibri", size=10, bold=True, color="000000")
    reserve_font = Font(name="Calibri", size=10, bold=True, color="B91C1C")
    footer_font = Font(name="Calibri", size=9, italic=True, color="64748B")

    header_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
    mpd_bg_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    thin_border_side = Side(border_style="thin", color="CBD5E1")
    table_border = Border(
        left=thin_border_side,
        right=thin_border_side,
        top=thin_border_side,
        bottom=thin_border_side
    )
    header_border = Border(
        left=thin_border_side,
        right=thin_border_side,
        top=thin_border_side,
        bottom=Side(border_style="medium", color="475569")
    )

    # 1. Шапка документа
    ws.merge_cells("A1:F1")
    ws["A1"] = company_name
    ws["A1"].font = company_font
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center")

    ws.merge_cells("A2:F2")
    ws["A2"] = user_division
    ws["A2"].font = division_font
    ws["A2"].alignment = Alignment(horizontal="left", vertical="center")

    ws.merge_cells("A4:F4")
    ws["A4"] = f"БАЗИРОВАНИЕ ВС НА {report_data['target_date_formatted']} год"
    ws["A4"].font = title_font
    ws["A4"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[4].height = 28

    # 2. Заголовки колонок
    headers = ["№", "МПД", "Тип ВС", "№", "Дата прибытия", "Примечания"]
    header_row_idx = 6

    for col_idx, h_text in enumerate(headers, start=1):
        cell = ws.cell(row=header_row_idx, column=col_idx, value=h_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = header_border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[header_row_idx].height = 24

    current_row = header_row_idx + 1

    # 3. Данные по МПД
    for group in report_data['mpd_groups']:
        aircrafts = group['aircrafts']

        for i, ac in enumerate(aircrafts):
            is_first = (i == 0)

            # Колонка 1: Порядковый номер МПД
            cell_num = ws.cell(row=current_row, column=1, value=f"{group['index']}." if is_first else "")
            cell_num.font = bold_data_font if is_first else data_font
            cell_num.alignment = Alignment(horizontal="center", vertical="top")
            cell_num.border = table_border
            if is_first:
                cell_num.fill = mpd_bg_fill

            # Колонка 2: Название МПД
            cell_mpd = ws.cell(row=current_row, column=2, value=group['mpd_name'] if is_first else "")
            cell_mpd.font = bold_data_font if is_first else data_font
            cell_mpd.alignment = Alignment(horizontal="left", vertical="top")
            cell_mpd.border = table_border
            if is_first:
                cell_mpd.fill = mpd_bg_fill

            # Колонка 3: Тип ВС
            cell_type = ws.cell(row=current_row, column=3, value=ac['type_name'])
            cell_type.font = data_font
            cell_type.alignment = Alignment(horizontal="center", vertical="center")
            cell_type.border = table_border

            # Колонка 4: Номер ВС
            cell_reg = ws.cell(row=current_row, column=4, value=ac['registration_number'])
            cell_reg.font = bold_data_font
            cell_reg.alignment = Alignment(horizontal="center", vertical="center")
            cell_reg.border = table_border

            # Колонка 5: Дата прибытия
            cell_date = ws.cell(row=current_row, column=5, value=ac['arrival_date_formatted'])
            cell_date.font = data_font
            cell_date.alignment = Alignment(horizontal="center", vertical="center")
            cell_date.border = table_border

            # Колонка 6: Примечания
            cell_comment = ws.cell(row=current_row, column=6, value=ac['comment'])
            cell_comment.font = reserve_font if ac['is_reserve'] else data_font
            cell_comment.alignment = Alignment(horizontal="left", vertical="center")
            cell_comment.border = table_border

            ws.row_dimensions[current_row].height = 20
            current_row += 1

    # 4. Итоговая строка
    current_row += 1
    ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=6)
    type_str = ", ".join([f"{t['type_name']}: {t['count']}" for t in report_data['type_counts']]) if report_data['type_counts'] else "нет данных"
    summary_text = (
        f"ИТОГО: ВС на базировании: {report_data['total_aircrafts']} ед. "
        f"(Задействовано МПД: {report_data['total_mpds']}, В резерве: {report_data['total_reserve']}). "
        f"Распределение по типам: {type_str}"
    )
    cell_summary = ws.cell(row=current_row, column=1, value=summary_text)
    cell_summary.font = bold_data_font
    cell_summary.alignment = Alignment(horizontal="left", vertical="center")

    current_row += 2
    footer_text = (
        f"Составитель: {author_name} ({user_division}) | "
        f"Дата и время формирования: {timezone.now().strftime('%d.%m.%Y %H:%M')}"
    )
    ws.cell(row=current_row, column=1, value=footer_text).font = footer_font

    # Автоматическая настройка ширины колонок
    col_widths = {1: 8, 2: 38, 3: 16, 4: 16, 5: 18, 6: 32}
    for col_idx, width in col_widths.items():
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = width

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    filename = f"basing_aircraft_{report_data['target_date_formatted']}.xlsx"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required
def aircraft_basing_report_view(request):
    """
    Отображает официальный отчет
    «БАЗИРОВАНИЕ ВС НА [Дата] год»
    с группировкой бортов по МПД, указанием типа ВС, номера, даты прибытия и примечаний (в т.ч. Резерв).
    Поддерживает фильтрацию по дате, МПД, типу ВС, печатную форму и выгрузку в Excel.
    """
    date_str = request.GET.get('date', '').strip()
    mpd_id = request.GET.get('mpd', '').strip()
    type_id = request.GET.get('type', '').strip()
    export_format = request.GET.get('export', '').strip().lower()

    # Определение даты среза
    target_date = timezone.now().date()
    if date_str:
        for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d-%m-%Y', '%d/%m/%Y'):
            try:
                target_date = datetime.strptime(date_str, fmt).date()
                break
            except (ValueError, TypeError):
                continue

    try:
        mpd_id_int = int(mpd_id) if mpd_id else None
    except ValueError:
        mpd_id_int = None

    try:
        type_id_int = int(type_id) if type_id else None
    except ValueError:
        type_id_int = None

    # Получаем сгруппированные данные отчета через селектор
    report_data = get_aircraft_basing_report_data(
        target_date=target_date,
        mpd_id=mpd_id_int,
        aircraft_type_id=type_id_int
    )

    # Определение подразделения пользователя
    user_division = ""
    try:
        if hasattr(request.user, 'user_work_profile') and request.user.user_work_profile and request.user.user_work_profile.divisions:
            user_division = request.user.user_work_profile.divisions.name or str(request.user.user_work_profile.divisions)
    except Exception:
        pass

    if not user_division:
        user_division = "Служба планирования и организации полетов"

    author_name = (
        request.user.title
        if (hasattr(request.user, 'title') and request.user.title)
        else (request.user.get_full_name() or request.user.username)
    )
    company_name = "ООО «Авиакомпания «БАРКОЛ»"

    # Экспорт в Excel при наличии параметра ?export=excel
    if export_format == 'excel':
        return generate_basing_excel_response(
            report_data=report_data,
            company_name=company_name,
            user_division=user_division,
            author_name=author_name
        )

    # Справочники для фильтрации
    mpds_list = PlaceProductionActivity.objects.filter(in_planning=True).order_by('name')
    types_list = TypeProperty.objects.filter(estate__isnull=False).distinct().order_by('type_property')

    prev_date = target_date - timedelta(days=1)
    next_date = target_date + timedelta(days=1)

    context = {
        'report': report_data,
        'target_date': target_date,
        'target_date_str': target_date.strftime('%Y-%m-%d'),
        'target_date_formatted': target_date.strftime('%d.%m.%Y'),
        'target_date_short': target_date.strftime('%d.%m.%y'),
        'prev_date_str': prev_date.strftime('%Y-%m-%d'),
        'next_date_str': next_date.strftime('%Y-%m-%d'),
        'mpds_list': mpds_list,
        'types_list': types_list,
        'selected_mpd_id': mpd_id_int,
        'selected_type_id': type_id_int,
        'user_division': user_division,
        'author_name': author_name,
        'company_name': company_name,
        'generation_time': timezone.now().strftime('%d.%m.%Y %H:%M'),
        'title': f"Базирование ВС на {target_date.strftime('%d.%m.%Y')} год",
    }

    return render(request, 'flight_planning/aircraft_basing_report.html', context)





