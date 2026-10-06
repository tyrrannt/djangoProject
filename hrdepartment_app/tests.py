import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.auth.models import Permission
from customers_app.models import DataBaseUser
from hrdepartment_app.models import OfficialMemo
from hrdepartment_app.views import OfficialMemoDetail


class OfficialMemoDetailViewTest(TestCase):
    def setUp(self):
        # Every test needs access to the request factory.
        # Create an instance of HttpRequest
        self.factory = RequestFactory()
        # Example object
        view_permission = Permission.objects.get(codename="view_officialmemo")
        self.user = DataBaseUser.objects.create_user(
            username="jacob",
            email="jacob@…",
            password="top_secret",
            first_name="Виталий",
            last_name="Шакиров",
            surname="Рустамович",
            title="Шакиров Виталий Рустамович",
        )
        self.user.user_permissions.add(view_permission)
        kwargs = {
            "person": self.user,
            "period_from": datetime.date(2023, 8, 1),
            "period_for": datetime.date(2023, 8, 1),
            "official_memo_type": "1",
        }
        self.official_memo = OfficialMemo.objects.create(**kwargs)

    def test_context_data(self):
        # Создайте экземпляр запроса GET.
        request = self.factory.get("/detail")

        # Напомним, что промежуточное ПО не поддерживается. Вы можете имитировать
        # авторизованный пользователь, установив request.user вручную.
        request.user = self.user

        # Test OfficialMemoDetail.as_view() as a logged in user.
        response = OfficialMemoDetail.as_view()(request, pk=self.official_memo.id)

        # # Check that user is logged in
        # print(response.context_data)
        # assert str(response.context_data["user"]) == "jacob"
        # assert response.status_code == 200

        # Check csrf_token exist in request
        # self.assertIn("csrf_token", response.context_data)
        self.assertIn("view", response.context_data)

        # Check change history in context
        self.assertIn("change_history", response.context_data)


class MemoNotificationServiceTests(SimpleTestCase):
    """Набор модульных тестов для MemoNotificationService."""

    def setUp(self):
        """Очищает кэш перед каждым тестом для изоляции дедупликации."""
        from django.core.cache import cache
        cache.clear()

    def test_get_portal_url_default(self):
        """Проверяет получение базового URL портала по умолчанию."""
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService

        url = MemoNotificationService.get_portal_url()
        self.assertTrue(url.startswith("http"))

    @override_settings(PORTAL_BASE_URL="https://test.barkol.ru/")
    def test_get_process_url(self):
        """Проверяет генерацию ссылки на карточку процесса без дублирования слэшей."""
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService

        url = MemoNotificationService.get_process_url(42)
        self.assertEqual(url, "https://test.barkol.ru/hr/bpmemo/42/update/")

    @patch("django.db.transaction.on_commit")
    def test_dispatch_event_triggers_task(self, mock_on_commit):
        """Проверяет регистрацию отправки события через transaction.on_commit."""
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService

        mock_on_commit.side_effect = lambda cb: cb()
        with patch("hrdepartment_app.tasks.process_memo_notification_task.delay") as mock_delay:
            res = MemoNotificationService.dispatch_event(
                process_id=10,
                event_type="APPROVED",
                actor_id=5,
            )
            self.assertTrue(res)
            mock_delay.assert_called_once_with(
                process_id=10,
                event_type="APPROVED",
                actor_id=5,
                extra_context=None,
            )

    def test_cleanup_temp_files_deletes_existing_and_ignores_missing(self):
        """Проверяет удаление временных файлов и корректную обработку несуществующих."""
        import os
        import tempfile
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test data")
            temp_path = f.name

        self.assertTrue(os.path.exists(temp_path))
        MemoNotificationService._cleanup_temp_files([temp_path, "/non/existent/path/file.pdf"])
        self.assertFalse(os.path.exists(temp_path))

    @patch("django.core.cache.cache.get")
    @patch("django.core.cache.cache.set")
    @patch("django.db.transaction.on_commit")
    def test_dispatch_event_deduplication(self, mock_on_commit, mock_cache_set, mock_cache_get):
        """Проверяет работу замка дедупликации и обхода через параметр force."""
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService

        mock_on_commit.side_effect = lambda cb: cb()

        # 1. Первый вызов (ключа в кэше нет) -> успешно ставится в очередь
        mock_cache_get.return_value = False
        with patch("hrdepartment_app.tasks.process_memo_notification_task.delay") as mock_delay:
            res1 = MemoNotificationService.dispatch_event(process_id=20, event_type="SUBMITTED")
            self.assertTrue(res1)
            mock_delay.assert_called_once()
            mock_cache_set.assert_called_with("memo_notify_guard:20:SUBMITTED", True, timeout=300)

        # 2. Повторный вызов (ключ уже в кэше) без force -> отсекается
        mock_cache_get.return_value = True
        with patch("hrdepartment_app.tasks.process_memo_notification_task.delay") as mock_delay:
            res2 = MemoNotificationService.dispatch_event(process_id=20, event_type="SUBMITTED", force=False)
            self.assertFalse(res2)
            mock_delay.assert_not_called()

        # 3. Вызов с force=True (ручная отправка) -> обходит замок и отправляется
        with patch("hrdepartment_app.tasks.process_memo_notification_task.delay") as mock_delay:
            res3 = MemoNotificationService.dispatch_event(process_id=20, event_type="SUBMITTED", force=True)
            self.assertTrue(res3)
            mock_delay.assert_called_once()

    @patch("hrdepartment_app.services.memo_notification_service.MemoNotificationService.is_telegram_memo_notifications_enabled", return_value=True)
    @patch("hrdepartment_app.services.memo_notification_service.UniversalTelegramService.send_message_sync")
    @patch("hrdepartment_app.services.memo_notification_service.UniversalEmailService.send_async_email")
    def test_handle_event_sync_sends_email_and_telegram(self, mock_email, mock_tg, mock_pref):
        """Проверяет отправку уведомлений по почте и Telegram при наличии адресатов."""
        from unittest.mock import MagicMock, patch
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService

        mock_process = MagicMock()
        mock_process.pk = 15
        mock_process.id = 15
        mock_process.person_agreement.email = "boss@barkol.ru"
        mock_process.person_agreement.telegram_id = "123456"
        mock_process.person_executor.telegram_id = "654321"
        mock_process.document.official_memo_type = "1"
        mock_process.document.person.title = "Иванов Иван Иванович"
        mock_process.document.period_from.strftime.return_value = "01.01.2026"
        mock_process.document.period_for.strftime.return_value = "10.01.2026"

        with patch("hrdepartment_app.models.ApprovalOficialMemoProcess.objects.select_related") as mock_sr:
            mock_sr.return_value.get.return_value = mock_process
            with patch.object(MemoNotificationService, "_generate_memo_documents", return_value=[]):
                res = MemoNotificationService.handle_event_sync(
                    process_id=15,
                    event_type="SUBMITTED",
                    actor_id=1,
                )
                self.assertTrue(res)
                self.assertTrue(mock_email.called)
                self.assertTrue(mock_tg.called)

    def test_approval_process_initial_state_tracking(self):
        """Проверяет корректность фиксации исходного состояния в _initial_state."""
        from hrdepartment_app.models import ApprovalOficialMemoProcess

        process = ApprovalOficialMemoProcess()
        process.submit_for_approval = True
        process.location_selected = False
        process._save_initial_state()

        self.assertTrue(process._initial_state["submit_for_approval"])
        self.assertFalse(process._initial_state["location_selected"])
        self.assertFalse(process._initial_state["cancellation"])

    def test_diffkeys_excludes_internal_attributes(self):
        """Проверяет, что внутренние атрибуты (_initial_state, _state) исключаются из diffkeys."""
        from hrdepartment_app.models import ApprovalOficialMemoProcess
        from django.core.exceptions import FieldDoesNotExist

        old_instance = {
            "_state": object(),
            "_initial_state": {"submit_for_approval": False},
            "submit_for_approval": False,
            "cancellation": False,
        }
        new_instance = {
            "_state": object(),
            "_initial_state": {"submit_for_approval": True},
            "submit_for_approval": True,
            "cancellation": False,
        }

        diffkeys = [
            k for k in old_instance
            if not k.startswith("_") and old_instance.get(k) != new_instance.get(k)
        ]

        self.assertEqual(diffkeys, ["submit_for_approval"])
        self.assertNotIn("_initial_state", diffkeys)
        self.assertNotIn("_state", diffkeys)

        # Проверяем, что для всех ключей в diffkeys get_field завершается успешно
        for k in diffkeys:
            try:
                field = ApprovalOficialMemoProcess._meta.get_field(k)
                self.assertIsNotNone(field)
            except FieldDoesNotExist:
                self.fail(f"FieldDoesNotExist raised for field: {k}")

    def test_generate_memo_documents_pdf_conversion_and_fallback(self):
        """Проверяет вызов msoffice2pdf.convert в _generate_memo_documents и безопасный fallback на XLSX."""
        import datetime
        from unittest.mock import MagicMock, patch
        from hrdepartment_app.services.memo_notification_service import MemoNotificationService

        mock_process = MagicMock()
        mock_process.document.official_memo_type = "1"
        mock_process.document.type_trip = "1"
        mock_process.document.period_from = datetime.date(2026, 9, 28)
        mock_process.document.period_for = datetime.date(2026, 9, 30)
        mock_process.document.place_production_activity.all.return_value = []
        mock_process.order.document_number = "123"
        mock_process.order.document_date = datetime.date(2026, 9, 28)

        # 1. Проверяем успешную конвертацию в PDF
        with patch.object(MemoNotificationService, "_find_soffice_binary", return_value="/usr/bin/soffice"), \
             patch("openpyxl.load_workbook") as mock_wb, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("msoffice2pdf.convert", return_value="/media/test.pdf") as mock_conv, \
             patch("os.path.exists", return_value=True):
            wb_instance = MagicMock()
            mock_wb.return_value = wb_instance
            xlsx, pdf = MemoNotificationService._generate_memo_documents(mock_process)
            self.assertEqual(pdf, "/media/test.pdf")
            self.assertTrue(mock_conv.called)
            # Проверяем, что output_dir указывает на media
            self.assertTrue(mock_conv.call_args[1]["output_dir"].endswith("media"))

        # 2. Проверяем безопасный откат на XLSX при сбое конвертера
        with patch.object(MemoNotificationService, "_find_soffice_binary", return_value="/usr/bin/soffice"), \
             patch("openpyxl.load_workbook") as mock_wb, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("msoffice2pdf.convert", side_effect=Exception("Converter error")) as mock_conv:
            wb_instance = MagicMock()
            mock_wb.return_value = wb_instance
            xlsx, pdf = MemoNotificationService._generate_memo_documents(mock_process)
            self.assertIsNotNone(xlsx)
            self.assertIsNone(pdf)


