from django.contrib.auth.decorators import login_required
from django.db.models import Q
from administration_app.models import make_menu
from contracts_app.models import Contract, TypeContract, TypeProperty, TypeDocuments
from customers_app.models import DataBaseUser, Counteragent, Division, Posts, AccessLevel
from hrdepartment_app.models import ApprovalOficialMemoProcess, BusinessProcessDirection, DocumentsJobDescription


# ToDo: Создать модель в которую будет записываться вся статистика, а занесение информации будет посредством метода моделей save()

def get_all_contracts(request):
    # make_menu()
    all_contract = Contract.objects.all()
    contracts_count = Contract.objects.filter(Q(parent_category=None), Q(allowed_placed=True),
                                              Q(type_of_document__type_document='Договор')).count()
    all_users = DataBaseUser.objects.all()
    all_type_of_contract = TypeContract.objects.all()
    all_type_property = TypeProperty.objects.all()
    all_counteragent = Counteragent.objects.all()
    all_prolongation = Contract.type_of_prolongation
    all_divisions = Division.objects.filter(active=True).order_by('code')
    all_access = AccessLevel.objects.all()
    all_type_of_document = TypeDocuments.objects.all()
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

    return {'all_contract': all_contract, 'employee': all_users, 'type_property': all_type_property,
            'counteragent': all_counteragent, 'prolongation': all_prolongation, 'division': all_divisions,
            'type_contract': all_type_of_contract, 'contracts_count': contracts_count,
            'contracts_not_published': contracts_not_published, 'posts_not_published': posts_not_published,
            'contracts_not_published_count': contracts_not_published_count, 'access': all_access,
            'documents_not_published': documents_not_published,
            'documents_not_published_count': documents_not_published_count,
            'posts_not_published_count': posts_not_published_count, 'type_of_document': all_type_of_document, }


def get_approval_oficial_memo_process(request):
    if not request.user.is_anonymous:
        try:
            business_process_direction_list = BusinessProcessDirection.objects.filter(
                person_agreement=request.user.user_work_profile.job)
            person_executor_job_list = list()
            for item in business_process_direction_list:
                person_executor_job_list = [items[0] for items in item.person_executor.values_list()]
            person_executor_list = [item for item in
                                    DataBaseUser.objects.filter(user_work_profile__job__in=person_executor_job_list)]
            person_agreement = ApprovalOficialMemoProcess.objects.filter(
                Q(person_executor__in=person_executor_list) & Q(document_not_agreed=False))
            return {
                'person_agreement': person_agreement,
                'document_not_agreed': person_agreement.count(),
                'person_distributor': '',
                'person_department_staff': '',
            }
        except Exception as _ex:
            return {}
    else:
        return {}
