"""Unit-тесты для пакета интеграции с Kerio Connect Administration API."""

from unittest.mock import MagicMock, patch
from django.contrib.auth import get_user_model
from django.test import TestCase

from mailbox_app.models import MailAccount
from mailbox_app.services.kerio.client import KerioConnectAdminClient
from mailbox_app.services.kerio.domains import DomainManager
from mailbox_app.services.kerio.exceptions import (
    KerioAPIError,
    KerioAuthenticationError,
    KerioConnectionError,
    KerioObjectNotFoundError,
    KerioSessionExpired,
    KerioValidationError,
)
from mailbox_app.services.kerio.pop3_download import Pop3DownloadManager
from mailbox_app.services.kerio.service import KerioAdminService
from mailbox_app.services.kerio.users import UserManager

User = get_user_model()


class KerioClientTestCase(TestCase):
    """Тестирование низкоуровневого JSON-RPC клиента KerioConnectAdminClient."""

    def setUp(self) -> None:
        """Подготовка тестовых данных."""
        self.api_url = "https://192.168.10.242:4040/admin/api/jsonrpc/"
        self.username = "admin"
        self.password = "secret"
        self.client = KerioConnectAdminClient(
            api_url=self.api_url,
            username=self.username,
            password=self.password,
            verify_ssl=False,
            timeout=5,
        )

    @patch("requests.Session.post")
    def test_login_success(self, mock_post: MagicMock) -> None:
        """Тест успешной авторизации Session.login."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "token": "test_token_12345",
                "user": {"userName": "admin", "fullName": "Administrator"},
            },
        }

        token = self.client.login()
        self.assertEqual(token, "test_token_12345")
        self.assertEqual(self.client.token, "test_token_12345")
        self.assertEqual(self.client.session.headers.get("X-Token"), "test_token_12345")
        self.assertEqual(self.client.session.cookies.get("SESSION_CONNECT_WEBADMIN"), "test_token_12345")

    @patch("requests.Session.post")
    def test_login_failure(self, mock_post: MagicMock) -> None:
        """Тест ошибки авторизации при неверных учетных данных."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "Invalid user name or password."},
        }

        with self.assertRaises(KerioAuthenticationError) as ctx:
            self.client.login()
        self.assertIn("Invalid user name or password", str(ctx.exception))

    @patch("requests.Session.post")
    def test_call_method_success(self, mock_post: MagicMock) -> None:
        """Тест вызова произвольного метода API."""
        self.client.token = "active_token"
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"list": [{"id": "d1", "name": "barkol.ru"}]},
        }

        result = self.client.call("Domains.get")
        self.assertIn("list", result)
        self.assertEqual(len(result["list"]), 1)
        self.assertEqual(result["list"][0]["name"], "barkol.ru")

    @patch("requests.Session.post")
    def test_session_expired_auto_reauth(self, mock_post: MagicMock) -> None:
        """Тест автоматической повторной авторизации при протухании токена."""
        self.client.token = "old_expired_token"

        # 1-й запрос: Session expired
        # 2-й запрос: Session.login (успешно)
        # 3-й запрос: повтор исходного метода (успешно)
        mock_post.side_effect = [
            MagicMock(
                status_code=200,
                json=lambda: {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "error": {"code": -32001, "message": "Session expired."},
                },
            ),
            MagicMock(
                status_code=200,
                json=lambda: {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "result": {"token": "fresh_token_999"},
                },
            ),
            MagicMock(
                status_code=200,
                json=lambda: {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "result": {"list": [{"id": "u1", "loginName": "shakirov"}]},
                },
            ),
        ]

        result = self.client.call("Users.get")
        self.assertEqual(self.client.token, "fresh_token_999")
        self.assertIn("list", result)
        self.assertEqual(result["list"][0]["loginName"], "shakirov")


