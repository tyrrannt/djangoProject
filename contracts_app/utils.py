from contracts_app.models import TypeContract, TypeProperty, Contract
from customers_app.models import DataBaseUser, Counteragent, Division


class GetAllObject:

    def get_object(self):
        context = {}
        all_users = DataBaseUser.objects.all()
        all_type_of_contract = TypeContract.objects.all()
        all_type_property = TypeProperty.objects.all()
        all_counteragent = Counteragent.objects.all()
        all_prolongation = Contract.type_of_prolongation
        all_divisions = Division.objects.all()
        context['employee'] = all_users
        context['type_property'] = all_type_property
        context['counteragent'] = all_counteragent
        context['prolongation'] = all_prolongation
        context['division'] = all_divisions
        context['type_contract'] = all_type_of_contract
        return context
