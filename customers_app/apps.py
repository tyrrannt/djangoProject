from django.apps import AppConfig


class CustomersAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'customers_app'
    verbose_name = 'Пользователи'

    def ready(self):
        import customers_app.signals
