from django.apps import AppConfig


class FinanceAppConfig(AppConfig):
    """
    Конфигурация приложения finance_app.
    """
    default_auto_field = "django.db.models.BigAutoField"
    name = "finance_app"
    verbose_name = "Финансовый блок"

    def ready(self) -> None:
        """
        Метод инициализации приложения. Импортирует сигналы.
        """
        import finance_app.signals
