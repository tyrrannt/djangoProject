from django.db.models import Q
import psutil
from contracts_app.models import Contract, TypeContract, TypeProperty
from customers_app.models import DataBaseUser, Counteragent, Division


def get_all_contracts(request):
    print(psutil.cpu_count())
    all_contract = Contract.objects.all()
    contracts_count = Contract.objects.filter(Q(parent_category=None), Q(allowed_placed=True)).count()
    all_users = DataBaseUser.objects.all()
    all_type_of_contract = TypeContract.objects.all()
    all_type_property = TypeProperty.objects.all()
    all_counteragent = Counteragent.objects.all()
    all_prolongation = Contract.type_of_prolongation
    all_divisions = Division.objects.all()
    contracts_not_published = Contract.objects.filter(allowed_placed=False)
    contracts_not_published_count = Contract.objects.filter(allowed_placed=False).count()
    return {'all_contract': all_contract, 'employee': all_users, 'type_property': all_type_property,
            'counteragent': all_counteragent, 'prolongation': all_prolongation, 'division': all_divisions,
            'type_contract': all_type_of_contract, 'contracts_count': contracts_count,
            'contracts_not_published': contracts_not_published,
            'contracts_not_published_count': contracts_not_published_count}
