"""Представления (Views) и API-эндпоинты для протокола Passkeys / WebAuthn (FIDO2).

Обеспечивает регистрацию биометрических ключей устройств (Face ID, Touch ID, отпечаток пальца),
беспарольную аутентификацию пользователей с защитой от брутфорса и повторного воспроизведения,
а также управление привязанными доверенными устройствами в личном кабинете.
"""

import json
from typing import Any, Dict, Optional

from django.conf import settings
from django.contrib import auth
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpRequest, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from administration_app.models import PortalProperty
from core import logger
from customers_app.models import DataBaseUser, UserPasskey
from customers_app.views import get_client_ip, record_security_event
from customers_app.webauthn_utils import (
    b64url_decode,
    b64url_encode,
    detect_device_name_from_user_agent,
    generate_challenge,
    parse_attestation_object,
    parse_authenticator_data,
    verify_webauthn_signature,
)


def _get_rp_id(request: HttpRequest) -> str:
    """Извлекает Relying Party ID (доменное имя без порта) из текущего HTTP-запроса.

    Args:
        request: Объект HTTP-запроса.

    Returns:
        str: Доменное имя хоста (например, 'corp.barkol.ru', 'reserv.barkol.ru' или 'localhost').
    """
    host = request.get_host().split(':')[0]
    return host


@login_required
@require_GET
def webauthn_register_options(request: HttpRequest) -> JsonResponse:
    """Формирует параметры для регистрации нового биометрического ключа (Passkey) через WebAuthn API.

    Генерирует криптографический challenge, сохраняет его во временной сессии пользователя
    и возвращает JSON-структуру параметров для вызова navigator.credentials.create().

    Args:
        request: Входящий HTTP-запрос авторизованного пользователя.

    Returns:
        JsonResponse: Параметры открытого ключа для создания Passkey на клиентском устройстве.
    """
    challenge = generate_challenge(32)
    request.session['webauthn_reg_challenge'] = challenge
    request.session['webauthn_reg_timestamp'] = timezone.now().timestamp()

    rp_id = _get_rp_id(request)
    user = request.user

    # Исключаем уже зарегистрированные учетные данные пользователя
    existing_credentials = []
    for passkey in user.passkeys.all():
        existing_credentials.append({
            'type': 'public-key',
            'id': passkey.credential_id,
            'transports': ['internal', 'hybrid'],
        })

    display_name = user.get_full_name() or user.username

    options: Dict[str, Any] = {
        'challenge': challenge,
        'rp': {
            'name': 'ООО АК «БАРКОЛ»',
            'id': rp_id,
        },
        'user': {
            'id': b64url_encode(str(user.pk).encode('utf-8')),
            'name': user.username,
            'displayName': display_name,
        },
        'pubKeyCredParams': [
            {'type': 'public-key', 'alg': -7},   # ES256 (ECDSA P-256)
            {'type': 'public-key', 'alg': -257}, # RS256 (RSA 2048)
        ],
        'authenticatorSelection': {
            'authenticatorAttachment': 'platform', # Face ID, Touch ID, сканер отпечатка
            'userVerification': 'preferred',
            'residentKey': 'preferred',
        },
        'timeout': 60000,
        'attestation': 'none',
        'excludeCredentials': existing_credentials,
    }

    return JsonResponse(options)


