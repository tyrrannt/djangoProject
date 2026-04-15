from django.core.cache import cache
from django.db.models import Q

from contracts_app.models import Contract
from customers_app.models import Posts
from hrdepartment_app.models import (
    ApprovalOficialMemoProcess,
    DocumentsJobDescription, CreatingTeam, BusinessProcessRoutes,
)
from core import logger
from django.urls import resolve, Resolver404
from django.utils.translation import gettext as _


def breadcrumbs(request):
    path = request.path
    path_segments = [s for s in path.split('/') if s]
    crumbs = []
    url_acc = '/'

    # Словарь для перевода статических сегментов (если не используете стандартный .po файл)
    # Можно расширять по мере добавления разделов
    MAPPING = {
        'forms': _('Формы'),
        'advanced': _('Дополнительно'),
        'users': _('Пользователи'),
        'profile': _('Профиль'),
        'settings': _('Настройки'),
        'contracts': _('Договора'),
        'blank': _('Бланки'),
        'guidance_documents': _('Руководящие документы'),
        'medical': _('Медицинские направления'),
        'hr': _('Документация'),
        'operational': _('Нормативные акты'),
        'jobdescription': _('Должностные инструкции'),
        'briefings': _('Инструктажи'),
        'labor_protection_instructions': _('Инструкции по ТО ВС'),
        'provisions': _('Положения'),
        'order': _('Приказы'),
        'labor_protection': _('Процедуры по охране труда'),
        'help': _('Справка'),
        'staff': _('Список пользователей'),
        'team': _('Старшие бригад'),
        'report': _('Отчёты'),
        'jobs': _('Должности'),
        'harmful': _('Вредные условия труда'),
        'typedocuments': _('Типы документов'),
        'typecontracts': _('Типы договоров'),
        'typepropertys': _('Типы имущества'),
        'estate': _('Имущество'),
        'divisions': _('Подразделения'),
        'counteragent': _('Контрагенты'),
        'documents': _('Документы контрагентов'),
        'purpose': _('Цели служебных поездок'),
        'medicalorg': _('Медицинские организации'),
        'place': _('Места назначения'),
        'student_agreement': _('Ученические договора'),
        'bpmemo': _('Бизнес-процесс'),
        'memo': _('Служебные записки'),
        'lock-screen': _('Блокировка экрана'),
        'cancel': _('Отмена'),
        'update': _('Редактирование'),
        'delete': _('Удаление'),
        'timesheet': _('Табель'),
        # '': _(''),
    }

    for i, segment in enumerate(path_segments):
        url_acc += f"{segment}/"

        # 1. Проверяем в словаре MAPPING
        # 2. Если нет — делаем человекочитаемым (заменяем тире и ставим заглавную)
        name = MAPPING.get(segment.lower())
        if not name:
            name = segment.replace('-', ' ').replace('_', ' ').capitalize()

        try:
            resolve(url_acc)
            crumbs.append({
                'name': name,
                'url': url_acc if i < len(path_segments) - 1 else None
            })
        except Resolver404:
            # Для ID или ненайденных путей оставляем просто текст
            crumbs.append({
                'name': name,
                'url': None
            })

    return {'breadcrumbs': crumbs}

# ToDo: Создать модель в которую будет записываться вся статистика,
#  а занесение информации будет посредством метода моделей save()

def get_all_contracts(request):
    data = {}
    if request.user.is_anonymous:
        return data

    cache_key = f"get_all_contracts_{request.user.id}"

    contracts_count = Contract.objects.filter(
        Q(parent_category=None),
        Q(allowed_placed=True),
        Q(type_of_document__type_document="Договор"),
    ).count()

    if not request.user.is_anonymous:
        try:
            contracts_not_published = Contract.objects.filter(Q(allowed_placed=False))
            documents_not_published = DocumentsJobDescription.objects.filter(
                Q(allowed_placed=False)
            )
        except Exception as _ex:
            contracts_not_published = Contract.objects.filter(allowed_placed=False)
            documents_not_published = DocumentsJobDescription.objects.filter(
                allowed_placed=False
            )
        contracts_not_published_count = contracts_not_published.count()
        documents_not_published_count = documents_not_published.count()
    else:
        contracts_not_published = ""
        contracts_not_published_count = 0
        documents_not_published = ""
        documents_not_published_count = 0

    posts_not_published = Posts.objects.filter(allowed_placed=False)
    posts_not_published_count = Posts.objects.filter(allowed_placed=False).count()

    data = {
        "contracts_count": contracts_count,
        "contracts_not_published": contracts_not_published,
        "posts_not_published": posts_not_published,
        "contracts_not_published_count": contracts_not_published_count,
        "documents_not_published": documents_not_published,
        "documents_not_published_count": documents_not_published_count,
        "posts_not_published_count": posts_not_published_count,
    }

    cache.set(cache_key, data, 60 * 15)  # Кэшировать результат на 15 минут
    return data


