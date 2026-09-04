"""Модуль сервисов для валидации, инспекции и конвертации SSL-сертификатов.

Предоставляет функции для парсинга PEM-сертификатов, цепочек доверия и закрытых ключей,
проверки их взаимного соответствия, извлечения метаданных (SAN, сроки, издатели)
и экспорта в форматы PEM (Fullchain, Bundle, Cert, Key), DER, PKCS#7 (P7B),
PKCS#12 (PFX) и единый ZIP-архив.
"""

import datetime
import io
import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import pkcs7, pkcs12
from cryptography.x509.oid import ExtensionOID, NameOID


def normalize_pem(pem_str: str) -> str:
    """Нормализует PEM-строку, устраняя невалидные отступы и пробелы.

    Args:
        pem_str (str): Исходный текст сертификата или ключа в PEM-формате.

    Returns:
        str: Очищенная строка с корректными переносами строк.
    """
    if not pem_str:
        return ""
    # Нормализуем переносы строк CRLF -> LF
    cleaned = pem_str.replace("\r\n", "\n").replace("\r", "\n").strip()
    return cleaned


def sanitize_filename(name: str, default: str = "certificate") -> str:
    """Формирует безопасное имя файла на основе Common Name или доменного имени.

    Args:
        name (str): Исходная строка (например, '*.barkol.ru' или 'portal.barkol.ru').
        default (str, optional): Дефолтное имя, если очищенная строка пуста. Defaults to "certificate".

    Returns:
        str: Безопасное имя файла без пробелов и спецсимволов.
    """
    if not name:
        return default
    # Заменяем звездочки для wildcard-сертификатов
    name = name.replace("*", "wildcard")
    # Оставляем только буквы, цифры, дефисы и подчеркивания
    sanitized = re.sub(r"[^a-zA-Z0-9_\-]+", "_", name).strip("_")
    return sanitized if sanitized else default


def parse_pem_certificates(pem_data: str) -> List[x509.Certificate]:
    """Парсит один или несколько X.509 сертификатов из PEM-строки.

    Args:
        pem_data (str): Текст с одним или несколькими PEM-сертификатами.

    Returns:
        List[x509.Certificate]: Список объектов X.509 сертификатов.

    Raises:
        ValueError: Если не удалось распарсить ни одного сертификата.
    """
    cleaned = normalize_pem(pem_data)
    if not cleaned:
        return []

    # Убеждаемся, что присутствуют маркеры PEM
    if "-----BEGIN CERTIFICATE-----" not in cleaned:
        raise ValueError("Сертификат должен начинаться с '-----BEGIN CERTIFICATE-----'")

    try:
        certs = x509.load_pem_x509_certificates(cleaned.encode("utf-8"))
        if not certs:
            raise ValueError("Не найдено корректных X.509 сертификатов в предоставленном тексте.")
        return certs
    except Exception as exc:
        raise ValueError(f"Ошибка парсинга сертификатов: {exc}") from exc


def parse_pem_private_key(pem_data: str, password: Optional[str] = None) -> Any:
    """Парсит закрытый ключ из PEM-строки с поддержкой RSA, ECDSA и шифрования.

    Args:
        pem_data (str): Текст закрытого ключа в PEM-формате.
        password (Optional[str], optional): Пароль для расшифровки ключа, если ключ зашифрован.

    Returns:
        Any: Экземпляр приватного ключа (RSAPrivateKey, EllipticCurvePrivateKey и др.).

    Raises:
        ValueError: Если ключ поврежден, имеет неподдерживаемый формат или неверный пароль.
    """
    cleaned = normalize_pem(pem_data)
    if not cleaned:
        return None

    # Проверка наличия маркера приватного ключа
    if "PRIVATE KEY-----" not in cleaned:
        raise ValueError("Закрытый ключ должен содержать блок '-----BEGIN ... PRIVATE KEY-----'")

    pwd_bytes = password.encode("utf-8") if password else None

    try:
        return serialization.load_pem_private_key(cleaned.encode("utf-8"), password=pwd_bytes)
    except TypeError as exc:
        if "Password was not given but private key is encrypted" in str(exc):
            raise ValueError("Закрытый ключ зашифрован паролем. Пожалуйста, укажите пароль для расшифровки.") from exc
        raise ValueError(f"Ошибка загрузки закрытого ключа: {exc}") from exc
    except ValueError as exc:
        err_msg = str(exc)
        if "Bad decrypt" in err_msg or "incorrect password" in err_msg.lower():
            raise ValueError("Неверный пароль для расшифровки закрытого ключа.") from exc
        raise ValueError(f"Некорректный формат закрытого ключа: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Не удалось прочитать закрытый ключ: {exc}") from exc


