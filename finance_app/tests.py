from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

from customers_app.models import Counteragent
from finance_app.models import (
    Organization,
    ObligationType,
    FinancialContract,
    FinancialObligation,
    PaymentSchedule,
    PaymentFact,
    DebtSnapshot,
    CreditAgreement,
    CreditPaymentSchedule,
    CreditPaymentFact,
    Notification,
    SyncLog,
    FinanceAuditLog,
    UserNotificationSetting,
)
from finance_app.services.sync_service import SyncService
from finance_app.services.notification_service import NotificationService
from finance_app.services.finance_selector import FinanceSelector
from finance_app.services.report_service import ReportService
from finance_app.middleware import _thread_locals

User = get_user_model()


class FinanceAppTestCase(TestCase):
    """
    Класс тестирования функционала финансового блока.
    """

    def setUp(self) -> None:
        """
        Инициализация тестовых данных перед каждым тестом.
        """
        # Создаем тестового пользователя
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@barkol.ru",
            password="testpassword",
            first_name="Тест",
            last_name="Тестовый"
        )
        # Устанавливаем пользователя в thread-local для тестов сигналов аудита
        _thread_locals.user = self.user

        # Создаем типы обязательств
        self.ob_type_credit, _ = ObligationType.objects.get_or_create(
            code="credit", defaults={"name": "Банковский кредит"}
        )
        self.ob_type_provider, _ = ObligationType.objects.get_or_create(
            code="provider", defaults={"name": "Договор с поставщиком"}
        )

        # Создаем тестовую организацию
        self.org = Organization.objects.create(
            name="Тестовое ЮЛ Баркол",
            inn="7701000001",
            kpp="770101001",
            ogrn="1027700000001",
            ref_key="org-ref-123"
        )

        # Создаем тестового контрагента
        self.counteragent = Counteragent.objects.create(
            short_name="Тестовый Контрагент",
            inn="7702000002",
            type_counteragent="juridical_person",
            ref_key="agent-ref-123"
        )

    def tearDown(self) -> None:
        """
        Очистка thread-local после выполнения теста.
        """
        if hasattr(_thread_locals, "user"):
            del _thread_locals.user

    def test_audit_logging_create_update_delete(self) -> None:
        """
        Проверка автоматического логирования создания, изменения и удаления объектов.
        """
        # Проверяем аудит при создании
        contract = FinancialContract.objects.create(
            contract_number="TEST-001",
            date_conclusion=date.today(),
            counteragent=self.counteragent,
            organization=self.org,
            cost=Decimal("100000.00"),
            employee=self.user,
            ref_key="contract-ref-123"
        )
        content_type = ContentType.objects.get_for_model(FinancialContract)
        create_logs = FinanceAuditLog.objects.filter(
            content_type=content_type, object_id=contract.pk, action="create"
        )
        self.assertEqual(create_logs.count(), 1)
        self.assertEqual(create_logs.first().user, self.user)

        # Проверяем аудит при изменении
        contract.cost = Decimal("150000.00")
        contract.save()
        update_logs = FinanceAuditLog.objects.filter(
            content_type=content_type, object_id=contract.pk, action="update"
        )
        self.assertEqual(update_logs.count(), 1)
        self.assertEqual(update_logs.first().field_name, "Сумма договора")
        self.assertEqual(update_logs.first().old_value, "100000.00")
        self.assertEqual(update_logs.first().new_value, "150000.00")

        # Проверяем аудит при удалении
        contract_id = contract.pk
        contract.delete()
        delete_logs = FinanceAuditLog.objects.filter(
            content_type=content_type, object_id=contract_id, action="delete"
        )
        self.assertEqual(delete_logs.count(), 1)

    def test_payment_schedule_status_flow(self) -> None:
        """
        Проверка расчета статусов графиков плановых платежей.
        """
        contract = FinancialContract.objects.create(
            contract_number="TEST-002",
            date_conclusion=date.today() - timedelta(days=60),
            counteragent=self.counteragent,
            organization=self.org,
            cost=300000.00,
            end_date=date.today() + timedelta(days=300)
        )
        obligation = FinancialObligation.objects.create(
            contract=contract,
            counteragent=self.counteragent,
            cost=300000.00,
            date_origin=contract.date_conclusion,
            date_execution=contract.end_date,
            obligation_type=self.ob_type_provider
        )

        # Создаем 3 плановых платежа
        ps1 = PaymentSchedule.objects.create(
            obligation=obligation,
            payment_date=date.today() - timedelta(days=10),  # Просрочен
            amount=100000.00,
            status="planned"
        )
        ps2 = PaymentSchedule.objects.create(
            obligation=obligation,
            payment_date=date.today() + timedelta(days=20),  # В будущем
            amount=100000.00,
            status="planned"
        )

        # 1. Запускаем обновление статусов без оплат
        SyncService.update_payment_schedules_statuses()
        ps1.refresh_from_db()
        ps2.refresh_from_db()
        self.assertEqual(ps1.status, "overdue")
        self.assertEqual(ps2.status, "planned")

        # 2. Добавляем частичную оплату
        PaymentFact.objects.create(
            obligation=obligation,
            payment_date=date.today() - timedelta(days=12),
            amount=50000.00,
            payment_doc_number="DOC-1"
        )
        SyncService.update_payment_schedules_statuses()
        ps1.refresh_from_db()
        self.assertEqual(ps1.status, "partially_paid")

        # 3. Добавляем полную оплату
        PaymentFact.objects.create(
            obligation=obligation,
            payment_date=date.today() - timedelta(days=8),
            amount=60000.00,
            payment_doc_number="DOC-2"
        )
        SyncService.update_payment_schedules_statuses()
        ps1.refresh_from_db()
        self.assertEqual(ps1.status, "paid")

    def test_credit_agreement_schedules_and_debts(self) -> None:
        """
        Проверка генерации аннуитетного графика по кредиту и расчета остатка задолженности.
        """
        credit = CreditAgreement.objects.create(
            bank=self.counteragent,
            contract_number="CRED-999",
            contract_date=date.today() - timedelta(days=90),
            amount=1200000.00,
            interest_rate=12.00,
            term_months=12,
            remaining_debt=1200000.00,
            employee=self.user
        )

        # Генерируем график
        SyncService._generate_credit_schedules(credit)
        schedules = credit.payment_schedules.all()
        self.assertEqual(schedules.count(), 12)

        # Складываем сумму по графику основного долга
        total_principal = sum(s.principal for s in schedules)
        self.assertAlmostEqual(float(total_principal), 1200000.00, places=2)

        # Добавим факт оплаты кредита (покрываем первый платеж)
        first_schedule = schedules.first()
        CreditPaymentFact.objects.create(
            credit_agreement=credit,
            schedule=first_schedule,
            payment_date=first_schedule.payment_date,
            amount=first_schedule.total_amount,
            payment_doc_number="PAY-CRED-1"
        )

        SyncService.update_credits_statuses()
        credit.refresh_from_db()
        first_schedule.refresh_from_db()

        self.assertEqual(first_schedule.status, "paid")
        self.assertTrue(credit.remaining_debt < credit.amount)

    @override_settings(EMAIL_HOST_USER="test@barkol.ru")
    def test_notification_channels(self) -> None:
        """
        Проверка логики отправки уведомлений и настроек пользователя.
        """
        # Настраиваем каналы уведомлений пользователя
        settings_obj = UserNotificationSetting.objects.create(
            user=self.user,
            portal_enabled=True,
            email_enabled=True,
            telegram_enabled=True
        )
        self.user.telegram_id = "123456789"
        self.user.save()

        # Мокаем отправку писем и telegram-сообщений
        with patch("finance_app.services.notification_service.send_mail") as mock_mail, \
             patch("requests.post") as mock_post:
            
            mock_mail.return_value = 1
            mock_post.return_value.status_code = 200

            NotificationService.send_notification_to_user(self.user, "Тестовое сообщение")

            # Проверяем, что в БД созданы 3 уведомления (для каждого канала)
            notifications = Notification.objects.filter(user=self.user)
            self.assertEqual(notifications.count(), 3)
            self.assertTrue(notifications.filter(channel="portal").exists())
            self.assertTrue(notifications.filter(channel="email").exists())
            self.assertTrue(notifications.filter(channel="telegram").exists())

            # Проверяем вызовы моков
            mock_mail.assert_called_once()
            mock_post.assert_called_once()

    @patch("finance_app.services.sync_service.get_jsons_data")
    def test_sync_service_fallback_on_odata_error(self, mock_get_jsons) -> None:
        """
        Проверка, что сервис синхронизации успешно отрабатывает с mock-данными,
        если 1С OData недоступна (возвращает пустые словари).
        """
        # Имитируем падение соединения
        mock_get_jsons.return_value = {"value": ""}

        # Запускаем синхронизацию
        orgs_count = SyncService.sync_organizations()
        agents_count = SyncService.sync_counteragents()

        self.assertTrue(orgs_count > 0)
        self.assertTrue(agents_count > 0)

        # Проверяем наличие SyncLog со статусом success
        logs = SyncLog.objects.filter(status="success")
        self.assertEqual(logs.count(), 2)

    def test_finance_selector_dashboard_data(self) -> None:
        """
        Проверка правильности формирования данных для дашборда через FinanceSelector.
        """
        # Создаем финансовый договор
        contract = FinancialContract.objects.create(
            contract_number="CAL-001",
            date_conclusion=date.today(),
            counteragent=self.counteragent,
            organization=self.org,
            cost=Decimal("200000.00"),
            employee=self.user,
            ref_key="contract-cal-123"
        )
        # Обязательство
        obligation = FinancialObligation.objects.create(
            contract=contract,
            counteragent=self.counteragent,
            cost=Decimal("200000.00"),
            date_origin=date.today(),
            date_execution=date.today() + timedelta(days=30),
            obligation_type=self.ob_type_provider,
            status="active"
        )
        
        # Получаем данные дашборда для суперпользователя (видит всё)
        self.user.is_superuser = True
        self.user.save()
        
        dashboard_data = FinanceSelector.get_dashboard_data(self.user)
        self.assertEqual(dashboard_data["total_sum"], 200000.00)
        self.assertEqual(dashboard_data["creditor_total_debt"], 200000.00)
        self.assertEqual(dashboard_data["debtor_total_debt"], 0.00)

    def test_finance_selector_visibility_filter(self) -> None:
        """
        Проверка фильтрации видимости объектов для обычных пользователей.
        """
        # Создаем другого пользователя
        other_user = User.objects.create_user(
            username="otheruser",
            email="other@barkol.ru",
            password="password"
        )
        
        # Договор первого пользователя
        FinancialContract.objects.create(
            contract_number="USER-1",
            date_conclusion=date.today(),
            counteragent=self.counteragent,
            organization=self.org,
            cost=Decimal("50000.00"),
            employee=self.user,
            ref_key="c-1"
        )
        
        # Договор второго пользователя
        FinancialContract.objects.create(
            contract_number="USER-2",
            date_conclusion=date.today(),
            counteragent=self.counteragent,
            organization=self.org,
            cost=Decimal("80000.00"),
            employee=other_user,
            ref_key="c-2"
        )
        
        # Обычный пользователь видит только свои договоры
        visible_contracts = FinanceSelector.apply_visibility_filter(other_user, FinancialContract.objects.all())
        self.assertEqual(visible_contracts.count(), 1)
        self.assertEqual(visible_contracts.first().contract_number, "USER-2")

    def test_report_service_generation(self) -> None:
        """
        Проверка генерации отчетов в XLSX и PDF форматах.
        """
        # Создаем данные для отчетов
        FinancialContract.objects.create(
            contract_number="REP-001",
            date_conclusion=date.today(),
            counteragent=self.counteragent,
            organization=self.org,
            cost=Decimal("150000.00"),
            employee=self.user,
            ref_key="rep-ref"
        )
        
        # Тестируем генерацию XLSX
        xlsx_bytes = ReportService.generate_xlsx("contracts_registry", self.user)
        self.assertTrue(len(xlsx_bytes) > 0)
        
        # Тестируем генерацию PDF
        pdf_bytes = ReportService.generate_pdf("contracts_registry", self.user)
        self.assertTrue(len(pdf_bytes) > 0)

    def test_views_dashboard_and_reports(self) -> None:
        """
        Проверка доступности представлений дашборда, календаря и отчетов.
        """
        self.client.force_login(self.user)
        
        # Дашборд
        response = self.client.get("/finance/")
        self.assertEqual(response.status_code, 200)
        
        # Календарь
        response = self.client.get("/finance/calendar/")
        self.assertEqual(response.status_code, 200)
        
        # Отчеты
        response = self.client.get("/finance/reports/")
        self.assertEqual(response.status_code, 200)
        
        # Экспорт отчета в XLSX
        response = self.client.get("/finance/reports/contracts_registry/export/?format=xlsx")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        # Экспорт отчета в PDF
        response = self.client.get("/finance/reports/contracts_registry/export/?format=pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
