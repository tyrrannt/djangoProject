# password_manager/generator.py
"""
Криптографически безопасный генератор паролей.

Использует модуль `secrets` вместо `random` для соответствия
требованиям безопасности (CWE-330: Use of Insufficiently Random Values).
"""

import secrets
import string


class PasswordGenerator:
    """
    Генератор паролей с настраиваемой энтропией и фильтрацией символов.
    """
    DEFAULT_LENGTH = 12
    SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    # Символы, которые визуально похожи (l/1/I, 0/O/o)
    SIMILAR_CHARS = "l1I0Oo"

    @classmethod
    def generate(
            cls,
            length: int = DEFAULT_LENGTH,
            use_special: bool = True,
            exclude_similar: bool = False
    ) -> str:
        """
        Генерирует пароль заданной длины с учетом политик сложности.

        Args:
            length: Минимальная длина пароля (по умолчанию 12).
            use_special: Включать ли спецсимволы.
            exclude_similar: Исключать ли визуально похожие символы.

        Returns:
            str: Сгенерированный пароль.
        """
        # Формируем пул допустимых символов
        pool = string.ascii_letters + string.digits
        if use_special:
            pool += cls.SPECIAL_CHARS
        if exclude_similar:
            pool = ''.join(c for c in pool if c not in cls.SIMILAR_CHARS)

        # Гарантируем наличие хотя бы одного символа из каждой обязательной категории
        mandatory = []
        upper_pool = string.ascii_uppercase.replace('O', '').replace('I',
                                                                     '') if exclude_similar else string.ascii_uppercase
        lower_pool = string.ascii_lowercase.replace('l', '') if exclude_similar else string.ascii_lowercase
        digit_pool = string.digits.replace('1', '').replace('0', '') if exclude_similar else string.digits

        if any(c in upper_pool for c in pool):
            mandatory.append(secrets.choice(upper_pool))
        if any(c in lower_pool for c in pool):
            mandatory.append(secrets.choice(lower_pool))
        if any(c in digit_pool for c in pool):
            mandatory.append(secrets.choice(digit_pool))
        if use_special and any(c in cls.SPECIAL_CHARS for c in pool):
            mandatory.append(secrets.choice(cls.SPECIAL_CHARS))

        # Заполняем оставшуюся длину
        remaining = max(0, length - len(mandatory))
        password_list = mandatory + [secrets.choice(pool) for _ in range(remaining)]

        # Перемешиваем с использованием криптографически безопасного ГПСЧ
        rng = secrets.SystemRandom()
        rng.shuffle(password_list)

        return ''.join(password_list)