def verify_key_matches_cert(private_key: Any, cert: x509.Certificate) -> bool:
    """Проверяет соответствие закрытого ключа открытому ключу сертификата.

    Сравнивает каноническое бинарное представление открытого ключа (SubjectPublicKeyInfo в DER)
    между закрытым ключом и открытым сертификатом.

    Args:
        private_key (Any): Объект закрытого ключа.
        cert (x509.Certificate): Объект сертификата X.509.

    Returns:
        bool: True если открытые ключи совпадают, иначе False.
    """
    if private_key is None or cert is None:
        return False
    try:
        key_pub = private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        cert_pub = cert.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return key_pub == cert_pub
    except Exception:
        return False


def extract_cert_info(cert: x509.Certificate) -> Dict[str, Any]:
    """Извлекает подробные метаданные и параметры из X.509 сертификата.

    Args:
        cert (x509.Certificate): Сертификат X.509.

    Returns:
        Dict[str, Any]: Словарь с извлеченными параметрами:
            - 'common_name' (str): Общее имя (CN) субъекта.
            - 'organization' (str): Организация субъекта (O).
            - 'country' (str): Страна субъекта (C).
            - 'issuer_cn' (str): CN удостоверяющего центра (CA).
            - 'issuer_o' (str): Организация удостоверяющего центра.
            - 'valid_from' (str): Начало действия (UTC) в формате YYYY-MM-DD HH:MM:SS.
            - 'valid_to' (str): Окончание действия (UTC) в формате YYYY-MM-DD HH:MM:SS.
            - 'is_valid' (bool): Флаг текущей валидности по времени.
            - 'days_left' (int): Число оставшихся дней действия (или отрицательное, если истек).
            - 'status_text' (str): Текстовое описание статуса.
            - 'status_badge_class' (str): CSS-класс бейджа ('success', 'warning', 'danger').
            - 'sans' (List[str]): Список альтернативных DNS-имен и IP-адресов (SAN).
            - 'serial_number_hex' (str): Серийный номер в шестнадцатеричном виде.
            - 'signature_algorithm' (str): Название алгоритма подписи.
            - 'key_type' (str): Тип открытого ключа (RSA, EC и т.д.) и его размер.
            - 'fingerprint_sha256' (str): SHA-256 отпечаток сертификата.
    """
    # Субъект
    cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    common_name = cn_attrs[0].value if cn_attrs else "—"

    o_attrs = cert.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)
    organization = o_attrs[0].value if o_attrs else "—"

    c_attrs = cert.subject.get_attributes_for_oid(NameOID.COUNTRY_NAME)
    country = c_attrs[0].value if c_attrs else "—"

    # Издатель
    issuer_cn_attrs = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
    issuer_cn = issuer_cn_attrs[0].value if issuer_cn_attrs else "—"

    issuer_o_attrs = cert.issuer.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)
    issuer_o = issuer_o_attrs[0].value if issuer_o_attrs else "—"

    # SAN
    sans: List[str] = []
    try:
        san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        dns_names = san_ext.value.get_values_for_type(x509.DNSName)
        ip_addresses = [str(ip) for ip in san_ext.value.get_values_for_type(x509.IPAddress)]
        sans = dns_names + ip_addresses
    except Exception:
        sans = []

    # Даты действия
    now = datetime.datetime.now(datetime.timezone.utc)
    if hasattr(cert, "not_valid_before_utc"):
        not_before = cert.not_valid_before_utc
        not_after = cert.not_valid_after_utc
    else:
        not_before = cert.not_valid_before.replace(tzinfo=datetime.timezone.utc) if cert.not_valid_before.tzinfo is None else cert.not_valid_before
        not_after = cert.not_valid_after.replace(tzinfo=datetime.timezone.utc) if cert.not_valid_after.tzinfo is None else cert.not_valid_after

    is_valid = not_before <= now <= not_after
    delta = not_after - now
    days_left = delta.days

    if days_left < 0:
        status_text = f"Срок действия истек {abs(days_left)} дн. назад"
        status_badge_class = "danger"
    elif days_left <= 30:
        status_text = f"Истекает через {days_left} дн."
        status_badge_class = "warning"
    else:
        status_text = f"Действителен (осталось {days_left} дн.)"
        status_badge_class = "success"

    # Тип ключа
    pub_key = cert.public_key()
    if isinstance(pub_key, rsa.RSAPublicKey):
        key_type = f"RSA {pub_key.key_size} бит"
    elif isinstance(pub_key, ec.EllipticCurvePublicKey):
        key_type = f"ECDSA ({pub_key.curve.name})"
    else:
        key_type = type(pub_key).__name__

    # Отпечаток SHA-256
    fp_sha256 = cert.fingerprint(hashes.SHA256()).hex().upper()
    formatted_fp = ":".join(fp_sha256[i : i + 2] for i in range(0, len(fp_sha256), 2))

    return {
        "common_name": common_name,
        "organization": organization,
        "country": country,
        "issuer_cn": issuer_cn,
        "issuer_o": issuer_o,
        "valid_from": not_before.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "valid_to": not_after.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "is_valid": is_valid,
        "days_left": days_left,
        "status_text": status_text,
        "status_badge_class": status_badge_class,
        "sans": sans,
        "serial_number_hex": hex(cert.serial_number),
        "signature_algorithm": cert.signature_algorithm_oid._name if hasattr(cert.signature_algorithm_oid, "_name") else str(cert.signature_algorithm_oid),
        "key_type": key_type,
        "fingerprint_sha256": formatted_fp,
    }


