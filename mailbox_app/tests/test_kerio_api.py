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
        self.mock_client.call.assert_called_with("Users.remove", params={"userIds": ["u_2"]})

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
        """Тест создания полного контура ящика (Kerio + POP3 + Django MailAccount)."""
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
        )

        self.assertTrue(report["success"])
        self.assertEqual(report["email"], "v.shakirov@barkol.ru")
        self.assertEqual(report["steps"]["kerio_user"]["status"], "ok")
        self.assertEqual(report["steps"]["kerio_pop3_download"]["status"], "ok")
        self.assertEqual(report["steps"]["django_account"]["status"], "ok")

        # Проверяем созданный MailAccount в БД Django
        account = MailAccount.objects.get(user=self.user)
        self.assertEqual(account.email, "v.shakirov@barkol.ru")
        self.assertEqual(account.get_password(), "UltraSecretPassword123")
        self.assertEqual(account.imap_host, "imap.barkol.ru")
        self.assertEqual(account.smtp_host, "sm.barkol.ru")
        self.assertTrue(account.is_active)


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
        self.assertEqual(login_lvl3, "alexey.abramov")

        occupied.add("alexey.abramov")

        # Уровень 4: числовой суффикс
        login_lvl4 = generate_corporate_mailbox_login("Алексей", "Абрамов", "Борисович", existing_logins=occupied)
        self.assertEqual(login_lvl4, "a.abramov2")

        occupied.add("a.abramov2")
        login_lvl4_next = generate_corporate_mailbox_login("Алексей", "Абрамов", "Борисович", existing_logins=occupied)
        self.assertEqual(login_lvl4_next, "a.abramov3")