def make_list(n):
    for _ in range(n):
        yield []  # empty list


def get_approval_oficial_memo_process(request):
    if request.user.is_anonymous:
        return {"notifications": []}

    notifications = []

    def add_notification(qs, icon, title, url_name, view_all_url, color="red", large=False):
        items = list(qs)
        if not items:
            return

        if callable(color):
            items_with_color = [(item, color(item)) for item in items]
        else:
            items_with_color = [(item, color) for item in items]

        notifications.append({
            "count": len(items),
            "icon_class": icon,
            "title": title,
            "items": items_with_color,
            "url_name": url_name,
            "view_all_url": view_all_url,
            "large": large
        })

    try:
        user = request.user
        profile = user.user_work_profile
        job = profile.job

        job_pk = job.pk
        division_pk = job.division_affiliation.pk
        division_name = job.division_affiliation.name

        # ===== Роли (1 запрос вместо 8) =====
        routes = BusinessProcessRoutes.objects.filter(
            business_process_type__in=["1", "2"]
        ).values(
            "business_process_type",
            "person_agreement__pk",
            "person_clerk__pk",
            "person_hr__pk",
            "person_sd__pk",
            "person_accounting__pk",
        )

        person_agreement = set()
        person_clerk = set()
        person_hr = set()
        person_distributor = set()
        person_accounting = set()

        person_agreement_cto = set()
        person_clerk_cto = set()
        person_hr_cto = set()

        for r in routes:
            if r["business_process_type"] == "1":
                person_agreement.add(r["person_agreement__pk"])
                person_clerk.add(r["person_clerk__pk"])
                person_hr.add(r["person_hr__pk"])
                person_distributor.add(r["person_sd__pk"])
                person_accounting.add(r["person_accounting__pk"])
            else:
                person_agreement_cto.add(r["person_agreement__pk"])
                person_clerk_cto.add(r["person_clerk__pk"])
                person_hr_cto.add(r["person_hr__pk"])

        # ===== Базовый queryset (убрали N+1) =====
        bpmemo_qs = ApprovalOficialMemoProcess.objects.exclude(cancellation=True).select_related(
            "document",
            "document__person",
            "document__person__user_work_profile",
            "document__person__user_work_profile__job",
            "person_executor__user_work_profile__job__division_affiliation",
        )

        # ===== Цвет =====
        def color_by_job(item):
            t = item.document.person.user_work_profile.job.type_of_job
            if t == "1":
                return "red"
            elif t == "2":
                return "green"
            return "black"

        # ===== Обычные БП =====
        if user.pk in person_agreement or user.is_superuser:
            add_notification(
                bpmemo_qs.filter(
                    person_executor__user_work_profile__job__division_affiliation__name=division_name,
                    document_not_agreed=False
                ),
                "bx bx-select-multiple", "Согласование",
                "hrdepartment_app:bpmemo_update", "hrdepartment_app:bpmemo_list"
            )

        if user.pk in person_distributor or user.is_superuser:
            add_notification(
                bpmemo_qs.filter(
                    location_selected=False,
                    document_not_agreed=True
                ).exclude(document__official_memo_type="3"),
                "bx bx-hotel", "Место проживания",
                "hrdepartment_app:bpmemo_update", "hrdepartment_app:bpmemo_list"
            )

        if user.pk in person_clerk or user.is_superuser:
            add_notification(
                bpmemo_qs.filter(
                    person_executor__user_work_profile__job__division_affiliation__pk=division_pk,
                    originals_received=False,
                    process_accepted=True
                ).exclude(document__official_memo_type="2"),
                "bx bx-notepad", "Оригиналы",
                "hrdepartment_app:bpmemo_update", "hrdepartment_app:bpmemo_list",
                color=color_by_job
            )

        if user.pk in person_hr or user.is_superuser:
            add_notification(
                bpmemo_qs.filter(
                    process_accepted=False,
                    location_selected=True
                ).exclude(document__official_memo_type="3"),
                "bx bx-user-pin", "Приказ",
                "hrdepartment_app:bpmemo_update", "hrdepartment_app:bpmemo_list",
                color=color_by_job
            )

            add_notification(
                bpmemo_qs.filter(
                    hr_accepted=False,
                    originals_received=True,
                    date_transfer_hr__isnull=False
                ).exclude(document__official_memo_type="2"),
                "bx bx-pencil", "Проверка",
                "hrdepartment_app:bpmemo_update", "hrdepartment_app:bpmemo_list",
                color=color_by_job
            )

        if user.pk in person_accounting or user.is_superuser:
            add_notification(
                bpmemo_qs.filter(
                    accepted_accounting=False,
                    hr_accepted=True
                ).exclude(document__official_memo_type="2"),
                "bx bx-check-shield", "Авансовый отчет",
                "hrdepartment_app:bpmemo_update", "hrdepartment_app:bpmemo_list"
            )

            add_notification(
                bpmemo_qs.filter(
                    document__expenses=False,
                    document__expenses_summ__gt=0,
                    process_accepted=True
                ),
                "bx bxs-bank text-danger", "Запрос аванса",
                "hrdepartment_app:expenses_list", "hrdepartment_app:expenses_list"
            )

        # ===== CTO =====
        team_qs = CreatingTeam.objects.exclude(cancellation=True)

        if user.pk in person_agreement_cto or user.is_superuser:
            add_notification(
                team_qs.filter(agreed=False),
                "fa fa-check text-primary", "Согласование приказа СБ",
                "hrdepartment_app:team_agreed", "hrdepartment_app:team_list"
            )

        if user.pk in person_hr_cto or user.is_superuser:
            add_notification(
                team_qs.filter(agreed=True)
                .filter(Q(number="") | Q(scan_file="")),
                "fa fa-book text-primary", "Регистрация приказа СБ",
                "hrdepartment_app:team_number", "hrdepartment_app:team_list"
            )

        if user.pk in person_clerk_cto or user.is_superuser:
            add_notification(
                team_qs.filter(agreed=True)
                .exclude(number="")
                .exclude(scan_file="")
                .filter(email_send=False),
                "fa fa-envelope text-primary", "Отправка письма приказа СБ",
                "hrdepartment_app:team", "hrdepartment_app:team_list"
            )

        return {"notifications": notifications}

    except Exception as ex:
        logger.error(ex)
        return {"notifications": []}
