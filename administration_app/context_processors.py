import pathlib
from pprint import pprint

from django.core.cache import cache
from django.db.models import Q
from django.views.decorators.cache import cache_page

from contracts_app.models import Contract
from customers_app.models import DataBaseUser, Posts, RoleType
from djangoProject.settings import MEDIA_ROOT
from hrdepartment_app.models import (
    ApprovalOficialMemoProcess,
    BusinessProcessDirection,
    DocumentsJobDescription, CreatingTeam, OfficialMemo,
)
from loguru import logger


# logger.add("debug.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
#            rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
#            serialize=config('LOG_SERIALIZE'))


# ToDo: Создать модель в которую будет записываться вся статистика,
#  а занесение информации будет посредством метода моделей save()

# @cache_page(60 * 15)  # Кэшировать результат на 15 минут
# def get_all_contracts(request):
#     # make_menu()
#     contracts_count = Contract.objects.filter(
#         Q(parent_category=None),
#         Q(allowed_placed=True),
#         Q(type_of_document__type_document="Договор"),
#     ).count()
#     if not request.user.is_anonymous:
#         try:
#             contracts_not_published = Contract.objects.filter(Q(allowed_placed=False))
#             documents_not_published = DocumentsJobDescription.objects.filter(
#                 Q(allowed_placed=False)
#             )
#         except Exception as _ex:
#             contracts_not_published = Contract.objects.filter(allowed_placed=False)
#             documents_not_published = DocumentsJobDescription.objects.filter(
#                 allowed_placed=False
#             )
#         contracts_not_published_count = contracts_not_published.count()
#         documents_not_published_count = documents_not_published.count()
#     else:
#         contracts_not_published = ""
#         contracts_not_published_count = 0
#         documents_not_published = ""
#         documents_not_published_count = 0
#     posts_not_published = Posts.objects.filter(allowed_placed=False)
#     posts_not_published_count = Posts.objects.filter(allowed_placed=False).count()
#     return {
#         "contracts_count": contracts_count,
#         "contracts_not_published": contracts_not_published,
#         "posts_not_published": posts_not_published,
#         "contracts_not_published_count": contracts_not_published_count,
#         "documents_not_published": documents_not_published,
#         "documents_not_published_count": documents_not_published_count,
#         "posts_not_published_count": posts_not_published_count,
#     }

def get_all_contracts(request):
    cache_key = f"get_all_contracts_{request.user.id}"

    contracts_count = Contract.objects.filter(
        Q(parent_category=None),
        Q(allowed_placed=True),
        Q(type_of_document__type_document="Договор"),
    ).count()

    if not request.user.is_anonymous:
        try:
            contracts_not_published = Contract.objects.filter(Q(allowed_placed=False))
            documents_not_published = DocumentsJobDescription.objects.filter(
                Q(allowed_placed=False)
            )
        except Exception as _ex:
            contracts_not_published = Contract.objects.filter(allowed_placed=False)
            documents_not_published = DocumentsJobDescription.objects.filter(
                allowed_placed=False
            )
        contracts_not_published_count = contracts_not_published.count()
        documents_not_published_count = documents_not_published.count()
    else:
        contracts_not_published = ""
        contracts_not_published_count = 0
        documents_not_published = ""
        documents_not_published_count = 0

    posts_not_published = Posts.objects.filter(allowed_placed=False)
    posts_not_published_count = Posts.objects.filter(allowed_placed=False).count()

    data = {
        "contracts_count": contracts_count,
        "contracts_not_published": contracts_not_published,
        "posts_not_published": posts_not_published,
        "contracts_not_published_count": contracts_not_published_count,
        "documents_not_published": documents_not_published,
        "documents_not_published_count": documents_not_published_count,
        "posts_not_published_count": posts_not_published_count,
    }

    cache.set(cache_key, data, 60 * 15)  # Кэшировать результат на 15 минут
    return data


def make_list(n):
    for _ in range(n):
        yield []  # empty list


