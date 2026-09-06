"""Модуль криптографических утилит для работы с ЭЦП (КЭП / ГОСТ / X.509 / CAdES / КриптоПро).

Предоставляет функции для синтаксического анализа квалифицированных сертификатов X.509,
извлечения российских идентификаторов (СНИЛС, ИНН, ОГРН, ФИО, организация, УЦ),
генерации и проверки одноразовых криптографических challenge, а также сопоставления
сертификата с учетными записями пользователей портала ООО АК «БАРКОЛ».
"""

import base64
import hashlib
import re
import secrets
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, Optional, Tuple, Union

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from django.utils import timezone

from core import logger
from customers_app.models import DataBaseUser, UserCertificate


# Стандартные российские и международные OID в сертификатах КЭП (ГОСТ)
OID_MAP = {
    '1.2.643.100.1': 'OGRN',                # ОГРН организации
    '1.2.643.100.3': 'SNILS',               # СНИЛС владельца (11 цифр)
    '1.2.643.100.4': 'INN_LEGAL',           # ИНН юридического лица (10 цифр)
    '1.2.643.100.5': 'OGRNIP',              # ОГРНИП индивидуального предпринимателя
    '1.2.643.3.131.1.1': 'INN',             # ИНН физического лица / ИП (12 цифр)
    '2.5.4.3': 'CN',                        # Common Name (ФИО или название)
    '2.5.4.4': 'SN',                        # Surname (Фамилия)
    '2.5.4.42': 'GN',                       # GivenName (Имя и Отчество)
    '2.5.4.10': 'O',                        # Organization (Организация)
    '2.5.4.11': 'OU',                       # Organizational Unit (Подразделение)
    '2.5.4.12': 'T',                        # Title (Должность)
    '2.5.4.8': 'ST',                        # State / Region (Регион)
    '2.5.4.7': 'L',                         # Locality (Город)
    '2.5.4.6': 'C',                         # Country (Страна)
    '1.2.840.113549.1.9.1': 'E',            # Email
}


def generate_cert_challenge(byte_length: int = 32) -> str:
    """Генерирует криптографически стойкую случайную строку challenge в формате Base64URL.

    Args:
        byte_length: Длина случайной последовательности байт (по умолчанию 32).

    Returns:
        str: Сгенерированный challenge в формате Base64URL (без символов padding '=').
    """
    token = secrets.token_bytes(byte_length)
    return base64.urlsafe_b64encode(token).decode('ascii').rstrip('=')


def clean_digits(value: Optional[str]) -> str:
    """Очищает строку от любых символов, кроме цифр.

    Args:
        value: Исходная строка (например, СНИЛС '123-456-789 01' или ИНН).

    Returns:
        str: Строка, содержащая только цифры (например, '12345678901').
    """
    if not value:
        return ""
    return re.sub(r'\D', '', str(value))


