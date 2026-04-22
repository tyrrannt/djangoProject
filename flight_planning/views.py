# flight_planning/views.py
import json
from datetime import datetime, timedelta

from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import transaction
from django.contrib.auth.decorators import login_required

from customers_app.models import DataBaseUser
from hrdepartment_app.models import PlaceProductionActivity
from .models import PilotAssignment

# Вариант 2: Точное совпадение с названиями должностей
ALLOWED_JOBS = ['командир', 'пилот', 'бортмеханик', 'Командир', 'Бортмеханик', 'инструктор']

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
    ).filter(q_conditions).order_by('last_name', 'first_name').distinct()

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

    # Загружаем существующие назначения за месяц
    assignments = PilotAssignment.objects.filter(
        date__year=year,
        date__month=month
    ).select_related('pilot', 'mpd')

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
        try:
            # Проверяем наличие user_work_profile и job
            if hasattr(a.pilot, 'user_work_profile') and a.pilot.user_work_profile:
                if hasattr(a.pilot.user_work_profile, 'job') and a.pilot.user_work_profile.job:
                    job_name = a.pilot.user_work_profile.job.name
                    is_commander = job_name and 'командир' in job_name.lower()
        except Exception as e:
            print(f"Error getting job info for pilot {a.pilot_id}: {e}")

        assignment_map[mpd_id][date_str].append({
            'pilot_id': a.pilot_id,
            'pilot_name': a.pilot.title or a.pilot.username,
            'pilot_job': job_name or 'Должность не указана',
            'is_commander': is_commander,
            'assignment_id': a.id
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
        'assignment_map': assignment_map,
        'prev_year': prev_month_date.year,
        'prev_month': prev_month_date.month,
        'next_year': next_month_date.year,
        'next_month': next_month_date.month,
        'month_name': first_day.strftime('%B %Y'),
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
        try:
            if hasattr(pilot, 'user_work_profile') and pilot.user_work_profile:
                if hasattr(pilot.user_work_profile, 'job') and pilot.user_work_profile.job:
                    job_name = pilot.user_work_profile.job.name
                    is_commander = job_name and 'командир' in job_name.lower()
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
            'is_commander': is_commander
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
    Получить должность пилота и статус командира
    """
    pilot_id = request.GET.get('pilot_id')
    if not pilot_id:
        return JsonResponse({'error': 'pilot_id required'}, status=400)

    try:
        pilot = get_object_or_404(DataBaseUser, id=pilot_id)
        job_name = None
        is_commander = False

        if hasattr(pilot, 'user_work_profile') and pilot.user_work_profile:
            if pilot.user_work_profile.job:
                job_name = pilot.user_work_profile.job.name
                is_commander = job_name and 'командир' in job_name.lower()

        return JsonResponse({
            'job_name': job_name or 'Должность не указана',
            'is_commander': is_commander
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)