def get_approval_oficial_memo_process(request):
    notifications = []
    if not request.user.is_anonymous:
        try:
            # Инициализация списков для ролей
            person_executor, person_agreement, person_clerk, person_hr, person_distributor, person_accounting = make_list(6)
            person_executor_cto, person_agreement_cto, person_clerk_cto, person_hr_cto = make_list(4)

            # Получение данных для бизнес-процессов
            business_process = BusinessProcessDirection.objects.filter(business_process_type=1).values_list(
                'person_executor', 'person_agreement', 'clerk', 'person_hr'
            )
            for item in business_process:
                person_executor.append(item[0])  # Исполнители
                person_agreement.append(item[1])  # Согласователи
                person_clerk.append(item[2])  # Делопроизводители
                person_hr.append(item[3])  # Сотрудники ОК

            # Получение списка сотрудников НО
            person_distributor.extend(
                DataBaseUser.objects.filter(
                    Q(type_of_role=RoleType.NO) & Q(user_work_profile__job__right_to_approval=True)
                ).values_list('pk', flat=True).exclude(is_active=False)
            )

            # Получение списка сотрудников бухгалтерии
            person_accounting.extend(
                DataBaseUser.objects.filter(
                    Q(type_of_role=RoleType.ACCOUNTING) & Q(user_work_profile__job__right_to_approval=True)
                ).values_list('pk', flat=True).exclude(is_active=False)
            )

            # Получение данных для бизнес-процессов CTO
            business_process_cto = BusinessProcessDirection.objects.filter(business_process_type=2)
            for item in business_process_cto:
                person_executor_cto.extend(item.person_executor.values_list('pk', flat=True))
                person_agreement_cto.extend(item.person_agreement.values_list('pk', flat=True))
                person_clerk_cto.extend(item.clerk.values_list('pk', flat=True))
                person_hr_cto.extend(item.person_hr.values_list('pk', flat=True))

            # Формирование уведомлений
            if request.user.user_work_profile.job.pk in person_agreement:
                agreement = ApprovalOficialMemoProcess.objects.filter(
                    Q(person_executor__user_work_profile__job__division_affiliation__name=request.user.user_work_profile.job.division_affiliation.name) &
                    Q(document_not_agreed=False)
                ).exclude(cancellation=True)
                agreement_color = [(item, 'red') for item in agreement]
                notifications.append({
                    'count': agreement.count(),
                    'icon_class': 'bx bx-select-multiple',
                    'title': 'Согласование',
                    'items': agreement_color,
                    'url_name': 'hrdepartment_app:bpmemo_update',
                    'view_all_url': 'hrdepartment_app:bpmemo_list',
                    'large': False
                })

            if request.user.pk in person_distributor:
                distributor = ApprovalOficialMemoProcess.objects.filter(
                    Q(location_selected=False) & Q(document_not_agreed=True)
                ).exclude(cancellation=True).exclude(document__official_memo_type="3")
                distributor_color = [(item, 'red') for item in distributor]
                notifications.append({
                    'count': distributor.count(),
                    'icon_class': 'bx bx-hotel',
                    'title': 'Место проживания',
                    'items': distributor_color,
                    'url_name': 'hrdepartment_app:bpmemo_update',
                    'view_all_url': 'hrdepartment_app:bpmemo_list',
                    'large': False
                })
            if request.user.user_work_profile.job.pk in person_clerk:
                clerk = ApprovalOficialMemoProcess.objects.filter(
                    Q(person_executor__user_work_profile__job__division_affiliation__pk=request.user.user_work_profile.job.division_affiliation.pk) &
                    Q(originals_received=False) & Q(process_accepted=True)
                ).exclude(cancellation=True).exclude(document__official_memo_type="2")
                clerk_color = [
                    (
                        item,
                        'red' if item.document.person.user_work_profile.job.type_of_job == "1"
                        else 'green' if item.document.person.user_work_profile.job.type_of_job == "2"
                        else 'black'
                    )
                    for item in clerk]
                notifications.append({
                    'count': clerk.count(),
                    'icon_class': 'bx bx-notepad',
                    'title': 'Оригиналы',
                    'items': clerk_color,
                    'url_name': 'hrdepartment_app:bpmemo_update',
                    'view_all_url': 'hrdepartment_app:bpmemo_list',
                    'large': False
                })

            if request.user.user_work_profile.job.pk in person_hr:
                hr = ApprovalOficialMemoProcess.objects.filter(
                    Q(process_accepted=False) & Q(location_selected=True)
                ).exclude(cancellation=True).exclude(document__official_memo_type="3")
                hr_color = [
                    (
                        item,
                        'red' if item.document.person.user_work_profile.job.type_of_job == "1"
                        else 'green' if item.document.person.user_work_profile.job.type_of_job == "2"
                        else 'black'
                    )
                    for item in hr
                ]
                notifications.append({
                    'count': hr.count(),
                    'icon_class': 'bx bx-user-pin',
                    'title': 'Приказ',
                    'items': hr_color,
                    'url_name': 'hrdepartment_app:bpmemo_update',
                    'view_all_url': 'hrdepartment_app:bpmemo_list',
                    'large': False
                })

                hr_accepted = ApprovalOficialMemoProcess.objects.filter(
                    Q(hr_accepted=False) & Q(originals_received=True) & Q(date_transfer_hr__isnull=False)
                ).exclude(cancellation=True).exclude(document__official_memo_type="2")
                hr_accepted_color = [
                    (
                        item,
                        'red' if item.document.person.user_work_profile.job.type_of_job == "1"
                        else 'green' if item.document.person.user_work_profile.job.type_of_job == "2"
                        else 'black'
                    )
                    for item in hr_accepted]
                notifications.append({
                    'count': hr_accepted.count(),
                    'icon_class': 'bx bx-pencil',
                    'title': 'Проверка',
                    'items': hr_accepted_color,
                    'url_name': 'hrdepartment_app:bpmemo_update',
                    'view_all_url': 'hrdepartment_app:bpmemo_list',
                    'large': False
                })

            if request.user.pk in person_accounting or request.user.is_superuser:
                accounting = ApprovalOficialMemoProcess.objects.filter(
                    Q(accepted_accounting=False) & Q(hr_accepted=True)
                ).exclude(cancellation=True).exclude(document__official_memo_type="2")
                accounting_color = [(item, 'red') for item in accounting]
                notifications.append({
                    'count': accounting.count(),
                    'icon_class': 'bx bx-check-shield',
                    'title': 'Авансовый отчет',
                    'items': accounting_color,
                    'url_name': 'hrdepartment_app:bpmemo_update',
                    'view_all_url': 'hrdepartment_app:bpmemo_list',
                    'large': False
                })

                expenses_dicts = ApprovalOficialMemoProcess.objects.filter(
                    Q(document__expenses=False) & Q(document__expenses_summ__gt=0) & Q(process_accepted=True)
                )
                expenses_dicts_color = [(item, 'red') for item in expenses_dicts]
                notifications.append({
                    'count': expenses_dicts.count(),
                    'icon_class': 'bx bxs-bank text-danger',
                    'title': 'Запрос аванса',
                    'items': expenses_dicts_color,
                    'url_name': 'hrdepartment_app:expenses_list',
                    'view_all_url': 'hrdepartment_app:expenses_list',
                    'large': False
                })

            # Уведомления для CTO
            if request.user.user_work_profile.job.pk in person_agreement_cto or request.user.is_superuser:
                agreement_cto = CreatingTeam.objects.filter(Q(agreed=False)).exclude(cancellation=True)
                agreement_cto_color = [(item, 'red') for item in agreement_cto]
                notifications.append({
                    'count': agreement_cto.count(),
                    'icon_class': 'fa fa-check text-primary',
                    'title': 'Согласование приказа СБ',
                    'items': agreement_cto_color,
                    'url_name': 'hrdepartment_app:team_agreed',
                    'view_all_url': 'hrdepartment_app:team_list',
                    'large': False
                })

            if request.user.user_work_profile.job.pk in person_hr_cto or request.user.is_superuser:
                hr_cto = CreatingTeam.objects.filter(Q(agreed=True) & (Q(number='') | Q(scan_file=''))).exclude(cancellation=True)
                hr_cto_color = [(item, 'red') for item in hr_cto]
                notifications.append({
                    'count': hr_cto.count(),
                    'icon_class': 'fa fa-book text-primary',
                    'title': 'Регистрация приказа СБ',
                    'items': hr_cto_color,
                    'url_name': 'hrdepartment_app:team_number',
                    'view_all_url': 'hrdepartment_app:team_list',
                    'large': False
                })

            if request.user.user_work_profile.job.pk in person_clerk_cto or request.user.is_superuser:
                clerk_cto = CreatingTeam.objects.filter(Q(agreed=True) & ~Q(number='') & ~Q(scan_file='') & Q(email_send=False)).exclude(cancellation=True)
                clerk_cto_color = [(item, 'red') for item in clerk_cto]
                notifications.append({
                    'count': clerk_cto.count(),
                    'icon_class': 'fa fa-envelope text-primary',
                    'title': 'Отправка письма приказа СБ',
                    'items': clerk_cto_color,
                    'url_name': 'hrdepartment_app:team',
                    'view_all_url': 'hrdepartment_app:team_list',
                    'large': False
                })
            return {"notifications": notifications}

        except Exception as _ex:
            logger.exception(_ex)
            return {"notifications": []}
    else:
        return {"notifications": []}