class KerioManagersTestCase(TestCase):
    """Тестирование менеджеров доменов, пользователей и правил POP3."""

    def setUp(self) -> None:
        """Инициализация мок-клиента."""
        self.mock_client = MagicMock(spec=KerioConnectAdminClient)
        self.mock_client.token = "mock_token"

    def test_domain_manager(self) -> None:
        """Тест выборки доменов и разрешения domainId."""
        manager = DomainManager(self.mock_client)
        self.mock_client.call.return_value = {
            "list": [
                {"id": "dom_1", "name": "barkol.ru", "isPrimary": True},
                {"id": "dom_2", "name": "complang.ru", "isPrimary": False},
            ]
        }

        domains = manager.get_domains()
        self.assertEqual(len(domains), 2)

        dom_id = manager.get_domain_id("barkol.ru")
        self.assertEqual(dom_id, "dom_1")

        with self.assertRaises(KerioObjectNotFoundError):
            manager.get_domain_id("unknown-domain.com")

    def test_user_manager_crud(self) -> None:
        """Тест операций над пользователями (создание, получение, пароль, удаление)."""
        manager = UserManager(self.mock_client)

        # 1. get_users
        self.mock_client.call.return_value = {
            "list": [{"id": "u_1", "loginName": "shakirov", "fullName": "Виталий Шакиров"}],
            "totalItems": 1,
        }
        users_res = manager.get_users()
        self.assertEqual(users_res["totalItems"], 1)

        # 2. create_user
        self.mock_client.call.return_value = {"createdUserIds": ["u_2"]}
        create_res = manager.create_user(
            domain_id="dom_1",
            login_name="i.ivanov",
            password="Password123!",
            full_name="Иван Иванов",
            quota_mb=1024,
        )
        self.assertEqual(create_res, {"createdUserIds": ["u_2"]})

        # 3. set_password
        self.mock_client.call.return_value = {"success": True}
        manager.set_password("u_2", "NewPass456!")
        self.mock_client.call.assert_called()

        # 4. remove_user
        manager.remove_user("u_2")
        self.mock_client.call.assert_called_with(
            "Users.remove",
            params={
                "requests": [
                    {
                        "userId": "u_2",
                        "method": "DeleteFolder",
                        "mode": "DSModeDelete",
                        "removeReferences": True,
                        "targetUserId": "",
                    }
                ]
            },
            suppress_log=True,
        )

    def test_remove_user_with_uri_domain_extraction_and_fallback(self) -> None:
        """Тест удаления пользователя с автоматическим извлечением domainId из URI и fallback при -32602."""
        manager = UserManager(self.mock_client)
        user_uri = "keriodb://user/f16df5f7-c299-47f6-b631-8efff9f1d222/3cc2f617-c761-42e3-8e33-1f61f73517fa"

        # Симулируем ошибку -32602 на первом кандидате {"requests": [DeleteFolder]}
        # и успех на втором кандидате {"requests": [KeepFolder]}
        self.mock_client.call.side_effect = [
            KerioAPIError("[Код -32602] Invalid params.", code=-32602),
            {"errors": []},
        ]

        res = manager.remove_user(user_uri)
        self.assertEqual(res, {"errors": []})
        self.assertEqual(self.mock_client.call.call_count, 2)
        # Проверяем, что второй вызов содержал KeepFolder
        second_call = self.mock_client.call.call_args_list[1]
        self.assertEqual(second_call[0][0], "Users.remove")
        self.assertEqual(second_call[1]["params"]["requests"][0]["method"], "KeepFolder")
        self.assertEqual(second_call[1]["params"]["requests"][0]["userId"], user_uri)

    def test_pop3_download_manager(self) -> None:
        """Тест менеджера правил «Загрузка POP3» со стандартными настройками."""
        manager = Pop3DownloadManager(self.mock_client)

        # create_pop3_account с параметрами по умолчанию (mail.barkol.ru:995 SSL, delete=True)
        self.mock_client.call.return_value = {"createdAccountIds": ["pop_1"]}
        res = manager.create_pop3_account(
            target_user="i.ivanov",
            password="SecretPassword!",
            username="i.ivanov@barkol.ru",
        )
        self.assertEqual(res, {"createdAccountIds": ["pop_1"]})

        call_args = self.mock_client.call.call_args[1]["params"]["accounts"][0]
        self.assertEqual(call_args["server"], "mail.barkol.ru")
        self.assertEqual(call_args["port"], 995)
        self.assertEqual(call_args["mode"], "SpecialPort")
        self.assertEqual(call_args["leaveOnServer"]["enabled"], False)
        self.assertEqual(call_args["deliveryAddress"], "i.ivanov")


