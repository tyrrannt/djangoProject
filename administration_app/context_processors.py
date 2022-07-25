from contracts_app.models import Contract, TypeContract, TypeProperty
from customers_app.models import DataBaseUser, Counteragent, Division


def get_all_contracts(request):
    all_contract = Contract.objects.all().count()
    all_users = DataBaseUser.objects.all()
    all_type_of_contract = TypeContract.objects.all()
    all_type_property = TypeProperty.objects.all()
    all_counteragent = Counteragent.objects.all()
    all_prolongation = Contract.type_of_prolongation
    all_divisions = Division.objects.all()
    return {'all_contract': all_contract, 'employee': all_users, 'type_property': all_type_property,
            'counteragent': all_counteragent, 'prolongation': all_prolongation, 'division': all_divisions,
            'type_contract': all_type_of_contract}
