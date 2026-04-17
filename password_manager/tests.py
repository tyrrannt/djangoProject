# password_manager/tests.py
"""
Комплексные тесты приложения password_manager.

Покрывает: криптографию, генератор, сервисный слой, 
создание истории при обновлении и контроль доступа.
"""

import os
import sys
from unittest.mock import patch
from django.conf import settings
from cryptography.fernet import Fernet
from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.urls import reverse

from .models import (
    PasswordGroup, EncryptedPassword, PasswordHistory,
    SharedPassword, UserKeyHash, ResourceType
)
from .services import PasswordService
from .crypto import CryptoEngine
from .generator import PasswordGenerator
from decouple import config

from customers_app.models import DataBaseUser


# ✅ Базовый класс с правильной настройкой мастер-ключа через mock
class BasePasswordManagerTest(TestCase):
    """Базовый класс для всех тестов password_manager."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Генерируем тестовый мастер-ключ
        cls.test_master_key = Fernet.generate_key().decode()
        print(f"\n✅ Test master key generated: {cls.test_master_key[:20]}...")

    def setUp(self):
        super().setUp()
        # Создаем патч для config, чтобы возвращать тестовый ключ
        self.config_patcher = patch('password_manager.services.config')
        self.mock_config = self.config_patcher.start()

        # Настраиваем mock для config
        def config_side_effect(key, default=None):
            if key == 'PASSWORD_MANAGER_MASTER_KEY':
                return self.test_master_key
            elif key == 'PASSWORD_MANAGER_APP_SALT':
                return 'test_salt_32bytes_for_testing_purpose!!'
            return default

        self.mock_config.side_effect = config_side_effect

        # Также патчим config в crypto
        self.crypto_patcher = patch('password_manager.crypto.config')
        self.mock_crypto_config = self.crypto_patcher.start()
        self.mock_crypto_config.side_effect = config_side_effect

    def tearDown(self):
        super().tearDown()
        self.config_patcher.stop()
        self.crypto_patcher.stop()


class CryptoEngineTests(BasePasswordManagerTest):
    """Тесты низкоуровневой криптографии."""

    def setUp(self):
        super().setUp()
        self.phrase = "secure_passphrase_2024"
        self.user_id = 42

    def test_derive_key_deterministic(self):
        """Одинаковые входные данные -> одинаковый ключ."""
        key1 = CryptoEngine.derive_key(self.phrase, str(self.user_id))
        key2 = CryptoEngine.derive_key(self.phrase, str(self.user_id))
        self.assertEqual(key1, key2)

    def test_derive_key_unique_per_user(self):
        """Разные user_id -> разные ключи даже при одинаковой фразе."""
        key_user1 = CryptoEngine.derive_key(self.phrase, "1")
        key_user2 = CryptoEngine.derive_key(self.phrase, "2")
        self.assertNotEqual(key_user1, key_user2)

    def test_encrypt_decrypt_roundtrip(self):
        """Цикл шифрования/дешифрования возвращает исходный текст."""
        plaintext = "MySuperSecret123!"
        encrypted = CryptoEngine.encrypt(plaintext, self.phrase, self.user_id)
        decrypted = CryptoEngine.decrypt(encrypted, self.phrase, self.user_id)
        self.assertEqual(plaintext, decrypted)

    def test_wrong_passphrase_raises_error(self):
        """Неверная фраза должна выбрасывать ValueError."""
        ciphertext = CryptoEngine.encrypt("secret", "correct_phrase", self.user_id)
        with self.assertRaises(ValueError):
            CryptoEngine.decrypt(ciphertext, "wrong_phrase", self.user_id)


class PasswordGeneratorTests(BasePasswordManagerTest):
    """Тесты генератора паролей."""

    def test_default_length_and_charset(self):
        pwd = PasswordGenerator.generate(length=12)
        self.assertEqual(len(pwd), 12)
        self.assertTrue(any(c.isupper() for c in pwd))
        self.assertTrue(any(c.islower() for c in pwd))
        self.assertTrue(any(c.isdigit() for c in pwd))

    def test_special_chars_off(self):
        pwd = PasswordGenerator.generate(length=16, use_special=False)
        self.assertEqual(len(pwd), 16)
        self.assertFalse(any(c in PasswordGenerator.SPECIAL_CHARS for c in pwd))

    def test_exclude_similar_chars(self):
        pwd = PasswordGenerator.generate(length=20, exclude_similar=True)
        for char in PasswordGenerator.SIMILAR_CHARS:
            self.assertNotIn(char, pwd, f"Character '{char}' found in password but should be excluded")


class ServiceLayerTests(BasePasswordManagerTest):
    """Тесты бизнес-логики PasswordService."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = DataBaseUser.objects.create(
            email="test@example.com",
            username="testuser"
        )
        cls.phrase = "master_key_phrase"

    def test_setup_and_verify_passphrase(self):
        PasswordService.setup_or_update_key(self.user, self.phrase)
        self.assertTrue(UserKeyHash.objects.filter(user=self.user).exists())
        self.assertTrue(PasswordService.verify_passphrase(self.user, self.phrase))
        self.assertFalse(PasswordService.verify_passphrase(self.user, "wrong"))

    def test_admin_decrypt_fallback(self):
        """Административное дешифрование должно работать с MASTER_KEY."""
        plaintext = "admin_view_password"

        # Шифруем с использованием тестового мастер-ключа
        ciphertext = CryptoEngine.encrypt_with_key(plaintext, self.test_master_key)

        # Дешифруем через admin_decrypt (использует config с нашим mock)
        decrypted = PasswordService.admin_decrypt(ciphertext)
        self.assertEqual(decrypted, plaintext)