class KerioAdminServiceTestCase(TestCase):
    """Интеграционное тестирование высокоуровневого сервиса KerioAdminService."""

    def setUp(self) -> None:
        """Создание тестового пользователя Django."""
        self.user = User.objects.create_user(
            username="test_user",
            email="test_user@barkol.ru",
            password="test_password",
            first_name="Виталий",
            last_name="Шакиров",
        )
        self.mock_client = MagicMock(spec=KerioConnectAdminClient)
        self.mock_client.token = "mock_token"
        self.mock_client.api_url = "https://192.168.10.242:4040/admin/api/jsonrpc/"
        self.mock_client.username = "admin"
        self.service = KerioAdminService(client=self.mock_client)

    def test_test_admin_connection_success(self) -> None:
        """Тест проверки доступности Kerio Connect API."""
        self.mock_client.call.return_value = {
            "list": [{"id": "d1", "name": "barkol.ru"}]
        }
        res = self.service.test_admin_connection()
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "online")
        self.assertEqual(res["domains_count"], 1)

    def test_provision_full_mailbox(self) -> None:
        """Тест создания полного контура ящика (Kerio + POP3 + Django MailAccount + email в DataBaseUser)."""
        self.mock_client.call.side_effect = [
            # 1. Domains.get
            {"list": [{"id": "dom_barkol", "name": "barkol.ru"}]},
            # 2. Users.create
            {"createdUserIds": ["k_user_1"]},
            # 3. Pop3Download.create
            {"createdAccountIds": ["k_pop_1"]},
        ]

        report = self.service.provision_full_mailbox(
            login_name="v.shakirov",
            password="UltraSecretPassword123",
            domain_name="barkol.ru",
            full_name="Виталий Шакиров",
            description="Ведущий инженер",
            django_user_id=self.user.pk,
            quota_mb=2048,
            save_email_to_user=True,
            sync_1c=False,
        )

        self.assertTrue(report["success"])
        self.assertEqual(report["email"], "v.shakirov@barkol.ru")
        self.assertEqual(report["steps"]["kerio_user"]["status"], "ok")
        self.assertEqual(report["steps"]["kerio_pop3_download"]["status"], "ok")
        self.assertEqual(report["steps"]["django_account"]["status"], "ok")
        self.assertEqual(report["steps"]["user_email_saved"]["status"], "ok")

        # Проверяем сохранение email в модели пользователя Django
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "v.shakirov@barkol.ru")

        # Проверяем созданный MailAccount в БД Django
        account = MailAccount.objects.get(user=self.user)
        self.assertEqual(account.email, "v.shakirov@barkol.ru")
        self.assertEqual(account.get_password(), "UltraSecretPassword123")
        self.assertEqual(account.imap_host, "imap.barkol.ru")
        self.assertEqual(account.smtp_host, "sm.barkol.ru")
        self.assertTrue(account.is_active)

        # Проверяем синхронизацию пароля в рабочем профиле сотрудника DataBaseUserWorkProfile
        if hasattr(self.user, "user_work_profile") and self.user.user_work_profile:
            self.assertEqual(self.user.user_work_profile.work_email_password, "UltraSecretPassword123")

    @patch("administration_app.utils.update_1c_physical_person_email")
    def test_provision_full_mailbox_with_1c_sync(self, mock_update_1c: MagicMock) -> None:
        """Тест создания ящика с синхронизацией email в 1С (ЗУП)."""
        mock_update_1c.return_value = (True, "Email успешно записан в 1С")

        self.mock_client.call.side_effect = [
            # 1. Domains.get
            {"list": [{"id": "dom_barkol", "name": "barkol.ru"}]},
            # 2. Users.create
            {"createdUserIds": ["k_user_2"]},
            # 3. Pop3Download.create
            {"createdAccountIds": ["k_pop_2"]},
        ]

        if hasattr(self.user, "person_ref_key"):
            self.user.person_ref_key = "72095052-970f-11e3-84fb-00e05301b4e4"
            self.user.save()

        report = self.service.provision_full_mailbox(
            login_name="v.shakirov2",
            password="UltraSecretPassword123",
            domain_name="barkol.ru",
            full_name="Виталий Шакиров",
            description="Ведущий инженер",
            django_user_id=self.user.pk,
            quota_mb=2048,
            save_email_to_user=True,
            sync_1c=True,
        )

        self.assertTrue(report["success"])
        self.assertEqual(report["email"], "v.shakirov2@barkol.ru")
        self.assertIn("sync_1c", report["steps"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "v.shakirov2@barkol.ru")

    def test_update_user_password_syncs_work_profile(self) -> None:
        """Тест синхронизации пароля в MailAccount и DataBaseUserWorkProfile при сбросе/смене пароля."""
        # 1. Подготовка MailAccount для пользователя
        account = MailAccount.objects.create(
            user=self.user,
            email="v.shakirov@barkol.ru",
            display_name="Виталий Шакиров",
            imap_host="imap.barkol.ru",
            imap_port=993,
            imap_use_ssl=True,
            smtp_host="sm.barkol.ru",
            smtp_port=465,
            smtp_use_ssl=True,
            is_active=True,
        )
        account.set_password("OldPassword111")
        account.save()

        # 2. Мокируем ответы Kerio Connect (Domains.get, Users.get, Users.setPassword, Delivery.getPop3AccountList)
        self.mock_client.call.side_effect = [
            # Domains.get (get_domain_id)
            {"list": [{"id": "dom_barkol", "name": "barkol.ru"}]},
            # Users.get (get_user_by_login)
            {"list": [{"id": "u_kerio_1", "loginName": "v.shakirov"}]},
            # Users.setPassword
            {"success": True},
            # Delivery.getPop3AccountList (get_account_for_user)
            {"list": [{"id": "pop_rule_1", "deliveryAddress": "v.shakirov"}]},
            # Delivery.setPop3Account / update_pop3_account
            {"success": True},
            # Smtp.get (SmtpDeliveryManager.set_route_password_for_sender)
            {"smtp": {"deliveryRules": []}},
        ]

        res = self.service.update_user_password(
            login_name="v.shakirov",
            new_password="BrandNewPassword999!",
            domain_name="barkol.ru",
            update_django=True,
        )
        self.assertTrue(res["success"])

        # Проверяем обновленный пароль в MailAccount
        account.refresh_from_db()
        self.assertEqual(account.get_password(), "BrandNewPassword999!")

        # Проверяем обновленный пароль в профиле пользователя на сайте
        self.user.refresh_from_db()
        if hasattr(self.user, "user_work_profile") and self.user.user_work_profile:
            self.assertEqual(self.user.user_work_profile.work_email_password, "BrandNewPassword999!")

    def test_delete_user_with_external_isp_deletion(self) -> None:
        """Тест комплексного удаления пользователя с удалением из Kerio Connect и ISPmanager."""
        from mailbox_app.models import MailAccount

        # Создаем тестовый MailAccount
        account, _ = MailAccount.objects.get_or_create(
            user=self.user,
            defaults={
                "email": "v.shakirov@barkol.ru",
                "display_name": "Вадим Шакиров",
                "imap_host": "imap.barkol.ru",
                "imap_port": 993,
                "imap_use_ssl": True,
                "smtp_host": "sm.barkol.ru",
                "smtp_port": 465,
                "smtp_use_ssl": True,
                "is_active": True,
            },
        )

        mock_ext_delete = MagicMock(return_value=True)
        self.service.external_provider.delete_mailbox = mock_ext_delete

        self.mock_client.call.side_effect = [
            # Pop3.get (get_account_for_user)
            {"list": [{"id": "pop3://account/1", "targetUser": "v.shakirov"}]},
            # Pop3.remove
            {"success": True},
            # Smtp.get (remove_route_for_sender)
            {"smtp": {"deliveryRules": []}},
            # Domains.get (get_domain_id)
            {"list": [{"id": "dom_barkol", "name": "barkol.ru"}]},
            # Users.get (get_user_by_login)
            {"list": [{"id": "keriodb://user/dom_barkol/user_1", "loginName": "v.shakirov"}]},
            # Users.remove
            {"success": True},
        ]

        res = self.service.delete_user(
            login_name="v.shakirov",
            domain_name="barkol.ru",
            delete_external=True,
        )

        self.assertTrue(res["success"])
        self.assertTrue(res["deleted"])
        self.assertEqual(res["steps"]["external_server"], "ok")
        self.assertEqual(res["steps"]["kerio_user"], "ok")
        mock_ext_delete.assert_called_once_with("v.shakirov@barkol.ru")
        self.assertFalse(MailAccount.objects.filter(email="v.shakirov@barkol.ru").exists())

    def test_audit_mailboxes_sync(self) -> None:
        """Тест комплексного аудита синхронизации почтовых ящиков (Kerio Connect ↔ ISPmanager)."""
        # Мокируем список пользователей Kerio
        self.service.get_users_list = MagicMock(return_value={
            "list": [
                {
                    "loginName": "v.shakirov",
                    "email": "v.shakirov@barkol.ru",
                    "fullName": "Вадим Шакиров",
                    "isEnabled": True,
                    "has_pop3_download": True,
                    "has_smtp_delivery": True,
                    "is_individual_smtp_delivery": True,
                },
                {
                    "loginName": "a.abramov",
                    "email": "a.abramov@barkol.ru",
                    "fullName": "Алексей Абрамов",
                    "isEnabled": True,
                    "has_pop3_download": False,
                    "has_smtp_delivery": True,
                    "is_individual_smtp_delivery": False,
                },
            ]
        })

        # Мокируем провайдер ISPmanager
        self.service.external_provider.is_configured = True
        self.service.external_provider.get_mailboxes = MagicMock(return_value=[
            {
                "email": "v.shakirov@barkol.ru",
                "name": "v.shakirov",
                "domain": "barkol.ru",
                "quota": "1024",
                "used": "150",
                "status": "active",
            },
            {
                "email": "orphan@barkol.ru",
                "name": "orphan",
                "domain": "barkol.ru",
                "quota": "512",
                "used": "10",
                "status": "active",
            },
        ])

        audit = self.service.audit_mailboxes_sync(domain_name="barkol.ru")

        self.assertTrue(audit["success"])
        self.assertEqual(audit["summary"]["total_kerio"], 2)
        self.assertEqual(audit["summary"]["total_isp"], 2)
        self.assertEqual(audit["summary"]["synced_count"], 1)
        self.assertEqual(audit["summary"]["missing_in_isp_count"], 1)
        self.assertEqual(audit["summary"]["orphaned_in_isp_count"], 1)
        self.assertEqual(len(audit["users"]), 2)
        self.assertEqual(len(audit["orphans"]), 1)

        # Проверяем статусы пользователей
        u_shakirov = next(u for u in audit["users"] if u["login"] == "v.shakirov")
        self.assertTrue(u_shakirov["in_ispmanager"])
        self.assertEqual(u_shakirov["sync_status"], "synced")

        u_abramov = next(u for u in audit["users"] if u["login"] == "a.abramov")
        self.assertFalse(u_abramov["in_ispmanager"])
        self.assertEqual(u_abramov["sync_status"], "missing_in_isp")

    @patch("administration_app.utils.update_1c_physical_person_email")
    def test_sync_user_email_to_portal_and_1c(self, mock_update_1c: MagicMock) -> None:
        """Тест метода sync_user_email_to_portal_and_1c для обновления email в модели пользователя и 1С."""
        mock_update_1c.return_value = (True, "OK в 1С")

        if hasattr(self.user, "person_ref_key"):
            self.user.person_ref_key = "72095052-970f-11e3-84fb-00e05301b4e4"
            self.user.email = "old.email@barkol.ru"
            self.user.save()

        res = self.service.sync_user_email_to_portal_and_1c(
            login_name="v.shakirov",
            domain_name="barkol.ru",
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["email"], "v.shakirov@barkol.ru")
        self.assertTrue(res["portal_synced"])
        self.assertTrue(res["one_c_synced"])

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "v.shakirov@barkol.ru")
        mock_update_1c.assert_called_once_with(
            person_ref_key="72095052-970f-11e3-84fb-00e05301b4e4",
            email="v.shakirov@barkol.ru",
            base_index=0,
        )


