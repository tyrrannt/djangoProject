from django.core.management.base import BaseCommand
from customers_app.models import DataBaseUser


class Command(BaseCommand):
    def handle(self, *args, **options):
        super_user = DataBaseUser.objects.create_superuser('shakirov', 'shakirov.vitaliy@gmail.com', 'EpicBoss08108108',
                                                           age=40)