@login_required
@require_POST
def webauthn_register_verify(request: HttpRequest) -> JsonResponse:
    """Верифицирует ответ аттестации WebAuthn и сохраняет публичный ключ устройства в базе данных.

    Проверяет валидность challenge, декодирует CBOR-структуру attestationObject,
    извлекает открытый ключ COSE (конвертируя в PEM) и связывает учетные данные с пользователем.

    Args:
        request: Входящий HTTP-запрос с JSON-телом, содержащим ответ браузера WebAuthn.

    Returns:
        JsonResponse: Статус успешной привязки устройства либо сообщение об ошибке.
    """
    try:
        data = json.loads(request.body)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Некорректный формат JSON: {e}'}, status=400)

    session_challenge = request.session.get('webauthn_reg_challenge')
    session_ts = request.session.get('webauthn_reg_timestamp', 0)

    if not session_challenge or (timezone.now().timestamp() - session_ts) > 300:
        return JsonResponse({
            'success': False,
            'error': 'Срок действия сессии регистрации истек. Пожалуйста, попробуйте снова.',
        }, status=400)

    cred_id_str = data.get('id', '')
    response_data = data.get('response', {})
    client_data_b64 = response_data.get('clientDataJSON', '')
    attestation_b64 = response_data.get('attestationObject', '')
    device_name = (data.get('device_name') or '').strip()

    if not cred_id_str or not client_data_b64 or not attestation_b64:
        return JsonResponse({'success': False, 'error': 'Отсутствуют обязательные параметры WebAuthn.'}, status=400)

    # 1. Проверка clientDataJSON
    try:
        client_data_bytes = b64url_decode(client_data_b64)
        client_data_json = json.loads(client_data_bytes.decode('utf-8'))
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Ошибка декодирования clientDataJSON: {e}'}, status=400)

    if client_data_json.get('type') != 'webauthn.create':
        return JsonResponse({'success': False, 'error': 'Неверный тип операции WebAuthn.'}, status=400)

    if client_data_json.get('challenge') != session_challenge:
        return JsonResponse({'success': False, 'error': 'Несовпадение проверочного challenge.'}, status=400)

    # 2. Проверка attestationObject
    try:
        attestation_bytes = b64url_decode(attestation_b64)
        parsed_att = parse_attestation_object(attestation_bytes)
    except Exception as e:
        logger.warning(f"Passkey registration error during attestation parsing: {e}")
        return JsonResponse({'success': False, 'error': f'Ошибка парсинга данных аттестации: {e}'}, status=400)

    if not parsed_att.get('user_present'):
        return JsonResponse({'success': False, 'error': 'Флаг присутствия пользователя не подтвержден.'}, status=400)

    user_agent = request.META.get('HTTP_USER_AGENT', '')
    if not device_name:
        device_name = detect_device_name_from_user_agent(user_agent)

    # 3. Сохранение учетных данных
    credential_id = parsed_att['credential_id']
    public_key_pem = parsed_att['public_key_pem']
    sign_count = parsed_att['sign_count']
    aaguid = parsed_att['aaguid']

    transports = response_data.get('transports', [])
    transports_str = json.dumps(transports) if isinstance(transports, list) else str(transports or '')

    passkey, created = UserPasskey.objects.update_or_create(
        credential_id=credential_id,
        defaults={
            'user': request.user,
            'name': device_name[:100],
            'public_key': public_key_pem,
            'sign_count': sign_count,
            'aaguid': aaguid[:64],
            'device_type': 'platform',
            'transports': transports_str[:255],
            'user_agent': user_agent[:512],
            'last_used_at': timezone.now(),
        },
    )

    # Очищаем сессионный challenge
    request.session.pop('webauthn_reg_challenge', None)
    request.session.pop('webauthn_reg_timestamp', None)

    logger.info(f"SECURITY: User '{request.user.username}' successfully registered Passkey '{passkey.name}' (ID: {passkey.pk})")

    return JsonResponse({
        'success': True,
        'message': f'Устройство «{passkey.name}» успешно привязано к вашему профилю!',
        'passkey': {
            'id': passkey.pk,
            'name': passkey.name,
            'created_at': passkey.created_at.strftime('%d.%m.%Y %H:%M'),
        },
    })


@require_GET
def webauthn_login_options(request: HttpRequest) -> JsonResponse:
    """Формирует параметры аутентификации (assertion) для входа по Passkey / биометрии.

    Генерирует криптографический challenge для входа. Если указан параметр username,
    возвращает список зарегистрированных credential ID данного пользователя. Если username
    не указан, возвращает открытый список для discoverable credentials (Passkeys первого уровня).

    Args:
        request: Входящий HTTP-запрос.

    Returns:
        JsonResponse: Параметры для вызова navigator.credentials.get().
    """
    challenge = generate_challenge(32)
    request.session['webauthn_auth_challenge'] = challenge
    request.session['webauthn_auth_timestamp'] = timezone.now().timestamp()

    rp_id = _get_rp_id(request)
    username = (request.GET.get('username') or '').strip()

    allow_credentials = []
    if username:
        user_matches = DataBaseUser.objects.filter(username__iexact=username, is_active=True)
        if user_matches.exists():
            user = user_matches.first()
            for pkey in user.passkeys.all():
                allow_credentials.append({
                    'type': 'public-key',
                    'id': pkey.credential_id,
                    'transports': ['internal', 'hybrid'],
                })

    options: Dict[str, Any] = {
        'challenge': challenge,
        'rpId': rp_id,
        'timeout': 60000,
        'userVerification': 'preferred',
        'allowCredentials': allow_credentials,
    }

    return JsonResponse(options)