class CorporateLoginUtilsTestCase(TestCase):
    """Тестирование транслитерации и генерации корпоративных логинов BARKOL."""

    def test_transliteration(self) -> None:
        """Тест транслитерации кириллицы по стандарту BARKOL."""
        from mailbox_app.services.kerio.utils import transliterate_ru_to_en

        self.assertEqual(transliterate_ru_to_en("Абрамов"), "abramov")
        self.assertEqual(transliterate_ru_to_en("Дерянин"), "deryanin")
        self.assertEqual(transliterate_ru_to_en("Чупрына"), "chupryna")
        self.assertEqual(transliterate_ru_to_en("Шакиров"), "shakirov")
        self.assertEqual(transliterate_ru_to_en("Щукин"), "shchukin")
        self.assertEqual(transliterate_ru_to_en("Мамин-Сибиряк"), "mamin-sibiryak")

    def test_fio_parsing(self) -> None:
        """Тест извлечения компонентов ФИО."""
        from mailbox_app.services.kerio.utils import parse_fio_components

        fn, ln, mn = parse_fio_components("Абрамов Алексей Борисович")
        self.assertEqual(ln, "Абрамов")
        self.assertEqual(fn, "Алексей")
        self.assertEqual(mn, "Борисович")

    def test_corporate_login_generation_standard(self) -> None:
        """Тест генерации стандартного логина (первая буква имени + фамилия)."""
        from mailbox_app.services.kerio.utils import generate_corporate_mailbox_login

        login = generate_corporate_mailbox_login("Алексей", "Абрамов", "Борисович")
        self.assertEqual(login, "a.abramov")

        login2 = generate_corporate_mailbox_login("Андрей", "Дерянин")
        self.assertEqual(login2, "a.deryanin")

    def test_collision_resolution_levels(self) -> None:
        """Тест 4-уровневого разрешения коллизий тезок."""
        from mailbox_app.services.kerio.utils import generate_corporate_mailbox_login

        occupied = {"a.abramov"}

        # Уровень 2: инициал имени + инициал отчества
        login_lvl2 = generate_corporate_mailbox_login("Алексей", "Абрамов", "Борисович", existing_logins=occupied)
        self.assertEqual(login_lvl2, "ab.abramov")

        occupied.add("ab.abramov")

        # Уровень 3: полное имя + фамилия
        login_lvl3 = generate_corporate_mailbox_login("Алексей", "Абрамов", "Борисович", existing_logins=occupied)
        self.assertEqual(login_lvl3, "aleksey.abramov")

        occupied.add("aleksey.abramov")

        # Уровень 4: числовой суффикс
        login_lvl4 = generate_corporate_mailbox_login("Алексей", "Абрамов", "Борисович", existing_logins=occupied)
        self.assertEqual(login_lvl4, "a.abramov2")

        occupied.add("a.abramov2")
        login_lvl4_next = generate_corporate_mailbox_login("Алексей", "Абрамов", "Борисович", existing_logins=occupied)
        self.assertEqual(login_lvl4_next, "a.abramov3")


