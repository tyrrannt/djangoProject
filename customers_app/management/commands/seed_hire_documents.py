# -*- coding: utf-8 -*-
"""Management-команда наполнения справочника типов документов при приёме и подписантов."""

from django.core.management.base import BaseCommand

from customers_app.models import ConsentType, DataBaseUser, DocumentSigner

DEFAULT_CONSENT_TYPES = [
    {
        "code": "biometric",
        "name": "Согласие на обработку биометрических данных",
        "number_prefix": "БС",
        "requires_signer": False,
        "is_required_on_hire": True,
        "sort_order": 10,
        "description": "Согласие сотрудника на обработку биометрических персональных данных.",
    },
    {
        "code": "personal_data",
        "name": "Согласие на обработку персональных данных",
        "number_prefix": "ПД",
        "requires_signer": False,
        "is_required_on_hire": True,
        "sort_order": 20,
        "description": "Согласие работника на обработку персональных данных (152-ФЗ).",
    },
    {
        "code": "nda_ki",
        "name": "Соглашение о неразглашении конфиденциальной информации",
        "number_prefix": "СКИ",
        "requires_signer": True,
        "is_required_on_hire": True,
        "sort_order": 30,
        "description": "Соглашение о неразглашении конфиденциальной информации (подписывается Генеральным директором или Первым заместителем генерального директора-исполнительный директор).",
    },
    {
        "code": "commercial_secret",
        "name": "Обязательство о неразглашении коммерческой тайны",
        "number_prefix": "ОКТ",
        "requires_signer": False,
        "is_required_on_hire": True,
        "sort_order": 40,
        "description": "Обязательство работника о неразглашении сведений, составляющих коммерческую тайну.",
    },
    {
        "code": "military_duty",
        "name": "Обязанности граждан по воинскому учёту",
        "number_prefix": "ВУ",
        "requires_signer": False,
        "is_required_on_hire": True,
        "sort_order": 50,
        "description": "Памятка-расписка об ознакомлении с обязанностями граждан по воинскому учёту.",
    },
    {
        "code": "material_liability",
        "name": "Договор о полной индивидуальной материальной ответственности",
        "number_prefix": "ДМО",
        "requires_signer": True,
        "is_required_on_hire": True,
        "sort_order": 60,
        "description": "Договор о полной индивидуальной материальной ответственности (подписывается Генеральным директором или Первым заместителем генерального директора-исполнительный директор).",
    },
]

DEFAULT_SIGNERS = [
    {
        "short_name": "В.С. Бархотов",
        "last_name_lookup": "Бархотов",
        "full_name_genitive": "Бархотова Виктора Сергеевича",
        "position_genitive": "генерального директора",
        "acts_by_charter": True,
        "is_default": True,
        "sort_order": 10,
    },
    {
        "short_name": "Д.А. Шмаков",
        "last_name_lookup": "Шмаков",
        "full_name_genitive": "Шмакова Дмитрия Александровича",
        "position_genitive": "первого заместителя генерального директора-исполнительного директора",
        "acts_by_charter": False,
        "is_default": False,
        "sort_order": 20,
    },
]


class Command(BaseCommand):
    """Заполняет базовые типы документов при приёме на работу и подписантов."""

    help = "Создаёт или обновляет 6 типов документов при приёме на работу и 2 подписантов (директор и первый заместитель)."

    def handle(self, *args, **options) -> None:
        """Выполняет идемпотентный сидинг типов документов и подписантов."""
        created_types = 0
        for item in DEFAULT_CONSENT_TYPES:
            obj, created = ConsentType.objects.update_or_create(
                code=item["code"],
                defaults={
                    "name": item["name"],
                    "number_prefix": item["number_prefix"],
                    "requires_signer": item["requires_signer"],
                    "is_required_on_hire": item["is_required_on_hire"],
                    "sort_order": item["sort_order"],
                    "description": item["description"],
                    "is_active": True,
                },
            )
            if created:
                created_types += 1

        created_signers = 0
        for s in DEFAULT_SIGNERS:
            emp = DataBaseUser.objects.filter(last_name__iexact=s["last_name_lookup"], is_active=True).first()
            obj, created = DocumentSigner.objects.update_or_create(
                short_name=s["short_name"],
                defaults={
                    "employee": emp,
                    "full_name_genitive": s["full_name_genitive"],
                    "position_genitive": s["position_genitive"],
                    "acts_by_charter": s["acts_by_charter"],
                    "is_default": s["is_default"],
                    "sort_order": s["sort_order"],
                    "is_active": True,
                },
            )
            if created:
                created_signers += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: типов документов создано {created_types} (всего {ConsentType.objects.count()}), "
                f"подписантов создано {created_signers} (всего {DocumentSigner.objects.count()})."
            )
        )