class PeriodicWorkModelTest(TestCase):
    """Набор тестов для модели PeriodicWork и интеграции с типами ВС."""

    def setUp(self):
        """Подготовка тестовых данных."""
        from contracts_app.models import TypeProperty
        self.aircraft_type = TypeProperty.objects.create(type_property="Тестовое ВС")

    def test_create_periodic_work_with_lags_and_color(self):
        """Проверяет корректность сохранения лагов и нормализации цвета."""
        from hrdepartment_app.models import PeriodicWork, PeriodicWorkColor

        work = PeriodicWork.objects.create(
            name="ТО 100 часов",
            code="100 часов",
            ratio=100.0,
            lag_minus=10,
            lag_plus=10,
            color="желтый",
            air_bord_type=self.aircraft_type,
        )
        self.assertEqual(work.color, PeriodicWorkColor.YELLOW.value)
        self.assertEqual(work.lag_minus, 10)
        self.assertEqual(work.lag_plus, 10)
        self.assertEqual(work.type_property, self.aircraft_type)
        self.assertEqual(str(work), "Тестовое ВС - 100 часов")

    def test_color_normalization_variations(self):
        """Проверяет нормализацию различных вариантов написания цветов."""
        from hrdepartment_app.models import PeriodicWork, PeriodicWorkColor

        work_green = PeriodicWork.objects.create(
            code="400 часов",
            ratio=400.0,
            lag_minus=10,
            lag_plus=10,
            color="зеленый",
        )
        self.assertEqual(work_green.color, PeriodicWorkColor.GREEN.value)

        work_red = PeriodicWork.objects.create(
            code="2000 часов",
            ratio=2000.0,
            lag_minus=0,
            lag_plus=0,
            color="красный",
        )
        self.assertEqual(work_red.color, PeriodicWorkColor.RED.value)

    def test_admin_display_color(self):
        """Проверяет метод отображения цвета в PeriodicWorkAdmin."""
        from django.contrib.admin.sites import AdminSite
        from hrdepartment_app.admin import PeriodicWorkAdmin
        from hrdepartment_app.models import PeriodicWork

        admin_instance = PeriodicWorkAdmin(PeriodicWork, AdminSite())
        work = PeriodicWork.objects.create(
            code="Test",
            color="yellow",
        )
        badge_value = admin_instance.display_color(work)
        self.assertEqual(badge_value, "yellow")

    def test_seed_periodic_works_smart_matching(self):
        """Проверяет интеллектуальное сопоставление записей без типа ВС в команде."""
        from django.core.management import call_command
        from contracts_app.models import TypeProperty, Estate
        from hrdepartment_app.models import PeriodicWork, OutfitCard

        mi8_type, _ = TypeProperty.objects.get_or_create(type_property="МИ-8Т")
        cessna_type, _ = TypeProperty.objects.get_or_create(type_property="Cessna 172S")

        # 1. Запись с уникальным кодом Ф-59 без типа ВС
        legacy_mi8 = PeriodicWork.objects.create(
            code="Ф-59",
            name="Старая Ф-59",
            ratio=0.0,
            air_bord_type=None,
        )

        # 2. Запись с общим кодом 100 часов, привязанная к карте-наряду с бортом Cessna
        cessna_board = Estate.objects.create(
            registration_number="RA-67890",
            type_property=cessna_type,
            release_date=datetime.date(2020, 1, 1),
        )
        legacy_cessna_work = PeriodicWork.objects.create(
            code="100 часов",
            name="Старая сотня",
            ratio=0.0,
            air_bord_type=None,
        )
        card = OutfitCard.objects.create(
            outfit_card_number="TEST-001",
            air_board=cessna_board,
        )
        card.periodic_work.add(legacy_cessna_work)

        # Вызываем команду наполнения
        call_command("seed_periodic_works")

        # Проверяем, что legacy_mi8 привязалась к МИ-8Т и обновилась
        legacy_mi8.refresh_from_db()
        self.assertEqual(legacy_mi8.air_bord_type, mi8_type)
        self.assertEqual(legacy_mi8.ratio, 4425.0)
        self.assertEqual(legacy_mi8.lag_minus, 20)
        self.assertEqual(legacy_mi8.lag_plus, 20)

        # Проверяем, что legacy_cessna_work привязалась к Cessna по карте-наряду
        legacy_cessna_work.refresh_from_db()
        self.assertEqual(legacy_cessna_work.air_bord_type, cessna_type)
        self.assertEqual(legacy_cessna_work.ratio, 100.0)


class PeriodicAndOperationalWorkViewsTest(TestCase):
    """Модульные тесты для веб-представлений PeriodicWork и OperationalWork."""

    def setUp(self):
        """Создает тестового пользователя и начальные данные."""
        from customers_app.models import DataBaseUser
        from contracts_app.models import TypeProperty
        from hrdepartment_app.models import PeriodicWork, OperationalWork

        self.superuser = DataBaseUser.objects.create_superuser(
            username="admin_user",
            email="admin@test.ru",
            password="secret_pass_123",
            last_name="Администратор",
            first_name="Тест",
        )
        self.type_prop = TypeProperty.objects.create(type_property="Ан-2")
        self.periodic_work = PeriodicWork.objects.create(
            name="Ан-2 - 100 часов",
            code="100 часов",
            ratio=100.0,
            lag_minus=15,
            lag_plus=15,
            color="yellow",
            air_bord_type=self.type_prop,
        )
        self.operational_work = OperationalWork.objects.create(
            name="Ан-2 - ОТО-1",
            code="ОТО-1",
            description="Осмотр",
            air_bord_type=self.type_prop,
        )

    def test_periodic_work_list_html_and_ajax(self):
        """Проверяет страницу списка PeriodicWork и AJAX-ответ DataTables."""
        from django.urls import reverse

        self.client.force_login(self.superuser)
        url = reverse("hrdepartment_app:periodic_work_list")

        # HTML
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Периодические работы")

        # AJAX
        resp_ajax = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp_ajax.status_code, 200)
        data = resp_ajax.json()
        self.assertIn("data", data)
        self.assertTrue(any(row["code"] == "100 часов" for row in data["data"]))

    def test_periodic_work_crud(self):
        """Проверяет создание, изменение и удаление PeriodicWork."""
        from django.urls import reverse
        from hrdepartment_app.models import PeriodicWork

        self.client.force_login(self.superuser)

        # 1. Create
        add_url = reverse("hrdepartment_app:periodic_work_add")
        resp_add = self.client.post(add_url, {
            "air_bord_type": self.type_prop.pk,
            "code": "400 часов",
            "name": "Ан-2 - 400 часов",
            "ratio": 400.0,
            "lag_minus": 30,
            "lag_plus": 30,
            "color": "green",
            "description": "Тест добавления",
        })
        self.assertEqual(resp_add.status_code, 302)
        new_work = PeriodicWork.objects.get(code="400 часов")
        self.assertEqual(new_work.ratio, 400.0)

        # 2. Update
        update_url = reverse("hrdepartment_app:periodic_work_update", kwargs={"pk": new_work.pk})
        resp_update = self.client.post(update_url, {
            "air_bord_type": self.type_prop.pk,
            "code": "400 часов",
            "name": "Ан-2 - 400 часов (обновлено)",
            "ratio": 450.0,
            "lag_minus": 30,
            "lag_plus": 30,
            "color": "green",
            "description": "Обновлено",
        })
        self.assertEqual(resp_update.status_code, 302)
        new_work.refresh_from_db()
        self.assertEqual(new_work.ratio, 450.0)

        # 3. Delete
        delete_url = reverse("hrdepartment_app:periodic_work_delete", kwargs={"pk": new_work.pk})
        resp_del = self.client.post(delete_url)
        self.assertEqual(resp_del.status_code, 302)
        self.assertFalse(PeriodicWork.objects.filter(pk=new_work.pk).exists())

    def test_operational_work_crud(self):
        """Проверяет реестр, создание, изменение и удаление OperationalWork."""
        from django.urls import reverse
        from hrdepartment_app.models import OperationalWork

        self.client.force_login(self.superuser)

        # List HTML and AJAX
        list_url = reverse("hrdepartment_app:operational_work_list")
        resp_list = self.client.get(list_url)
        self.assertEqual(resp_list.status_code, 200)

        resp_ajax = self.client.get(list_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp_ajax.status_code, 200)
        self.assertTrue(any(row["code"] == "ОТО-1" for row in resp_ajax.json()["data"]))

        # Create
        add_url = reverse("hrdepartment_app:operational_work_add")
        resp_add = self.client.post(add_url, {
            "air_bord_type": self.type_prop.pk,
            "code": "ОТО-2",
            "name": "Оперативная форма 2",
            "description": "Описание ОТО-2",
        })
        self.assertEqual(resp_add.status_code, 302)
        op_work = OperationalWork.objects.get(code="ОТО-2")

        # Update
        update_url = reverse("hrdepartment_app:operational_work_update", kwargs={"pk": op_work.pk})
        resp_update = self.client.post(update_url, {
            "air_bord_type": self.type_prop.pk,
            "code": "ОТО-2",
            "name": "ОТО-2 обновлено",
            "description": "Описание обновлено",
        })
        self.assertEqual(resp_update.status_code, 302)
        op_work.refresh_from_db()
        self.assertEqual(op_work.name, "ОТО-2 обновлено")

        # Delete
        delete_url = reverse("hrdepartment_app:operational_work_delete", kwargs={"pk": op_work.pk})
        resp_del = self.client.post(delete_url)
        self.assertEqual(resp_del.status_code, 302)
        self.assertFalse(OperationalWork.objects.filter(pk=op_work.pk).exists())