class SmtpDeliveryManagerTestCase(TestCase):
    """Тестирование менеджера правил исходящей ретрансляции SmtpDeliveryManager («Доставка SMTP»)."""

    def setUp(self) -> None:
        """Подготовка тестовых данных."""
        self.client = MagicMock(spec=KerioConnectAdminClient)
        from mailbox_app.services.kerio.smtp_delivery import SmtpDeliveryManager
        self.manager = SmtpDeliveryManager(self.client)

    def test_get_routes_normalization(self) -> None:
        """Тест получения и нормализации структуры правил Доставка SMTP."""
        self.client.call.return_value = {
            "list": [
                {
                    "id": "keriodb://deliveryroute/123",
                    "isEnabled": True,
                    "description": "Ретрансляция для a.administrator@barkol.ru",
                    "hostName": "smtp.barkol.ru",
                    "port": 587,
                    "authentication": {
                        "isRequired": True,
                        "userName": "a.administrator@barkol.ru",
                        "password": "secretPassword",
                        "authType": "Auth",
                    },
                    "condition": {
                        "test": "RelayCondSender",
                        "comparator": "RelayCompEqual",
                        "pattern": "a.administrator@barkol.ru",
                    },
                }
            ]
        }

        routes = self.manager.get_routes()
        self.assertEqual(len(routes), 1)
        r = routes[0]
        self.assertEqual(r["id"], "keriodb://deliveryroute/123")
        self.assertTrue(r["isEnabled"])
        self.assertEqual(r["matchPattern"], "a.administrator@barkol.ru")
        self.assertEqual(r["sender"], "a.administrator@barkol.ru")
        self.assertEqual(r["server"], "smtp.barkol.ru")
        self.assertEqual(r["port"], 587)
        self.assertEqual(r["userName"], "a.administrator@barkol.ru")
        self.assertTrue(r["hasPassword"])

    def test_get_route_for_sender(self) -> None:
        """Тест поиска правила по email или логину отправителя."""
        self.client.call.return_value = {
            "list": [
                {
                    "id": "keriodb://deliveryroute/admin_route",
                    "isEnabled": True,
                    "hostName": "smtp.barkol.ru",
                    "port": 587,
                    "authentication": {"isRequired": True, "userName": "a.administrator@barkol.ru", "password": "123"},
                    "condition": {"test": "RelayCondSender", "pattern": "a.administrator@barkol.ru"},
                }
            ]
        }

        # Поиск по полному email
        found1 = self.manager.get_route_for_sender("a.administrator@barkol.ru")
        self.assertIsNotNone(found1)
        self.assertEqual(found1["id"], "keriodb://deliveryroute/admin_route")

        # Поиск по короткому логину
        found2 = self.manager.get_route_for_sender("a.administrator")
        self.assertIsNotNone(found2)
        self.assertEqual(found2["id"], "keriodb://deliveryroute/admin_route")

        # Поиск для пользователя, попадающего под общее серверное правило
        found_other = self.manager.get_route_for_sender("other.user@barkol.ru")
        self.assertIsNotNone(found_other)
        self.assertEqual(found_other["sender"], "*@barkol.ru")
        self.assertEqual(found_other["server"], "smtp.barkol.ru")
        self.assertEqual(found_other["port"], 587)
        self.assertTrue(found_other["isGlobal"])

    def test_create_delivery_route(self) -> None:
        """Тест создания правила ретрансляции SMTP через Smtp.setRelayDeliveryRuleList."""
        created_rule = {
            "id": "keriodb://deliveryroute/new_route_id",
            "isEnabled": True,
            "description": "Ретрансляция SMTP для a.administrator@barkol.ru",
            "hostName": "smtp.barkol.ru",
            "port": 587,
            "authentication": {
                "isRequired": True,
                "userName": "a.administrator@barkol.ru",
                "password": "securePassword123",
                "authType": "Auth",
            },
            "condition": {
                "test": "RelayCondSender",
                "comparator": "RelayCompEqual",
                "pattern": "a.administrator@barkol.ru",
            },
        }
        self.client.call.side_effect = [
            {"list": []},
            {"result": {}},
            {"list": [created_rule]},
        ]

        res = self.manager.create_delivery_route(
            sender_email="a.administrator@barkol.ru",
            password="securePassword123",
            relay_host="smtp.barkol.ru",
            relay_port=587,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["method"], "Smtp.setRelayDeliveryRuleList")
        self.assertEqual(res["sender"], "a.administrator@barkol.ru")
        self.assertEqual(res["relay_host"], "smtp.barkol.ru")
        self.assertEqual(res["relay_port"], 587)
        self.assertEqual(res["id"], "keriodb://deliveryroute/new_route_id")

    def test_create_delivery_route_method_not_found_fallback(self) -> None:
        """Тест корректной обработки ситуации, когда в API Kerio Connect метод Smtp.setRelayDeliveryRuleList отсутствует (-32601), переход на Smtp.set."""
        from mailbox_app.services.kerio.exceptions import KerioObjectNotFoundError

        smtp_config = {
            "server": {
                "delivery": {
                    "useSsl": True,
                    "customRules": [],
                }
            }
        }

        def mock_call(method: str, params: dict = None) -> dict:
            if method == "Smtp.get":
                return smtp_config
            if method == "Smtp.set":
                return {"result": "ok"}
            raise KerioObjectNotFoundError("[Код -32601] Method not found.")

        self.client.call.side_effect = mock_call

        res = self.manager.create_delivery_route(
            sender_email="a.administrator@barkol.ru",
            password="securePassword123",
            relay_host="smtp.barkol.ru",
            relay_port=587,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["method"], "Smtp.set")
        self.assertEqual(res["sender"], "a.administrator@barkol.ru")

    def test_remove_delivery_route(self) -> None:
        """Тест удаления правила доставки SMTP через Smtp.setRelayDeliveryRuleList."""
        existing_rule = {
            "id": "keriodb://deliveryroute/123",
            "isEnabled": True,
            "condition": {"test": "RelayCondSender", "pattern": "a.administrator@barkol.ru"},
        }
        self.client.call.side_effect = [
            {"list": [existing_rule]},
            {"result": {}},
        ]

        res = self.manager.remove_delivery_route("keriodb://deliveryroute/123")
        self.assertTrue(res["success"])
        self.assertEqual(res["method"], "Smtp.setRelayDeliveryRuleList")

    def test_extract_routes_from_smtp_get(self) -> None:
        """Тест извлечения индивидуальных правил из конфигурации Smtp.get (таблица «Доставка SMTP»)."""
        from mailbox_app.services.kerio.exceptions import KerioObjectNotFoundError

        def mock_call(method: str, params: dict = None) -> dict:
            if method == "Smtp.get":
                return {
                    "server": {
                        "delivery": {
                            "useSsl": True,
                            "customRules": [
                                {
                                    "id": "keriodb://deliveryroute/e.shevcova",
                                    "isEnabled": True,
                                    "description": "e.shevcova",
                                    "conditionType": "ConditionSender",
                                    "matchPattern": "e.shevcova@barkol.ru",
                                    "actionType": "ActionRelayServer",
                                    "relayServer": {
                                        "server": "smtp.barkol.ru",
                                        "port": 587,
                                        "mode": "StlsCommand",
                                        "authentication": {
                                            "isEnabled": True,
                                            "userName": "e.shevcova@barkol.ru",
                                            "password": "secretPassword",
                                        },
                                    },
                                }
                            ],
                        }
                    }
                }
            raise KerioObjectNotFoundError("[Код -32601] Method not found.")

        self.client.call.side_effect = mock_call
        routes = self.manager.get_routes()
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0]["description"], "e.shevcova")
        self.assertEqual(routes[0]["sender"], "e.shevcova@barkol.ru")
        self.assertEqual(routes[0]["server"], "smtp.barkol.ru")

    def test_create_delivery_route_via_smtp_set(self) -> None:
        """Тест создания правила через Smtp.get -> Smtp.set при отсутствии прямого табличного метода."""
        from mailbox_app.services.kerio.exceptions import KerioObjectNotFoundError

        smtp_config = {
            "server": {
                "delivery": {
                    "useSsl": True,
                    "customRules": [],
                }
            }
        }

        def mock_call(method: str, params: dict = None) -> dict:
            if method == "Smtp.get":
                return smtp_config
            if method == "Smtp.set":
                return {"result": "ok"}
            raise KerioObjectNotFoundError("[Код -32601] Method not found.")

        self.client.call.side_effect = mock_call
        res = self.manager.create_delivery_route(
            sender_email="a.administrator@barkol.ru",
            password="securePassword123",
            relay_host="smtp.barkol.ru",
            relay_port=587,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["method"], "Smtp.set")
        self.assertEqual(res["sender"], "a.administrator@barkol.ru")

    def test_get_django_setting_fallback(self) -> None:
        """Тест безопасного извлечения параметров с fallback значением."""
        from mailbox_app.services.kerio.utils import get_django_setting

        val = get_django_setting("NON_EXISTING_SETTING_12345", "fallback_val")
        self.assertEqual(val, "fallback_val")

    def test_get_users_list_individual_vs_global_smtp(self) -> None:
        """Тест корректной классификации индивидуального и серверного SMTP Relay в get_users_list."""
        from mailbox_app.services.kerio.exceptions import KerioObjectNotFoundError
        from mailbox_app.services.kerio.service import KerioAdminService

        mock_client = MagicMock(spec=KerioConnectAdminClient)
        mock_client.token = "token123"

        def mock_call(method: str, params: dict = None) -> dict:
            if method == "Domains.get":
                return {
                    "list": [{"id": "dom_barkol", "name": "barkol.ru"}],
                    "totalItems": 1,
                }
            if method == "Users.get":
                return {
                    "list": [
                        {"id": "u1", "loginName": "a.administrator", "fullName": "Admin User", "isEnabled": True},
                        {"id": "u2", "loginName": "e.shevcova", "fullName": "Elena Shevcova", "isEnabled": True},
                    ],
                    "totalItems": 2,
                }
            if method == "Delivery.getPop3AccountList":
                return {
                    "list": [
                        {"id": "p1", "targetUser": "a.administrator", "server": "mail.barkol.ru", "port": 995, "isActive": True}
                    ]
                }
            if method == "Smtp.get":
                return {
                    "server": {
                        "delivery": {
                            "customRules": [
                                {
                                    "id": "keriodb://deliveryroute/e.shevcova",
                                    "matchPattern": "e.shevcova@barkol.ru",
                                    "relayServer": {"server": "smtp.barkol.ru", "port": 587},
                                }
                            ]
                        }
                    }
                }
            raise KerioObjectNotFoundError("Method not found")

        mock_client.call.side_effect = mock_call
        service = KerioAdminService(client=mock_client)
        result = service.get_users_list(domain_name="barkol.ru")

        self.assertEqual(result["totalItems"], 2)
        users = result["list"]

        # u1: a.administrator -> индивидуального правила нет, но есть серверный fallback
        admin_u = next(u for u in users if u["loginName"] == "a.administrator")
        self.assertTrue(admin_u["has_smtp_delivery"])
        self.assertFalse(admin_u["is_individual_smtp_delivery"])

        # u2: e.shevcova -> индивидуальное правило есть
        elena_u = next(u for u in users if u["loginName"] == "e.shevcova")
        self.assertTrue(elena_u["has_smtp_delivery"])
        self.assertTrue(elena_u["is_individual_smtp_delivery"])

    def test_get_users_list_alphabetical_sorting(self) -> None:
        """Тест сортировки пользователей по алфавиту (по ФИО и логину)."""
        from mailbox_app.services.kerio.service import KerioAdminService

        mock_client = MagicMock(spec=KerioConnectAdminClient)
        mock_client.token = "token123"

        def mock_call(method: str, params: dict = None) -> dict:
            if method == "Domains.get":
                return {"list": [{"id": "dom_barkol", "name": "barkol.ru"}], "totalItems": 1}
            if method == "Users.get":
                return {
                    "list": [
                        {"id": "u3", "loginName": "z.zaytsev", "fullName": "Яковлев Яков", "isEnabled": True},
                        {"id": "u1", "loginName": "b.borisov", "fullName": "Алексеев Алексей", "isEnabled": True},
                        {"id": "u2", "loginName": "a.andreev", "fullName": "Борисов Борис", "isEnabled": True},
                    ],
                    "totalItems": 3,
                }
            if method == "Delivery.getPop3AccountList":
                return {"list": []}
            if method == "Smtp.get":
                return {"server": {"delivery": {"customRules": []}}}
            return {}

        mock_client.call.side_effect = mock_call
        service = KerioAdminService(client=mock_client)
        result = service.get_users_list(domain_name="barkol.ru")
        users = result["list"]

        self.assertEqual(len(users), 3)
        self.assertEqual(users[0]["fullName"], "Алексеев Алексей")
        self.assertEqual(users[1]["fullName"], "Борисов Борис")
        self.assertEqual(users[2]["fullName"], "Яковлев Яков")


