"""Сервисный слой аналитики, отчетов по исполнительской дисциплине и экспорта в Excel.

Модуль агрегирует данные об эффективности выполнения задач сотрудниками и подразделениями
авиакомпании, вычисляет индекс дисциплины (% выполнения в срок, просрочки, среднее время закрытия)
и формирует оформленные отчеты Microsoft Excel (.xlsx) по корпоративному стандарту ООО «Авиакомпания «БАРКОЛ».
"""

import datetime
import io
import logging
from typing import Any, Dict, List, Optional

from django.db.models import Count, Q, QuerySet
from django.utils import timezone
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from customers_app.models import DataBaseUser, Division
from tasks_app.models import Task, TaskRole, TaskStatus

logger = logging.getLogger(__name__)


class ReportService:
    """Сервис аналитики и формирования отчетов по исполнительской дисциплине."""

    @staticmethod
    def get_discipline_report_data(
        date_from: Optional[datetime.date] = None,
        date_to: Optional[datetime.date] = None,
        division_id: Optional[int] = None,
        employee_id: Optional[int] = None,
        current_user: Optional[DataBaseUser] = None
    ) -> Dict[str, Any]:
        """Формирует структурированные агрегированные данные для отчета по дисциплине.

        Args:
            date_from (Optional[datetime.date]): Начальная дата периода выборки.
            date_to (Optional[datetime.date]): Конечная дата периода выборки.
            division_id (Optional[int]): Первичный ключ подразделения для фильтрации.
            employee_id (Optional[int]): Первичный ключ сотрудника для фильтрации.
            current_user (Optional[DataBaseUser]): Текущий пользователь, формирующий отчет.

        Returns:
            Dict[str, Any]: Словарь со сводными KPI, статистикой по подразделениям,
                статистикой по сотрудникам и списком задач.
        """
        now = timezone.now()
        today = now.date()

        # Период по умолчанию — текущий месяц
        if not date_from:
            date_from = today.replace(day=1)
        if not date_to:
            # Конец текущего месяца
            next_month = (date_from.replace(day=28) + datetime.timedelta(days=4))
            date_to = next_month - datetime.timedelta(days=next_month.day)

        # Границы дат со временем для точной фильтрации
        tz = timezone.get_current_timezone()
        dt_start = timezone.make_aware(datetime.datetime.combine(date_from, datetime.time.min), tz)
        dt_end = timezone.make_aware(datetime.datetime.combine(date_to, datetime.time.max), tz)

        # Базовый QuerySet задач за период
        qs = Task.objects.filter(
            Q(created_at__range=(dt_start, dt_end)) |
            Q(end_date__range=(dt_start, dt_end)) |
            Q(completed_at__range=(dt_start, dt_end))
        ).distinct()

        # Фильтрация по подразделению
        if division_id:
            qs = qs.filter(
                Q(user__user_work_profile__divisions_id=division_id) |
                Q(responsible__user_work_profile__divisions_id=division_id) |
                Q(assignees__user_work_profile__divisions_id=division_id)
            ).distinct()

        # Фильтрация по конкретному сотруднику
        if employee_id:
            qs = qs.filter(
                Q(responsible_id=employee_id) |
                Q(assignees__id=employee_id) |
                Q(user_id=employee_id)
            ).distinct()

        tasks = list(qs.select_related(
            'user', 'responsible', 'category', 'eds_signed_by',
            'responsible__user_work_profile__divisions',
            'responsible__user_work_profile__job',
            'user__user_work_profile__divisions'
        ).prefetch_related('assignees', 'subtasks', 'files'))

        # Подсчет сводных показателей
        total_count = len(tasks)
        completed_on_time_count = 0
        completed_overdue_count = 0
        in_progress_count = 0
        active_overdue_count = 0
        eds_signed_count = 0
        total_completion_hours = 0.0
        closed_tasks_with_duration = 0

        detailed_tasks = []

        for task in tasks:
            is_completed = task.status == TaskStatus.COMPLETED or task.completed
            is_overdue = False
            delay_days = 0
            timeliness_status = 'В работе'

            if task.eds_signature:
                eds_signed_count += 1

            if is_completed:
                if task.completed_at and task.end_date and task.completed_at > task.end_date:
                    is_overdue = True
                    completed_overdue_count += 1
                    delay = task.completed_at - task.end_date
                    delay_days = max(1, delay.days)
                    timeliness_status = f'Закрыта с опозданием на {delay_days} дн.'
                else:
                    completed_on_time_count += 1
                    timeliness_status = 'Выполнена в срок'

                if task.completed_at and task.created_at:
                    duration = (task.completed_at - task.created_at).total_seconds() / 3600.0
                    if duration > 0:
                        total_completion_hours += duration
                        closed_tasks_with_duration += 1
            else:
                if task.end_date and task.end_date < now:
                    is_overdue = True
                    active_overdue_count += 1
                    delay = now - task.end_date
                    delay_days = max(1, delay.days)
                    timeliness_status = f'Просрочена на {delay_days} дн.'
                else:
                    in_progress_count += 1
                    timeliness_status = 'В процессе исполнения'

            detailed_tasks.append({
                'task': task,
                'is_completed': is_completed,
                'is_overdue': is_overdue,
                'delay_days': delay_days,
                'timeliness_status': timeliness_status,
                'has_eds': bool(task.eds_signature),
            })

        # Индекс исполнительской дисциплины компании
        # (выполненные вовремя) / (всего закрытых + текущих просроченных) * 100
        closed_and_overdue = completed_on_time_count + completed_overdue_count + active_overdue_count
        if closed_and_overdue > 0:
            discipline_rate = round((completed_on_time_count / closed_and_overdue) * 100.0, 1)
        else:
            discipline_rate = 100.0 if total_count > 0 else 0.0

        avg_completion_days = 0.0
        if closed_tasks_with_duration > 0:
            avg_completion_days = round((total_completion_hours / closed_tasks_with_duration) / 24.0, 1)

        # 2. Агрегация по подразделениям
        division_map: Dict[Any, Dict[str, Any]] = {}
        all_divisions = Division.objects.all().order_by('name')
        for div in all_divisions:
            division_map[div.id] = {
                'id': div.id,
                'name': div.name,
                'total': 0,
                'completed_on_time': 0,
                'completed_overdue': 0,
                'in_progress': 0,
                'active_overdue': 0,
                'eds_count': 0,
            }

        # Специальный бакет для задач без подразделения
        division_map[None] = {
            'id': None,
            'name': 'Без подразделения / Прочие',
            'total': 0,
            'completed_on_time': 0,
            'completed_overdue': 0,
            'in_progress': 0,
            'active_overdue': 0,
            'eds_count': 0,
        }

        # 3. Агрегация по сотрудникам (ответственным и исполнителям)
        employee_map: Dict[int, Dict[str, Any]] = {}

        for item in detailed_tasks:
            t: Task = item['task']
            resp = t.responsible or t.user
            div_id = None
            if resp and hasattr(resp, 'user_work_profile') and resp.user_work_profile and resp.user_work_profile.divisions:
                div_id = resp.user_work_profile.divisions.id

            if div_id in division_map:
                div_bucket = division_map[div_id]
            else:
                div_bucket = division_map[None]

            div_bucket['total'] += 1
            if item['is_completed']:
                if item['is_overdue']:
                    div_bucket['completed_overdue'] += 1
                else:
                    div_bucket['completed_on_time'] += 1
            else:
                if item['is_overdue']:
                    div_bucket['active_overdue'] += 1
                else:
                    div_bucket['in_progress'] += 1

            if item['has_eds']:
                div_bucket['eds_count'] += 1

            # Для сотрудника
            if resp:
                emp_id = resp.id
                if emp_id not in employee_map:
                    job_title = 'Сотрудник'
                    div_name = '—'
                    if hasattr(resp, 'user_work_profile') and resp.user_work_profile:
                        if resp.user_work_profile.job:
                            job_title = resp.user_work_profile.job.name
                        if resp.user_work_profile.divisions:
                            div_name = resp.user_work_profile.divisions.name

                    employee_map[emp_id] = {
                        'user': resp,
                        'full_name': getattr(resp, 'title', None) or resp.get_full_name() or resp.username,
                        'job_title': job_title,
                        'division_name': div_name,
                        'total': 0,
                        'completed_on_time': 0,
                        'completed_overdue': 0,
                        'in_progress': 0,
                        'active_overdue': 0,
                        'eds_count': 0,
                    }

                emp_bucket = employee_map[emp_id]
                emp_bucket['total'] += 1
                if item['is_completed']:
                    if item['is_overdue']:
                        emp_bucket['completed_overdue'] += 1
                    else:
                        emp_bucket['completed_on_time'] += 1
                else:
                    if item['is_overdue']:
                        emp_bucket['active_overdue'] += 1
                    else:
                        emp_bucket['in_progress'] += 1

                if item['has_eds']:
                    emp_bucket['eds_count'] += 1

        # Формируем список статистики подразделений с расчетом %
        division_stats = []
        for div_id, d in division_map.items():
            if d['total'] > 0:
                sub_closed_overdue = d['completed_on_time'] + d['completed_overdue'] + d['active_overdue']
                if sub_closed_overdue > 0:
                    d_rate = round((d['completed_on_time'] / sub_closed_overdue) * 100.0, 1)
                else:
                    d_rate = 100.0
                d['discipline_rate'] = d_rate
                division_stats.append(d)

        division_stats.sort(key=lambda x: x['total'], reverse=True)

        # Формируем список статистики сотрудников с расчетом % и рейтинга
        employee_stats = []
        for emp_id, emp in employee_map.items():
            sub_closed_overdue = emp['completed_on_time'] + emp['completed_overdue'] + emp['active_overdue']
            if sub_closed_overdue > 0:
                e_rate = round((emp['completed_on_time'] / sub_closed_overdue) * 100.0, 1)
            else:
                e_rate = 100.0
            emp['discipline_rate'] = e_rate

            if e_rate >= 90.0:
                emp['badge_class'] = 'success'
                emp['grade'] = 'Отлично'
            elif e_rate >= 70.0:
                emp['badge_class'] = 'warning text-dark'
                emp['grade'] = 'Удовлетворительно'
            else:
                emp['badge_class'] = 'danger'
                emp['grade'] = 'Низкая дисциплина'

            employee_stats.append(emp)

        employee_stats.sort(key=lambda x: (x['discipline_rate'], x['total']), reverse=True)

        return {
            'date_from': date_from,
            'date_to': date_to,
            'selected_division_id': division_id,
            'selected_employee_id': employee_id,
            'total_count': total_count,
            'completed_on_time_count': completed_on_time_count,
            'completed_overdue_count': completed_overdue_count,
            'in_progress_count': in_progress_count,
            'active_overdue_count': active_overdue_count,
            'eds_signed_count': eds_signed_count,
            'discipline_rate': discipline_rate,
            'avg_completion_days': avg_completion_days,
            'division_stats': division_stats,
            'employee_stats': employee_stats,
            'detailed_tasks': detailed_tasks,
            'generated_at': now,
        }

    @staticmethod
    def generate_discipline_report_excel(report_data: Dict[str, Any]) -> openpyxl.Workbook:
        """Создает стилизованную книгу Excel (.xlsx) с отчетом по дисциплине.

        Книга содержит 3 листа:
        1. Сводные показатели и подразделения;
        2. Исполнительская дисциплина сотрудников;
        3. Детальный реестр поручений.

        Args:
            report_data (Dict[str, Any]): Результат выполнения get_discipline_report_data.

        Returns:
            openpyxl.Workbook: Сформированная рабочая книга Excel.
        """
        wb = openpyxl.Workbook()
        # Лист 1: Сводная информация
        ws_summary = wb.active
        ws_summary.title = "Сводный отчет"
        ws_summary.views.sheetView[0].showGridLines = True

        # Стили
        font_title = Font(name="Calibri", size=13, bold=True, color="1A3A5C")
        font_subtitle = Font(name="Calibri", size=10, italic=True, color="475569")
        font_section = Font(name="Calibri", size=11, bold=True, color="1E293B")
        font_header = Font(name="Calibri", size=9.5, bold=True, color="FFFFFF")
        font_bold = Font(name="Calibri", size=9.5, bold=True, color="000000")
        font_regular = Font(name="Calibri", size=9.5, color="1E293B")
        font_kpi_val = Font(name="Calibri", size=14, bold=True, color="1A3A5C")

        fill_header = PatternFill(start_color="1A3A5C", end_color="1A3A5C", fill_type="solid")
        fill_subhdr = PatternFill(start_color="2C5282", end_color="2C5282", fill_type="solid")
        fill_kpi_card = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
        fill_zebra = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        fill_success = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        fill_danger = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")

        border_thin = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1")
        )

        align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        align_left = Alignment(horizontal="left", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")

        # 1. Шапка документа
        ws_summary.merge_cells("A1:G1")
        ws_summary["A1"] = "ООО «АВИАКОМПАНИЯ «БАРКОЛ»"
        ws_summary["A1"].font = font_subtitle
        ws_summary["A1"].alignment = align_center

        ws_summary.merge_cells("A2:G2")
        ws_summary["A2"] = "ОТЧЕТ ПО ИСПОЛНИТЕЛЬСКОЙ ДИСЦИПЛИНЕ И КОНТРОЛЮ ПОРУЧЕНИЙ"
        ws_summary["A2"].font = font_title
        ws_summary["A2"].alignment = align_center

        d_from_str = report_data['date_from'].strftime('%d.%m.%Y')
        d_to_str = report_data['date_to'].strftime('%d.%m.%Y')
        gen_at_str = report_data['generated_at'].strftime('%d.%m.%Y %H:%M')

        ws_summary.merge_cells("A3:G3")
        ws_summary["A3"] = f"Период анализа: {d_from_str} — {d_to_str} | Сформирован: {gen_at_str}"
        ws_summary["A3"].font = font_subtitle
        ws_summary["A3"].alignment = align_center

        # 2. Блок KPI карточек
        kpis = [
            ("Всего поручений", report_data['total_count']),
            ("Выполнено в срок", report_data['completed_on_time_count']),
            ("Закрыто с просрочкой", report_data['completed_overdue_count']),
            ("В работе", report_data['in_progress_count']),
            ("Текущие просрочки", report_data['active_overdue_count']),
            ("С ЭЦП визированием", report_data['eds_signed_count']),
            ("Индекс дисциплины", f"{report_data['discipline_rate']}%"),
        ]

        row = 5
        ws_summary.row_dimensions[row].height = 24
        ws_summary.row_dimensions[row + 1].height = 28

        for col_idx, (kpi_title, kpi_val) in enumerate(kpis, start=1):
            c_title = ws_summary.cell(row=row, column=col_idx, value=kpi_title)
            c_title.font = font_bold
            c_title.alignment = align_center
            c_title.fill = fill_kpi_card
            c_title.border = border_thin

            c_val = ws_summary.cell(row=row + 1, column=col_idx, value=kpi_val)
            c_val.font = font_kpi_val
            c_val.alignment = align_center
            c_val.fill = fill_kpi_card
            c_val.border = border_thin

        # 3. Таблица по подразделениям
        row = 8
        ws_summary.cell(row=row, column=1, value="Анализ исполнительской дисциплины по подразделениям").font = font_section
        row += 1

        headers_div = [
            "№", "Наименование подразделения", "Всего задач", "Выполнено в срок",
            "С опозданием", "В работе", "Текущие просрочки", "Индекс дисциплины %"
        ]

        ws_summary.row_dimensions[row].height = 25
        for c_idx, h_text in enumerate(headers_div, start=1):
            cell = ws_summary.cell(row=row, column=c_idx, value=h_text)
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = align_center
            cell.border = border_thin

        for idx, div in enumerate(report_data['division_stats'], start=1):
            row += 1
            ws_summary.row_dimensions[row].height = 20
            is_even = (idx % 2 == 0)
            row_fill = fill_zebra if is_even else None

            cells_data = [
                (idx, align_center),
                (div['name'], align_left),
                (div['total'], align_center),
                (div['completed_on_time'], align_center),
                (div['completed_overdue'], align_center),
                (div['in_progress'], align_center),
                (div['active_overdue'], align_center),
                (f"{div['discipline_rate']}%", align_center),
            ]

            for c_idx, (val, aln) in enumerate(cells_data, start=1):
                cell = ws_summary.cell(row=row, column=c_idx, value=val)
                cell.font = font_regular
                cell.alignment = aln
                cell.border = border_thin
                if row_fill:
                    cell.fill = row_fill

                # Выделение % дисциплины
                if c_idx == 8:
                    if div['discipline_rate'] >= 90:
                        cell.fill = fill_success
                    elif div['discipline_rate'] < 70:
                        cell.fill = fill_danger

        # Лист 2: Статистика по сотрудникам
        ws_emp = wb.create_sheet(title="Сотрудники")
        ws_emp.views.sheetView[0].showGridLines = True

        ws_emp.merge_cells("A1:I1")
        ws_emp["A1"] = "РЕЙТИНГ ИСПОЛНИТЕЛЬСКОЙ ДИСЦИПЛИНЫ СОТРУДНИКОВ"
        ws_emp["A1"].font = font_title
        ws_emp["A1"].alignment = align_center

        row = 3
        headers_emp = [
            "№", "ФИО сотрудника", "Должность", "Подразделение", "Всего поручений",
            "В срок", "С просрочкой", "В работе", "Текущие просрочки", "Индекс дисциплины %", "Оценка"
        ]

        ws_emp.row_dimensions[row].height = 25
        for c_idx, h_text in enumerate(headers_emp, start=1):
            cell = ws_emp.cell(row=row, column=c_idx, value=h_text)
            cell.font = font_header
            cell.fill = fill_subhdr
            cell.alignment = align_center
            cell.border = border_thin

        for idx, emp in enumerate(report_data['employee_stats'], start=1):
            row += 1
            ws_emp.row_dimensions[row].height = 20
            is_even = (idx % 2 == 0)
            row_fill = fill_zebra if is_even else None

            cells_data = [
                (idx, align_center),
                (emp['full_name'], align_left),
                (emp['job_title'], align_left),
                (emp['division_name'], align_left),
                (emp['total'], align_center),
                (emp['completed_on_time'], align_center),
                (emp['completed_overdue'], align_center),
                (emp['in_progress'], align_center),
                (emp['active_overdue'], align_center),
                (f"{emp['discipline_rate']}%", align_center),
                (emp['grade'], align_center),
            ]

            for c_idx, (val, aln) in enumerate(cells_data, start=1):
                cell = ws_emp.cell(row=row, column=c_idx, value=val)
                cell.font = font_regular
                cell.alignment = aln
                cell.border = border_thin
                if row_fill:
                    cell.fill = row_fill

                if c_idx == 10:
                    if emp['discipline_rate'] >= 90:
                        cell.fill = fill_success
                    elif emp['discipline_rate'] < 70:
                        cell.fill = fill_danger

        # Лист 3: Детальный реестр поручений
        ws_tasks = wb.create_sheet(title="Реестр поручений")
        ws_tasks.views.sheetView[0].showGridLines = True

        ws_tasks.merge_cells("A1:K1")
        ws_tasks["A1"] = "РЕЕСТР ПОРУЧЕНИЙ ЗА АНАЛИЗИРУЕМЫЙ ПЕРИОД"
        ws_tasks["A1"].font = font_title
        ws_tasks["A1"].alignment = align_center

        row = 3
        headers_tasks = [
            "№ п/п", "ID", "Наименование поручения", "Постановщик (Автор)", "Ответственный исполнитель",
            "Приоритет", "Текущий статус", "Плановый срок (дедлайн)", "Фактическое закрытие", "ЭЦП", "Результат исполнения"
        ]

        ws_tasks.row_dimensions[row].height = 25
        for c_idx, h_text in enumerate(headers_tasks, start=1):
            cell = ws_tasks.cell(row=row, column=c_idx, value=h_text)
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = align_center
            cell.border = border_thin

        for idx, item in enumerate(report_data['detailed_tasks'], start=1):
            t: Task = item['task']
            row += 1
            ws_tasks.row_dimensions[row].height = 20
            is_even = (idx % 2 == 0)
            row_fill = fill_zebra if is_even else None

            author_name = getattr(t.user, 'title', None) or (t.user.get_full_name() if t.user else '—')
            resp_name = getattr(t.responsible, 'title', None) or (t.responsible.get_full_name() if t.responsible else '—')
            end_date_str = t.end_date.strftime('%d.%m.%Y %H:%M') if t.end_date else '—'
            comp_date_str = t.completed_at.strftime('%d.%m.%Y %H:%M') if t.completed_at else '—'
            eds_str = "Да (КЭП)" if item['has_eds'] else ("Требуется" if t.requires_eds else "Нет")

            cells_data = [
                (idx, align_center),
                (t.id, align_center),
                (t.title, align_left),
                (author_name, align_left),
                (resp_name, align_left),
                (t.get_priority_display(), align_center),
                (t.get_status_display(), align_center),
                (end_date_str, align_center),
                (comp_date_str, align_center),
                (eds_str, align_center),
                (item['timeliness_status'], align_left),
            ]

            for c_idx, (val, aln) in enumerate(cells_data, start=1):
                cell = ws_tasks.cell(row=row, column=c_idx, value=val)
                cell.font = font_regular
                cell.alignment = aln
                cell.border = border_thin
                if row_fill:
                    cell.fill = row_fill

                if c_idx == 11:
                    if "Выполнена в срок" in str(val):
                        cell.fill = fill_success
                    elif "опозданием" in str(val) or "Просрочена" in str(val):
                        cell.fill = fill_danger

        # Автоматическая подгонка ширины столбцов и freeze_panes для всех листов
        for ws in [ws_summary, ws_emp, ws_tasks]:
            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    # Пропускаем объединенные ячейки в шапке
                    if cell.row in [1, 2, 3] and ws.title in ["Сводный отчет", "Сотрудники", "Реестр поручений"]:
                        continue
                    if cell.value:
                        val_str = str(cell.value)
                        max_len = max(max_len, len(val_str))
                ws.column_dimensions[col_letter].width = max(max_len + 3, 11)

        ws_summary.freeze_panes = "A10"
        ws_emp.freeze_panes = "A4"
        ws_tasks.freeze_panes = "A4"

        return wb