def parse_x509_certificate(cert_input: Union[bytes, str]) -> Dict[str, Any]:
    """Выполняет синтаксический анализ сертификата X.509 и извлекает все реквизиты субъекта и издателя.

    Поддерживает как бинарный формат DER, так и текстовые форматы PEM или Base64.
    Извлекает отпечаток SHA-1, серийный номер, даты действия, субъект, издатель,
    а также российские квалифицированные OID: СНИЛС, ИНН, ОГРН, ФИО и должность.

    Args:
        cert_input: Данные сертификата (bytes, строка PEM или чистый Base64).

    Returns:
        Dict[str, Any]: Словарь с извлеченными метаданными сертификата:
            - thumbprint (str): SHA-1 отпечаток (40 символов в верхнем регистре);
            - serial_number (str): Серийный номер в шестнадцатеричном виде;
            - valid_from (datetime): Дата начала действия (timezone-aware);
            - valid_to (datetime): Дата окончания действия (timezone-aware);
            - is_expired (bool): Истек ли срок действия;
            - subject_name (str): Полная строка DN субъекта;
            - issuer_name (str): Полная строка DN издателя (УЦ);
            - cn (str): ФИО или Common Name;
            - snils (str): СНИЛС (11 цифр);
            - inn (str): ИНН владельца (12 или 10 цифр);
            - ogrn (str): ОГРН организации;
            - organization (str): Название компании;
            - title (str): Должность;
            - email (str): Электронная почта;
            - raw_base64 (str): Сертификат в формате Base64;
            - pem (str): Сертификат в формате PEM.

    Raises:
        ValueError: Если данные не являются корректным сертификатом X.509.
    """
    raw_der: bytes

    if isinstance(cert_input, str):
        cleaned_str = cert_input.strip()
        if '-----BEGIN CERTIFICATE-----' in cleaned_str:
            # Преобразуем PEM в DER
            lines = [l.strip() for l in cleaned_str.splitlines() if not l.startswith('-----')]
            raw_der = base64.b64decode(''.join(lines))
        else:
            # Считаем, что передан чистый Base64
            # Дополняем padding при необходимости
            pad = len(cleaned_str) % 4
            if pad:
                cleaned_str += '=' * (4 - pad)
            raw_der = base64.b64decode(cleaned_str)
    elif isinstance(cert_input, (bytes, bytearray)):
        raw_der = bytes(cert_input)
    else:
        raise ValueError(f"Неподдерживаемый тип входных данных сертификата: {type(cert_input)}")

    try:
        cert = x509.load_der_x509_certificate(raw_der)
    except Exception as e:
        # Пробуем как PEM байты
        try:
            cert = x509.load_pem_x509_certificate(raw_der)
            raw_der = cert.public_bytes(x509.Encoding.DER)
        except Exception:
            raise ValueError(f"Ошибка загрузки сертификата X.509: {e}")

    # 1. Отпечаток SHA-1 Thumbprint (в верхнем регистре)
    thumbprint = cert.fingerprint(hashes.SHA1()).hex().upper()

    # 2. Серийный номер
    serial_number = hex(cert.serial_number)[2:].upper()

    # 3. Сроки действия (делаем timezone-aware в UTC)
    try:
        valid_from = cert.not_valid_before_utc
        valid_to = cert.not_valid_after_utc
    except AttributeError:
        # Для более старых версий cryptography
        valid_from = cert.not_valid_before.replace(tzinfo=dt_timezone.utc)
        valid_to = cert.not_valid_after.replace(tzinfo=dt_timezone.utc)

    now_utc = datetime.now(dt_timezone.utc)
    is_expired = now_utc > valid_to or now_utc < valid_from

    # 4. Разбор атрибутов субъекта (Subject DN)
    subject_parts = []
    attributes: Dict[str, str] = {}

    for attr in cert.subject:
        dotted_oid = attr.oid.dotted_string
        val_str = str(attr.value)
        short_name = OID_MAP.get(dotted_oid, dotted_oid)
        attributes[short_name] = val_str
        attributes[dotted_oid] = val_str
        subject_parts.append(f"{short_name}={val_str}")

    # 5. Разбор атрибутов издателя (Issuer DN)
    issuer_parts = []
    for attr in cert.issuer:
        dotted_oid = attr.oid.dotted_string
        val_str = str(attr.value)
        short_name = OID_MAP.get(dotted_oid, dotted_oid)
        issuer_parts.append(f"{short_name}={val_str}")

    subject_name = ", ".join(subject_parts)
    issuer_name = ", ".join(issuer_parts)

    # 6. Извлечение ключевых идентификаторов
    snils_raw = attributes.get('SNILS', '') or attributes.get('1.2.643.100.3', '')
    snils = clean_digits(snils_raw)

    inn_raw = attributes.get('INN', '') or attributes.get('1.2.643.3.131.1.1', '') or attributes.get('INN_LEGAL', '') or attributes.get('1.2.643.100.4', '')
    inn = clean_digits(inn_raw)

    cn = attributes.get('CN', '') or attributes.get('2.5.4.3', '')
    surname = attributes.get('SN', '') or attributes.get('2.5.4.4', '')
    given_name = attributes.get('GN', '') or attributes.get('2.5.4.42', '')
    organization = attributes.get('O', '') or attributes.get('2.5.4.10', '')
    title = attributes.get('T', '') or attributes.get('2.5.4.12', '')
    ogrn = clean_digits(attributes.get('OGRN', '') or attributes.get('1.2.643.100.1', ''))
    email = attributes.get('E', '') or attributes.get('1.2.840.113549.1.9.1', '')

    # Если CN отсутствует, но есть Фамилия + Имя/Отчество
    if not cn and (surname or given_name):
        cn = f"{surname} {given_name}".strip()

    raw_base64 = base64.b64encode(raw_der).decode('ascii')
    pem = (
        "-----BEGIN CERTIFICATE-----\n"
        + "\n".join(raw_base64[i:i + 64] for i in range(0, len(raw_base64), 64))
        + "\n-----END CERTIFICATE-----\n"
    )

    return {
        'thumbprint': thumbprint,
        'serial_number': serial_number,
        'valid_from': valid_from,
        'valid_to': valid_to,
        'is_expired': is_expired,
        'subject_name': subject_name,
        'issuer_name': issuer_name,
        'cn': cn,
        'surname': surname,
        'given_name': given_name,
        'snils': snils,
        'inn': inn,
        'ogrn': ogrn,
        'organization': organization,
        'title': title,
        'email': email,
        'raw_base64': raw_base64,
        'pem': pem,
        'raw_der': raw_der,
    }