# скрипт до изменения
# def get_approval_oficial_memo_process(request):
#     notifications = []
#     if request.user.is_anonymous:
#         return {"notifications": []}
#
#     def add_notification(qs, icon, title, url_name, view_all_url, color="red", large=False):
#         """Упрощает добавление уведомлений."""
#         if not qs.exists():
#             return
#         if callable(color):
#             items = [(item, color(item)) for item in qs]
#         else:
#             items = [(item, color) for item in qs]
#         notifications.append({
#             "count": qs.count(),
#             "icon_class": icon,
#             "title": title,
#             "items": items,
#             "url_name": url_name,
#             "view_all_url": view_all_url,
#             "large": large
#         })
#
#     try:
#         user = request.user
#         job_pk = user.user_work_profile.job.pk
#         division_pk = user.user_work_profile.job.division_affiliation.pk
#         division_name = user.user_work_profile.job.division_affiliation.name
#
#         # ===== Сбор ролей =====
#         bp1 = BusinessProcessRoutes.objects.filter(business_process_type=1)
#         bp2 = BusinessProcessRoutes.objects.filter(business_process_type=2)
#
#         person_agreement = set(bp1.values_list("person_agreement__pk", flat=True))
#         person_clerk = set(bp1.values_list("person_clerk__pk", flat=True))
#         person_hr = set(bp1.values_list("person_hr__pk", flat=True))
#         person_agreement_cto = set(bp2.values_list("person_agreement__pk", flat=True))
#         person_clerk_cto = set(bp2.values_list("person_clerk__pk", flat=True))
#         person_hr_cto = set(bp2.values_list("person_hr__pk", flat=True))
#         person_distributor = set(bp1.values_list("person_sd__pk", flat=True))
#         person_accounting = set(bp1.values_list("person_accounting__pk", flat=True))
#
#         # person_distributor = set(DataBaseUser.objects.filter(
#         #     type_of_role=RoleType.NO,
#         #     user_work_profile__job__right_to_approval=True,
#         #     is_active=True
#         # ).values_list("pk", flat=True))
#         #
#         # person_accounting = set(DataBaseUser.objects.filter(
#         #     type_of_role=RoleType.ACCOUNTING,
#         #     user_work_profile__job__right_to_approval=True,
#         #     is_active=True
#         # ).values_list("pk", flat=True))
#
#         bpmemo_qs = ApprovalOficialMemoProcess.objects.exclude(cancellation=True)
#
#         # ===== Обычные БП =====
#         if user.pk in person_agreement or user.is_superuser:
#             add_notification(
#                 bpmemo_qs.filter(
#                     person_executor__user_work_profile__job__division_affiliation__name=division_name,
#                     document_not_agreed=False
#                 ),
#                 "bx bx-select-multiple", "Согласование",
#                 "hrdepartment_app:bpmemo_update", "hrdepartment_app:bpmemo_list"
#             )
#
#         if user.pk in person_distributor or user.is_superuser:
#             add_notification(
#                 bpmemo_qs.filter(location_selected=False, document_not_agreed=True)
#                 .exclude(document__official_memo_type="3"),
#                 "bx bx-hotel", "Место проживания",
#                 "hrdepartment_app:bpmemo_update", "hrdepartment_app:bpmemo_list"
#             )
#
#         if user.pk in person_clerk or user.is_superuser:
#             add_notification(
#                 bpmemo_qs.filter(
#                     person_executor__user_work_profile__job__division_affiliation__pk=division_pk,
#                     originals_received=False, process_accepted=True
#                 ).exclude(document__official_memo_type="2"),
#                 "bx bx-notepad", "Оригиналы",
#                 "hrdepartment_app:bpmemo_update", "hrdepartment_app:bpmemo_list",
#                 color=lambda i: "red" if i.document.person.user_work_profile.job.type_of_job == "1"
#                 else "green" if i.document.person.user_work_profile.job.type_of_job == "2"
#                 else "black"
#             )
#
#         if user.pk in person_hr or user.is_superuser:
#             add_notification(
#                 bpmemo_qs.filter(process_accepted=False, location_selected=True)
#                 .exclude(document__official_memo_type="3"),
#                 "bx bx-user-pin", "Приказ",
#                 "hrdepartment_app:bpmemo_update", "hrdepartment_app:bpmemo_list",
#                 color=lambda i: "red" if i.document.person.user_work_profile.job.type_of_job == "1"
#                 else "green" if i.document.person.user_work_profile.job.type_of_job == "2"
#                 else "black"
#             )
#             add_notification(
#                 bpmemo_qs.filter(
#                     hr_accepted=False, originals_received=True, date_transfer_hr__isnull=False
#                 ).exclude(document__official_memo_type="2"),
#                 "bx bx-pencil", "Проверка",
#                 "hrdepartment_app:bpmemo_update", "hrdepartment_app:bpmemo_list",
#                 color=lambda i: "red" if i.document.person.user_work_profile.job.type_of_job == "1"
#                 else "green" if i.document.person.user_work_profile.job.type_of_job == "2"
#                 else "black"
#             )
#
#         if user.pk in person_accounting or user.is_superuser:
#             add_notification(
#                 bpmemo_qs.filter(accepted_accounting=False, hr_accepted=True)
#                 .exclude(document__official_memo_type="2"),
#                 "bx bx-check-shield", "Авансовый отчет",
#                 "hrdepartment_app:bpmemo_update", "hrdepartment_app:bpmemo_list"
#             )
#             add_notification(
#                 bpmemo_qs.filter(
#                     document__expenses=False, document__expenses_summ__gt=0, process_accepted=True
#                 ),
#                 "bx bxs-bank text-danger", "Запрос аванса",
#                 "hrdepartment_app:expenses_list", "hrdepartment_app:expenses_list"
#             )
#
#         # ===== CTO =====
#         if user.pk in person_agreement_cto or user.is_superuser:
#             add_notification(
#                 CreatingTeam.objects.filter(agreed=False).exclude(cancellation=True),
#                 "fa fa-check text-primary", "Согласование приказа СБ",
#                 "hrdepartment_app:team_agreed", "hrdepartment_app:team_list"
#             )
#
#         if user.pk in person_hr_cto or user.is_superuser:
#             add_notification(
#                 CreatingTeam.objects.filter(agreed=True)
#                 .filter(Q(number="") | Q(scan_file=""))
#                 .exclude(cancellation=True),
#                 "fa fa-book text-primary", "Регистрация приказа СБ",
#                 "hrdepartment_app:team_number", "hrdepartment_app:team_list"
#             )
#
#         if user.pk in person_clerk_cto or user.is_superuser:
#             add_notification(
#                 CreatingTeam.objects.filter(agreed=True)
#                 .exclude(number="").exclude(scan_file="")
#                 .filter(email_send=False)
#                 .exclude(cancellation=True),
#                 "fa fa-envelope text-primary", "Отправка письма приказа СБ",
#                 "hrdepartment_app:team", "hrdepartment_app:team_list"
#             )
#         return {"notifications": notifications}
#
#     except Exception as ex:
#         logger.error(ex)
#         return {"notifications": []}


#
# def get_qrcode(request):
#     import qrcode
#
#     img = qrcode.make(request.build_absolute_uri())
#     try:
#         img.save(pathlib.Path.joinpath(MEDIA_ROOT, f"qr/{request.user.ref_key}.png"))
#         return {"qrcode": f"/media/qr/{request.user.ref_key}.png"}
#     except AttributeError:
#         return {}