def inspect_ssl_bundle(
    cert_pem: str,
    key_pem: str = "",
    chain_pem: str = "",
    key_password: Optional[str] = None,
) -> Dict[str, Any]:
    """Выполняет аудит и проверку введенных компонентов SSL (сертификат, ключ, цепочка).

    Args:
        cert_pem (str): Текст сертификата или связки сертификатов в формате PEM.
        key_pem (str, optional): Текст закрытого ключа в формате PEM. Defaults to "".
        chain_pem (str, optional): Текст цепочки промежуточных/корневых сертификатов в формате PEM. Defaults to "".
        key_password (Optional[str], optional): Пароль для расшифровки закрытого ключа. Defaults to None.

    Returns:
        Dict[str, Any]: Словарь с результатами проверки:
            - 'success' (bool): True если основной сертификат успешно разобран.
            - 'error' (str, optional): Текст ошибки, если разбор не удался.
            - 'cert_info' (Dict[str, Any]): Метаданные основного сертификата.
            - 'key_status' (str): Статус ключа ('match', 'mismatch', 'invalid', 'encrypted', 'empty').
            - 'key_message' (str): Сообщение о статусе закрытого ключа.
            - 'chain_count' (int): Число сертификатов в цепочке.
            - 'chain_list' (List[Dict[str, str]]): Список сертификатов цепочки с CN и сроками.
            - 'recommended_filename' (str): Рекомендуемое базовое имя файла.
    """
    cleaned_cert = normalize_pem(cert_pem)
    cleaned_key = normalize_pem(key_pem)
    cleaned_chain = normalize_pem(chain_pem)

    if not cleaned_cert:
        return {
            "success": False,
            "error": "Поле 'SSL-сертификат' не заполнено. Вставьте содержимое PEM-сертификата.",
        }

    try:
        all_certs = parse_pem_certificates(cleaned_cert)
    except ValueError as exc:
        return {
            "success": False,
            "error": str(exc),
        }

    leaf_cert = all_certs[0]
    extra_certs_from_cert_field = all_certs[1:]

    # Разбор цепочки
    chain_certs: List[x509.Certificate] = []
    if cleaned_chain:
        try:
            chain_certs = parse_pem_certificates(cleaned_chain)
        except ValueError as exc:
            return {
                "success": False,
                "error": f"Ошибка в поле 'Цепочка SSL-сертификатов': {exc}",
            }
    elif extra_certs_from_cert_field:
        chain_certs = extra_certs_from_cert_field

    # Разбор ключа
    key_status = "empty"
    key_message = "Закрытый ключ не указан"
    priv_key_obj = None

    if cleaned_key:
        try:
            priv_key_obj = parse_pem_private_key(cleaned_key, password=key_password)
            if priv_key_obj:
                if verify_key_matches_cert(priv_key_obj, leaf_cert):
                    key_status = "match"
                    key_message = "Закрытый ключ валиден и полностью соответствует сертификату"
                else:
                    key_status = "mismatch"
                    key_message = "Внимание: закрытый ключ НЕ соответствует данному сертификату!"
        except ValueError as exc:
            err_str = str(exc)
            if "зашифрован" in err_str.lower():
                key_status = "encrypted"
                key_message = err_str
            else:
                key_status = "invalid"
                key_message = err_str

    cert_info = extract_cert_info(leaf_cert)
    recommended_name = sanitize_filename(cert_info["common_name"])

    chain_list: List[Dict[str, str]] = []
    for idx, c in enumerate(chain_certs, 1):
        cn_attr = c.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        iss_attr = c.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
        cn_val = cn_attr[0].value if cn_attr else f"Cert #{idx}"
        iss_val = iss_attr[0].value if iss_attr else "—"
        is_root = c.subject == c.issuer
        chain_valid_to = c.not_valid_after_utc if hasattr(c, "not_valid_after_utc") else c.not_valid_after
        chain_list.append({
            "order": str(idx),
            "common_name": str(cn_val),
            "issuer_cn": str(iss_val),
            "valid_to": chain_valid_to.strftime("%Y-%m-%d"),
            "is_root": is_root,
        })

    return {
        "success": True,
        "cert_info": cert_info,
        "key_status": key_status,
        "key_message": key_message,
        "chain_count": len(chain_certs),
        "chain_list": chain_list,
        "recommended_filename": recommended_name,
    }