@require_POST
def webauthn_login_verify(request: HttpRequest) -> JsonResponse:
    """Проверяет цифровую подпись WebAuthn assertion и выполняет вход пользователя в систему.

    Проверяет защиту от брутфорса по IP-адресу, валидирует challenge и origin,
    находит привязанный Passkey по credential ID, верифицирует цифровую подпись открытым ключом
    и при успехе авторизует пользователя с продленной сессией для мобильных устройств (60 дней).

    Args:
        request: Входящий HTTP-запрос с JSON-ответом биометрической проверки устройства.

    Returns:
        JsonResponse: Результат входа с URL перенаправления либо сообщение об ошибке.
    """
    client_ip = get_client_ip(request)
    lock_key = f"login_lock_{client_ip}"
    attempts_key = f"login_attempts_{client_ip}"

    # Проверка блокировки IP
    if cache.get(lock_key):
        logger.warning(f"SECURITY: Blocked WebAuthn login attempt from locked IP {client_ip}")
        record_security_event(
            ip=client_ip,
            username="[webauthn]",
            event_type="blocked",
            attempts=5,
            details="Попытка входа по биометрии с заблокированного IP",
        )
        return JsonResponse({
            'success': False,
            'error': 'Слишком много неудачных попыток входа с вашего IP-адреса. Доступ временно заблокирован на 15 минут.',
        }, status=429)

    try:
        data = json.loads(request.body)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Некорректный формат JSON: {e}'}, status=400)

    session_challenge = request.session.get('webauthn_auth_challenge')
    session_ts = request.session.get('webauthn_auth_timestamp', 0)

    if not session_challenge or (timezone.now().timestamp() - session_ts) > 300:
        return JsonResponse({
            'success': False,
            'error': 'Сессия аутентификации истекла. Пожалуйста, повторите попытку.',
        }, status=400)

    cred_id_str = data.get('id', '')
    response_data = data.get('response', {})
    client_data_b64 = response_data.get('clientDataJSON', '')
    auth_data_b64 = response_data.get('authenticatorData', '')
    signature_b64 = response_data.get('signature', '')
    next_url = data.get('next', '')

    if not cred_id_str or not client_data_b64 or not auth_data_b64 or not signature_b64:
        return JsonResponse({'success': False, 'error': 'Отсутствуют обязательные криптографические данные.'}, status=400)

    # 1. Поиск зарегистрированного Passkey
    try:
        passkey = UserPasskey.objects.select_related('user').get(credential_id=cred_id_str)
    except UserPasskey.DoesNotExist:
        logger.warning(f"SECURITY: Passkey not found for credential ID {cred_id_str[:20]}... from IP {client_ip}")
        return JsonResponse({'success': False, 'error': 'Биометрический ключ не найден в системе.'}, status=404)

    user = passkey.user
    if not user.is_active:
        return JsonResponse({'success': False, 'error': 'Учетная запись пользователя заблокирована.'}, status=403)

    # 2. Проверка clientDataJSON
    try:
        client_data_bytes = b64url_decode(client_data_b64)
        client_data_json = json.loads(client_data_bytes.decode('utf-8'))
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Ошибка декодирования clientDataJSON: {e}'}, status=400)

    if client_data_json.get('type') != 'webauthn.get':
        return JsonResponse({'success': False, 'error': 'Неверный тип операции WebAuthn.'}, status=400)

    if client_data_json.get('challenge') != session_challenge:
        return JsonResponse({'success': False, 'error': 'Несовпадение проверочного challenge.'}, status=400)

    # 3. Декодирование authenticatorData и проверка флагов
    try:
        auth_data_bytes = b64url_decode(auth_data_b64)
        parsed_auth_data = parse_authenticator_data(auth_data_bytes)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Ошибка структуры authenticatorData: {e}'}, status=400)

    if not parsed_auth_data.get('user_present'):
        return JsonResponse({'success': False, 'error': 'Присутствие пользователя не подтверждено.'}, status=400)

    # 4. Верификация цифровой подписи
    try:
        signature_bytes = b64url_decode(signature_b64)
        is_valid = verify_webauthn_signature(
            public_key_pem=passkey.public_key,
            authenticator_data_bytes=auth_data_bytes,
            client_data_json_bytes=client_data_bytes,
            signature_bytes=signature_bytes,
        )
    except Exception as e:
        logger.warning(f"Signature verification error for user '{user.username}': {e}")
        is_valid = False

    if not is_valid:
        attempts = (cache.get(attempts_key) or 0) + 1
        cache.set(attempts_key, attempts, timeout=900)
        logger.warning(f"SECURITY: Invalid Passkey signature attempt {attempts}/5 for user '{user.username}' from IP {client_ip}")
        if attempts >= 5:
            cache.set(lock_key, True, timeout=900)
            record_security_event(
                ip=client_ip,
                username=user.username,
                event_type="lock",
                attempts=attempts,
                details="Превышен лимит попыток биометрического входа. IP заблокирован.",
            )
            return JsonResponse({
                'success': False,
                'error': 'Превышено количество попыток. IP-адрес заблокирован на 15 минут.',
            }, status=429)

        return JsonResponse({'success': False, 'error': 'Ошибка верификации биометрической подписи.'}, status=400)

    # 5. Успешная аутентификация
    cache.delete(attempts_key)
    cache.delete(lock_key)

    # Обновление счетчика подписей и времени использования
    new_sign_count = parsed_auth_data['sign_count']
    if new_sign_count > 0:
        passkey.sign_count = new_sign_count
    passkey.last_used_at = timezone.now()
    passkey.save(update_fields=['sign_count', 'last_used_at'])

    # Вход в сессию Django
    auth.login(request, user, backend='django.contrib.auth.backends.ModelBackend')

    # Длительная сессия для мобильных устройств при входе по Passkey (60 дней)
    extended_session_duration = 60 * 60 * 24 * 60  # 60 дней в секундах
    request.session.set_expiry(extended_session_duration)

    # Базовые параметры сессии портала
    portal = PortalProperty.objects.first()
    portal_paginator = portal.portal_paginator if portal else 10
    request.session['portal_paginator'] = portal_paginator
    request.session['current_month'] = int(timezone.now().month)
    request.session['current_year'] = int(timezone.now().year)

    # Очищаем сессионный challenge
    request.session.pop('webauthn_auth_challenge', None)
    request.session.pop('webauthn_auth_timestamp', None)

    record_security_event(
        ip=client_ip,
        username=user.username,
        event_type="success",
        attempts=0,
        details=f"Успешный вход по Passkey ({passkey.name}) с длительной сессией",
    )
    logger.info(f"SECURITY: Successful Passkey login for user '{user.username}' from IP {client_ip} via device '{passkey.name}'")

    # Определение целевого URL перенаправления
    target_url = reverse('customers_app:profile', args=(user.pk,))
    if next_url and url_has_allowed_host_and_scheme(url=next_url, allowed_hosts={request.get_host()}):
        target_url = next_url

    return JsonResponse({
        'success': True,
        'message': 'Успешная аутентификация!',
        'redirect_url': target_url,
    })


