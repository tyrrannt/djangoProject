"""Сервисы формирования сертификатов, генерации QR-кодов и проверки подлинности."""

import io
from typing import Dict, Any, Optional
from datetime import timedelta
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from testing_app.models import TestingAttempt, TestingAuditLog


def generate_certificate_qr_code(attempt: TestingAttempt, request=None) -> Optional[str]:
    """Генерирует изображение QR-кода со ссылкой на страницу проверки подлинности.

    Если QR-код уже сохранен в модели attempt.qr_code_image, возвращает его URL.
    В противном случае генерирует PNG с помощью qrcode, сохраняет в хранилище media
    и возвращает URL.

    Args:
        attempt (TestingAttempt): Успешно завершенная попытка сдачи теста.
        request (Optional[HttpRequest]): Запрос для формирования абсолютного URL.

    Returns:
        Optional[str]: URL сгенерированного файла QR-кода.
    """
    if not attempt.is_passed or not attempt.certificate_uuid:
        return None

    # Если QR-код уже сгенерирован и файл существует
    if attempt.qr_code_image:
        try:
            return attempt.qr_code_image.url
        except Exception:
            pass

    import qrcode
    from qrcode.image.styledpil import StyledPilImage
    from qrcode.image.styles.moduledrawers import CircleModuleDrawer

    # Формируем URL верификации
    relative_url = reverse("testing_app:certificate_verify", kwargs={"certificate_uuid": attempt.certificate_uuid})
    if request:
        verify_url = request.build_absolute_uri(relative_url)
    else:
        verify_url = relative_url

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(verify_url)
    qr.make(fit=True)

    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=CircleModuleDrawer(radius_factor=0.6),
        fill_color=(30, 58, 138),  # Фирменный синий Баркол #1E3A8A
        back_color=(255, 255, 255),
    )

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    file_name = f"qr_{attempt.certificate_uuid}.png"

    attempt.qr_code_image.save(file_name, ContentFile(buffer.getvalue()), save=True)
    return attempt.qr_code_image.url