def generate_ssl_export(
    format_type: str,
    cert_pem: str,
    key_pem: str = "",
    chain_pem: str = "",
    pfx_password: str = "",
    key_password: Optional[str] = None,
    base_name: str = "certificate",
    pem_export_mode: str = "fullchain",
) -> Tuple[bytes, str, str]:
    """Генерирует готовый файл сертификата в запрошенном формате для скачивания.

    Args:
        format_type (str): Желаемый формат: 'pem', 'der', 'p7b', 'pfx', 'zip'.
        cert_pem (str): Текст сертификата в формате PEM.
        key_pem (str, optional): Текст закрытого ключа в формате PEM. Defaults to "".
        chain_pem (str, optional): Текст цепочки промежуточных сертификатов. Defaults to "".
        pfx_password (str, optional): Пароль для шифрования PKCS#12 контейнера. Defaults to "".
        key_password (Optional[str], optional): Пароль для расшифровки закрытого ключа. Defaults to None.
        base_name (str, optional): Базовое имя скачиваемого файла. Defaults to "certificate".
        pem_export_mode (str, optional): Режим PEM: 'fullchain', 'bundle', 'cert', 'key', 'chain'. Defaults to "fullchain".

    Returns:
        Tuple[bytes, str, str]: Кортеж из трех элементов:
            - bytes: Бинарное или текстовое содержимое файла.
            - str: Имя файла с расширением (например, 'portal_barkol_ru.pfx').
            - str: MIME-тип содержимого (Content-Type).

    Raises:
        ValueError: При некорректных входных данных или невозможности сформировать файл.
    """
    cleaned_cert = normalize_pem(cert_pem)
    cleaned_key = normalize_pem(key_pem)
    cleaned_chain = normalize_pem(chain_pem)

    if not cleaned_cert:
        raise ValueError("Сертификат обязателен для экспорта.")

    all_certs = parse_pem_certificates(cleaned_cert)
    leaf_cert = all_certs[0]
    extra_from_cert = all_certs[1:]

    # Цепочка
    chain_certs: List[x509.Certificate] = []
    if cleaned_chain:
        chain_certs = parse_pem_certificates(cleaned_chain)
    elif extra_from_cert:
        chain_certs = extra_from_cert

    # Ключ
    priv_key_obj = None
    if cleaned_key:
        priv_key_obj = parse_pem_private_key(cleaned_key, password=key_password)

    safe_name = sanitize_filename(base_name)

    # 1. PEM
    if format_type == "pem":
        leaf_pem = leaf_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8").strip()
        chain_pems = [c.public_bytes(serialization.Encoding.PEM).decode("utf-8").strip() for c in chain_certs]
        chain_str = "\n".join(chain_pems)

        if pem_export_mode == "cert":
            content = (leaf_pem + "\n").encode("utf-8")
            filename = f"{safe_name}.crt"
            content_type = "application/x-pem-file"
        elif pem_export_mode == "key":
            if not priv_key_obj:
                raise ValueError("Для экспорта закрытого ключа необходимо заполнить поле 'Ключ SSL-сертификата'.")
            key_export = priv_key_obj.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
            return key_export, f"{safe_name}.key", "application/x-pem-file"
        elif pem_export_mode == "chain":
            if not chain_str:
                raise ValueError("Цепочка сертификатов отсутствует.")
            content = (chain_str + "\n").encode("utf-8")
            filename = f"{safe_name}_chain.crt"
            content_type = "application/x-pem-file"
        elif pem_export_mode == "bundle":
            # Ключ + Сертификат + Цепочка (all-in-one для HAProxy)
            parts: List[str] = []
            if priv_key_obj:
                key_str = priv_key_obj.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                ).decode("utf-8").strip()
                parts.append(key_str)
            parts.append(leaf_pem)
            if chain_str:
                parts.append(chain_str)
            content = ("\n".join(parts) + "\n").encode("utf-8")
            filename = f"{safe_name}_bundle.pem"
            content_type = "application/x-pem-file"
        else:
            # Fullchain по умолчанию: Сертификат + Цепочка
            parts = [leaf_pem]
            if chain_str:
                parts.append(chain_str)
            content = ("\n".join(parts) + "\n").encode("utf-8")
            filename = f"{safe_name}_fullchain.pem"
            content_type = "application/x-pem-file"

        return content, filename, content_type

    # 2. DER
    if format_type == "der":
        der_bytes = leaf_cert.public_bytes(serialization.Encoding.DER)
        return der_bytes, f"{safe_name}.der", "application/x-x509-ca-cert"

    # 3. PKCS#7 (P7B)
    if format_type in ("p7b", "pkcs7", "p7b_pem"):
        certs_to_pack = [leaf_cert] + chain_certs
        encoding = serialization.Encoding.PEM if format_type == "p7b_pem" else serialization.Encoding.DER
        p7b_bytes = pkcs7.serialize_certificates(certs_to_pack, encoding)
        ext = "p7b"
        content_type = "application/x-pkcs7-certificates"
        filename = f"{safe_name}.{ext}" if format_type != "p7b_pem" else f"{safe_name}_pem.p7b"
        return p7b_bytes, filename, content_type

    # 4. PKCS#12 (PFX)
    if format_type in ("pfx", "pkcs12"):
        if pfx_password:
            encryption = serialization.BestAvailableEncryption(pfx_password.encode("utf-8"))
        else:
            encryption = serialization.NoEncryption()

        cas = chain_certs if chain_certs else None
        pfx_bytes = pkcs12.serialize_key_and_certificates(
            name=safe_name.encode("utf-8"),
            key=priv_key_obj,
            cert=leaf_cert,
            cas=cas,
            encryption_algorithm=encryption,
        )
        return pfx_bytes, f"{safe_name}.pfx", "application/x-pkcs12"

    # 5. ZIP пакет со всеми форматами
    if format_type == "zip":
        return _generate_zip_package(
            leaf_cert=leaf_cert,
            priv_key_obj=priv_key_obj,
            chain_certs=chain_certs,
            pfx_password=pfx_password,
            safe_name=safe_name,
        )

    raise ValueError(f"Неизвестный формат экспорта: {format_type}")


