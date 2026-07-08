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
            }
            return Response(data)
        except Exception as e:
            logger.error(f"Error in UserProfileAPIView: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from hrdepartment_app.hrdepartment_util import get_working_hours

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

            days_list = []
            for key, rows in data_dict.items():
                for row in rows:
                    if len(row) < 12: continue
                    r1, r2, r3, r4, r5, r6, r7, r8, r9, r10, r11, r12 = row[:12]
                    
                    if r1 <= datetime.datetime.today().date():
                        days_list.append({
                            'date': r1.strftime('%Y-%m-%d') if hasattr(r1, 'strftime') else str(r1),
                            'fact_start': r2.strftime('%H:%M') if r2 and hasattr(r2, 'strftime') else str(r2) if r2 else None,
                            'fact_end': r3.strftime('%H:%M') if r3 and hasattr(r3, 'strftime') else str(r3) if r3 else None,
                            'sign': str(r4) if r4 else "",
                            'status': str(r8) if r8 else "",
                            'total_day_time': str(r11) if r11 else "0"
                        })

            response_data = {
                'period_start': first_day.strftime('%Y-%m-%d') if hasattr(first_day, 'strftime') else str(first_day),
                'period_end': last_day.strftime('%Y-%m-%d') if hasattr(last_day, 'strftime') else str(last_day),
                'plan_start': user_start.strftime('%H:%M') if user_start and hasattr(user_start, 'strftime') else str(user_start) if user_start else None,
                'plan_end': user_end.strftime('%H:%M') if user_end and hasattr(user_end, 'strftime') else str(user_end) if user_end else None,
                'total_score': str(total_score) if total_score else "0",
                'days': days_list
            }

            return Response(response_data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