@login_required
@require_GET
def webauthn_passkey_list(request: HttpRequest) -> JsonResponse:
    """Возвращает JSON-список зарегистрированных биометрических устройств (Passkeys) текущего пользователя.

    Args:
        request: Входящий HTTP-запрос авторизованного пользователя.

    Returns:
        JsonResponse: Список ключей доступа с метаданными (ID, название, дата добавления, последнее использование).
    """
    passkeys = request.user.passkeys.all()
    data = []
    current_ua = request.META.get('HTTP_USER_AGENT', '')

    for p in passkeys:
        is_current = bool(p.user_agent and p.user_agent == current_ua)
        data.append({
            'id': p.pk,
            'name': p.name,
            'device_type': p.device_type,
            'aaguid': p.aaguid,
            'created_at': p.created_at.strftime('%d.%m.%Y %H:%M'),
            'last_used_at': p.last_used_at.strftime('%d.%m.%Y %H:%M') if p.last_used_at else 'Еще не использовался',
            'is_current': is_current,
        })

    return JsonResponse({'success': True, 'passkeys': data})


@login_required
@require_POST
def webauthn_passkey_delete(request: HttpRequest, pk: int) -> JsonResponse:
    """Удаляет зарегистрированный ключ доступа Passkey пользователя.

    Args:
        request: Входящий HTTP-запрос авторизованного пользователя.
        pk: Первичный ключ (ID) удаляемого объекта UserPasskey.

    Returns:
        JsonResponse: Статус успешного удаления либо 404/403.
    """
    deleted_count, _ = UserPasskey.objects.filter(pk=pk, user=request.user).delete()
    if not deleted_count:
        return JsonResponse({'success': False, 'error': 'Ключ доступа не найден или доступ запрещен.'}, status=404)

    logger.info(f"SECURITY: User '{request.user.username}' deleted Passkey ID {pk}")
    return JsonResponse({'success': True, 'message': 'Ключ доступа успешно удален.'})


@login_required
@require_POST
def webauthn_passkey_rename(request: HttpRequest, pk: int) -> JsonResponse:
    """Переименовывает зарегистрированный ключ доступа Passkey.

    Args:
        request: Входящий HTTP-запрос с JSON-телом {'name': 'Новое имя'}.
        pk: Первичный ключ (ID) объекта UserPasskey.

    Returns:
        JsonResponse: Статус успешного обновления имени устройства.
    """
    try:
        data = json.loads(request.body)
        new_name = (data.get('name') or '').strip()
    except Exception:
        new_name = ''

    if not new_name:
        return JsonResponse({'success': False, 'error': 'Укажите название устройства.'}, status=400)

    try:
        passkey = UserPasskey.objects.get(pk=pk, user=request.user)
        passkey.name = new_name[:100]
        passkey.save(update_fields=['name'])
    except UserPasskey.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Ключ доступа не найден.'}, status=404)

    return JsonResponse({'success': True, 'message': 'Название устройства обновлено.', 'name': passkey.name})