def _generate_zip_package(
    leaf_cert: x509.Certificate,
    priv_key_obj: Any,
    chain_certs: List[x509.Certificate],
    pfx_password: str,
    safe_name: str,
) -> Tuple[bytes, str, str]:
    """Формирует в оперативной памяти полный ZIP-архив со всеми форматами SSL.

    Args:
        leaf_cert (x509.Certificate): Основной сертификат X.509.
        priv_key_obj (Any): Объект закрытого ключа (если указан).
        chain_certs (List[x509.Certificate]): Список сертификатов цепочки.
        pfx_password (str): Пароль для шифрования PFX-контейнера.
        safe_name (str): Базовое имя файлов.

    Returns:
        Tuple[bytes, str, str]: Бинарные байты ZIP-архива, имя архива и MIME-тип 'application/zip'.
    """
    zip_buffer = io.BytesIO()
    leaf_pem = leaf_cert.public_bytes(serialization.Encoding.PEM)
    chain_pems = [c.public_bytes(serialization.Encoding.PEM) for c in chain_certs]

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Сертификат .crt
        zf.writestr(f"{safe_name}.crt", leaf_pem)

        # 2. Сертификат в бинарном DER
        zf.writestr(f"{safe_name}.der", leaf_cert.public_bytes(serialization.Encoding.DER))

        # 3. Цепочка (если есть)
        if chain_pems:
            chain_combined = b"\n".join(chain_pems) + b"\n"
            zf.writestr(f"{safe_name}_chain.crt", chain_combined)

        # 4. Fullchain PEM (Сертификат + Цепочка)
        fullchain_bytes = leaf_pem
        if chain_pems:
            fullchain_bytes += b"\n" + b"\n".join(chain_pems) + b"\n"
        zf.writestr(f"{safe_name}_fullchain.pem", fullchain_bytes)

        # 5. PKCS#7 (P7B)
        all_certs = [leaf_cert] + chain_certs
        p7b_der = pkcs7.serialize_certificates(all_certs, serialization.Encoding.DER)
        p7b_pem = pkcs7.serialize_certificates(all_certs, serialization.Encoding.PEM)
        zf.writestr(f"{safe_name}.p7b", p7b_der)
        zf.writestr(f"{safe_name}_pem.p7b", p7b_pem)

        # 6. Ключ и контейнеры с ключом (если ключ передан)
        if priv_key_obj:
            key_pem = priv_key_obj.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
            zf.writestr(f"{safe_name}.key", key_pem)

            # All-in-One PEM (Ключ + Сертификат + Цепочка)
            bundle_bytes = key_pem + b"\n" + fullchain_bytes
            zf.writestr(f"{safe_name}_bundle.pem", bundle_bytes)

            # PFX (PKCS#12)
            enc = serialization.BestAvailableEncryption(pfx_password.encode("utf-8")) if pfx_password else serialization.NoEncryption()
            pfx_bytes = pkcs12.serialize_key_and_certificates(
                name=safe_name.encode("utf-8"),
                key=priv_key_obj,
                cert=leaf_cert,
                cas=chain_certs if chain_certs else None,
                encryption_algorithm=enc,
            )
            zf.writestr(f"{safe_name}.pfx", pfx_bytes)

        # 7. Инструкция README.txt
        readme_text = (
            f"ПАКЕТ SSL-СЕРТИФИКАТА ДЛЯ: {safe_name}\n"
            f"Дата генерации пакета: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"------------------------------------------------------------------------\n\n"
            f"СОСТАВ АРХИВА:\n"
            f"1. {safe_name}.crt              — Сертификат сервера в формате PEM (X.509)\n"
            f"2. {safe_name}_fullchain.pem    — Сертификат вместе с цепочкой доверия (для Nginx / Apache)\n"
            f"3. {safe_name}.der              — Сертификат в бинарном формате ASN.1 DER (для Java / Windows)\n"
            f"4. {safe_name}.p7b              — Контейнер PKCS#7 (бинарный DER) с цепочкой CA\n"
            f"5. {safe_name}_pem.p7b          — Контейнер PKCS#7 (текстовый PEM)\n"
        )
        if priv_key_obj:
            readme_text += (
                f"6. {safe_name}.key              — Закрытый ключ сервера (RSA/ECDSA PEM, без пароля)\n"
                f"7. {safe_name}_bundle.pem       — Объединенный файл (Ключ + Сертификат + Цепочка для HAProxy)\n"
                f"8. {safe_name}.pfx              — Контейнер PKCS#12 (PFX) для Windows IIS / Exchange / Tomcat\n"
            )
            if pfx_password:
                readme_text += f"   * Пароль для PFX-контейнера: установлен пользователем при экспорте\n"
            else:
                readme_text += f"   * Пароль для PFX-контейнера: отсутствует (без пароля)\n"

        readme_text += (
            f"\nИНСТРУКЦИЯ ПО ПРИМЕНЕНИЮ:\n\n"
            f"• Nginx:\n"
            f"    ssl_certificate /etc/ssl/{safe_name}_fullchain.pem;\n"
            f"    ssl_certificate_key /etc/ssl/{safe_name}.key;\n\n"
            f"• Apache 2.4+:\n"
            f"    SSLCertificateFile /etc/ssl/{safe_name}_fullchain.pem\n"
            f"    SSLCertificateKeyFile /etc/ssl/{safe_name}.key\n\n"
            f"• HAProxy:\n"
            f"    bind *:443 ssl crt /etc/haproxy/certs/{safe_name}_bundle.pem\n\n"
            f"• Windows Server (IIS):\n"
            f"    Импортируйте файл {safe_name}.pfx через диспетчер сертификатов (certlm.msc) или консоль IIS.\n"
        )
        zf.writestr("README.txt", readme_text.encode("utf-8"))

    zip_buffer.seek(0)
    return zip_buffer.getvalue(), f"{safe_name}_ssl_package.zip", "application/zip"


