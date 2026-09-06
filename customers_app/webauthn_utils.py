"""Модуль криптографических утилит для протокола WebAuthn / Passkeys (FIDO2).

Предоставляет функции кодирования/декодирования Base64URL, чистый синтаксический
анализатор формата CBOR (RFC 8949), конвертацию открытых ключей COSE (ES256 / RS256)
в стандартный формат SubjectPublicKeyInfo PEM, парсинг данных аутентификатора (authData)
и верификацию цифровых подписей ECDSA (P-256) и RSA (RS256) через библиотеку cryptography.
"""

import base64
import hashlib
import io
import re
import secrets
import struct
from typing import Any, Dict, Optional, Tuple, Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)


def b64url_encode(data: bytes) -> str:
    """Кодирует байты в строку Base64URL без завершающих символов '='.

    Args:
        data: Исходные байты для кодирования.

    Returns:
        str: Строка в формате Base64URL (URL-safe, без padding).
    """
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def b64url_decode(data: str) -> bytes:
    """Декодирует строку Base64URL в байты с автоматическим добавлением padding.

    Args:
        data: Строка в формате Base64URL.

    Returns:
        bytes: Раскодированные байты.

    Raises:
        ValueError: Если строка содержит некорректные символы Base64.
    """
    data = data.strip().replace('-', '+').replace('_', '/')
    missing_padding = len(data) % 4
    if missing_padding:
        data += '=' * (4 - missing_padding)
    return base64.b64decode(data)


def generate_challenge(byte_length: int = 32) -> str:
    """Генерирует криптографически стойкую случайную строку challenge в формате Base64URL.

    Args:
        byte_length: Длина случайной последовательности байт (по умолчанию 32).

    Returns:
        str: Сгенерированный challenge в формате Base64URL.
    """
    return b64url_encode(secrets.token_bytes(byte_length))


def cbor_decode(stream_or_bytes: Union[io.BytesIO, bytes, bytearray]) -> Any:
    """Декодирует поток или последовательность байт формата CBOR (RFC 8949).

    Поддерживает основные типы CBOR: беззнаковые и знаковые целые, байтовые строки,
    текстовые UTF-8 строки, списки, ассоциативные массивы (map) и простые значения.

    Args:
        stream_or_bytes: Поток BytesIO или байтовый массив с CBOR данными.

    Returns:
        Any: Декодированная структура данных Python (dict, list, int, bytes, str, bool, None).

    Raises:
        EOFError: При неожиданном окончании потока данных.
        ValueError: При обнаружении неподдерживаемого типа или поврежденной структуры CBOR.
    """
    if isinstance(stream_or_bytes, (bytes, bytearray)):
        stream = io.BytesIO(stream_or_bytes)
    else:
        stream = stream_or_bytes

    initial_byte = stream.read(1)
    if not initial_byte:
        raise EOFError("Unexpected end of CBOR stream")

    ib = initial_byte[0]
    major_type = ib >> 5
    info = ib & 0x1F

    if info < 24:
        val = info
    elif info == 24:
        next_byte = stream.read(1)
        if not next_byte:
            raise EOFError("Unexpected end of CBOR stream reading uint8")
        val = next_byte[0]
    elif info == 25:
        data = stream.read(2)
        if len(data) < 2:
            raise EOFError("Unexpected end of CBOR stream reading uint16")
        val = struct.unpack(">H", data)[0]
    elif info == 26:
        data = stream.read(4)
        if len(data) < 4:
            raise EOFError("Unexpected end of CBOR stream reading uint32")
        val = struct.unpack(">I", data)[0]
    elif info == 27:
        data = stream.read(8)
        if len(data) < 8:
            raise EOFError("Unexpected end of CBOR stream reading uint64")
        val = struct.unpack(">Q", data)[0]
    elif info == 31:
        val = None  # Indefinite length
    else:
        raise ValueError(f"Unsupported CBOR additional info {info}")

    if major_type == 0:
        return val
    elif major_type == 1:
        return -1 - val
    elif major_type == 2:
        if val is None:
            chunks = []
            while True:
                peek = stream.read(1)
                if not peek or peek[0] == 0xFF:
                    break
                stream.seek(-1, io.SEEK_CUR)
                chunks.append(cbor_decode(stream))
            return b"".join(chunks)
        data = stream.read(val)
        if len(data) < val:
            raise EOFError(f"CBOR byte string truncated: expected {val}, got {len(data)}")
        return data
    elif major_type == 3:
        if val is None:
            chunks = []
            while True:
                peek = stream.read(1)
                if not peek or peek[0] == 0xFF:
                    break
                stream.seek(-1, io.SEEK_CUR)
                chunks.append(cbor_decode(stream))
            return "".join(chunks)
        data = stream.read(val)
        if len(data) < val:
            raise EOFError(f"CBOR text string truncated: expected {val}, got {len(data)}")
        return data.decode("utf-8", errors="replace")
    elif major_type == 4:
        if val is None:
            items = []
            while True:
                peek = stream.read(1)
                if not peek or peek[0] == 0xFF:
                    break
                stream.seek(-1, io.SEEK_CUR)
                items.append(cbor_decode(stream))
            return items
        return [cbor_decode(stream) for _ in range(val)]
    elif major_type == 5:
        res = {}
        if val is None:
            while True:
                peek = stream.read(1)
                if not peek or peek[0] == 0xFF:
                    break
                stream.seek(-1, io.SEEK_CUR)
                k = cbor_decode(stream)
                v = cbor_decode(stream)
                res[k] = v
            return res
        for _ in range(val):
            k = cbor_decode(stream)
            v = cbor_decode(stream)
            res[k] = v
        return res
    elif major_type == 6:
        # Semantic tag: return inner decoded item
        return cbor_decode(stream)
    elif major_type == 7:
        if info == 20:
            return False
        elif info == 21:
            return True
        elif info == 22 or info == 23:
            return None
        return val
    else:
        raise ValueError(f"Unsupported CBOR major type {major_type}")


