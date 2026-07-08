# customers_app/api_views.py
import hashlib
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone
from .models import DataBaseUser
from .customers_util import get_settlement_sheet, get_jsons, camel_case_to_text, get_chart_of_calculation_types, get_worked_out_by_the_workers
import datetime
from core import logger
from rest_framework.exceptions import ValidationError
from hrdepartment_app.models import ReportCard

class PayrollAPIView(APIView):
    """
    API View to get payroll (settlement sheet) data.
    Requires year, month and passphrase.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        year = request.data.get('year')
        month = request.data.get('month')
        passphrase = request.data.get('passphrase', '')

        if not year or not month:
            return Response({'error': 'Year and month are required'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate passphrase
        hash_pass = hashlib.sha256(passphrase.encode()).hexdigest()
        hash_null = hashlib.sha256(''.encode()).hexdigest()
        
        if hash_pass != request.user.passphrase or hash_pass == hash_null:
            return Response({'error': 'Invalid passphrase'}, status=status.HTTP_403_FORBIDDEN)

        try:
            if len(str(month)) == 1:
                month = '0' + str(month)
            
            # We want structured data, not HTML.
            # I will implement a structured version of get_settlement_sheet logic here or as a new utility.
            data = self.get_structured_payroll(str(month), str(year), request.user.person_ref_key)
            return Response(data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_structured_payroll(self, selected_month, selected_year, users_uuid):
        # Implementation based on get_settlement_sheet but returning dict
        # This is a bit redundant but ensures we get clean data for mobile
        
        acc_reg_acc = get_jsons(
            f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/AccumulationRegister_НачисленияУдержанияПоСотрудникам_RecordType?$format=application/json;odata=nometadata&$filter=ФизическоеЛицо_Key%20eq%20guid%27{users_uuid}%27%20and%20Period%20eq%20datetime%27{selected_year}-{selected_month}-01T00:00:00%27",
            0,
        )
        acc_reg_set = get_jsons(
            f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/AccumulationRegister_ВзаиморасчетыССотрудниками_RecordType?$format=application/json;odata=nometadata&$filter=ФизическоеЛицо_Key%20eq%20guid%27{users_uuid}%27%20and%20Period%20eq%20datetime%27{selected_year}-{selected_month}-01T00:00:00%27%20and%20ГруппаНачисленияУдержанияВыплаты%20eq%20%27Выплачено%27",
            0,
        )

        acc_reg_date = {"value": []}
        if len(acc_reg_set.get('value', [])) > 0:
            ref_keys = [item['Recorder'] for item in acc_reg_set['value']]
            filter_param = " or ".join(f"Ref_Key eq guid'{key}'" for key in ref_keys)
            acc_reg_date = get_jsons(
                f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/Document_ВедомостьНаВыплатуЗарплатыВБанк?$filter={filter_param}&$format=json",
                0)

        period = datetime.datetime.strptime(f"{selected_year}-{selected_month}-01", "%Y-%m-%d")
        
        accrued_items = []
        withheld_items = []
        paid_items = []
        total_accrued = 0.0
        total_withheld = 0.0
        total_paid = 0.0

        for items in acc_reg_acc.get("value", []):
            if period == datetime.datetime.strptime(items["Period"][:10], "%Y-%m-%d") and items["Active"]:
                work_time = get_worked_out_by_the_workers(selected_month, selected_year, users_uuid, items["НачислениеУдержание"])
                
                amount = float(items.get("Сумма", 0))
                if items["ГруппаНачисленияУдержанияВыплаты"] == "Начислено":
                    accrued_items.append({
                        "description": get_chart_of_calculation_types(items["НачислениеУдержание"]),
                        "days_worked": work_time[0] if work_time[0] != 0 else 0,
                        "hours_worked": work_time[1] if work_time[1] != 0 else 0,
                        "paid_days": work_time[2] if work_time[2] != 0 else 0,
                        "amount": amount
                    })
                    total_accrued += amount
                else:
                    withheld_items.append({
                        "description": items["НачислениеУдержание"],
                        "amount": amount
                    })
                    total_withheld += amount

        for items in acc_reg_set.get("value", []):
            item_data = {
                "document": camel_case_to_text(items["ВидВзаиморасчетов"]),
                "amount": float(items.get("СуммаВзаиморасчетов", 0)),
            }
            for date_item in acc_reg_date.get("value", []):
                if items["Recorder"] == date_item["Ref_Key"]:
                    item_data['date'] = date_item.get('Date')
                    item_data['number'] = date_item.get('Number')
                    item_data['reason'] = date_item.get('Основания')
            
            paid_items.append(item_data)
            total_paid += item_data["amount"]

        return {
            "accrued": {"items": accrued_items, "total": total_accrued},
            "withheld": {"items": withheld_items, "total": total_withheld},
            "paid": {"items": paid_items, "total": total_paid},
            "currency": "RUB"
        }

class UserProfileAPIView(APIView):
    """
    API View to get basic user profile info.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            user = request.user
            
            # Безопасное получение аватара
            avatar_url = None
            if user.avatar:
                try:
                    avatar_url = request.build_absolute_uri(user.avatar.url)
                except Exception as e:
                    logger.debug(f"Error building avatar URL: {e}")

            # Безопасное получение должности и подразделения
            job_name = None
            division_name = None
            
            work_profile = getattr(user, 'user_work_profile', None)
            if work_profile:
                if work_profile.job:
                    job_name = work_profile.job.name
                if work_profile.divisions:
                    division_name = work_profile.divisions.name

            experience = ""
            if work_profile and getattr(work_profile, 'date_of_employment', None):
                try:
                    from administration_app.utils import get_today_data_delta
                    experience = get_today_data_delta(work_profile.date_of_employment, 0)
                except Exception as e:
                    pass

            # Check finance access
            has_finance_access = False
            if user.is_superuser:
                has_finance_access = True
            elif user.groups.filter(name__icontains='руковод').exists():
                has_finance_access = True
            elif work_profile and work_profile.divisions and work_profile.divisions.type_of_role == "3":
                has_finance_access = True

            data = {
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "surname": user.surname or "",
                "email": user.email or "",
                "avatar": avatar_url,
                "job": job_name,
                "division": division_name,
                "has_finance_access": has_finance_access,
                "work_email_password": work_profile.work_email_password if work_profile else "",
                "experience": experience,
            }
            return Response(data)
        except Exception as e:
            logger.error(f"Error in UserProfileAPIView: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from hrdepartment_app.hrdepartment_util import get_working_hours
from hrdepartment_app.models import get_norm_time_at_custom_day
import math

def format_seconds_to_hhmm(seconds):
    try:
        sec = float(seconds)
        if sec < 0:
            sec = abs(sec)
            sign = "-"
        else:
            sign = ""
        hours = math.floor(sec / 3600)
        minutes = math.floor((sec % 3600) / 60)
        return f"{sign}{int(hours):02d}:{int(minutes):02d}"
    except (ValueError, TypeError):
        return "00:00"

def get_status_full_name(code):
    mapping = {
        "Я": "Явка",
        "СП": "Служебная поездка",
        "К": "Командировка",
        "О": "Отпуск",
        "Б": "Больничный",
        "М": "Мед осмотр",
        "В": "Выходной",
        "П": "Праздник",
        "ГО": "Гос. обязанности"
    }
    return mapping.get(str(code), str(code))

class WorkTimeAPIView(APIView):
    """
    API View to get working hours data for a specific year and month.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        year = request.data.get('year')
        month = request.data.get('month')

        if not year or not month:
            return Response({'error': 'Year and month are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report_date = datetime.datetime(year=int(year), month=int(month), day=1)
            data_dict, total_score, first_day, last_day, user_start, user_end = get_working_hours(
                request.user.pk, report_date
            )

            daily_stats = {}
            for key, rows in data_dict.items():
                for row in rows:
                    if len(row) < 12: continue
                    r1, r2, r3, r4, r5, r6, r7, r8, r9, r10, r11, r12 = row[:12]
                    
                    if r1 <= datetime.datetime.today().date():
                        if r1 not in daily_stats:
                            daily_stats[r1] = {
                                'fact_start': r2,
                                'fact_end': r3,
                                'statuses': [r8] if r8 else [],
                                'time_worked': float(r11) if r11 else 0.0,
                            }
                        else:
                            daily_stats[r1]['time_worked'] += float(r11) if r11 else 0.0
                            if r8:
                                daily_stats[r1]['statuses'].append(r8)

            days_list = []
            total_delta_score = 0
            
            for d in sorted(daily_stats.keys()):
                stats = daily_stats[d]
                norm_time = get_norm_time_at_custom_day(d)
                
                fact_start_str = stats['fact_start'].strftime('%H:%M') if stats['fact_start'] and hasattr(stats['fact_start'], 'strftime') else str(stats['fact_start']) if stats['fact_start'] else None
                fact_end_str = stats['fact_end'].strftime('%H:%M') if stats['fact_end'] and hasattr(stats['fact_end'], 'strftime') else str(stats['fact_end']) if stats['fact_end'] else None
                
                is_current_day = (d == datetime.datetime.today().date())
                missing_time = not fact_start_str or not fact_end_str or fact_end_str == 'по н.в.' or fact_end_str == '00:00'
                
                is_vacation = 'О' in stats['statuses']
                is_sick_or_trip = any(s in stats['statuses'] for s in ['Б', 'М', 'СП', 'К'])
                
                if is_current_day and missing_time:
                    total_day_time_str = "Актуализация итогов"
                    sign_str = ""
                else:
                    if is_vacation:
                        delta_time = stats['time_worked']
                    elif is_sick_or_trip:
                        delta_time = 0
                    else:
                        delta_time = stats['time_worked'] - norm_time
                        
                    total_delta_score += delta_time
                    sign_str = "-" if delta_time < 0 else ""
                    total_day_time_str = format_seconds_to_hhmm(delta_time)
                
                # Format statuses
                unique_statuses = []
                for st in stats['statuses']:
                    if st not in unique_statuses:
                        unique_statuses.append(st)
                status_str = ", ".join([get_status_full_name(s) for s in unique_statuses])
                
                days_list.append({
                    'date': d.strftime('%d.%m.%Y'),
                    'fact_start': fact_start_str,
                    'fact_end': fact_end_str,
                    'sign': sign_str,
                    'status': status_str,
                    'total_day_time': total_day_time_str
                })

            response_data = {
                'period_start': first_day.strftime('%d.%m.%Y') if hasattr(first_day, 'strftime') else str(first_day),
                'period_end': last_day.strftime('%d.%m.%Y') if hasattr(last_day, 'strftime') else str(last_day),
                'plan_start': user_start.strftime('%H:%M') if user_start and hasattr(user_start, 'strftime') else str(user_start) if user_start else None,
                'plan_end': user_end.strftime('%H:%M') if user_end and hasattr(user_end, 'strftime') else str(user_end) if user_end else None,
                'total_score': format_seconds_to_hhmm(total_delta_score),
                'days': days_list
            }

            return Response(response_data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ReportCardManualCreateAPIView(APIView):
    """
    API View to manually add a ReportCard entry.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        user = request.user
        
        day_str = data.get('date')
        start_str = data.get('start_time')
        end_str = data.get('end_time')
        reason = data.get('reason')
        
        if not all([day_str, start_str, end_str, reason]):
            return Response({'error': 'Все поля (дата, время прихода/ухода, причина) обязательны'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            report_date = datetime.datetime.strptime(day_str, '%Y-%m-%d').date()
            start_t = datetime.datetime.strptime(start_str, '%H:%M').time()
            end_t = datetime.datetime.strptime(end_str, '%H:%M').time()
        except ValueError:
            return Response({'error': 'Неверный формат даты или времени'}, status=status.HTTP_400_BAD_REQUEST)
            
        today = datetime.date.today()
        min_date = today - datetime.timedelta(days=21)
        max_date = today + datetime.timedelta(days=7)
        
        if not (min_date <= report_date <= max_date):
            return Response({'error': 'Запись возможна только за последние 3 недели и на 1 неделю вперед'}, status=status.HTTP_400_BAD_REQUEST)
            
        if start_t < datetime.time(6, 0):
            return Response({'error': 'Время прихода не может быть раньше 06:00'}, status=status.HTTP_400_BAD_REQUEST)
            
        if end_t > datetime.time(21, 0):
            return Response({'error': 'Время ухода не может быть позже 21:00'}, status=status.HTTP_400_BAD_REQUEST)
            
        if start_t > end_t:
            return Response({'error': 'Время прихода не может быть позже времени ухода'}, status=status.HTTP_400_BAD_REQUEST)
            
        # Create record
        ReportCard.objects.create(
            employee=user,
            report_card_day=report_date,
            start_time=start_t,
            end_time=end_t,
            reason_adjustment=reason,
            record_type="13", # Ручной ввод
            manual_input=True
        )
        
        return Response({'success': True, 'message': 'Запись успешно добавлена'})

class ReportCardManualListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        today = datetime.date.today()
        min_date = today - datetime.timedelta(days=21)
        max_date = today + datetime.timedelta(days=7)
        
        cards = ReportCard.objects.filter(
            employee=user,
            manual_input=True,
            report_card_day__range=(min_date, max_date)
        ).order_by('-report_card_day')
        
        data = []
        for c in cards:
            data.append({
                'id': c.pk,
                'date': c.report_card_day.strftime('%Y-%m-%d') if c.report_card_day else None,
                'start_time': c.start_time.strftime('%H:%M') if c.start_time else None,
                'end_time': c.end_time.strftime('%H:%M') if c.end_time else None,
                'reason': c.reason_adjustment
            })
            
        return Response(data)

class ReportCardManualDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        try:
            return ReportCard.objects.get(pk=pk, employee=user, manual_input=True)
        except ReportCard.DoesNotExist:
            return None

    def put(self, request, pk):
        card = self.get_object(pk, request.user)
        if not card:
            return Response({'error': 'Запись не найдена'}, status=status.HTTP_404_NOT_FOUND)
            
        data = request.data
        day_str = data.get('date')
        start_str = data.get('start_time')
        end_str = data.get('end_time')
        reason = data.get('reason')
        
        if not all([day_str, start_str, end_str, reason]):
            return Response({'error': 'Все поля обязательны'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            report_date = datetime.datetime.strptime(day_str, '%Y-%m-%d').date()
            start_t = datetime.datetime.strptime(start_str, '%H:%M').time()
            end_t = datetime.datetime.strptime(end_str, '%H:%M').time()
        except ValueError:
            return Response({'error': 'Неверный формат даты или времени'}, status=status.HTTP_400_BAD_REQUEST)
            
        today = datetime.date.today()
        min_date = today - datetime.timedelta(days=21)
        max_date = today + datetime.timedelta(days=7)
        
        if not (min_date <= report_date <= max_date):
            return Response({'error': 'Запись возможна только за последние 3 недели и на 1 неделю вперед'}, status=status.HTTP_400_BAD_REQUEST)
            
        if start_t < datetime.time(6, 0):
            return Response({'error': 'Время прихода не может быть раньше 06:00'}, status=status.HTTP_400_BAD_REQUEST)
            
        if end_t > datetime.time(21, 0):
            return Response({'error': 'Время ухода не может быть позже 21:00'}, status=status.HTTP_400_BAD_REQUEST)
            
        if start_t > end_t:
            return Response({'error': 'Время прихода не может быть позже времени ухода'}, status=status.HTTP_400_BAD_REQUEST)
            
        card.report_card_day = report_date
        card.start_time = start_t
        card.end_time = end_t
        card.reason_adjustment = reason
        card.save()
        
        return Response({'success': True, 'message': 'Запись успешно обновлена'})

    def delete(self, request, pk):
        card = self.get_object(pk, request.user)
        if not card:
            return Response({'error': 'Запись не найдена'}, status=status.HTTP_404_NOT_FOUND)
            
        # Optional: check date constraint for deletion as well
        today = datetime.date.today()
        min_date = today - datetime.timedelta(days=21)
        max_date = today + datetime.timedelta(days=7)
        if not (min_date <= card.report_card_day <= max_date):
            return Response({'error': 'Невозможно удалить запись за пределами допустимого интервала'}, status=status.HTTP_400_BAD_REQUEST)
            
        card.delete()
        return Response({'success': True, 'message': 'Запись успешно удалена'})

