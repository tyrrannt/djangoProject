from django.core.management import BaseCommand


class Command(BaseCommand):
    help = 'Запуск бота'

    def handle(self, *args, **options):
        pass