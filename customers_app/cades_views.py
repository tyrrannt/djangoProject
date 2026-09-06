"""Представления (Views) и API-эндпоинты для входа по ЭЦП (КЭП / ГОСТ / КриптоПро / Рутокен).

Обеспечивает выдачу одноразовых криптографических challenge, валидацию цифровых подписей,
парсинг сертификатов X.509, поиск и автоматическое сопоставление сотрудников по СНИЛС/ИНН,
беспарольную авторизацию в системе, а также управление сертификатами в личном кабинете.
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
from django.views.decorators.http import require_GET, require_POST

from core import logger
from customers_app.cades_utils import (
    find_user_by_certificate,
    generate_cert_challenge,
    parse_x509_certificate,
    verify_signature_and_extract_cert,
)
from customers_app.models import DataBaseUser, UserCertificate
from customers_app.views import get_client_ip, record_security_event


# Лимиты безопасности для защиты от перебора ЭЦП
CADES_MAX_ATTEMPTS = 5
CADES_BAN_TIMEOUT = 900  # 15 минут


@require_GET
def cades_login_challenge(request: HttpRequest) -> JsonResponse:
    """Генерирует одноразовый криптографический challenge для аутентификации по ЭЦП.

    Сохраняет challenge во временной сессии пользователя со сроком действия 5 минут.

    Args:
        request: Входящий HTTP-запрос.

    Returns:
        JsonResponse: JSON с полем challenge в формате Base64URL.
    """
    challenge = generate_cert_challenge(32)
    request.session['cades_auth_challenge'] = challenge
    request.session['cades_auth_timestamp'] = timezone.now().timestamp()

    return JsonResponse({
        'success': True,
        'challenge': challenge,
    })


@require_POST
def cades_login_verify(request: HttpRequest) -> JsonResponse:
    """Верифицирует цифровую подпись ЭЦП, находит пользователя и выполняет вход в систему.

    Проверяет защиту от брутфорса по IP-адресу, валидирует сессионный challenge,
    извлекает метаданные сертификата (СНИЛС, ИНН, ФИО, отпечаток SHA-1),
    сопоставляет с учетной записью сотрудника и авторизует пользователя с продленной сессией.

    Args:
        request: Входящий HTTP-запрос с JSON-телом, содержащим 'signature', 'certificate' и 'next'.

    Returns:
        JsonResponse: Статус успешного входа и URL для перенаправления либо сообщение об ошибке.
    """
    ip = get_client_ip(request)

    # 1. Защита от перебора по IP
    ban_cache_key = f"cades_banned_{ip}"
    if cache.get(ban_cache_key):
        return JsonResponse({
            'success': False,
            'error': 'Слишком много неудачных попыток входа по ЭЦП. Доступ временно заблокирован на 15 минут.',
        }, status=429)

    attempts_cache_key = f"cades_attempts_{ip}"
    failed_attempts = cache.get(attempts_cache_key, 0)

    try:
        data = json.loads(request.body)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Некорректный формат JSON: {e}'}, status=400)

    session_challenge = request.session.get('cades_auth_challenge')
    session_ts = request.session.get('cades_auth_timestamp', 0)

    if not session_challenge or (timezone.now().timestamp() - session_ts) > 300:
        return JsonResponse({
            'success': False,
            'error': 'Срок действия сессии подписи истек. Пожалуйста, попробуйте снова.',
        }, status=400)

    signed_data_b64 = data.get('signature', '').strip()
    cert_b64 = data.get('certificate', '').strip()
    next_url = data.get('next', '').strip()

    if not signed_data_b64:
        return JsonResponse({'success': False, 'error': 'Отсутствуют данные цифровой подписи.'}, status=400)

    # 2. Верификация подписи и парсинг сертификата
    try:
        cert_info = verify_signature_and_extract_cert(
            signed_data_b64=signed_data_b64,
            expected_challenge=session_challenge,
            cert_b64=cert_b64,
        )
    except ValueError as e:
        failed_attempts += 1
        cache.set(attempts_cache_key, failed_attempts, 900)
        if failed_attempts >= CADES_MAX_ATTEMPTS:
            cache.set(ban_cache_key, True, CADES_BAN_TIMEOUT)
            record_security_event(
                request,
                f"SECURITY_ALERT: IP {ip} banned due to {CADES_MAX_ATTEMPTS} failed CAdES signature attempts."
            )
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

    # 3. Сопоставление с пользователем портала
    user, cert_obj, is_new_binding = find_user_by_certificate(cert_info)

    if not user or not user.is_active:
        failed_attempts += 1
        cache.set(attempts_cache_key, failed_attempts, 900)
        snils_display = cert_info.get('snils') or 'не указан'
        inn_display = cert_info.get('inn') or 'не указан'
        cn_display = cert_info.get('cn') or 'Неизвестный владелец'
        logger.warning(
            f"CADES_AUTH_FAILED: User with Certificate '{cn_display}' (SNILS: {snils_display}, INN: {inn_display}) "
            f"not found or inactive. IP: {ip}"
        )
        return JsonResponse({
            'success': False,
            'error': (
                f"Сотрудник с сертификатом «{cn_display}» (СНИЛС: {snils_display}, ИНН: {inn_display}) "
                "не найден в базе данных портала. Обратитесь к администратору или привяжите сертификат "
                "в личном кабинете после стандартного входа."
            ),
        }, status=404)

    # 4. Автоматическая привязка сертификата к профилю либо обновление даты использования
    cert_name = f"КЭП {cert_info.get('organization') or cert_info.get('cn') or 'ЭЦП'}"
    if not cert_obj:
        cert_obj, _ = UserCertificate.objects.update_or_create(
            thumbprint=cert_info['thumbprint'],
            defaults={
                'user': user,
                'name': cert_name[:200],
                'serial_number': cert_info.get('serial_number', ''),
                'subject_name': cert_info.get('subject_name', ''),
                'issuer_name': cert_info.get('issuer_name', ''),
                'snils': cert_info.get('snils', ''),
                'inn': cert_info.get('inn', ''),
                'cn': cert_info.get('cn', ''),
                'valid_from': cert_info.get('valid_from'),
                'valid_to': cert_info.get('valid_to'),
                'certificate_data': cert_info.get('raw_base64', ''),
                'is_active': True,
                'last_used_at': timezone.now(),
            }
        )
        logger.info(
            f"CADES_BINDING: Certificate '{cert_obj.name}' (Thumbprint: {cert_obj.thumbprint}) "
            f"automatically bound to user '{user.username}' (ID: {user.pk})."
        )
    else:
        cert_obj.last_used_at = timezone.now()
        cert_obj.save(update_fields=['last_used_at'])

    # 5. Авторизация пользователя в Django
    auth.login(request, user, backend='django.contrib.auth.backends.ModelBackend')

    # Продление сессии на 30 дней для удобства работы
    request.session.set_expiry(60 * 60 * 24 * 30)

    # Очистка сессионных challenge и счетчиков ошибок
    request.session.pop('cades_auth_challenge', None)
    request.session.pop('cades_auth_timestamp', None)
    cache.delete(attempts_cache_key)

    record_security_event(
        request,
        f"Успешный вход в систему по сертификату ЭЦП «{cert_obj.name}» (Thumbprint: {cert_obj.thumbprint[:10]}...)"
    )

    # Определение безопасного URL для редиректа
    redirect_url = reverse('customers_app:index')
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure()
    ):
        redirect_url = next_url

    return JsonResponse({
        'success': True,
        'message': f'Добро пожаловать, {user.get_full_name() or user.username}!',
        'redirect_url': redirect_url,
        'user': {
            'id': user.pk,
            'username': user.username,
            'full_name': user.get_full_name(),
        },
    })


@login_required
@require_GET
def cades_cert_list(request: HttpRequest) -> JsonResponse:
    """Возвращает список привязанных сертификатов ЭЦП текущего пользователя.

    Args:
        request: Входящий HTTP-запрос авторизованного пользователя.

    Returns:
        JsonResponse: Список сертификатов с реквизитами и статусом активности.
    """
    certs = UserCertificate.objects.filter(user=request.user).order_by('-created_at')
    result = []

    for cert in certs:
        result.append({
            'id': cert.pk,
            'name': cert.name,
            'thumbprint': cert.thumbprint,
            'serial_number': cert.serial_number,
            'cn': cert.cn,
            'snils': cert.snils,
            'inn': cert.inn,
            'issuer_name': cert.issuer_name,
            'valid_from': cert.valid_from.strftime('%d.%m.%Y %H:%M') if cert.valid_from else '—',
            'valid_to': cert.valid_to.strftime('%d.%m.%Y %H:%M') if cert.valid_to else '—',
            'is_expired': cert.is_expired(),
            'is_active': cert.is_active,
            'created_at': cert.created_at.strftime('%d.%m.%Y %H:%M'),
            'last_used_at': cert.last_used_at.strftime('%d.%m.%Y %H:%M') if cert.last_used_at else '—',
        })

    return JsonResponse({'success': True, 'certificates': result})


@login_required
@require_POST
def cades_cert_register(request: HttpRequest) -> JsonResponse:
    """Привязывает новый сертификат ЭЦП к учетной записи авторизованного пользователя.

    Args:
        request: Входящий HTTP-запрос с телом JSON, содержащим 'certificate' и 'name'.

    Returns:
        JsonResponse: Статус успешной привязки сертификата либо сообщение об ошибке.
    """
    try:
        data = json.loads(request.body)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Некорректный JSON: {e}'}, status=400)

    cert_b64 = data.get('certificate', '').strip()
    custom_name = data.get('name', '').strip()

    if not cert_b64:
        return JsonResponse({'success': False, 'error': 'Отсутствуют данные сертификата.'}, status=400)

    try:
        cert_info = parse_x509_certificate(cert_b64)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Ошибка синтаксического анализа сертификата: {e}'}, status=400)

    if cert_info['is_expired']:
        return JsonResponse({
            'success': False,
            'error': f'Срок действия данного сертификата истек ({cert_info["valid_to"].strftime("%d.%m.%Y %H:%M")}).',
        }, status=400)

    # Проверка, не привязан ли этот сертификат к другому пользователю
    existing = UserCertificate.objects.filter(thumbprint=cert_info['thumbprint']).first()
    if existing and existing.user != request.user:
        return JsonResponse({
            'success': False,
            'error': 'Этот сертификат уже привязан к учетной записи другого сотрудника.',
        }, status=400)

    name = custom_name or f"КЭП {cert_info.get('organization') or cert_info.get('cn') or 'ЭЦП'}"

    cert_obj, created = UserCertificate.objects.update_or_create(
        thumbprint=cert_info['thumbprint'],
        defaults={
            'user': request.user,
            'name': name[:200],
            'serial_number': cert_info.get('serial_number', ''),
            'subject_name': cert_info.get('subject_name', ''),
            'issuer_name': cert_info.get('issuer_name', ''),
            'snils': cert_info.get('snils', ''),
            'inn': cert_info.get('inn', ''),
            'cn': cert_info.get('cn', ''),
            'valid_from': cert_info.get('valid_from'),
            'valid_to': cert_info.get('valid_to'),
            'certificate_data': cert_info.get('raw_base64', ''),
            'is_active': True,
        }
    )

    logger.info(
        f"CADES_REGISTER: User '{request.user.username}' successfully registered Certificate '{cert_obj.name}' "
        f"(Thumbprint: {cert_obj.thumbprint})."
    )

    return JsonResponse({
        'success': True,
        'message': f'Сертификат «{cert_obj.name}» успешно привязан к вашему профилю!',
        'certificate': {
            'id': cert_obj.pk,
            'name': cert_obj.name,
            'cn': cert_obj.cn,
            'valid_to': cert_obj.valid_to.strftime('%d.%m.%Y %H:%M') if cert_obj.valid_to else '—',
        },
    })


@login_required
@require_POST
def cades_cert_delete(request: HttpRequest, pk: int) -> JsonResponse:
    """Отзывает (удаляет) привязанный сертификат ЭЦП текущего пользователя.

    Args:
        request: Входящий HTTP-запрос.
        pk: Первичный ключ (ID) удаляемого объекта `UserCertificate`.

    Returns:
        JsonResponse: Статус успешного удаления либо сообщение об ошибке.
    """
    deleted_count, _ = UserCertificate.objects.filter(pk=pk, user=request.user).delete()

    if deleted_count > 0:
        logger.info(f"CADES_DELETE: User '{request.user.username}' deleted Certificate ID {pk}.")
        return JsonResponse({
            'success': True,
            'message': 'Сертификат ЭЦП успешно отозван и удален.',
        })

    return JsonResponse({'success': False, 'error': 'Сертификат не найден или уже удален.'}, status=404)