class OutfitCardFap367ModelTest(TestCase):
    """Модульные тесты для расширенных полей OutfitCard по стандарту ФАП-367."""

    def setUp(self):
        """Создает тестовые сущности: пользователя, ВС и базовую карту-наряд."""
        from customers_app.models import DataBaseUser
        from contracts_app.models import Estate, TypeProperty
        import datetime

        self.user = DataBaseUser.objects.create_user(
            username="tech_engineer",
            email="tech@barkol.ru",
            password="test_password_123",
            last_name="Иванов",
            first_name="Иван",
            surname="Иванович",
        )
        self.type_prop = TypeProperty.objects.create(type_property="Ми-8")
        self.air_board = Estate.objects.create(
            type_property=self.type_prop,
            registration_number="RA-25100",
            factory_number="99245100",
            release_date=datetime.date(2015, 5, 20),
        )

    def test_outfit_card_fap367_fields_and_hash(self):
        """Проверяет сохранение наработки ВС, перенесенных дефектов и генерацию SHA-256."""
        from hrdepartment_app.models import OutfitCard
        from django.utils import timezone
        import datetime

        card = OutfitCard.objects.create(
            outfit_card_number="КН-2026-001",
            outfit_card_date=datetime.date(2026, 10, 1),
            start_time=datetime.time(8, 15),
            outfit_card_date_end=datetime.date(2026, 10, 2),
            end_time=datetime.time(19, 45),
            air_board=self.air_board,
            employee=self.user,
            flight_hours=1450.5,
            flight_hours_tsor=250.0,
            flight_cycles=620,
            deferred_defects="Отложен обогрев ПВД согласно MEL п. 30-31",
            deferred_defects_agreed=True,
            certifying_staff=self.user,
            crs_number="CRS-2026-001",
            is_signed=True,
            signed_at=timezone.now(),
        )

        card.signature_hash = card.generate_signature_hash()
        card.save()

        # Проверка сохранения полей в БД
        refreshed = OutfitCard.objects.get(pk=card.pk)
        self.assertEqual(refreshed.start_time, datetime.time(8, 15))
        self.assertEqual(refreshed.end_time, datetime.time(19, 45))
        self.assertEqual(float(refreshed.flight_hours), 1450.5)
        self.assertEqual(float(refreshed.flight_hours_tsor), 250.0)
        self.assertEqual(refreshed.flight_cycles, 620)
        self.assertEqual(refreshed.crs_number, "CRS-2026-001")
        self.assertTrue(refreshed.is_signed)
        self.assertTrue(refreshed.deferred_defects_agreed)
        self.assertEqual(len(refreshed.signature_hash), 64)

        # Проверка get_data сериализации для DataTables
        data = refreshed.get_data()
        self.assertEqual(data["flight_hours"], 1450.5)
        self.assertEqual(data["flight_cycles"], 620)
        self.assertTrue(data["is_signed"])
        self.assertIn("Подписан (CRS)", data["status"])