def to_dative_fullname(last_name: str, first_name: str, surname: str = "", gender: str = "") -> str:
    """Склоняет полное ФИО человека в дательный падеж (кому?).

    Поддерживает склонение мужских и женских русских и распространенных фамилий,
    имен и отчеств в соответствии с правилами русской грамматики.

    Args:
        last_name (str): Фамилия.
        first_name (str): Имя.
        surname (str): Отчество.
        gender (str): Пол ('male', 'female', 'мужской', 'женский' или пусто).

    Returns:
        str: Полное ФИО в дательном падеже (например, "Иванову Ивану Ивановичу").
    """
    last_name = (last_name or "").strip()
    first_name = (first_name or "").strip()
    surname = (surname or "").strip()

    if not last_name and not first_name:
        return ""

    # Определение грамматического пола
    is_female = False
    if gender in ("female", "женский"):
        is_female = True
    elif surname.endswith(("вна", "чна", "шна", "ична")):
        is_female = True
    elif surname.endswith(("ич", "ыч")):
        is_female = False
    elif last_name.endswith(("ова", "ева", "ина", "ына", "ая", "яя")):
        is_female = True
    elif first_name.endswith(("а", "я")) and first_name not in ("Илья", "Никита", "Данила", "Лука", "Фома", "Савва", "Кузьма"):
        is_female = True

    # 1. Склонение отчества
    d_pn = surname
    if surname:
        if is_female:
            if surname.endswith("на"):
                d_pn = surname[:-1] + "е"
        else:
            if surname.endswith("ич"):
                d_pn = surname + "у"

    # 2. Склонение имени
    d_fn = first_name
    if first_name:
        if is_female:
            if first_name.endswith("ия"):
                d_fn = first_name[:-2] + "ии"
            elif first_name.endswith(("а", "я")):
                d_fn = first_name[:-1] + "е"
            elif first_name.endswith("ь"):
                d_fn = first_name[:-1] + "и"
        else:
            if first_name in ("Павел", "павел"):
                d_fn = "Павлу"
            elif first_name in ("Петр", "Пётр", "петр", "пётр"):
                d_fn = "Петру"
            elif first_name in ("Лев", "лев"):
                d_fn = "Льву"
            elif first_name.endswith("ий"):
                d_fn = first_name[:-2] + "ию"
            elif first_name.endswith("ей"):
                d_fn = first_name[:-2] + "ею"
            elif first_name.endswith(("ай", "ой", "уй")):
                d_fn = first_name[:-1] + "ю"
            elif first_name.endswith("ь"):
                d_fn = first_name[:-1] + "ю"
            elif first_name.endswith(("а", "я")):
                d_fn = first_name[:-1] + "е"
            elif first_name.endswith("й"):
                d_fn = first_name[:-1] + "ю"
            else:
                d_fn = first_name + "у"

    # 3. Склонение фамилии
    d_ln = last_name
    if last_name:
        if is_female:
            if last_name.endswith(("ова", "ева", "ина", "ына")):
                d_ln = last_name[:-1] + "ой"
            elif last_name.endswith(("ая", "яя")):
                d_ln = last_name[:-2] + "ой"
            elif last_name.endswith(("а", "я")) and not last_name.endswith(("о", "е", "и", "у", "ю", "ых", "их")):
                d_ln = last_name[:-1] + "е"
        else:
            if last_name.endswith(("ский", "цкий", "ый", "ой")):
                d_ln = last_name[:-2] + "ому"
            elif last_name.endswith("ий"):
                d_ln = last_name[:-2] + "ему"
            elif last_name.endswith(("о", "е", "э", "и", "у", "ю", "ых", "их")):
                d_ln = last_name
            elif last_name.endswith("ь"):
                d_ln = last_name[:-1] + "ю"
            elif last_name.endswith("й"):
                d_ln = last_name[:-1] + "ю"
            elif last_name.endswith(("а", "я")):
                d_ln = last_name[:-1] + "е"
            else:
                d_ln = last_name + "у"

    parts = [d_ln, d_fn, d_pn]
    return " ".join(filter(None, parts)).strip()


def get_user_full_name_with_patronymic(user) -> str:
    """Возвращает полное ФИО пользователя в именительном падеже (Фамилия Имя Отчество).

    Args:
        user: Экземпляр пользователя (DataBaseUser).

    Returns:
        str: Полное ФИО (например, "Иванов Иван Иванович").
    """
    last_name = (getattr(user, "last_name", "") or "").strip()
    first_name = (getattr(user, "first_name", "") or "").strip()
    surname = (getattr(user, "surname", "") or "").strip()
    if last_name or first_name or surname:
        return " ".join(filter(None, [last_name, first_name, surname])).strip()
    title = getattr(user, "title", "")
    if title:
        return title.strip()
    return user.get_full_name() or getattr(user, "username", "")


def get_user_dative_name(user) -> str:
    """Возвращает полное ФИО пользователя в дательном падеже (кому?).

    Args:
        user: Экземпляр пользователя (DataBaseUser).

    Returns:
        str: Полное ФИО в дательном падеже (например, "Иванову Ивану Ивановичу").
    """
    last_name = getattr(user, "last_name", "") or ""
    first_name = getattr(user, "first_name", "") or ""
    surname = getattr(user, "surname", "") or ""
    gender = getattr(user, "gender", "") or ""

    if not last_name and not first_name:
        title = getattr(user, "title", "") or user.get_full_name() or getattr(user, "username", "")
        parts = title.split()
        if len(parts) >= 3:
            last_name, first_name, surname = parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            last_name, first_name = parts[0], parts[1]
        elif len(parts) == 1:
            last_name = parts[0]

    return to_dative_fullname(last_name, first_name, surname, gender)