def generate_demo_ssl_bundle() -> Dict[str, str]:
    """Генерирует тестовую иерархию SSL (Root CA, Intermediate CA, Server Cert + Key).

    Используется для быстрой демонстрации работы страницы и тестирования функционала суперадминистратором.

    Returns:
        Dict[str, str]: Словарь с тремя ключами:
            - 'cert_pem': PEM-текст тестового сертификата 'portal.barkol.ru'.
            - 'key_pem': PEM-текст закрытого RSA-ключа 2048 бит.
            - 'chain_pem': PEM-текст цепочки (промежуточный CA + корневой CA).
            - 'filename': Рекомендуемое имя файла ('portal_barkol_ru').
    """
    now = datetime.datetime.now(datetime.timezone.utc)

    # 1. Корневой CA (Root CA)
    root_key = rsa.generate_private_key(65537, 2048)
    root_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Barkol Root CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ООО Авиакомпания БАРКОЛ"),
        x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
    ])
    root_cert = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_key.public_key())
        .serial_number(1001)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(root_key, hashes.SHA256())
    )

    # 2. Промежуточный CA (Intermediate CA)
    inter_key = rsa.generate_private_key(65537, 2048)
    inter_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Barkol Intermediate CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ООО Авиакомпания БАРКОЛ"),
        x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
    ])
    inter_cert = (
        x509.CertificateBuilder()
        .subject_name(inter_name)
        .issuer_name(root_name)
        .public_key(inter_key.public_key())
        .serial_number(1002)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1825))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(root_key, hashes.SHA256())
    )

    # 3. Сертификат конечного узла (Server Leaf Cert)
    server_key = rsa.generate_private_key(65537, 2048)
    server_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "portal.barkol.ru"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ООО Авиакомпания БАРКОЛ"),
        x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
    ])
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(inter_name)
        .public_key(server_key.public_key())
        .serial_number(1003)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("portal.barkol.ru"),
                x509.DNSName("*.portal.barkol.ru"),
                x509.DNSName("barkol.ru"),
            ]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(inter_key, hashes.SHA256())
    )

    cert_pem = server_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    key_pem = server_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    chain_pem = (
        inter_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
        + root_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    )

    return {
        "cert_pem": cert_pem,
        "key_pem": key_pem,
        "chain_pem": chain_pem,
        "filename": "portal_barkol_ru",
    }