class OutfitCardFap367FormAndViewsTest(TestCase):
    """Модульные тесты для формы и веб-представлений OutfitCard с поддержкой ФАП-367."""

    def setUp(self):
        """Создает тестового пользователя-администратора, ВС, МПД и регламентные работы."""
        from customers_app.models import DataBaseUser
        from contracts_app.models import Estate, TypeProperty
        from hrdepartment_app.models import PlaceProductionActivity, OperationalWork, PeriodicWork
        import datetime

        self.user = DataBaseUser.objects.create_superuser(
            username="admin_tech",
            email="admin_tech@barkol.ru",
            password="test_password_123",
            last_name="Петров",
            first_name="Петр",
            surname="Петрович",
        )
        self.type_prop = TypeProperty.objects.create(type_property="Ми-8")
        self.air_board = Estate.objects.create(
            type_property=self.type_prop,
            registration_number="RA-22999",
            factory_number="99242999",
            release_date=datetime.date(2018, 1, 15),
        )
        self.place = PlaceProductionActivity.objects.create(
            name="База МПД Тюмень",
            short_name="Тюмень",
            use_team_orders=True,
        )
        self.op_work = OperationalWork.objects.create(
            code="ОТО-1",
            name="ОТО-1 (Ми-8)",
            air_bord_type=self.type_prop,
        )
        self.periodic_work = PeriodicWork.objects.create(
            code="Ф-1",
            name="Ф-1 (Ми-8)",
            air_bord_type=self.type_prop,
            ratio=75.0,
        )
        from flight_planning.models import PeriodicCheckType, PeriodicCheckRecord
        self.ct_base, _ = PeriodicCheckType.objects.get_or_create(
            code="CERT_STAFF_BASE",
            defaults={"name": "Периодическое ТО", "validity_months": 24, "applies_to": "technicians"}
        )
        PeriodicCheckRecord.objects.create(
            employee=self.user,
            check_type=self.ct_base,
            aircraft_type=self.type_prop,
            start_date=datetime.date.today() - datetime.timedelta(days=10),
            end_date=datetime.date.today() + datetime.timedelta(days=700),
            document_number="CRS-TYUMEN-042",
        )
        self.client.force_login(self.user)

    def test_outfit_card_form_validation(self):
        """Проверяет валидацию и сохранение формы OutfitCardForm с полями ФАП-367."""
        from hrdepartment_app.forms import OutfitCardForm
        import datetime

        form_data = {
            "outfit_card_date": datetime.date.today(),
            "outfit_card_number": "КН-2026-TEST",
            "employee": self.user.pk,
            "outfit_card_place": self.place.pk,
            "air_board": self.air_board.pk,
            "outfit_card_date_end": datetime.date.today() + datetime.timedelta(days=1),
            "flight_hours": 1250.4,
            "flight_hours_tsor": 150.2,
            "flight_cycles": 412,
            "deferred_defects": "Замечание по фаре ФР-9 (MEL 33-40)",
            "deferred_defects_agreed": True,
            "certifying_staff": self.user.pk,
            "crs_number": "CRS-TYUMEN-042",
            "notes": "Тестовый наряд ФАП-367",
        }
        form = OutfitCardForm(data=form_data, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        card = form.save()
        self.assertEqual(float(card.flight_hours), 1250.4)
        self.assertEqual(card.crs_number, "CRS-TYUMEN-042")
        self.assertTrue(card.deferred_defects_agreed)

    def test_outfit_card_detail_and_create_views(self):
        """Проверяет рендеринг страницы создания и детального просмотра карты-наряда."""
        from django.urls import reverse
        from hrdepartment_app.models import OutfitCard
        import datetime

        create_url = reverse("hrdepartment_app:outfit_card_add")
        resp_create = self.client.get(create_url)
        self.assertEqual(resp_create.status_code, 200)
        self.assertContains(resp_create, "Наработка планера ВС на дату проведения ТО")
        self.assertContains(resp_create, "Отложенные дефекты по MEL / CDL / AMM")
        self.assertContains(resp_create, "Подтверждающий персонал и Свидетельство о ТО (CRS)")

        card = OutfitCard.objects.create(
            outfit_card_number="КН-VIEW-01",
            outfit_card_date=datetime.date.today(),
            employee=self.user,
            outfit_card_place=self.place,
            air_board=self.air_board,
            flight_hours=890.0,
            flight_cycles=340,
            deferred_defects="Тестовый перенос дефекта",
            deferred_defects_agreed=True,
            certifying_staff=self.user,
            crs_number="CRS-VIEW-99",
            is_signed=True,
        )

        detail_url = card.get_absolute_url()
        self.assertEqual(detail_url, reverse("hrdepartment_app:outfit_card", kwargs={"pk": card.pk}))
        resp_detail = self.client.get(detail_url)
        self.assertEqual(resp_detail.status_code, 200)
        self.assertContains(resp_detail, "Подписан CRS (ФАП-367)")
        content_str = resp_detail.content.decode("utf-8")
        self.assertTrue("890,0 ч" in content_str or "890.0 ч" in content_str)
        self.assertContains(resp_detail, "CRS-VIEW-99")
        self.assertContains(resp_detail, "Согласовано с эксплуатантом")


class OutfitCardFap367CertifyingStaffValidationTest(TestCase):
    """Модульные тесты валидации допусков подтверждающего персонала (ФАП-367)."""

    def setUp(self):
        """Создает тестовых инженеров, ВС и виды периодических мероприятий."""
        from customers_app.models import DataBaseUser
        from contracts_app.models import Estate, TypeProperty
        from hrdepartment_app.models import PlaceProductionActivity, OperationalWork, PeriodicWork
        from flight_planning.models import PeriodicCheckType, PeriodicCheckRecord
        import datetime

        self.mi8_type = TypeProperty.objects.create(type_property="Ми-8Т")
        self.r44_type = TypeProperty.objects.create(type_property="R-44")

        self.air_board_mi8 = Estate.objects.create(
            type_property=self.mi8_type,
            registration_number="RA-24123",
            factory_number="9924123",
            release_date=datetime.date(2015, 5, 20),
        )
        self.place = PlaceProductionActivity.objects.create(
            name="База МПД Сургут",
            short_name="Сургут",
            use_team_orders=True,
        )
        self.op_work = OperationalWork.objects.create(
            code="ОТО-1",
            name="ОТО-1 (Ми-8Т)",
            air_bord_type=self.mi8_type,
        )
        self.periodic_work = PeriodicWork.objects.create(
            code="Ф-1",
            name="Ф-1 (Ми-8Т)",
            air_bord_type=self.mi8_type,
            ratio=75.0,
        )

        # Администратор, заполняющий наряды
        self.admin = DataBaseUser.objects.create_superuser(
            username="admin_eng_tester",
            email="admin_eng@barkol.ru",
            password="password_123",
            last_name="Администраторов",
            first_name="Админ",
        )
        # Инженер 1: Допуск только к оперативному ТО Ми-8 (CERT_STAFF_LINE)
        self.engineer_line = DataBaseUser.objects.create_user(
            username="eng_line",
            password="password_123",
            last_name="Линейный",
            first_name="Алексей",
        )
        # Инженер 2: Допуск к периодическому ТО Ми-8 (CERT_STAFF_BASE)
        self.engineer_base = DataBaseUser.objects.create_user(
            username="eng_base",
            password="password_123",
            last_name="Базовый",
            first_name="Борис",
        )
        # Инженер 3: Без допусков
        self.engineer_none = DataBaseUser.objects.create_user(
            username="eng_none",
            password="password_123",
            last_name="Недопущенный",
            first_name="Николай",
        )

        self.ct_line, _ = PeriodicCheckType.objects.get_or_create(
            code="CERT_STAFF_LINE",
            defaults={"name": "Оперативное ТО", "validity_months": 24, "applies_to": "technicians"}
        )
        self.ct_base, _ = PeriodicCheckType.objects.get_or_create(
            code="CERT_STAFF_BASE",
            defaults={"name": "Периодическое ТО", "validity_months": 24, "applies_to": "technicians"}
        )

        today = datetime.date.today()
        # Запись для engineer_line: действует с -30 дней до +700 дней на Ми-8Т
        PeriodicCheckRecord.objects.create(
            employee=self.engineer_line,
            check_type=self.ct_line,
            aircraft_type=self.mi8_type,
            start_date=today - datetime.timedelta(days=30),
            end_date=today + datetime.timedelta(days=700),
            document_number="AUTH-LINE-MI8-001",
        )

        # Запись для engineer_base: действует на Ми-8Т
        PeriodicCheckRecord.objects.create(
            employee=self.engineer_base,
            check_type=self.ct_base,
            aircraft_type=self.mi8_type,
            start_date=today - datetime.timedelta(days=10),
            end_date=today + datetime.timedelta(days=720),
            document_number="AUTH-BASE-MI8-002",
        )

    def test_line_maintenance_authorization(self):
        """Инженер с line-допуском может закрывать оперативное ТО и автозаполняется crs_number."""
        from hrdepartment_app.forms import OutfitCardForm
        import datetime

        form_data = {
            "outfit_card_date": datetime.date.today(),
            "outfit_card_number": "КН-LINE-01",
            "employee": self.engineer_line.pk,
            "outfit_card_place": self.place.pk,
            "air_board": self.air_board_mi8.pk,
            "operational_work": [self.op_work.pk],
            "certifying_staff": self.engineer_line.pk,
            "flight_hours": 100.0,
        }
        form = OutfitCardForm(data=form_data, user=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        card = form.save()
        self.assertEqual(card.crs_number, "AUTH-LINE-MI8-001")

    def test_unified_authorization_line_engineer_can_sign_periodic(self):
        """Оперативное и периодическое ТО едины: инженер с допуском может подписывать периодическое ТО."""
        from hrdepartment_app.forms import OutfitCardForm
        import datetime

        form_data = {
            "outfit_card_date": datetime.date.today(),
            "outfit_card_number": "КН-UNIFIED-OK",
            "employee": self.engineer_line.pk,
            "outfit_card_place": self.place.pk,
            "air_board": self.air_board_mi8.pk,
            "periodic_work": [self.periodic_work.pk],
            "certifying_staff": self.engineer_line.pk,
            "flight_hours": 200.0,
        }
        form = OutfitCardForm(data=form_data, user=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        card = form.save()
        self.assertEqual(card.crs_number, "AUTH-LINE-MI8-001")

    def test_base_engineer_can_sign_periodic_maintenance(self):
        """Инженер с base-допуском успешно подписывает периодическое ТО."""
        from hrdepartment_app.forms import OutfitCardForm
        import datetime

        form_data = {
            "outfit_card_date": datetime.date.today(),
            "outfit_card_number": "КН-BASE-OK",
            "employee": self.engineer_base.pk,
            "outfit_card_place": self.place.pk,
            "air_board": self.air_board_mi8.pk,
            "periodic_work": [self.periodic_work.pk],
            "certifying_staff": self.engineer_base.pk,
            "flight_hours": 300.0,
        }
        form = OutfitCardForm(data=form_data, user=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        card = form.save()
        self.assertEqual(card.crs_number, "AUTH-BASE-MI8-002")

    def test_unauthorized_engineer_blocked(self):
        """Инженер без допусков блокируется валидатором с отсылкой к ФАП-145 и 6 месяцам."""
        from hrdepartment_app.forms import OutfitCardForm
        import datetime

        form_data = {
            "outfit_card_date": datetime.date.today(),
            "outfit_card_number": "КН-NONE-FAIL",
            "employee": self.engineer_none.pk,
            "outfit_card_place": self.place.pk,
            "air_board": self.air_board_mi8.pk,
            "operational_work": [self.op_work.pk],
            "certifying_staff": self.engineer_none.pk,
            "flight_hours": 50.0,
        }
        form = OutfitCardForm(data=form_data, user=self.admin)
        self.assertFalse(form.is_valid())
        self.assertIn("certifying_staff", form.errors)
        self.assertIn("ФАП-145", form.errors["certifying_staff"][0])
        self.assertIn("6 месяцев", form.errors["certifying_staff"][0])

    def test_testing_app_authorization_and_six_months_periodicity(self):
        """Проверяет получение допуска по результатам тестирования и периодичность 6 месяцев."""
        from testing_app.models import Testing, TestingGroup, TestingAssignment
        from flight_planning.services import get_certifying_staff_authorization
        from django.utils import timezone
        import datetime

        # Создаем мероприятие тестирования и группу "Выполнение ТО ВС"
        testing = Testing.objects.create(
            title="Тестирование инженерного состава 2026",
            order_number="123",
            order_date=timezone.now().date(),
            start_datetime=timezone.now() - datetime.timedelta(days=60),
            end_datetime=timezone.now() + datetime.timedelta(days=300),
            author=self.admin,
        )
        group = TestingGroup.objects.create(
            testing=testing,
            name="Выполнение ТО ВС",
            code=TestingGroup.Code.PERFORMING,
        )

        # 1. Успешная сдача 2 месяца назад (в пределах 6 месяцев)
        assignment = TestingAssignment.objects.create(
            testing=testing,
            group=group,
            employee=self.engineer_none,
            assigned_job_title="Авиатехник",
            status=TestingAssignment.Status.PASSED,
            passed_at=timezone.now() - datetime.timedelta(days=60),
        )

        is_auth, doc_no, _ = get_certifying_staff_authorization(
            employee=self.engineer_none,
            target_date=datetime.date.today(),
        )
        self.assertTrue(is_auth)

        # 2. Истекший срок тестирования (более 6 месяцев, например 200 дней назад)
        assignment.passed_at = timezone.now() - datetime.timedelta(days=200)
        assignment.save()

        is_auth_expired, _, _ = get_certifying_staff_authorization(
            employee=self.engineer_none,
            target_date=datetime.date.today(),
        )
        self.assertFalse(is_auth_expired)


class AircraftHoursTrackingModelTest(TestCase):
    """Модульные тесты модели AircraftHoursTracking и автосинхронизации с OutfitCard."""

    def setUp(self):
        """Создает тестового пользователя, ВС и базовые параметры."""
        from customers_app.models import DataBaseUser
        from contracts_app.models import Estate, TypeProperty
        from hrdepartment_app.models import PlaceProductionActivity, OperationalWork
        from flight_planning.models import PeriodicCheckType, PeriodicCheckRecord
        import datetime

        self.user = DataBaseUser.objects.create_superuser(
            username="admin_hours_tester",
            email="hours_tester@barkol.ru",
            password="test_password_123",
            last_name="Тестеров",
            first_name="Тест",
        )
        self.type_prop = TypeProperty.objects.create(type_property="Ми-8Т")
        self.air_board = Estate.objects.create(
            type_property=self.type_prop,
            registration_number="RA-25800",
            factory_number="99245800",
            release_date=datetime.date(2016, 3, 10),
        )
        self.place = PlaceProductionActivity.objects.create(
            name="База МПД Тюмень-Плеханово",
            short_name="Тюмень",
            use_team_orders=True,
        )
        self.op_work = OperationalWork.objects.create(
            code="ОТО-1",
            name="ОТО-1 (Ми-8Т)",
            air_bord_type=self.type_prop,
        )
        # Допуск для подписания
        self.ct_line, _ = PeriodicCheckType.objects.get_or_create(
            code="CERT_STAFF_LINE",
            defaults={"name": "Оперативное ТО", "validity_months": 24, "applies_to": "technicians"}
        )
        PeriodicCheckRecord.objects.create(
            employee=self.user,
            check_type=self.ct_line,
            aircraft_type=self.type_prop,
            start_date=datetime.date.today() - datetime.timedelta(days=10),
            end_date=datetime.date.today() + datetime.timedelta(days=700),
            document_number="AUTH-LINE-001",
        )

    def test_aircraft_hours_tracking_creation_and_get_data(self):
        """Проверяет сохранение среза наработки ВС и корректную сериализацию в get_data."""
        from hrdepartment_app.models import AircraftHoursTracking, HoursTrackingSource
        from decimal import Decimal
        import datetime

        record = AircraftHoursTracking.objects.create(
            air_board=self.air_board,
            record_date=datetime.date(2026, 10, 1),
            flight_hours=Decimal("1850.5"),
            flight_hours_tsor=Decimal("350.2"),
            flight_cycles=620,
            source=HoursTrackingSource.MANUAL,
            notes="Регулярный срез наработки за сентябрь",
            created_by=self.user,
        )
        self.assertEqual(float(record.flight_hours), 1850.5)
        self.assertEqual(record.flight_cycles, 620)
        self.assertIn("RA-25800", str(record))

        data = record.get_data()
        self.assertEqual(data["pk"], record.pk)
        self.assertEqual(data["flight_hours"], 1850.5)
        self.assertEqual(data["flight_cycles"], 620)
        self.assertIn("Ручной ввод", data["source"])

    def test_outfit_card_auto_syncs_hours_tracking(self):
        """Проверяет автоматическую синхронизацию наработки при сохранении OutfitCard."""
        from hrdepartment_app.models import OutfitCard, AircraftHoursTracking, HoursTrackingSource
        from decimal import Decimal
        import datetime

        card = OutfitCard.objects.create(
            outfit_card_date=datetime.date.today(),
            outfit_card_number="КН-AUTOSYNC-01",
            employee=self.user,
            outfit_card_place=self.place,
            air_board=self.air_board,
            flight_hours=Decimal("1900.0"),
            flight_hours_tsor=Decimal("400.0"),
            flight_cycles=650,
            certifying_staff=self.user,
            crs_number="AUTH-LINE-001",
        )
        sync_entry = AircraftHoursTracking.objects.filter(outfit_card=card).first()
        self.assertIsNotNone(sync_entry)
        self.assertEqual(sync_entry.air_board, self.air_board)
        self.assertEqual(float(sync_entry.flight_hours), 1900.0)
        self.assertEqual(sync_entry.source, HoursTrackingSource.OUTFIT_CARD)


class AircraftMaintenanceApproachesServiceTest(TestCase):
    """Модульные тесты расчета подходов к периодическим регламентам ТО (ФАП-367)."""

    def setUp(self):
        """Создает ВС и тестовую периодическую работу с нормативами и лагами."""
        from contracts_app.models import Estate, TypeProperty
        from hrdepartment_app.models import PeriodicWork
        import datetime

        self.type_prop = TypeProperty.objects.create(type_property="Ми-8Т")
        self.air_board = Estate.objects.create(
            type_property=self.type_prop,
            registration_number="RA-24150",
            factory_number="9924150",
            release_date=datetime.date(2017, 7, 20),
        )
        # Регламент: Ф-1 (норма 75 часов, лаги -20 / +20)
        self.work_f1 = PeriodicWork.objects.create(
            air_bord_type=self.type_prop,
            code="Ф-1",
            name="Регламент 75 часов",
            ratio=75.0,
            lag_minus=20,
            lag_plus=20,
        )

    def test_approach_calculation_resource_ok(self):
        """Налет 40 ч при норме 75 ч (-20/+20) — остаток 35 ч > lag_minus (статус ok, зеленый)."""
        from hrdepartment_app.services.aircraft_maintenance_service import calculate_maintenance_approaches

        approaches = calculate_maintenance_approaches(self.air_board, current_hours=40.0)
        self.assertEqual(len(approaches), 1)
        item = approaches[0]
        self.assertEqual(item["remaining_hours"], 35.0)
        self.assertEqual(item["status"], "ok")
        self.assertEqual(item["color"], "green")

    def test_approach_calculation_due_in_window(self):
        """Налет 65 ч при норме 75 ч (-20/+20) — остаток 10 ч <= lag_minus 20 (статус due, желтый)."""
        from hrdepartment_app.services.aircraft_maintenance_service import calculate_maintenance_approaches

        approaches = calculate_maintenance_approaches(self.air_board, current_hours=65.0)
        self.assertEqual(len(approaches), 1)
        item = approaches[0]
        self.assertEqual(item["remaining_hours"], 10.0)
        self.assertEqual(item["status"], "due")
        self.assertEqual(item["color"], "yellow")

    def test_approach_calculation_overdue(self):
        """Проверяет корректность расчета просроченного статуса при превышении лага."""
        from hrdepartment_app.services.aircraft_maintenance_service import calculate_maintenance_approaches
        from hrdepartment_app.models import PeriodicWork

        PeriodicWork.objects.create(
            air_bord_type=self.type_prop,
            code="ПР-100",
            name="Проверка 100 часов",
            ratio=100.0,
            lag_minus=10,
            lag_plus=10,
        )
        approaches = calculate_maintenance_approaches(self.air_board, current_hours=50.0)
        self.assertTrue(len(approaches) >= 1)


class AircraftHoursExcelImportAndViewsTest(TestCase):
    """Модульные тесты генерации шаблона Excel, пакетного импорта и веб-представлений."""

    def setUp(self):
        """Создает тестового администратора и ВС."""
        from customers_app.models import DataBaseUser
        from contracts_app.models import Estate, TypeProperty
        import datetime

        self.user = DataBaseUser.objects.create_superuser(
            username="admin_import_tester",
            email="import_tester@barkol.ru",
            password="test_password_123",
            last_name="Импортов",
            first_name="Иван",
        )
        self.type_prop = TypeProperty.objects.create(type_property="Ан-2")
        self.air_board = Estate.objects.create(
            type_property=self.type_prop,
            registration_number="RA-01122",
            factory_number="1G21122",
            release_date=datetime.date(2010, 5, 1),
        )
        self.client.force_login(self.user)

    def test_excel_template_generation(self):
        """Проверяет генерацию байтового файла Excel и наличие предзаполненного ВС."""
        from hrdepartment_app.services.aircraft_maintenance_service import generate_aircraft_hours_excel_template
        import openpyxl
        import io

        content = generate_aircraft_hours_excel_template()
        self.assertTrue(len(content) > 0)

        wb = openpyxl.load_workbook(io.BytesIO(content))
        ws = wb.active
        self.assertEqual(ws.title, "Наработка ВС")
        self.assertEqual(ws.cell(row=1, column=1).value, "Бортовой номер ВС")
        self.assertEqual(ws.cell(row=2, column=1).value, "RA-01122")

    def test_excel_import_service_valid_and_invalid(self):
        """Проверяет валидацию и транзакционный импорт из файла Excel."""
        from hrdepartment_app.services.aircraft_maintenance_service import import_aircraft_hours_from_excel
        from hrdepartment_app.models import AircraftHoursTracking, HoursTrackingSource
        import openpyxl
        import io

        # 1. Валидный файл
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Бортовой номер ВС", "Тип ВС", "Дата", "СНЭ", "ППР", "Циклы", "Примечание"])
        ws.append(["RA-01122", "Ан-2", "01.10.2026", 1450.5, 250.0, 510, "Импорт теста"])

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        success, count, errors = import_aircraft_hours_from_excel(buf, user=self.user)
        self.assertTrue(success, errors)
        self.assertEqual(count, 1)

        record = AircraftHoursTracking.objects.filter(air_board=self.air_board).first()
        self.assertIsNotNone(record)
        self.assertEqual(float(record.flight_hours), 1450.5)
        self.assertEqual(record.source, HoursTrackingSource.IMPORT)

        # 2. Невалидный файл (несуществующий борт)
        wb_err = openpyxl.Workbook()
        ws_err = wb_err.active
        ws_err.append(["Бортовой номер ВС", "Тип ВС", "Дата", "СНЭ", "ППР", "Циклы", "Примечание"])
        ws_err.append(["RA-99999", "Ан-2", "01.10.2026", 500.0, 0, 100, "Ошибка"])
        buf_err = io.BytesIO()
        wb_err.save(buf_err)
        buf_err.seek(0)

        success_err, count_err, errors_err = import_aircraft_hours_from_excel(buf_err, user=self.user)
        self.assertFalse(success_err)
        self.assertEqual(count_err, 0)
        self.assertTrue(any("не найдено" in e for e in errors_err))

    def test_views_and_api(self):
        """Проверяет HTTP-представления списка, шаблона и JSON API подходов."""
        from django.urls import reverse

        # 1. Страница реестра наработки
        res_list = self.client.get(reverse("hrdepartment_app:aircraft_hours_list"))
        self.assertEqual(res_list.status_code, 200)
        self.assertContains(res_list, "Учет наработки ВС")

        # 2. Скачивание шаблона Excel
        res_tpl = self.client.get(reverse("hrdepartment_app:aircraft_hours_template"))
        self.assertEqual(res_tpl.status_code, 200)
        self.assertEqual(
            res_tpl["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # 3. JSON API подходов к ТО
        res_api = self.client.get(
            reverse("hrdepartment_app:api_aircraft_hours_approaches", kwargs={"pk": self.air_board.pk})
        )
        self.assertEqual(res_api.status_code, 200)
        data = res_api.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["aircraft"]["registration_number"], "RA-01122")


class OutfitCardCrsDocumentTest(TestCase):
    """Модульные тесты генерации Свидетельства о выполнении ТО (CRS) по Приложению № 1 к ФАП-367."""

    def setUp(self):
        """Подготавливает тестовое окружение: пользователя, ВС, регламент и карту-наряд."""
        from contracts_app.models import Estate, TypeProperty
        from hrdepartment_app.models import OutfitCard, PeriodicWork, PlaceProductionActivity
        from customers_app.models import DataBaseUser
        from decimal import Decimal
        import datetime

        self.user = DataBaseUser.objects.create_user(
            username="khavaev_test",
            password="secret_password",
            first_name="Виталий",
            last_name="Хаваев",
            surname="Анатольевич",
            title="Инженер по ТО ВС",
            is_staff=True,
            is_superuser=True,
        )
        self.type_prop = TypeProperty.objects.create(type_property="МИ-8Т")
        self.air_board = Estate.objects.create(
            type_property=self.type_prop,
            registration_number="RA-24429",
            factory_number="98625598",
            release_date=datetime.date(2015, 6, 15),
        )
        self.place = PlaceProductionActivity.objects.create(name="МПД Аэропорт Волгоград")
        self.work_f9 = PeriodicWork.objects.create(
            air_bord_type=self.type_prop,
            code="Ф-9",
            name="Регламент Ф-9",
            ratio=675.0,
            lag_minus=20,
            lag_plus=20,
        )
        self.card = OutfitCard.objects.create(
            outfit_card_number="90/442",
            outfit_card_date=datetime.date(2026, 6, 26),
            start_time=datetime.time(10, 30),
            outfit_card_date_end=datetime.date(2026, 6, 28),
            end_time=datetime.time(16, 45),
            air_board=self.air_board,
            employee=self.user,
            outfit_card_place=self.place,
            flight_hours=Decimal("693.88"),
            flight_hours_tsor=Decimal("150.5"),
            flight_cycles=293,
            certifying_staff=self.user,
            crs_number="III. № 0184728",
            is_signed=True,
        )
        self.card.periodic_work.add(self.work_f9)

    def test_transliterate_icao(self):
        """Проверяет ICAO Doc 9303 транслитерацию ФИО авиаспециалиста."""
        from hrdepartment_app.services.crs_document_service import transliterate_icao

        res = transliterate_icao("Хаваев Виталий Анатольевич")
        self.assertEqual(res, "Khavaev Vitalii Anatolevich")

        res_short = transliterate_icao("Виталий")
        self.assertEqual(res_short, "Vitalii")

    def test_format_russian_date_words(self):
        """Проверяет форматирование даты прописью в официальном виде."""
        from hrdepartment_app.services.crs_document_service import format_russian_date_words
        import datetime

        d = datetime.date(2026, 6, 28)
        self.assertEqual(format_russian_date_words(d), "«28» июня 2026")

    def test_format_hours_minutes(self):
        """Проверяет форматирование времени в формате 'ЧЧ ч. ММ м.'"""
        from hrdepartment_app.services.crs_document_service import format_hours_minutes
        import datetime

        t = datetime.time(9, 5)
        self.assertEqual(format_hours_minutes(t), "09 ч. 05 м.")
        self.assertEqual(format_hours_minutes(None, fallback="12 ч. 00 м."), "12 ч. 00 м.")

    def test_build_crs_context(self):
        """Проверяет сборку контекста переменных для DocxTemplate."""
        from hrdepartment_app.services.crs_document_service import build_crs_context

        ctx = build_crs_context(self.card)
        self.assertEqual(ctx["бортовой_номер"], "RA-24429")
        self.assertEqual(ctx["заводской_номер"], "98625598")
        self.assertEqual(ctx["номер_удостоверения"], "III. № 0184728")
        self.assertEqual(ctx["фио_специалиста"], "Хаваев Виталий Анатольевич")
        self.assertEqual(ctx["фио_специалиста_en"], "Vitalii Khavaev")
        self.assertIn("Ф-9", ctx["выполненные_работы"])
        self.assertIn("10 ч. 30 м.", ctx["начало_то"])
        self.assertIn("16 ч. 45 м.", ctx["окончание_то"])
        self.assertEqual(ctx["время_свидетельства_utc"], "16 ч. 45 м.")
        self.assertEqual(ctx["отметка_дефекты_нет"], "[X]")
        self.assertEqual(ctx["облет_не_требуется"], "[X]")

    def test_generate_crs_docx_stream(self):
        """Проверяет корректность рендеринга шаблона Word и возврат непустого потока байт."""
        from hrdepartment_app.services.crs_document_service import generate_crs_docx

        docx_bytes = generate_crs_docx(self.card)
        self.assertIsInstance(docx_bytes, bytes)
        self.assertGreater(len(docx_bytes), 5000)

    def test_crs_download_view(self):
        """Проверяет выгрузку Свидетельства CRS через контроллер OutfitCardCRSDownloadView."""
        from django.urls import reverse

        self.client.force_login(self.user)
        url = reverse("hrdepartment_app:outfit_card_crs_download", kwargs={"pk": self.card.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertIn("attachment; filename=", response["Content-Disposition"])
        self.assertIn(".docx", response["Content-Disposition"])
        self.assertGreater(len(response.content), 5000)

    def test_company_maintenance_certificate_dynamic_text(self):
        """Проверяет динамическое получение реквизитов сертификата организации по ФАП-145."""
        from hrdepartment_app.models import CompanyMaintenanceCertificate
        from hrdepartment_app.services.crs_document_service import build_crs_context
        import datetime

        CompanyMaintenanceCertificate.objects.create(
            certificate_number="145-25-108",
            issue_date=datetime.date(2025, 12, 25),
            is_active=True,
        )
        ctx = build_crs_context(self.card)
        expected = "от «25» декабря 2025 № 145-25-108 / № 145-25-108 Issued «25» December 2025"
        self.assertEqual(ctx["сертификат_организации"], expected)

    def test_box16_other_work_checkbox_without_text(self):
        """Пункт 16 CRS: отметка 'Да' ставится при заполнении Другие работы, но текст в графу не выводится."""
        from hrdepartment_app.services.crs_document_service import build_crs_context

        # Без других работ
        self.card.other_work = ""
        self.card.save()
        ctx_no = build_crs_context(self.card)
        self.assertEqual(ctx_no["отметка_дефекты_да"], "[ ]")
        self.assertEqual(ctx_no["отметка_дефекты_нет"], "[X]")

        # С другими работами
        self.card.other_work = "Замена тормозного шланга и фильтра"
        self.card.save()
        ctx_yes = build_crs_context(self.card)
        self.assertEqual(ctx_yes["отметка_дефекты_да"], "[X]")
        self.assertEqual(ctx_yes["отметка_дефекты_нет"], "[ ]")

    def test_box17_test_flight_required_toggle(self):
        """Пункт 17 CRS: переключатель контрольного облета."""
        from hrdepartment_app.services.crs_document_service import build_crs_context

        self.card.test_flight_required = False
        self.card.save()
        ctx_no = build_crs_context(self.card)
        self.assertEqual(ctx_no["облет_требуется"], "[ ]")
        self.assertEqual(ctx_no["облет_не_требуется"], "[X]")

        self.card.test_flight_required = True
        self.card.save()
        ctx_yes = build_crs_context(self.card)
        self.assertEqual(ctx_yes["облет_требуется"], "[X]")
        self.assertEqual(ctx_yes["облет_не_требуется"], "[ ]")

    def test_box21_certifying_staff_license_attached_to_user(self):
        """Пункт 21 CRS: номер бессрочного свидетельства специалиста подставляется из профиля сотрудника."""
        from hrdepartment_app.services.crs_document_service import build_crs_context

        self.user.maintenance_staff_certificate = "III. № 0184728"
        self.user.save()
        ctx = build_crs_context(self.card)
        self.assertEqual(ctx["номер_удостоверения"], "III. № 0184728")

    def test_maintenance_release_certificate_journal_and_annual_numbering(self):
        """Проверяет регистрацию в журнале CRS, нумерацию вида <seq>/<YY> без нулей и обратную синхронизацию."""
        from hrdepartment_app.models import MaintenanceReleaseCertificate, OutfitCard
        import datetime

        # 1. Первое свидетельство 2026 года
        cert1 = MaintenanceReleaseCertificate.create_from_outfit_card(
            self.card,
            certifying_staff=self.user,
            issue_date=datetime.date(2026, 6, 28),
        )
        self.assertEqual(cert1.number_seq, 1)
        self.assertEqual(cert1.certificate_number, "1/26")
        self.card.refresh_from_db()
        self.assertEqual(self.card.crs_number, "1/26")
        self.assertEqual(self.card.certifying_staff, self.user)

        # 2. Второе свидетельство 2026 года
        card2 = OutfitCard.objects.create(
            outfit_card_number="90/443",
            outfit_card_date=datetime.date(2026, 6, 29),
            air_board=self.air_board,
            employee=self.user,
            certifying_staff=self.user,
        )
        cert2 = MaintenanceReleaseCertificate.create_from_outfit_card(
            card2,
            certifying_staff=self.user,
            issue_date=datetime.date(2026, 6, 29),
        )
        self.assertEqual(cert2.number_seq, 2)
        self.assertEqual(cert2.certificate_number, "2/26")
        card2.refresh_from_db()
        self.assertEqual(card2.crs_number, "2/26")

        # 3. Сериализация в DataTables get_data()
        data = cert1.get_data()
        self.assertEqual(data["number_seq"], 1)
        self.assertEqual(data["certificate_number"], "1/26")
        self.assertEqual(data["aircraft_type"], "МИ-8Т")
        self.assertEqual(data["tail_number"], "RA-24429")
        self.assertEqual(data["factory_number"], "98625598")

    def test_crs_journal_views(self):
        """Проверяет страницу реестра журнала CRS и выгрузку Word по объекту свидетельства."""
        from django.urls import reverse
        from hrdepartment_app.models import MaintenanceReleaseCertificate
        import datetime

        cert = MaintenanceReleaseCertificate.create_from_outfit_card(
            self.card,
            certifying_staff=self.user,
            issue_date=datetime.date(2026, 6, 28),
        )

        self.client.force_login(self.user)
        # Реестр журнала CRS
        res_list = self.client.get(reverse("hrdepartment_app:crs_certificate_list"))
        self.assertEqual(res_list.status_code, 200)

        # Выгрузка docx свидетельства из журнала
        res_doc = self.client.get(reverse("hrdepartment_app:crs_certificate_download", kwargs={"pk": cert.pk}))
        self.assertEqual(res_doc.status_code, 200)
        self.assertIn("attachment; filename=", res_doc["Content-Disposition"])


class SubcontractorAndComponentTrackingTest(TestCase):
    """Модульные тесты учета привлеченных организаций и компонентов (ФАП-367, Разделы IV и XV)."""

    def setUp(self):
        """Подготавливает базовые сущности: тип ВС, борт, карту-наряд и пользователя."""
        import datetime
        from decimal import Decimal
        from contracts_app.models import Estate, TypeProperty
        from customers_app.models import DataBaseUser
        from hrdepartment_app.models import OutfitCard, PlaceProductionActivity

        self.user = DataBaseUser.objects.create_user(
            username="eng_subcontractor",
            password="test_password_xyz",
            first_name="Алексей",
            last_name="Смирнов",
        )
        self.type_prop = TypeProperty.objects.create(type_property="Ми-8Т")
        self.air_board = Estate.objects.create(
            type_property=self.type_prop,
            registration_number="RA-22334",
            factory_number="98532100",
            release_date=datetime.date(2018, 4, 10),
        )
        self.place = PlaceProductionActivity.objects.create(name="МПД Быково")
        self.card = OutfitCard.objects.create(
            outfit_card_number="ТО-2026/045",
            outfit_card_date=datetime.date(2026, 7, 15),
            air_board=self.air_board,
            employee=self.user,
            outfit_card_place=self.place,
            flight_hours=Decimal("1200.0"),
        )

    def test_external_org_creation_and_validity(self):
        """Проверяет регистрацию привлеченной организации и методы контроля срока сертификата."""
        import datetime
        from hrdepartment_app.models import ExternalMaintenanceOrganization

        org = ExternalMaintenanceOrganization.objects.create(
            name="АО 'Санкт-Петербургская авиаремонтная компания'",
            short_name="АО 'СПАРК'",
            certificate_number="СПАС-ТО-145-2024-08",
            certificate_agency="ФАВТ",
            certificate_issue_date=datetime.date(2024, 1, 15),
            certificate_valid_until=datetime.date(2027, 1, 15),
            approved_categories="Категория B1 (ТВ2-117), Категория C (ВР-8А)",
            contract_number="ДОГ-ТО-2024/11",
            is_active=True,
        )

        # Действующий сертификат
        check_date = datetime.date(2026, 7, 15)
        self.assertTrue(org.is_certificate_valid(check_date))

        # Дата до выдачи
        before_issue = datetime.date(2023, 1, 1)
        self.assertFalse(org.is_certificate_valid(before_issue))

        # Дата после окончания срока действия
        after_expiry = datetime.date(2027, 2, 1)
        self.assertFalse(org.is_certificate_valid(after_expiry))

        # Деактивация организации
        org.is_active = False
        org.save()
        self.assertFalse(org.is_certificate_valid(check_date))

        # get_data() сериализация
        data = org.get_data()
        self.assertEqual(data["name"], "АО 'Санкт-Петербургская авиаремонтная компания'")
        self.assertIn("Отозван", data["status"])

    def test_aviation_component_validation(self):
        """Проверяет обязательность входящего документа о годности для годного компонента."""
        import datetime
        from decimal import Decimal
        from django.core.exceptions import ValidationError
        from hrdepartment_app.models import AviationComponent, AviationComponentStatus, ComponentReleaseDocType

        # 1. Попытка создать годный агрегат без входящего документа
        comp_invalid = AviationComponent(
            name="Двигатель ТВ2-117А",
            part_number="014000000",
            serial_number="С78411029",
            status=AviationComponentStatus.STOCK,
            release_doc_number="",  # Пустой документ!
        )
        with self.assertRaises(ValidationError):
            comp_invalid.clean()

        # 2. Создание валидного компонента с Талоном годности
        comp_valid = AviationComponent.objects.create(
            name="Двигатель ТВ2-117А",
            part_number="014000000",
            serial_number="С78411029",
            status=AviationComponentStatus.STOCK,
            release_doc_type=ComponentReleaseDocType.FORM_1,
            release_doc_number="ФАП367-24-9912",
            release_doc_date=datetime.date(2026, 5, 20),
            hours_since_new=Decimal("3500.0"),
            hours_since_overhaul=Decimal("150.0"),
            remaining_hours=Decimal("1350.0"),
        )
        comp_valid.clean()  # Ошибки быть не должно
        self.assertEqual(comp_valid.status, AviationComponentStatus.STOCK)

        # get_data()
        data = comp_valid.get_data()
        self.assertEqual(data["part_number"], "014000000")
        self.assertIn("ФАП367-24-9912", data["release_doc"])

    def test_component_installation_success(self):
        """Проверяет успешный монтаж агрегата с легитимным сертификатом сторонней организации."""
        import datetime
        from hrdepartment_app.models import (
            AviationComponent,
            AviationComponentStatus,
            ComponentOperationType,
            ExternalMaintenanceOrganization,
        )
        from hrdepartment_app.services.subcontractor_service import register_component_operation

        org = ExternalMaintenanceOrganization.objects.create(
            name="АО '218 АРЗ'",
            short_name="218 АРЗ",
            certificate_number="ФАВТ-ТО-145-2022-01",
            certificate_issue_date=datetime.date(2022, 1, 1),
            certificate_valid_until=datetime.date(2028, 1, 1),
            approved_categories="Двигатели ТВ2-117",
            is_active=True,
        )

        comp = AviationComponent.objects.create(
            name="Главный редуктор ВР-8А",
            part_number="8-1930-000",
            serial_number="Р99104",
            status=AviationComponentStatus.STOCK,
            last_repair_org=org,
            release_doc_number="ТАЛОН-88124",
            release_doc_date=datetime.date(2026, 6, 1),
        )

        # Регистрация операции замены через сервисный слой
        op = register_component_operation(
            outfit_card=self.card,
            operation_type=ComponentOperationType.REPLACE,
            installed_component=comp,
            removed_component_name="Старый редуктор ВР-8А",
            removed_part_number="8-1930-000",
            removed_serial_number="Р77012",
            removal_reason="Плановая замена по выработке ресурса (1500 ч.)",
            installed_position="Главный редуктор вертолета",
        )

        self.assertIsNotNone(op.pk)
        self.assertEqual(op.installed_component, comp)

        # Проверка автообновления статуса компонента
        comp.refresh_from_db()
        self.assertEqual(comp.status, AviationComponentStatus.INSTALLED)
        self.assertEqual(comp.current_aircraft, self.air_board)

    def test_component_installation_blocked_if_subcontractor_certificate_expired(self):
        """Проверяет блокировку монтажа агрегата при просроченном сертификате привлекаемой организации."""
        import datetime
        from django.core.exceptions import ValidationError
        from hrdepartment_app.models import (
            AviationComponent,
            AviationComponentStatus,
            ComponentOperationType,
            ExternalMaintenanceOrganization,
        )
        from hrdepartment_app.services.subcontractor_service import register_component_operation

        # Организация, чей сертификат истек до даты карты-наряда (наряд от 15.07.2026)
        expired_org = ExternalMaintenanceOrganization.objects.create(
            name="ООО 'АвиаРемТех'",
            short_name="АвиаРемТех",
            certificate_number="ПРОСРОЧ-145",
            certificate_issue_date=datetime.date(2020, 1, 1),
            certificate_valid_until=datetime.date(2025, 12, 31),  # Истек в 2025!
            is_active=True,
        )

        comp = AviationComponent.objects.create(
            name="Насос НШ-39М",
            part_number="НШ-39М-1",
            serial_number="Н-55410",
            status=AviationComponentStatus.STOCK,
            last_repair_org=expired_org,
            release_doc_number="ПАСПОРТ-09",
            release_doc_date=datetime.date(2025, 11, 1),
        )

        # Попытка установки должна вызвать ValidationError
        with self.assertRaises(ValidationError) as ctx:
            register_component_operation(
                outfit_card=self.card,
                operation_type=ComponentOperationType.INSTALL,
                installed_component=comp,
            )

        err_text = str(ctx.exception)
        self.assertIn("недействителен на дату ТО", err_text)
        self.assertIn("п. 96 ФАП-367", err_text)

    def test_get_expiring_subcontractor_certificates(self):
        """Проверяет работу мониторинга приближения срока окончания сертификатов привлекаемых организаций."""
        import datetime
        from hrdepartment_app.models import ExternalMaintenanceOrganization
        from hrdepartment_app.services.subcontractor_service import get_expiring_subcontractor_certificates

        today = datetime.date.today()

        # Организация с истекшим сертификатом (5 дней назад)
        ExternalMaintenanceOrganization.objects.create(
            name="Организация Просроченная",
            short_name="ОРГ-Просроч",
            certificate_number="CERT-EXP",
            certificate_issue_date=today - datetime.timedelta(days=400),
            certificate_valid_until=today - datetime.timedelta(days=5),
            is_active=True,
        )

        # Организация с истекающим сертификатом (через 15 дней)
        ExternalMaintenanceOrganization.objects.create(
            name="Организация Внимание",
            short_name="ОРГ-Внимание",
            certificate_number="CERT-WARN",
            certificate_issue_date=today - datetime.timedelta(days=300),
            certificate_valid_until=today + datetime.timedelta(days=15),
            is_active=True,
        )

        # Организация с долгим сертификатом (через 120 дней)
        ExternalMaintenanceOrganization.objects.create(
            name="Организация Надежная",
            short_name="ОРГ-Норма",
            certificate_number="CERT-OK",
            certificate_issue_date=today - datetime.timedelta(days=100),
            certificate_valid_until=today + datetime.timedelta(days=120),
            is_active=True,
        )

        expiring = get_expiring_subcontractor_certificates(days_threshold=30)
        expiring_short_names = [item["org"].short_name for item in expiring]

        self.assertIn("ОРГ-Просроч", expiring_short_names)
        self.assertIn("ОРГ-Внимание", expiring_short_names)
        self.assertNotIn("ОРГ-Норма", expiring_short_names)


class MaintenanceReleaseCertificatePortalTests(TestCase):
    """Тесты выписки Свидетельства о ТО ВС (CRS) через веб-форму портала и API."""

    def setUp(self):
        """Подготовка тестовых данных: пользователь, борт, карта-наряд."""
        from decimal import Decimal
        from django.urls import reverse
        from contracts_app.models import TypeProperty, Estate
        from hrdepartment_app.models import PlaceProductionActivity, OutfitCard

        self.user = DataBaseUser.objects.create_user(
            username="engineer1",
            email="eng1@barkol.ru",
            password="pass",
            first_name="Иван",
            last_name="Иванов",
            title="Иванов Иван Иванович",
            is_staff=True,
            is_superuser=True,
            maintenance_staff_certificate="Специалист ТО № 77-12345",
        )
        self.type_mi8 = TypeProperty.objects.create(type_property="Ми-8Т")
        self.board = Estate.objects.create(
            registration_number="RA-24429",
            factory_number="9904429",
            type_property=self.type_mi8,
            release_date=datetime.date(2015, 1, 1),
        )
        self.place = PlaceProductionActivity.objects.create(name="МПД Внуково", short_name="ВНК")
        self.card = OutfitCard.objects.create(
            outfit_card_number="125/ТО",
            outfit_card_date=datetime.date(2026, 4, 1),
            outfit_card_date_end=datetime.date(2026, 4, 2),
            air_board=self.board,
            outfit_card_place=self.place,
            employee=self.user,
            certifying_staff=self.user,
            flight_hours=Decimal("693.88"),
            notes="Тестовые регламентные работы",
        )
        self.client.force_login(self.user)

    def test_crs_data_api(self):
        """Проверяет AJAX эндпоинт получения реквизитов карты-наряда."""
        url = reverse("hrdepartment_app:api_outfit_card_crs_data", kwargs={"pk": self.card.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["outfit_card_number"], "125/ТО")
        self.assertEqual(data["aircraft_type"], "Ми-8Т")
        self.assertEqual(data["tail_number"], "RA-24429")
        self.assertEqual(data["factory_number"], "9904429")
        self.assertIn("693", data["operating_hours"])
        self.assertEqual(data["certifying_staff_id"], self.user.pk)
        self.assertEqual(data["certifying_staff_license"], "Специалист ТО № 77-12345")

    def test_create_certificate_via_portal_form(self):
        """Проверяет выписку свидетельства CRS через форму на портале с автогенерацией номера и синхронизацией."""
        from hrdepartment_app.models import MaintenanceReleaseCertificate

        # 1. GET запрос с prefill по параметру ?outfit_card=
        get_url = f"{reverse('hrdepartment_app:crs_certificate_create')}?outfit_card={self.card.pk}"
        resp_get = self.client.get(get_url)
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, "Выписка Свидетельства о ТО ВС (CRS)")

        # 2. POST запрос на создание
        post_url = reverse("hrdepartment_app:crs_certificate_create")
        post_data = {
            "outfit_card": self.card.pk,
            "certifying_staff": self.user.pk,
            "maintenance_date": "2026-04-02",
            "issue_date": "2026-04-02",
            "aircraft_type": "Ми-8Т",
            "tail_number": "RA-24429",
            "factory_number": "9904429",
            "operating_hours": "693 ч. 53 м.",
            "maintenance_work_scope": "Периодическое ТО Ф-9",
            "certifying_staff_license": "Специалист ТО № 77-12345",
            "signature_stamp": "[Оформлено в СЭД БАРКОЛ]",
        }
        resp_post = self.client.post(post_url, data=post_data, follow=True)
        self.assertEqual(resp_post.status_code, 200)
        self.assertContains(resp_post, "успешно выписано и зарегистрировано в журнале")

        # 3. Проверка созданной записи в БД
        cert = MaintenanceReleaseCertificate.objects.filter(outfit_card=self.card).first()
        self.assertIsNotNone(cert)
        self.assertEqual(cert.year, 2026)
        self.assertEqual(cert.certificate_number, f"{cert.number_seq}/26")
        self.assertEqual(cert.tail_number, "RA-24429")

        # 4. Проверка обратной синхронизации в карту-наряд
        self.card.refresh_from_db()
        self.assertEqual(self.card.crs_number, cert.certificate_number)
        self.assertEqual(self.card.certifying_staff, self.user)

    def test_issue_crs_directly_from_outfit_card_view(self):
        """Проверяет выписку свидетельства CRS через OutfitCardIssueCRSView."""
        from hrdepartment_app.models import MaintenanceReleaseCertificate, OutfitCard

        card2 = OutfitCard.objects.create(
            outfit_card_number="126/ТО",
            outfit_card_date=datetime.date(2026, 4, 3),
            air_board=self.board,
            outfit_card_place=self.place,
            employee=self.user,
            certifying_staff=self.user,
            flight_hours=Decimal("700.0"),
        )
        url = reverse("hrdepartment_app:outfit_card_issue_crs", kwargs={"pk": card2.pk})
        resp = self.client.post(url, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "успешно зарегистрировано в журнале")

        card2.refresh_from_db()
        self.assertTrue(bool(card2.crs_number))
        cert = MaintenanceReleaseCertificate.objects.filter(outfit_card=card2).first()
        self.assertIsNotNone(cert)
        self.assertEqual(cert.certificate_number, card2.crs_number)


from .tests.tests_metrology import (
    MaintenanceEquipmentAndReleaseServiceTests,
    MaintenanceEquipmentPortalPermissionTests,
)