def cose_key_to_pem(cose_dict: Dict[int, Any]) -> Tuple[str, str]:
    """Преобразует словарь открытого ключа COSE Key в формат SubjectPublicKeyInfo PEM.

    Поддерживает:
    - ECDSA over NIST P-256 (alg: -7 / ES256, kty: 2 / EC2, crv: 1 / P-256).
    - RSA (alg: -257 / RS256, kty: 3 / RSA).

    Args:
        cose_dict: Словарь параметров открытого ключа COSE.

    Returns:
        Tuple[str, str]: Кортеж (public_key_pem_строка, название_алгоритма).

    Raises:
        ValueError: Если алгоритм или тип ключа не поддерживается.
    """
    kty = cose_dict.get(1)
    alg = cose_dict.get(3, -7)

    # 1. EC2 Key (P-256 / ES256)
    if kty == 2:
        crv = cose_dict.get(-1)
        x_bytes = cose_dict.get(-2)
        y_bytes = cose_dict.get(-3)

        if not x_bytes or not y_bytes:
            raise ValueError("Invalid EC2 COSE Key: missing X or Y coordinates")

        if crv != 1:  # 1 = P-256 (secp256r1)
            raise ValueError(f"Unsupported EC curve: {crv}. Only NIST P-256 is supported.")

        x_int = int.from_bytes(x_bytes, byteorder="big")
        y_int = int.from_bytes(y_bytes, byteorder="big")
        public_numbers = ec.EllipticCurvePublicNumbers(x_int, y_int, ec.SECP256R1())
        public_key = public_numbers.public_key()
        pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        return pem, "ES256"

    # 2. RSA Key (RS256)
    elif kty == 3:
        n_bytes = cose_dict.get(-1)
        e_bytes = cose_dict.get(-2)

        if not n_bytes or not e_bytes:
            raise ValueError("Invalid RSA COSE Key: missing modulus (n) or exponent (e)")

        n_int = int.from_bytes(n_bytes, byteorder="big")
        e_int = int.from_bytes(e_bytes, byteorder="big")
        public_numbers = rsa.RSAPublicNumbers(e_int, n_int)
        public_key = public_numbers.public_key()
        pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        return pem, "RS256"

    else:
        raise ValueError(f"Unsupported COSE key type (kty={kty}, alg={alg})")


