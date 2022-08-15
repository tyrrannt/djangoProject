from django.db.models import Q

from administration_app.models import make_menu
from contracts_app.models import Contract, TypeContract, TypeProperty, TypeDocuments
from customers_app.models import DataBaseUser, Counteragent, Division, Posts, AccessLevel


def get_all_contracts(request):
    make_menu()
    all_contract = Contract.objects.all()
    contracts_count = Contract.objects.filter(Q(parent_category=None), Q(allowed_placed=True)).count()
    all_users = DataBaseUser.objects.all()
    all_type_of_contract = TypeContract.objects.all()
    all_type_property = TypeProperty.objects.all()
    all_counteragent = Counteragent.objects.all()
    all_prolongation = Contract.type_of_prolongation
    all_divisions = Division.objects.all()
    all_access = AccessLevel.objects.all()
    all_type_of_document = TypeDocuments.objects.all()
    if not request.user.is_anonymous:
        contracts_not_published = Contract.objects.filter(Q(allowed_placed=False),
                                                          Q(access__level__gte=request.user.access_level.contracts_access_view))
        contracts_not_published_count = contracts_not_published.count()
    else:
        contracts_not_published = ''
        contracts_not_published_count = 0
    posts_not_published = Posts.objects.filter(allowed_placed=False)
    posts_not_published_count = Posts.objects.filter(allowed_placed=False).count()

    return {'all_contract': all_contract, 'employee': all_users, 'type_property': all_type_property,
            'counteragent': all_counteragent, 'prolongation': all_prolongation, 'division': all_divisions,
            'type_contract': all_type_of_contract, 'contracts_count': contracts_count,
            'contracts_not_published': contracts_not_published, 'posts_not_published': posts_not_published,
            'contracts_not_published_count': contracts_not_published_count, 'access': all_access,
            'posts_not_published_count': posts_not_published_count, 'type_of_document': all_type_of_document, }