class ISPmanagerExternalMailProviderTestCase(TestCase):
    """Тестирование адаптера ISPmanagerExternalMailProvider (Reg.ru хостинг)."""

    def test_unconfigured_provider_graceful_fallback(self) -> None:
        """Тест работы провайдера без настроенных параметров подключения."""
        from mailbox_app.services.kerio.external_provider import ISPmanagerExternalMailProvider

        provider = ISPmanagerExternalMailProvider(
            panel_url="https://mail.barkol.ru:1500/ispmgr",
            api_username="",
            api_password="",
        )
        self.assertFalse(provider.is_configured)

        res = provider.create_mailbox(
            email="test.user@barkol.ru",
            password="SecurePassword123!",
            full_name="Тестовый Пользователь",
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["provider"], "ispmanager")

        # Проверка смены пароля и удаления в неконфигурированном режиме
        self.assertTrue(provider.change_password("test.user@barkol.ru", "NewPass123!"))
        self.assertTrue(provider.check_mailbox_exists("test.user@barkol.ru"))
        self.assertTrue(provider.delete_mailbox("test.user@barkol.ru"))

    @patch("mailbox_app.services.kerio.external_provider.requests.post")
    def test_configured_provider_create_and_change_password(self, mock_post: MagicMock) -> None:
        """Тест создания ящика и смены пароля в настроенном провайдере ISPmanager."""
        from mailbox_app.services.kerio.external_provider import ISPmanagerExternalMailProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"doc": {"ok": ""}}
        mock_post.return_value = mock_resp

        provider = ISPmanagerExternalMailProvider(
            panel_url="https://mail.barkol.ru:1500/ispmgr",
            api_username="barkol_admin",
            api_password="HostingPassword123!",
        )
        self.assertTrue(provider.is_configured)

        # 1. Создание ящика
        res = provider.create_mailbox(
            email="i.ivanov@barkol.ru",
            password="SecretPassword123!",
            full_name="Иван Иванов",
            quota_mb=2048,
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "created")

        mock_post.assert_called()
        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["data"]["func"], "email.edit")
        self.assertEqual(call_kwargs["data"]["name"], "i.ivanov")
        self.assertEqual(call_kwargs["data"]["domain"], "barkol.ru")
        self.assertEqual(call_kwargs["data"]["domainname"], "barkol.ru")
        self.assertEqual(call_kwargs["data"]["plid"], "barkol.ru")
        self.assertEqual(call_kwargs["data"]["passwd"], "SecretPassword123!")
        self.assertEqual(call_kwargs["data"]["confirm"], "SecretPassword123!")
        self.assertEqual(call_kwargs["data"]["password"], "SecretPassword123!")
        self.assertEqual(call_kwargs["data"]["passwd_confirm"], "SecretPassword123!")
        self.assertEqual(call_kwargs["data"]["maxsize"], 2048)
        self.assertEqual(call_kwargs["data"]["quota"], 2048)
        self.assertEqual(call_kwargs["data"]["note"], "Иван Иванов")

        # 2. Смена пароля
        mock_post.reset_mock()
        pwd_res = provider.change_password("i.ivanov@barkol.ru", "NewPass456!")
        self.assertTrue(pwd_res)
        self.assertEqual(mock_post.call_args[1]["data"]["elid"], "i.ivanov")
        self.assertEqual(mock_post.call_args[1]["data"]["plid"], "barkol.ru")
        self.assertEqual(mock_post.call_args[1]["data"]["domainname"], "barkol.ru")
        self.assertEqual(mock_post.call_args[1]["data"]["passwd"], "NewPass456!")
        self.assertEqual(mock_post.call_args[1]["data"]["confirm"], "NewPass456!")
        self.assertEqual(mock_post.call_args[1]["data"]["password"], "NewPass456!")
        self.assertEqual(mock_post.call_args[1]["data"]["passwd_confirm"], "NewPass456!")

        # 3. Удаление ящика
        mock_post.reset_mock()
        del_res = provider.delete_mailbox("i.ivanov@barkol.ru")
        self.assertTrue(del_res)
        self.assertEqual(mock_post.call_args[1]["data"]["func"], "email.delete")
        self.assertEqual(mock_post.call_args[1]["data"]["elid"], "i.ivanov")
        self.assertEqual(mock_post.call_args[1]["data"]["plid"], "barkol.ru")

    @patch("mailbox_app.services.kerio.external_provider.requests.post")
    def test_provider_diagnostics_and_queries(self, mock_post: MagicMock) -> None:
        """Тест диагностических методов ISPmanager: test_connection, get_mailboxes, get_form_metadata, get_domains."""
        from mailbox_app.services.kerio.external_provider import ISPmanagerExternalMailProvider

        provider = ISPmanagerExternalMailProvider(
            panel_url="https://mail.barkol.ru:1500/ispmgr",
            api_username="barkol_admin",
            api_password="HostingPassword123!",
        )

        # 1. test_connection
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"doc": {"user": "barkol_admin"}}
        mock_post.return_value = mock_resp

        conn_res = provider.test_connection()
        self.assertTrue(conn_res["success"])
        self.assertEqual(conn_res["user"], "barkol_admin")

        # 2. get_form_metadata
        mock_resp.json.return_value = {
            "doc": {
                "name": {},
                "domain": {},
                "passwd": {},
                "confirm": {},
                "quota": {},
            }
        }
        form_res = provider.get_form_metadata("email.edit")
        self.assertTrue(form_res["success"])
        self.assertIn("passwd", form_res["data"]["doc"])

        # 3. get_mailboxes
        mock_resp.json.return_value = {
            "doc": {
                "elem": [
                    {"name": "a.administrator", "domain": "barkol.ru", "quota": "2048", "used": "120"},
                    {"name": "test.user@barkol.ru", "domain": "", "quota": "512", "used": "0"},
                ]
            }
        }
        boxes = provider.get_mailboxes(domain="barkol.ru")
        self.assertEqual(len(boxes), 2)
        self.assertEqual(boxes[0]["email"], "a.administrator@barkol.ru")
        self.assertEqual(boxes[1]["email"], "test.user@barkol.ru")

        # 4. get_domains
        mock_resp.json.return_value = {
            "doc": {
                "elem": [
                    {"name": "barkol.ru", "status": "active"},
                ]
            }
        }
        doms = provider.get_domains()
        self.assertEqual(len(doms), 1)
        self.assertEqual(doms[0]["name"], "barkol.ru")