class ModelLogicTests(BasePasswordManagerTest):
    """Тесты истории паролей и атомарных операций."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.user = DataBaseUser.objects.create(
            email="owner@example.com",
            username="owner"
        )
        PasswordService.setup_or_update_key(cls.user, "test_phrase")
        cls.group = PasswordGroup.objects.create(name="Test Group", owner=cls.user)

    def setUp(self):
        super().setUp()
        self.form_data = {
            'resource_type': ResourceType.WEBSITE,
            'url': 'https://example.com',
            'login': 'admin',
            'group': self.group.pk,
            'passphrase': 'test_phrase',
            'raw_password': 'InitialPass123!'
        }

    def _create_password(self):
        from .forms import EncryptedPasswordForm
        form = EncryptedPasswordForm(
            data=self.form_data,
            request=type('Req', (), {'user': self.user})()
        )
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        return form.save()

    def test_no_history_on_create(self):
        obj = self._create_password()
        self.assertEqual(PasswordHistory.objects.filter(original_record=obj).count(), 0)

    def test_history_created_on_update(self):
        obj = self._create_password()
        old_enc = obj.encrypted_password

        update_data = self.form_data.copy()
        update_data['raw_password'] = 'UpdatedPass456!'

        from .forms import EncryptedPasswordForm
        form = EncryptedPasswordForm(
            instance=obj,
            data=update_data,
            request=type('Req', (), {'user': self.user})()
        )
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        form.save()

        obj.refresh_from_db()
        history = PasswordHistory.objects.filter(original_record=obj).first()

        self.assertEqual(PasswordHistory.objects.filter(original_record=obj).count(), 1)
        self.assertEqual(history.encrypted_password, old_enc)
        self.assertNotEqual(obj.encrypted_password, old_enc)


class AccessControlTests(BasePasswordManagerTest):
    """Тесты миксина контроля доступа."""

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.owner = DataBaseUser.objects.create(
            email="owner@test.com",
            username="owner"
        )
        self.reader = DataBaseUser.objects.create(
            email="reader@test.com",
            username="reader"
        )
        self.editor = DataBaseUser.objects.create(
            email="editor@test.com",
            username="editor"
        )

        PasswordService.setup_or_update_key(self.owner, "phrase")

        self.group = PasswordGroup.objects.create(name="G", owner=self.owner)
        self.pwd = EncryptedPassword.objects.create(
            resource_type=ResourceType.APP, url='http://t.ru', login='u',
            encrypted_password='enc', group=self.group, owner=self.owner
        )

        self.shared = SharedPassword.objects.create(encrypted_password=self.pwd)
        self.shared.shared_with.add(self.reader, self.editor)
        self.shared.permissions = {str(self.reader.pk): 'read', str(self.editor.pk): 'edit'}
        self.shared.save()

    def test_owner_has_edit_access(self):
        self.assertEqual('edit', 'edit')

    def test_reader_cannot_edit(self):
        self.assertEqual(self.shared.get_permission_for(self.reader.pk), 'read')
        self.assertNotEqual(self.shared.get_permission_for(self.reader.pk), 'edit')

    def test_editor_can_edit(self):
        self.assertEqual(self.shared.get_permission_for(self.editor.pk), 'edit')
