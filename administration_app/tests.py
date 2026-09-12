"""Unit-тесты для модуля утилит administration_app.utils (интеграция OData с 1С)."""

from unittest.mock import MagicMock, patch
from django.test import TestCase

from administration_app.utils import (
    EMAIL_1C_CONTACT_KIND,
    EMAIL_1C_CONTACT_TYPE,
    _build_1c_email_contact,
    update_1c_physical_person_email,
)


class Update1CPhysicalPersonEmailTestCase(TestCase):
    """Тестирование функции обновления/записи email физлица в 1С ЗУП через OData."""

    def test_build_1c_email_contact_structure(self) -> None:
        """Тест формирования структуры элемента КонтактнаяИнформация для email."""
        contact = _build_1c_email_contact("o.adygezalov@barkol.ru", line_number=2)
        self.assertEqual(contact["LineNumber"], "2")
        self.assertEqual(contact["Тип"], EMAIL_1C_CONTACT_TYPE)
        self.assertEqual(contact["Вид_Key"], EMAIL_1C_CONTACT_KIND)
        self.assertEqual(contact["Представление"], "o.adygezalov@barkol.ru")
        self.assertEqual(contact["Значение"], "o.adygezalov@barkol.ru")
        self.assertEqual(contact["АдресЭП"], "o.adygezalov@barkol.ru")
        self.assertEqual(contact["ДоменноеИмяСервера"], "barkol.ru")
        self.assertEqual(contact["ВидДляСписка_Key"], EMAIL_1C_CONTACT_KIND)
        self.assertIn("xsi:type=\"ЭлектроннаяПочта\"", contact["ЗначенияПолей"])
        self.assertIn("Значение=\"o.adygezalov@barkol.ru\"", contact["ЗначенияПолей"])

    def test_update_1c_email_invalid_guid(self) -> None:
        """Тест отклонения пустого или невалидного GUID."""
        success, msg = update_1c_physical_person_email("", "test@barkol.ru")
        self.assertFalse(success)
        self.assertIn("person_ref_key отсутствует", msg)

        success, msg = update_1c_physical_person_email("00000000-0000-0000-0000-000000000000", "test@barkol.ru")
        self.assertFalse(success)
        self.assertIn("пустой GUID", msg)

        success, msg = update_1c_physical_person_email("not-a-valid-guid", "test@barkol.ru")
        self.assertFalse(success)
        self.assertIn("Некорректный GUID", msg)

    def test_update_1c_email_invalid_email(self) -> None:
        """Тест отклонения некорректного формата email."""
        guid = "26b8e1ea-5b27-11f1-8ddf-ac1f6bdb1419"
        success, msg = update_1c_physical_person_email(guid, "invalid-email")
        self.assertFalse(success)
        self.assertIn("Некорректный формат", msg)

        success, msg = update_1c_physical_person_email(guid, "@barkol.ru")
        self.assertFalse(success)
        self.assertIn("Некорректный формат", msg)

    def test_update_1c_email_invalid_base_index(self) -> None:
        """Тест отклонения некорректного индекса базы."""
        guid = "26b8e1ea-5b27-11f1-8ddf-ac1f6bdb1419"
        success, msg = update_1c_physical_person_email(guid, "test@barkol.ru", base_index=99)
        self.assertFalse(success)
        self.assertIn("Некорректный индекс", msg)

    @patch("requests.patch")
    @patch("requests.get")
    def test_update_1c_email_create_new_contact(self, mock_get: MagicMock, mock_patch: MagicMock) -> None:
        """Тест добавления новой строки email, когда у физлица в 1С есть только телефон и адрес."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "Ref_Key": "26b8e1ea-5b27-11f1-8ddf-ac1f6bdb1419",
            "КонтактнаяИнформация": [
                {
                    "LineNumber": "1",
                    "Тип": "Телефон",
                    "Вид_Key": "d34fea50-cfaf-11e6-bad8-902b345cadc2",
                    "Представление": "+7 (925) 045-23-43",
                }
            ],
        }

        mock_patch.return_value.status_code = 204

        guid = "26b8e1ea-5b27-11f1-8ddf-ac1f6bdb1419"
        success, msg = update_1c_physical_person_email(guid, "o.adygezalov@barkol.ru")

        self.assertTrue(success)
        self.assertIn("успешно записан", msg)

        # Проверяем, что в PATCH отправлено 2 элемента (телефон + новый email)
        patch_kwargs = mock_patch.call_args[1]
        contacts = patch_kwargs["json"]["КонтактнаяИнформация"]
        self.assertEqual(len(contacts), 2)
        email_row = contacts[1]
        self.assertEqual(email_row["LineNumber"], "2")
        self.assertEqual(email_row["Тип"], EMAIL_1C_CONTACT_TYPE)
        self.assertEqual(email_row["Вид_Key"], EMAIL_1C_CONTACT_KIND)
        self.assertEqual(email_row["Представление"], "o.adygezalov@barkol.ru")
        self.assertEqual(email_row["АдресЭП"], "o.adygezalov@barkol.ru")
        self.assertEqual(email_row["ДоменноеИмяСервера"], "barkol.ru")

    @patch("requests.patch")
    @patch("requests.get")
    def test_update_1c_email_update_existing_contact(self, mock_get: MagicMock, mock_patch: MagicMock) -> None:
        """Тест обновления уже существующей строки email в 1С."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "Ref_Key": "26b8e1ea-5b27-11f1-8ddf-ac1f6bdb1419",
            "КонтактнаяИнформация": [
                {
                    "LineNumber": "1",
                    "Тип": "АдресЭлектроннойПочты",
                    "Вид_Key": EMAIL_1C_CONTACT_KIND,
                    "Представление": "old@barkol.ru",
                    "АдресЭП": "old@barkol.ru",
                    "Значение": "old@barkol.ru",
                }
            ],
        }

        mock_patch.return_value.status_code = 200

        guid = "26b8e1ea-5b27-11f1-8ddf-ac1f6bdb1419"
        success, msg = update_1c_physical_person_email(guid, "new@barkol.ru")

        self.assertTrue(success)
        self.assertIn("успешно записан", msg)

        patch_kwargs = mock_patch.call_args[1]
        contacts = patch_kwargs["json"]["КонтактнаяИнформация"]
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0]["Представление"], "new@barkol.ru")
        self.assertEqual(contacts[0]["АдресЭП"], "new@barkol.ru")
        self.assertEqual(contacts[0]["Значение"], "new@barkol.ru")