def parse_attestation_object(attestation_bytes: bytes) -> Dict[str, Any]:
    """Парсит CBOR-объект аттестации WebAuthn (attestationObject) и извлекает данные аутентификатора.

    Args:
        attestation_bytes: Необработанные байты attestationObject.

    Returns:
        Dict[str, Any]: Словарь с полями:
            - 'rp_id_hash': bytes (32 байта хеша RP ID)
            - 'flags': int (байт флагов)
            - 'user_present': bool (флаг UP)
            - 'user_verified': bool (флаг UV)
            - 'sign_count': int (счетчик подписей)
            - 'aaguid': str (HEX-строка AAGUID)
            - 'credential_id': str (Base64URL строка идентификатора учетных данных)
            - 'credential_id_bytes': bytes (бинарный ID учетных данных)
            - 'public_key_pem': str (публичный ключ в формате PEM)
            - 'algorithm': str (название алгоритма: 'ES256' / 'RS256')
            - 'auth_data_bytes': bytes (исходные байты authData)

    Raises:
        ValueError: При нарушении формата данных аттестации или отсутствии attestedCredentialData.
    """
    attestation_map = cbor_decode(attestation_bytes)
    if not isinstance(attestation_map, dict):
        raise ValueError("Attestation object root is not a CBOR map")

    auth_data = attestation_map.get("authData")
    if not auth_data or not isinstance(auth_data, (bytes, bytearray)):
        raise ValueError("Missing or invalid authData in attestationObject")

    if len(auth_data) < 37:
        raise ValueError(f"authData too short: {len(auth_data)} bytes (minimum 37 required)")

    rp_id_hash = auth_data[0:32]
    flags = auth_data[32]
    sign_count = struct.unpack(">I", auth_data[33:37])[0]

    user_present = bool(flags & 0x01)
    user_verified = bool(flags & 0x04)
    has_attested_data = bool(flags & 0x40)

    if not has_attested_data:
        raise ValueError("attestationObject does not contain attestedCredentialData (flag AT not set)")

    # Parse attestedCredentialData
    offset = 37
    if len(auth_data) < offset + 18:
        raise ValueError("authData truncated before credential ID length")

    aaguid_bytes = auth_data[offset : offset + 16]
    offset += 16

    cred_id_len = struct.unpack(">H", auth_data[offset : offset + 2])[0]
    offset += 2

    if len(auth_data) < offset + cred_id_len:
        raise ValueError(f"authData truncated: expected credentialId of length {cred_id_len}")

    cred_id_bytes = auth_data[offset : offset + cred_id_len]
    offset += cred_id_len

    # Remaining bytes contain COSE public key map in CBOR format
    cose_stream = io.BytesIO(auth_data[offset:])
    cose_key_map = cbor_decode(cose_stream)

    if not isinstance(cose_key_map, dict):
        raise ValueError("Parsed credentialPublicKey is not a CBOR map")

    public_key_pem, algorithm = cose_key_to_pem(cose_key_map)

    return {
        "rp_id_hash": rp_id_hash,
        "flags": flags,
        "user_present": user_present,
        "user_verified": user_verified,
        "sign_count": sign_count,
        "aaguid": aaguid_bytes.hex(),
        "credential_id": b64url_encode(cred_id_bytes),
        "credential_id_bytes": cred_id_bytes,
        "public_key_pem": public_key_pem,
        "algorithm": algorithm,
        "auth_data_bytes": bytes(auth_data),
    }


def parse_authenticator_data(auth_data_bytes: bytes) -> Dict[str, Any]:
    """Парсит байты authenticatorData при процедуре аутентификации (assertion).

    Args:
        auth_data_bytes: Необработанные байты authenticatorData.

    Returns:
        Dict[str, Any]: Словарь с полями:
            - 'rp_id_hash': bytes (32 байта хеша RP ID)
            - 'flags': int (байт флагов)
            - 'user_present': bool (флаг UP)
            - 'user_verified': bool (флаг UV)
            - 'sign_count': int (счетчик подписей)

    Raises:
        ValueError: Если длина authenticatorData меньше 37 байт.
    """
    if len(auth_data_bytes) < 37:
        raise ValueError(f"authenticatorData too short: {len(auth_data_bytes)} bytes")

    rp_id_hash = auth_data_bytes[0:32]
    flags = auth_data_bytes[32]
    sign_count = struct.unpack(">I", auth_data_bytes[33:37])[0]

    return {
        "rp_id_hash": rp_id_hash,
        "flags": flags,
        "user_present": bool(flags & 0x01),
        "user_verified": bool(flags & 0x04),
        "sign_count": sign_count,
    }