# def get_approval_oficial_memo_process(request):
#     notifications = []
#     if not request.user.is_anonymous:
#         try:
#             expenses_dicts = 0
#             person_executor, person_agreement, person_clerk, person_hr, person_distributor, person_accounting = make_list(6)
#             executor, agreement, clerk, hr, distributor, accounting, hr_accepted = make_list(7)
#             business_process = BusinessProcessDirection.objects.filter(business_process_type=1).values_list('person_executor', 'person_agreement',
#                                                                                   'clerk', 'person_hr')
#             for item in business_process:
#                 person_executor.append(item[0])  # Получаем список исполнителей
#                 person_agreement.append(item[1])  # Получаем список согласователей
#                 person_clerk.append(item[2])  # Получаем список делопроизводителей
#                 person_hr.append(item[3])  # Получаем список сотрудников ОК
#
#             for item in DataBaseUser.objects.filter(Q(user_work_profile__divisions__type_of_role=1)
#                                                     & Q(user_work_profile__job__right_to_approval=True)).values('pk'):
#                 person_distributor.append(item['pk'])  # Получаем список сотрудников НО
#
#             for item in DataBaseUser.objects.filter(Q(user_work_profile__divisions__type_of_role=3)
#                                                     & Q(user_work_profile__job__right_to_approval=True)).values('pk'):
#                 person_accounting.append(item['pk'])  # Получаем список сотрудников бухгалтерии
#             if request.user.user_work_profile.job.pk in person_executor:
#                 pass  # Если пользователь является исполнителем
#
#             if request.user.user_work_profile.job.pk in person_agreement:
#                 # Если пользователь является согласователем
#                 agreement = ApprovalOficialMemoProcess.objects.filter(
#                     Q(person_executor__user_work_profile__job__type_of_job=request.user.user_work_profile.job.type_of_job) &
#                     Q(document_not_agreed=False)
#                 ).exclude(cancellation=True)
#
#             if request.user.pk in person_distributor:
#                 # Получение списка сотрудников НО
#                 distributor = (
#                     ApprovalOficialMemoProcess.objects.filter(
#                         Q(location_selected=False) & Q(document_not_agreed=True)
#                     )
#                     .exclude(cancellation=True)
#                     .exclude(document__official_memo_type="3")
#                 )
#
#             if request.user.user_work_profile.job.pk in person_clerk:
#                 # Если пользователь является делопроизводителем
#                 clerk = (
#                     ApprovalOficialMemoProcess.objects.filter(
#                         Q(person_executor__user_work_profile__divisions__type_of_role=request.user.user_work_profile.divisions.type_of_role) &
#                         Q(originals_received=False)
#                         & Q(process_accepted=True)
#                     )
#                     .exclude(cancellation=True)
#                     .exclude(document__official_memo_type="2")
#                 )
#
#             if request.user.user_work_profile.job.pk in person_hr:
#                 # Если пользователь является HR
#                 hr = (
#                     ApprovalOficialMemoProcess.objects.filter(
#                         Q(process_accepted=False) & Q(location_selected=True)
#                     )
#                     .exclude(cancellation=True)
#                     .exclude(document__official_memo_type="3")
#                 )
#                 hr_color = []
#                 for item in hr:
#                     if item.document.person.user_work_profile.job.division_affiliation.pk == 2:
#                         hr_color.append((item, 'green'))
#                     else:
#                         hr_color.append((item, 'red'))
#                 hr_accepted = (
#                     ApprovalOficialMemoProcess.objects.filter(
#                         Q(hr_accepted=False)
#                         & Q(originals_received=True)
#                         & Q(date_transfer_hr__isnull=False)
#                     )
#                     .exclude(cancellation=True)
#                     .exclude(document__official_memo_type="2")
#                 )
#
#             if (request.user.pk in person_accounting) or request.user.is_superuser:
#                 # Получение списка сотрудников бухгалтерии
#                 accounting = (
#                     ApprovalOficialMemoProcess.objects.filter(
#                         Q(accepted_accounting=False) & Q(hr_accepted=True)
#                     )
#                     .exclude(cancellation=True)
#                     .exclude(document__official_memo_type="2")
#                 )
#                 expenses_dicts = ApprovalOficialMemoProcess.objects.filter(
#                     Q(document__expenses=False) &
#                     Q(document__expenses_summ__gt=0) &
#                     Q(process_accepted=True)).values('document').count()
#                 # expenses_lists = [item['document'] for item in expenses_dicts]
#
#
#             person_executor_cto, person_agreement_cto, person_clerk_cto, person_hr_cto = make_list(4)
#             executor_cto, agreement_cto, clerk_cto, hr_cto = make_list(4)
#             business_process_cto = BusinessProcessDirection.objects.filter(business_process_type=2)
#
#
#             for item in business_process_cto:
#                 for ut in item.person_executor.iterator():
#                     person_executor_cto.append(ut.pk)  # Получаем список исполнителей
#                 for ut in item.person_agreement.iterator():
#                     person_agreement_cto.append(ut.pk)  # Получаем список согласователей
#                 for ut in item.clerk.iterator():
#                     person_clerk_cto.append(ut.pk)  # Получаем список делопроизводителей
#                 for ut in item.person_hr.iterator():
#                     person_hr_cto.append(ut.pk)  # Получаем список сотрудников ОК
#
#             if request.user.user_work_profile.job.pk in person_executor_cto:
#                 pass  # Если пользователь является исполнителем
#
#             if request.user.user_work_profile.job.pk in person_agreement_cto:
#                 # Если пользователь является согласователем
#                 agreement_cto = CreatingTeam.objects.filter(Q(agreed=False)).exclude(cancellation=True)
#             if request.user.user_work_profile.job.pk in person_hr_cto:
#                 # Если пользователь является согласователем
#                 query = Q(agreed=True) & (Q(number='') | Q(scan_file=''))
#                 hr_cto = CreatingTeam.objects.filter(query).exclude(cancellation=True)
#             if request.user.user_work_profile.job.pk in person_clerk_cto:
#                 # Если пользователь является согласователем
#                 query = Q(agreed=True) & ~Q(number='') & ~Q(scan_file='') & Q(email_send=False)
#                 clerk_cto = CreatingTeam.objects.filter(query).exclude(cancellation=True)
#
#             return {
#                 "person_agreement": person_agreement,
#                 "document_agreement": agreement,
#                 "document_not_agreed": agreement.count() if agreement else 0,
#                 "clerk": person_clerk,
#                 "originals_received": clerk,
#                 "originals_received_count": clerk.count() if clerk else 0,
#                 "person_distributor": person_distributor,
#                 "location_selected": distributor,
#                 "location_selected_count": distributor.count if distributor else 0,
#                 "person_department_staff": person_hr,
#                 "process_accepted": hr_color,
#                 "process_accepted_count": hr.count if hr else 0,
#                 "person_hr": person_hr,
#                 "hr_accepted": hr_accepted,
#                 "hr_accepted_count": hr_accepted.count if hr_accepted else 0,
#
#                 "accounting": person_accounting,
#                 "accounting_accepted": accounting,
#                 "accounting_accepted_count": accounting.count if accounting else 0,
#                 "accounting_expenses_count": expenses_dicts if expenses_dicts else 0,
#
#                 "agreement_cto": person_agreement_cto,
#                 "agreement_cto_accepted": agreement_cto,
#                 "agreement_cto_accepted_count": agreement_cto.count if agreement_cto else 0,
#
#                 "hr_cto": person_hr_cto,
#                 "hr_cto_accepted": hr_cto,
#                 "hr_cto_accepted_count": hr_cto.count if hr_cto else 0,
#
#                 "clerk_cto": person_clerk_cto,
#                 "clerk_cto_accepted": clerk_cto,
#                 "clerk_cto_accepted_count": clerk_cto.count if clerk_cto else 0,
#             }
#         except Exception as _ex:
#             logger.exception(_ex)
#             return {}
#     else:
#         return {}

#
# def get_qrcode(request):
#     import qrcode
#
#     img = qrcode.make(request.build_absolute_uri())
#     try:
#         img.save(pathlib.Path.joinpath(MEDIA_ROOT, f"qr/{request.user.ref_key}.png"))
#         return {"qrcode": f"/media/qr/{request.user.ref_key}.png"}
#     except AttributeError:
#         return {}
