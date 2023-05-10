from django.db.models import Q
from contracts_app.models import Contract
from customers_app.models import DataBaseUser, Posts, AccessLevel
from hrdepartment_app.models import ApprovalOficialMemoProcess, BusinessProcessDirection, DocumentsJobDescription
from loguru import logger

logger.add("debug.json", format="{time} {level} {message}", level="DEBUG", rotation="10 MB", compression="zip",
           serialize=True)


# ToDo: Создать модель в которую будет записываться вся статистика,
#  а занесение информации будет посредством метода моделей save()

def get_all_contracts(request):
    # make_menu()
    contracts_count = Contract.objects.filter(Q(parent_category=None), Q(allowed_placed=True),
                                              Q(type_of_document__type_document='Договор')).count()
    all_prolongation = Contract.type_of_prolongation
    all_access = AccessLevel.objects.all()
    if not request.user.is_anonymous:
        try:
            contracts_not_published = Contract.objects.filter(Q(allowed_placed=False))
            documents_not_published = DocumentsJobDescription.objects.filter(Q(allowed_placed=False))
        except Exception as _ex:
            contracts_not_published = Contract.objects.filter(allowed_placed=False)
            documents_not_published = DocumentsJobDescription.objects.filter(allowed_placed=False)
        contracts_not_published_count = contracts_not_published.count()
        documents_not_published_count = documents_not_published.count()
    else:
        contracts_not_published = ''
        contracts_not_published_count = 0
        documents_not_published = ''
        documents_not_published_count = 0
    # contracts_not_published = ''
    # contracts_not_published_count = 0
    posts_not_published = Posts.objects.filter(allowed_placed=False)
    posts_not_published_count = Posts.objects.filter(allowed_placed=False).count()

    return {'prolongation': all_prolongation,
            'contracts_count': contracts_count,
            'contracts_not_published': contracts_not_published, 'posts_not_published': posts_not_published,
            'contracts_not_published_count': contracts_not_published_count, 'access': all_access,
            'documents_not_published': documents_not_published,
            'documents_not_published_count': documents_not_published_count,
            'posts_not_published_count': posts_not_published_count}


def get_approval_oficial_memo_process(request):
    if not request.user.is_anonymous:
        try:
            business_process_direction_list = BusinessProcessDirection.objects.filter(person_agreement=request.user.user_work_profile.job)
            person_executor_job_list = list()
            for item in business_process_direction_list:
                person_executor_job_list = [items[0] for items in item.person_executor.values_list()]

            business_process_direction_list = BusinessProcessDirection.objects.filter(clerk=request.user.user_work_profile.job)
            clerk_job_list = list()
            clerk_job_list_executor = list()
            for item in business_process_direction_list:
                clerk_job_list = [items[0] for items in item.clerk.values_list()]
                clerk_job_list_executor = [items[0] for items in item.person_executor.values_list()]
            # Выбор согласующих лиц
            person_executor_list = [item for item in DataBaseUser.objects.filter(user_work_profile__job__in=person_executor_job_list)]
            person_agreement = ApprovalOficialMemoProcess.objects.filter(Q(person_executor__in=person_executor_list) & Q(document_not_agreed=False))
            # Получение списка сотрудников НО
            person_distributor_list = DataBaseUser.objects.filter(Q(user_work_profile__divisions__type_of_role=1) & Q(user_work_profile__job__right_to_approval=True))
            person_distributor = [item for item in person_distributor_list]
            location_selected = ApprovalOficialMemoProcess.objects.filter(Q(location_selected=False) & Q(document_not_agreed=True))
            # Получение списка сотрудников ОК
            person_department_staff_list = DataBaseUser.objects.filter(Q(user_work_profile__divisions__type_of_role=2) & Q(user_work_profile__job__right_to_approval=True))
            person_department_staff = [item for item in person_department_staff_list]
            process_accepted = ApprovalOficialMemoProcess.objects.filter(Q(process_accepted=False) & Q(location_selected=True))
            # Выбор делопроизводителя
            clerk_list = [item for item in DataBaseUser.objects.filter(user_work_profile__job__in=clerk_job_list)]
            clerk_list_executor = [item for item in DataBaseUser.objects.filter(user_work_profile__job__in=clerk_job_list_executor)]
            clerk = ApprovalOficialMemoProcess.objects.filter(
                Q(person_executor__in=clerk_list_executor) & Q(originals_received=False) & Q(process_accepted=True))
            # Получение списка сотрудников ОК 2
            person_hr_list = DataBaseUser.objects.filter(Q(user_work_profile__divisions__type_of_role=2) & Q(user_work_profile__job__right_to_approval=True))
            person_hr = [item for item in person_hr_list]
            hr_accepted = ApprovalOficialMemoProcess.objects.filter(Q(hr_accepted=False) & Q(originals_received=True))
            return {
                'person_agreement': person_agreement,
                'document_not_agreed': person_agreement.count(),
                'clerk': clerk_list,
                'originals_received': clerk,
                'originals_received_count': clerk.count(),
                'person_distributor': person_distributor,
                'location_selected': location_selected,
                'location_selected_count': location_selected.count,
                'person_department_staff': person_department_staff,
                'process_accepted': process_accepted,
                'process_accepted_count': process_accepted.count,
                'person_hr': person_hr,
                'hr_accepted': hr_accepted,
                'hr_accepted_count': hr_accepted.count,
            }
        except Exception as _ex:
            logger.error(_ex)
            return {}
    else:
        return {}