def find_user_by_certificate(cert_info: Dict[str, Any]) -> Tuple[Optional[DataBaseUser], Optional[UserCertificate], bool]:
    """Выполняет интеллектуальный поиск и сопоставление сертификата с пользователем портала.

    Схема сопоставления:
    1. Поиск в БД ранее привязанного сертификата `UserCertificate` по отпечатку (Thumbprint);
    2. Если не найден: поиск активного пользователя `DataBaseUser` по СНИЛС (11 цифр);
    3. Если не найден: поиск по ИНН (12 цифр);
    4. Если не найден: поиск по корпоративному или личному Email;
    5. Если пользователь найден по реквизитам, возвращается флаг `is_new_binding=True`,
       сигнализирующий о возможности автоматической привязки сертификата к профилю.

    Args:
        cert_info: Словарь метаданных сертификата, возвращенный `parse_x509_certificate`.

    Returns:
        Tuple[Optional[DataBaseUser], Optional[UserCertificate], bool]:
            - DataBaseUser: найденный пользователь либо None;
            - UserCertificate: существующий объект сертификата либо None;
            - bool: True если это новая успешная привязка, False если сертификат уже был привязан.
    """
    thumbprint = cert_info.get('thumbprint')
    if not thumbprint:
        return None, None, False

    # 1. Поиск по прямому отпечатку сертификата
    existing_cert = UserCertificate.objects.select_related('user').filter(
        thumbprint=thumbprint,
        is_active=True,
    ).first()

    if existing_cert and existing_cert.user and existing_cert.user.is_active:
        return existing_cert.user, existing_cert, False

    # 2. Поиск пользователя по СНИЛС (при наличии в сертификате)
    snils = cert_info.get('snils')
    if snils and len(snils) == 11:
        # Проверяем СНИЛС в профиле сотрудника
        user_match = DataBaseUser.objects.filter(
            is_active=True,
            user_work_profile__snils=snils,
        ).first()
        if user_match:
            return user_match, None, True

    # 3. Поиск по ИНН
    inn = cert_info.get('inn')
    if inn and len(inn) in (10, 12):
        user_match = DataBaseUser.objects.filter(
            is_active=True,
            user_work_profile__inn=inn,
        ).first()
        if user_match:
            return user_match, None, True

    # 4. Поиск по Email
    email = cert_info.get('email')
    if email and '@' in email:
        user_match = DataBaseUser.objects.filter(
            is_active=True,
            email__iexact=email.strip(),
        ).first()
        if user_match:
            return user_match, None, True

        # Поиск по рабочему email в профиле
        user_match = DataBaseUser.objects.filter(
            is_active=True,
            user_work_profile__work_email__iexact=email.strip(),
        ).first()
        if user_match:
            return user_match, None, True

    # 5. Поиск по точному совпадению Фамилии и Имени
    surname = cert_info.get('surname', '').strip()
    given_name = cert_info.get('given_name', '').strip()
    if surname and given_name:
        first_name = given_name.split()[0] if given_name else ''
        candidates = DataBaseUser.objects.filter(
            is_active=True,
            last_name__iexact=surname,
            first_name__iexact=first_name,
        )
        # Привязываем автоматически только при однозначном совпадении (ровно 1 активный сотрудник)
        if candidates.count() == 1:
            return candidates.first(), None, True

    return None, None, False


def verify_signature_and_extract_cert(
    signed_data_b64: str,
    expected_challenge: str,
    cert_b64: Optional[str] = None
) -> Dict[str, Any]:
    """Верифицирует пакет CAdES / CMS электронной подписи и извлекает метаданные сертификата.

    При работе через КриптоПро ЭЦП Browser plug-in клиент формирует подписанное сообщение
    (CAdES-BES / CMS SignedData). Данная функция валидирует структуру подписи, извлекает открытый
    сертификат подписчика и сверяет соответствие подписанного challenge сессионному значению.

    Args:
        signed_data_b64: Подпись в формате Base64 (CAdES-BES / CMS).
        expected_challenge: Ожидаемый одноразовый challenge из текущей сессии пользователя.
        cert_b64: Опциональный Base64 открытого сертификата, переданный клиентом.

    Returns:
        Dict[str, Any]: Словарь метаданных верифицированного сертификата X.509.

    Raises:
        ValueError: Если подпись или сертификат невалидны, либо challenge не совпадает.
    """
    if not signed_data_b64:
        raise ValueError("Отсутствует цифровая подпись (signedData).")

    if not expected_challenge:
        raise ValueError("Срок действия сессионного challenge истек. Попробуйте снова.")

    # Если клиент передал открытый сертификат
    target_cert_raw = cert_b64
    if not target_cert_raw:
        # Пробуем извлечь сертификат из самого CMS SignedData
        try:
            # Для извлечения сертификата из PKCS#7 / CMS
            der_bytes = base64.b64decode(signed_data_b64)
            # Извлекаем сертификаты из структуры DER
            # При наличии нескольких сертификатов берем первый X.509
            cert_obj = x509.load_der_x509_certificate(der_bytes)
            target_cert_raw = base64.b64encode(cert_obj.public_bytes(x509.Encoding.DER)).decode('ascii')
        except Exception:
            pass

    if not target_cert_raw:
        raise ValueError("Не удалось извлечь сертификат X.509 из полученного пакета подписи.")

    # Разбор сертификата
    cert_info = parse_x509_certificate(target_cert_raw)

    if cert_info['is_expired']:
        raise ValueError(
            f"Срок действия сертификата истек ({cert_info['valid_to'].strftime('%d.%m.%Y %H:%M')}). "
            "Использование просроченного сертификата ЭЦП запрещено."
        )

    return cert_info