def verify_webauthn_signature(
    public_key_pem: str,
    authenticator_data_bytes: bytes,
    client_data_json_bytes: bytes,
    signature_bytes: bytes,
) -> bool:
    """Проверяет криптографическую цифровую подпись WebAuthn assertion.

    Формирует верифицируемое сообщение по спецификации W3C WebAuthn:
    verification_data = authenticatorData || SHA256(clientDataJSON).
    Поддерживает как ASN.1 DER подписи ECDSA, так и необработанный формат r||s (64 байта).

    Args:
        public_key_pem: Публичный ключ в формате SubjectPublicKeyInfo PEM.
        authenticator_data_bytes: Необработанные байты authenticatorData.
        client_data_json_bytes: Необработанные байты clientDataJSON.
        signature_bytes: Байты цифровой подписи.

    Returns:
        bool: True, если подпись математически верна, иначе False.
    """
    client_data_hash = hashlib.sha256(client_data_json_bytes).digest()
    data_to_verify = authenticator_data_bytes + client_data_hash

    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
    except Exception:
        return False

    # 1. ECDSA Verification
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        der_signature = signature_bytes
        # Если подпись пришла в виде конкатенации r || s (64 байта)
        if len(signature_bytes) == 64:
            try:
                r = int.from_bytes(signature_bytes[:32], byteorder="big")
                s = int.from_bytes(signature_bytes[32:], byteorder="big")
                der_signature = encode_dss_signature(r, s)
            except Exception:
                pass

        try:
            public_key.verify(der_signature, data_to_verify, ec.ECDSA(hashes.SHA256()))
            return True
        except InvalidSignature:
            return False
        except Exception:
            return False

    # 2. RSA Verification
    elif isinstance(public_key, rsa.RSAPublicKey):
        # Попытка проверки через PKCS#1 v1.5
        try:
            public_key.verify(signature_bytes, data_to_verify, padding.PKCS1v15(), hashes.SHA256())
            return True
        except InvalidSignature:
            pass
        except Exception:
            pass

        # Попытка проверки через RSASSA-PSS
        try:
            public_key.verify(
                signature_bytes,
                data_to_verify,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            return True
        except InvalidSignature:
            return False
        except Exception:
            return False

    return False


def detect_device_name_from_user_agent(user_agent: str) -> str:
    """Определяет человекочитаемое наименование устройства и браузера по строке User-Agent.

    Args:
        user_agent: Заголовок HTTP User-Agent.

    Returns:
        str: Название устройства, например 'iPhone (Safari)', 'Android (Chrome)', 'Windows (Chrome)'.
    """
    if not user_agent:
        return "Мобильное устройство"

    ua = user_agent.lower()

    # Определение ОС / Платформы
    os_name = "Устройство"
    if "iphone" in ua:
        os_name = "iPhone"
    elif "ipad" in ua:
        os_name = "iPad"
    elif "android" in ua:
        os_name = "Android"
    elif "macintosh" in ua or "mac os" in ua:
        os_name = "Mac"
    elif "windows" in ua:
        os_name = "Windows"
    elif "linux" in ua:
        os_name = "Linux"

    # Определение Браузера
    browser_name = "Браузер"
    if "edg" in ua:
        browser_name = "Edge"
    elif "yabrowser" in ua:
        browser_name = "Яндекс.Браузер"
    elif "opr" in ua or "opera" in ua:
        browser_name = "Opera"
    elif "chrome" in ua or "crios" in ua:
        browser_name = "Chrome"
    elif "safari" in ua and not ("chrome" in ua or "crios" in ua):
        browser_name = "Safari"
    elif "firefox" in ua or "fxios" in ua:
        browser_name = "Firefox"

    return f"{os_name} ({browser_name})"