def get_certificate_context(attempt: TestingAttempt, request=None) -> Dict[str, Any]:
    """Формирует полный набор контекстных данных для отображения и печати сертификата.

    Args:
        attempt (TestingAttempt): Успешная попытка тестирования.
        request (Optional[HttpRequest]): HTTP-запрос для построения абсолютных путей.

    Returns:
        Dict[str, Any]: Словарь с юридическими и персональными реквизитами сертификата.
    """
    assignment = attempt.assignment
    testing = assignment.testing
    finished_at = attempt.finished_at or timezone.now()

    # Срок действия сертификата: 1 год со дня успешной сдачи
    valid_until = finished_at + timedelta(days=365)

    qr_url = generate_certificate_qr_code(attempt, request=request)
    verify_url = reverse("testing_app:certificate_verify", kwargs={"certificate_uuid": attempt.certificate_uuid})
    if request:
        full_verify_url = request.build_absolute_uri(verify_url)
    else:
        full_verify_url = verify_url

    employee_full_nom = get_user_full_name_with_patronymic(assignment.employee)
    employee_full_dat = get_user_dative_name(assignment.employee) or employee_full_nom

    return {
        "attempt": attempt,
        "assignment": assignment,
        "testing": testing,
        "company_name": "ООО Авиакомпания «БАРКОЛ»",
        "certificate_title": "УДОСТОВЕРЕНИЕ (СЕРТИФИКАТ)",
        "certificate_subtitle": "О прохождении периодической проверки знаний",
        "result_number": attempt.result_number,
        "certificate_uuid": attempt.certificate_uuid,
        "employee_name": employee_full_nom,
        "employee_name_dative": employee_full_dat,
        "job_title": assignment.assigned_job_title,
        "division_title": assignment.assigned_division_title,
        "group_name": assignment.group.name,
        "order_info": f"Приказ №{testing.order_number} от {testing.order_date.strftime('%d.%m.%Y')} «{testing.order_name}»",
        "issue_date": finished_at.strftime("%d.%m.%Y"),
        "valid_until_date": valid_until.strftime("%d.%m.%Y"),
        "score_percentage": attempt.score_percentage,
        "passing_score_percentage": attempt.passing_score_percentage,
        "total_questions": attempt.total_questions,
        "correct_answers_count": attempt.correct_answers_count,
        "qr_code_url": qr_url,
        "verify_url": full_verify_url,
    }


def verify_certificate_by_uuid(certificate_uuid: str) -> Optional[Dict[str, Any]]:
    """Выполняет поиск и верификацию сертификата по его уникальному UUID.

    Используется на закрытой странице проверки подлинности (QR-код).

    Args:
        certificate_uuid (str): Уникальный UUID сертификата.

    Returns:
        Optional[Dict[str, Any]]: Данные верифицированного сертификата или None при отсутствии.
    """
    attempt = TestingAttempt.objects.filter(
        certificate_uuid=certificate_uuid,
        is_passed=True,
        status=TestingAttempt.Status.COMPLETED
    ).select_related(
        "assignment__employee",
        "assignment__testing",
        "assignment__group"
    ).first()

    if not attempt:
        return None

    assignment = attempt.assignment
    testing = assignment.testing
    finished_at = attempt.finished_at or timezone.now()
    valid_until = finished_at + timedelta(days=365)
    is_expired = timezone.now() > valid_until

    employee_full_nom = get_user_full_name_with_patronymic(assignment.employee)
    employee_full_dat = get_user_dative_name(assignment.employee) or employee_full_nom

    return {
        "is_valid": True,
        "is_expired": is_expired,
        "attempt": attempt,
        "company_name": "ООО Авиакомпания «БАРКОЛ»",
        "result_number": attempt.result_number,
        "certificate_uuid": attempt.certificate_uuid,
        "employee_name": employee_full_nom,
        "employee_name_dative": employee_full_dat,
        "job_title": assignment.assigned_job_title,
        "division_title": assignment.assigned_division_title,
        "testing_title": testing.title,
        "order_info": f"Приказ №{testing.order_number} от {testing.order_date.strftime('%d.%m.%Y')}",
        "group_name": assignment.group.name,
        "finished_at": finished_at,
        "valid_until": valid_until,
        "score_percentage": attempt.score_percentage,
        "passing_score_percentage": attempt.passing_score_percentage,
    }
