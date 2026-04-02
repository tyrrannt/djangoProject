from django.apps import AppConfig


class TicketsAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = "tickets_app"
    verbose_name = 'Книга жалоб и предложений'

    def ready(self):
        import tickets_app.signals