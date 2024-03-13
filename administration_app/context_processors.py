import pathlib

from decouple import config
from django.db.models import Q
from contracts_app.models import Contract
from customers_app.models import DataBaseUser, Posts, AccessLevel
from djangoProject.settings import MEDIA_ROOT
from hrdepartment_app.models import (
    ApprovalOficialMemoProcess,
    BusinessProcessDirection,
    DocumentsJobDescription,
)
from loguru import logger


# logger.add("debug.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
#            rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
#            serialize=config('LOG_SERIALIZE'))


# ToDo: Создать модель в которую будет записываться вся статистика,
#  а занесение информации будет посредством метода моделей save()


def get_all_contracts(request):
    # make_menu()
    contracts_count = Contract.objects.filter(
        Q(parent_category=None),
        Q(allowed_placed=True),
        Q(type_of_document__type_document="Договор"),
    ).count()
    all_prolongation = Contract.type_of_prolongation
    all_access = AccessLevel.objects.all()
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
    # contracts_not_published = ''
    # contracts_not_published_count = 0
    posts_not_published = Posts.objects.filter(allowed_placed=False)
    posts_not_published_count = Posts.objects.filter(allowed_placed=False).count()

    return {
        "prolongation": all_prolongation,
        "contracts_count": contracts_count,
        "contracts_not_published": contracts_not_published,
        "posts_not_published": posts_not_published,
        "contracts_not_published_count": contracts_not_published_count,
        "access": all_access,
        "documents_not_published": documents_not_published,
        "documents_not_published_count": documents_not_published_count,
        "posts_not_published_count": posts_not_published_count,
    }


def make_list(n):
    for _ in range(n):
        yield []  # empty list


def get_approval_oficial_memo_process(request):
    if not request.user.is_anonymous:
        try:
            person_executor, person_agreement, person_clerk, person_hr, person_distributor, person_accounting = make_list(6)
            executor, agreement, clerk, hr, distributor, accounting, hr_accepted = make_list(7)
            business_process = BusinessProcessDirection.objects.all().values_list('person_executor', 'person_agreement',
                                                                                  'clerk', 'person_hr')
            for item in business_process:
                person_executor.append(item[0])  # Получаем список исполнителей
                person_agreement.append(item[1])  # Получаем список согласователей
                person_clerk.append(item[2])  # Получаем список делопроизводителей
                person_hr.append(item[3])  # Получаем список сотрудников ОК

            for item in DataBaseUser.objects.filter(Q(user_work_profile__divisions__type_of_role=1)
                                                    & Q(user_work_profile__job__right_to_approval=True)).values('pk'):
                person_distributor.append(item['pk'])  # Получаем список сотрудников НО

            for item in DataBaseUser.objects.filter(Q(user_work_profile__divisions__type_of_role=3)
                                                    & Q(user_work_profile__job__right_to_approval=True)).values('pk'):
                person_accounting.append(item['pk'])  # Получаем список сотрудников бухгалтерии

            if request.user.user_work_profile.job.pk in person_executor:
                pass  # Если пользователь является исполнителем

            if request.user.user_work_profile.job.pk in person_agreement:
                # Если пользователь является согласователем
                agreement = ApprovalOficialMemoProcess.objects.filter(
                    Q(person_agreement__user_work_profile__job__pk__in=person_agreement) &
                    Q(document_not_agreed=False)
                ).exclude(cancellation=True)

            if request.user.pk in person_distributor:
                # Получение списка сотрудников НО
                distributor = (
                    ApprovalOficialMemoProcess.objects.filter(
                        Q(location_selected=False) & Q(document_not_agreed=True)
                    )
                    .exclude(cancellation=True)
                    .exclude(document__official_memo_type="3")
                )

            if request.user.user_work_profile.job.pk in person_clerk:
                # Если пользователь является делопроизводителем
                clerk = (
                    ApprovalOficialMemoProcess.objects.filter(
                        Q(person_clerk__user_work_profile__job__type_of_job=request.user.user_work_profile.job.type_of_job) &
                        Q(originals_received=False)
                        & Q(process_accepted=True)
                    )
                    .exclude(cancellation=True)
                    .exclude(document__official_memo_type="2")
                )

            if request.user.user_work_profile.job.pk in person_hr:
                # Если пользователь является HR
                hr = (
                    ApprovalOficialMemoProcess.objects.filter(
                        Q(process_accepted=False) & Q(location_selected=True)
                    )
                    .exclude(cancellation=True)
                    .exclude(document__official_memo_type="3")
                )
                hr_accepted = (
                    ApprovalOficialMemoProcess.objects.filter(
                        Q(hr_accepted=False)
                        & Q(originals_received=True)
                        & Q(date_transfer_hr__isnull=False)
                    )
                    .exclude(cancellation=True)
                    .exclude(document__official_memo_type="2")
                )

            if request.user.pk in person_accounting:
                # Получение списка сотрудников бухгалтерии
                accounting = (
                    ApprovalOficialMemoProcess.objects.filter(
                        Q(accepted_accounting=False) & Q(hr_accepted=True)
                    )
                    .exclude(cancellation=True)
                    .exclude(document__official_memo_type="2")
                )

            return {
                "person_agreement": person_agreement,
                "document_agreement": agreement,
                "document_not_agreed": agreement.count() if agreement else 0,
                "clerk": person_clerk,
                "originals_received": clerk,
                "originals_received_count": clerk.count() if clerk else 0,
                "person_distributor": person_distributor,
                "location_selected": distributor,
                "location_selected_count": distributor.count if distributor else 0,
                "person_department_staff": person_hr,
                "process_accepted": hr,
                "process_accepted_count": hr.count if hr else 0,
                "person_hr": person_hr,
                "hr_accepted": hr_accepted,
                "hr_accepted_count": hr_accepted.count if hr_accepted else 0,
                "accounting": person_accounting,
                "accounting_accepted": accounting,
                "accounting_accepted_count": accounting.count if accounting else 0,
            }
        except Exception as _ex:
            logger.exception(_ex)
            return {}
    else:
        return {}


def get_qrcode(request):
    import qrcode

    # print(request.build_absolute_uri())
    img = qrcode.make(request.build_absolute_uri())
    # img = qrcode.make('request.build_absolute_uri()')
    try:
        img.save(pathlib.Path.joinpath(MEDIA_ROOT, f"qr/{request.user.ref_key}.png"))
        return {"qrcode": f"/media/qr/{request.user.ref_key}.png"}
    except AttributeError:
        return {}
