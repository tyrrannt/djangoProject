import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from django.db import models, transaction
from django.utils import timezone

from administration_app.utils import format_name_initials
from contracts_app.models import Estate
from customers_app.models import DataBaseUser, Division
from hrdepartment_app.models import PlaceProductionActivity


# Create your models here.
class NomenclatureUnit(models.Model):
    name = models.CharField(max_length=50, verbose_name="Название единицы измерения")
    short_name = models.CharField(max_length=10, verbose_name="Краткое название")

    def __str__(self):
        return f"{self.name} ({self.short_name})"

    class Meta:
        verbose_name = "Единица измерения"
        verbose_name_plural = "Единицы измерения"

class Grade(models.Model):
    name = models.CharField(max_length=100, verbose_name="Название градации")
    description = models.TextField(blank=True, verbose_name="Описание")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Класс годности"
        verbose_name_plural = "Классы годности"

class NomenclatureGroup(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название группы")
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, verbose_name="Родительская группа")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Группа"
        verbose_name_plural = "Группы"

class Nomenclature(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание")
    group = models.ForeignKey('NomenclatureGroup', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Группа")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Количество")
    unit = models.ForeignKey('NomenclatureUnit', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Единица измерения")

    # Дополнительные свойства
    serial_number = models.CharField(max_length=100, blank=True, verbose_name="Серийный номер")
    year_of_manufacture = models.DateField(null=True, blank=True, verbose_name="Год выпуска")
    weight = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Вес")
    dimensions = models.CharField(max_length=100, blank=True, verbose_name="Размеры")
    grade = models.ForeignKey('Grade', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Класс годности")

    # Связи с местом нахождения и имуществом
    location = models.ForeignKey(PlaceProductionActivity, on_delete=models.SET_NULL, null=True, blank=True,
                                 verbose_name="Место нахождения")
    estate = models.ForeignKey(Estate, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Имущество")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Номенклатура"
        verbose_name_plural = "Номенклатура"

class WayBill(models.Model):
    class Meta:
        verbose_name = "Транспортная накладная"
        verbose_name_plural = "Транспортные накладные"
        ordering = ["-date_of_creation"]

    STATES = (
        ("0", "Не обработана"),
        ("1", "Обработана"),
        ('2', "Отправлена"),
        ("3", "Принята"),
        ("4", "Отклонена"),
    )

    URGENCY_CHOICES = (
        ("0", "Не срочно"),
        ("1", "Срочно"),
        ("2", "Очень срочно"),
    )

    document_number = models.CharField(max_length=37, verbose_name="Номер документа", default=uuid.uuid4)
    document_date = models.DateField(verbose_name="Дата документа")
    place_of_departure = models.ForeignKey(PlaceProductionActivity, verbose_name="Куда",
                                           on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name="way_bill_place_of_departure")
    content = models.TextField(verbose_name="Содержание", default='')
    comment = models.CharField(verbose_name="Комментарий", default='', max_length=300)
    place_division = models.ForeignKey(Division, verbose_name="Подразделение", on_delete=models.SET_NULL,
                                       null=True, blank=True)
    sender = models.ForeignKey(DataBaseUser, max_length=100, verbose_name="Инициатор",
                               on_delete=models.SET_NULL, null=True, blank=True, related_name="way_bill_sender")
    state = models.CharField(max_length=100, verbose_name="Состояние", choices=STATES, default="0")
    responsible = models.ForeignKey(DataBaseUser, max_length=100, verbose_name="Получатель",
                                    on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="way_bill_responsible")
    date_of_creation = models.DateField(verbose_name="Дата и время создания",
                                        auto_now_add=True)  # При миграции указать 1 и вставить timezone.now()
    executor = models.ForeignKey(DataBaseUser, max_length=100, verbose_name="Исполнитель",
                                 on_delete=models.SET_NULL, null=True, blank=True, related_name="way_bill_executor")
    urgency = models.CharField(max_length=100, verbose_name="Срочность", choices=URGENCY_CHOICES, default="0")
    package_number = models.ForeignKey('Package', verbose_name="Посылка", on_delete=models.SET_NULL, null=True,
                                       blank=True)

    def __str__(self):
        return self.content

    def get_data(self):
        """
        Получает данные из экземпляра ReportCard.

        :return: словарь, содержащий следующие данные:
            - "pk": первичный ключ экземпляра ReportCard.
            - "employee": форматированные инициалы имени сотрудника.
            - "report_card_day": день табеля в формате "ДД.ММ.ГГГГ"
            - "start_time": время начала в формате "ЧЧ:ММ"
            - "end_time": время окончания в формате "ЧЧ:ММ"
            - "reason_adjustment": причина корректировки.
            - "record_type": отображение типа записи.
        """
        return {
            "pk": self.pk,
            "document_date": f"{self.document_date:%d.%m.%Y} г.",
            "place_of_departure": self.place_of_departure.name,
            "content": self.content,
            "comment": self.comment,
            "place_division": self.place_division.name,
            "sender": format_name_initials(self.sender.title),
            "state": self.get_state_display(),
            "responsible": format_name_initials(self.responsible.title),
            "date_of_creation": f"{self.date_of_creation:%d.%m.%Y} г.",
            "executor": format_name_initials(self.executor.title),
            "urgency": self.get_urgency_display(),
        }


class Package(models.Model):
    class Meta:
        verbose_name = 'Посылка'
        verbose_name_plural = 'Посылки'
        ordering = ["-date_of_dispatch"]

    TYPE_OF_SENDING = (
        ("0", "Логистическая компания"),
        ("1", "Водитель"),
        ("2", "Сотрудник"),
    )
    # При миграции указать 1 и вставить timezone.now()
    date_of_creation = models.DateField(verbose_name='Дата и время создания', auto_now_add=True)
    date_of_dispatch = models.DateField(verbose_name='Дата отправки', null=True, blank=True)
    place_of_dispatch = models.ForeignKey(PlaceProductionActivity, verbose_name='Точка назначения',
                                          on_delete=models.SET_NULL, null=True, blank=True)
    number_of_dispatch = models.CharField(verbose_name='Номер посылки', max_length=37, default='')
    executor = models.ForeignKey(DataBaseUser, max_length=100, verbose_name="Исполнитель",
                                 on_delete=models.SET_NULL, null=True, blank=True, related_name="dispatch_executor")
    type_of_dispatch = models.CharField(max_length=100, verbose_name="Тип отправки",
                                        choices=TYPE_OF_SENDING, default="0")

    def get_data(self):
        """
        Получает данные из экземпляра ReportCard.

        :return: словарь, содержащий следующие данные:
            - "pk": первичный ключ экземпляра ReportCard.
            - "employee": форматированные инициалы имени сотрудника.
            - "report_card_day": день табеля в формате "ДД.ММ.ГГГГ"
            - "start_time": время начала в формате "ЧЧ:ММ"
            - "end_time": время окончания в формате "ЧЧ:ММ"
            - "reason_adjustment": причина корректировки.
            - "record_type": отображение типа записи.
        """
        return {
            "pk": self.pk,
            "date_of_dispatch": f"{self.date_of_dispatch:%d.%m.%Y} г.",
            "number_of_dispatch": self.number_of_dispatch,
            "place_of_dispatch": self.place_of_dispatch.name,
            "executor": format_name_initials(self.executor.title) if self.executor else '',
            "type_of_dispatch": self.get_type_of_dispatch_display(),
        }


def image_directory_path(instance, filename):
    year = instance.date_of_creation
    return f"logist/PKG/{year.year}/{year.month}/{filename}"

class PackageImage(models.Model):
    class Meta:
        verbose_name = "Фотографию к посылке"
        verbose_name_plural = "Фотографии к посылкам"
        ordering = ["-date_of_creation"]
    date_of_creation = models.DateField(verbose_name='Дата и время создания', auto_now_add=True)
    image = models.ImageField(verbose_name='', upload_to=image_directory_path)
    caption = models.CharField(verbose_name='', max_length=200, default='')
    package = models.ForeignKey(Package, verbose_name='', on_delete=models.CASCADE)


# ==============================================================================
# ПОДСИСТЕМА ЭЛЕКТРОННОГО ДОКУМЕНТООБОРОТА (СЭД) И МАРШРУТИЗАЦИИ СОГЛАСОВАНИЯ
# ==============================================================================

def docflow_file_upload_to(instance: "DocFlowFileVersion", filename: str) -> str:
    """Генерирует структурированный относительный путь для сохранения файлов СЭД.

    Файлы организуются по структуре: `docflow/YYYY/MM/DD/<doc_uuid>/<filename>`,
    что обеспечивает масштабируемость файлового хранилища и исключает коллизии имен.

    Args:
        instance (DocFlowFileVersion): Экземпляр версии файла документа.
        filename (str): Исходное имя загружаемого файла.

    Returns:
        str: Относительный путь для сохранения файла в директории MEDIA_ROOT.
    """
    now = timezone.now()
    doc_id = "general"
    if instance.doc_file_id and instance.doc_file.document_id:
        doc_id = str(instance.doc_file.document_id)
    return f"docflow/{now.year}/{now.month:02d}/{now.day:02d}/{doc_id}/{filename}"


class DocFlowDocumentType(models.Model):
    """Справочник типов документов электронного документооборота (СЭД).

    Классифицирует входящие, исходящие и внутренние документы компании,
    определяет нормативный SLA согласования и правила маршрутизации.

    Attributes:
        name (CharField): Человекочитаемое название типа документа.
        category (CharField): Категория документооборота (INBOUND / OUTBOUND / INTERNAL).
        code (CharField): Уникальный мнемонический код типа (например, IN_STUDENT_CONTRACT).
        description (TextField): Подробное описание назначения и регламента.
        default_sla_hours (PositiveIntegerField): Нормативный срок согласования по умолчанию (в часах).
        is_active (BooleanField): Флаг доступности типа для создания документов.
        created_at (DateTimeField): Дата и время создания записи.
        updated_at (DateTimeField): Дата и время последнего обновления.
    """

    class Category(models.TextChoices):
        """Категории документооборота."""
        INBOUND = "INBOUND", "Входящий"
        OUTBOUND = "OUTBOUND", "Исходящий"
        INTERNAL = "INTERNAL", "Внутренний"

    name = models.CharField(max_length=255, verbose_name="Название типа документа")
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.INBOUND,
        verbose_name="Категория"
    )
    code = models.CharField(max_length=50, unique=True, verbose_name="Символьный код")
    description = models.TextField(blank=True, verbose_name="Описание и регламент")
    default_sla_hours = models.PositiveIntegerField(
        default=24,
        verbose_name="Срок согласования по умолчанию (в часах)"
    )
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Тип документа СЭД"
        verbose_name_plural = "Типы документов СЭД"
        ordering = ["category", "name"]

    def __str__(self) -> str:
        """Возвращает строковое представление типа документа."""
        return f"{self.get_category_display()}: {self.name}"


class DocFlowNumberCounter(models.Model):
    """Счетчик регистрационных номеров документов СЭД.

    Обеспечивает непрерывную и транзакционно-безопасную автонумерацию документов
    в разрезе года и категории потока (например, СЭД-ВХ-2026/00001, СЭД-ИС-2026/00001).

    Attributes:
        year (PositiveIntegerField): Календарный год регистрации (например, 2026).
        flow_type (CharField): Категория документооборота (INBOUND / OUTBOUND / INTERNAL).
        last_number (PositiveIntegerField): Последний выданный порядковый номер в году.
    """

    year = models.PositiveIntegerField(verbose_name="Год")
    flow_type = models.CharField(
        max_length=20,
        choices=DocFlowDocumentType.Category.choices,
        verbose_name="Тип документооборота"
    )
    last_number = models.PositiveIntegerField(default=0, verbose_name="Последний выданный номер")

    class Meta:
        verbose_name = "Счетчик номеров СЭД"
        verbose_name_plural = "Счетчики номеров СЭД"
        constraints = [
            models.UniqueConstraint(
                fields=["year", "flow_type"],
                name="unique_docflow_counter_year_flow"
            )
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление счетчика номеров."""
        return f"Счетчик {self.flow_type} ({self.year}) — {self.last_number}"

    @classmethod
    def generate_number(cls, flow_type: str, year: Optional[int] = None) -> str:
        """Генерирует следующий уникальный регистрационный номер документа СЭД.

        Формирует номер вида `СЭД-ВХ-YYYY/XXXXX` (для входящих), `СЭД-ИС-YYYY/XXXXX`
        (для исходящих) и `СЭД-ВН-YYYY/XXXXX` (для внутренних) с 5-значным счетчиком.
        Обеспечивает потокобезопасность и защиту от гонок (Race Conditions)
        с помощью `select_for_update()` и `transaction.atomic()`.

        Args:
            flow_type (str): Категория документооборота (INBOUND, OUTBOUND, INTERNAL).
            year (Optional[int]): Календарный год регистрации (по умолчанию текущий год).

        Returns:
            str: Сгенерированный официальный регистрационный номер (например, 'СЭД-ВХ-2026/00001').
        """
        if year is None:
            year = timezone.now().year

        prefix_map = {
            DocFlowDocumentType.Category.INBOUND: "СЭД-ВХ",
            DocFlowDocumentType.Category.OUTBOUND: "СЭД-ИС",
            DocFlowDocumentType.Category.INTERNAL: "СЭД-ВН",
        }
        prefix = prefix_map.get(flow_type, f"СЭД-{flow_type}")

        with transaction.atomic():
            counter, _ = cls.objects.select_for_update().get_or_create(
                year=year,
                flow_type=flow_type,
                defaults={"last_number": 0}
            )
            counter.last_number += 1
            counter.save(update_fields=["last_number"])
            return f"{prefix}-{year}/{counter.last_number:05d}"


class DocFlowDocument(models.Model):
    """Учетная карточка документа электронного документооборота (СЭД).

    Центральная сущность подсистемы СЭД, объединяющая метаданные документа,
    прикрепленные файлы, маршрут визирования, аудиторский след и связи
    со смежными подсистемами предприятия (контрагенты, договоры, накладные, грузы).

    Attributes:
        id (UUIDField): Первичный ключ (UUIDv4) для защищенных ссылок и верификации.
        reg_number (CharField): Официальный регистрационный номер (например, СЭД-ВХ-2026/00012).
        reg_date (DateField): Дата официальной регистрации документа.
        doc_type (ForeignKey): Тип документа из справочника DocFlowDocumentType.
        title (CharField): Краткое наименование / тема документа.
        description (TextField): Развернутое содержание или сопроводительный текст.
        status (CharField): Текущий статус жизненного цикла документа.
        flow_type (CharField): Категория потока (Входящий / Исходящий / Внутренний).
        urgency (CharField): Приоритет срочности рассмотрения.
        initiator (ForeignKey): Автор / Инициатор карточки документа (DataBaseUser).
        responsible (ForeignKey): Ответственный сотрудник за документ (DataBaseUser).
        counteragent (ForeignKey): Связанный контрагент из customers_app.Counteragent.
        counteragent_contact_email (EmailField): Контактный email для уведомлений.
        current_step_order (PositiveIntegerField): Порядковый номер активного шага маршрута.
        deadline (DateTimeField): Плановый предельный срок завершения согласования.
        created_at (DateTimeField): Дата и время создания карточки.
        updated_at (DateTimeField): Дата и время последнего изменения.
        related_waybill (ForeignKey): Связанная накладная WayBill.
        related_package (ForeignKey): Связанная посылка Package.
        related_contract (ForeignKey): Связанный договор contracts_app.Contract.
    """

    class Status(models.TextChoices):
        """Статусы жизненного цикла документа СЭД."""
        DRAFT = "DRAFT", "Черновик"
        ON_REGISTRATION = "ON_REGISTRATION", "На первичной регистрации"
        ON_APPROVAL = "ON_APPROVAL", "На согласовании"
        ON_REWORK = "ON_REWORK", "На доработке"
        APPROVED = "APPROVED", "Согласован / Принят"
        SIGNED = "SIGNED", "Подписан сторонами"
        EXECUTED = "EXECUTED", "Исполнен"
        REJECTED = "REJECTED", "Отклонен"
        ARCHIVED = "ARCHIVED", "В архиве"

    class Urgency(models.TextChoices):
        """Срочность рассмотрения документа."""
        NORMAL = "NORMAL", "Обычная"
        URGENT = "URGENT", "Срочно"
        CRITICAL = "CRITICAL", "Критически срочно"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="Идентификатор UUID"
    )
    reg_number = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        verbose_name="Регистрационный номер"
    )
    reg_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата регистрации"
    )
    doc_type = models.ForeignKey(
        DocFlowDocumentType,
        on_delete=models.PROTECT,
        related_name="documents",
        verbose_name="Тип документа"
    )
    title = models.CharField(max_length=500, verbose_name="Краткое наименование / тема")
    description = models.TextField(blank=True, verbose_name="Содержание / описание")
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name="Статус"
    )
    flow_type = models.CharField(
        max_length=20,
        choices=DocFlowDocumentType.Category.choices,
        default=DocFlowDocumentType.Category.INBOUND,
        verbose_name="Поток / Категория"
    )
    urgency = models.CharField(
        max_length=20,
        choices=Urgency.choices,
        default=Urgency.NORMAL,
        verbose_name="Срочность"
    )
    initiator = models.ForeignKey(
        DataBaseUser,
        on_delete=models.PROTECT,
        related_name="docflow_initiated_docs",
        verbose_name="Инициатор (Автор)"
    )
    responsible = models.ForeignKey(
        DataBaseUser,
        on_delete=models.PROTECT,
        related_name="docflow_responsible_docs",
        null=True,
        blank=True,
        verbose_name="Ответственный сотрудник"
    )
    counteragent = models.ForeignKey(
        'customers_app.Counteragent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docflow_documents",
        verbose_name="Контрагент"
    )
    counteragent_contact_email = models.EmailField(
        blank=True,
        verbose_name="Email контрагента для уведомлений"
    )
    current_step_order = models.PositiveIntegerField(
        default=1,
        verbose_name="Порядок текущего этапа"
    )
    deadline = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Плановый срок (дедлайн)"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата и время создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата и время изменения")

    # Связи со смежными сущностями
    related_waybill = models.ForeignKey(
        'logistics_app.WayBill',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docflow_documents",
        verbose_name="Связанная накладная"
    )
    related_package = models.ForeignKey(
        'logistics_app.Package',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docflow_documents",
        verbose_name="Связанная посылка"
    )
    related_contract = models.ForeignKey(
        'contracts_app.Contract',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docflow_documents",
        verbose_name="Связанный договор"
    )

    class Meta:
        verbose_name = "Документ СЭД"
        verbose_name_plural = "Документы СЭД"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "flow_type"], name="idx_docflow_status_flow"),
            models.Index(fields=["initiator", "status"], name="idx_docflow_init_status"),
            models.Index(fields=["responsible", "status"], name="idx_docflow_resp_status"),
            models.Index(fields=["reg_date", "status"], name="idx_docflow_date_status"),
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление документа с номером и названием."""
        num = self.reg_number or f"UUID:{str(self.id)[:8]}"
        return f"{num} — {self.title}"

    @property
    def is_draft(self) -> bool:
        """Возвращает True, если документ находится в статусе черновика."""
        return self.status == self.Status.DRAFT

    @property
    def is_on_approval(self) -> bool:
        """Возвращает True, если документ находится в процессе согласования."""
        return self.status == self.Status.ON_APPROVAL

    @property
    def is_approved(self) -> bool:
        """Возвращает True, если документ полностью согласован / принят."""
        return self.status in [self.Status.APPROVED, self.Status.SIGNED, self.Status.EXECUTED]

    @property
    def is_on_rework(self) -> bool:
        """Возвращает True, если документ возвращен на доработку."""
        return self.status == self.Status.ON_REWORK

    @property
    def main_file(self) -> Optional["DocFlowFile"]:
        """Возвращает основной прикрепленный файл документа."""
        return self.files.filter(is_main=True).first() or self.files.first()

    @property
    def active_steps(self):
        """Возвращает QuerySet активных шагов маршрута в статусе IN_PROGRESS."""
        return self.route_steps.filter(status="IN_PROGRESS")

    def assign_registration_number(self, save: bool = True) -> str:
        """Присваивает официальный регистрационный номер документу СЭД.

        Если номер уже существует, возвращает его без изменений. В противном случае
        обращается к транзакционному счетчику DocFlowNumberCounter для получения
        следующего уникального номера текущего года.

        Args:
            save (bool): Сохранять ли изменения в базе данных немедленно. Defaults to True.

        Returns:
            str: Официальный регистрационный номер документа.
        """
        if not self.reg_number:
            year = self.reg_date.year if self.reg_date else timezone.now().year
            if not self.reg_date:
                self.reg_date = timezone.now().date()
            if self.doc_type_id and not self.flow_type:
                self.flow_type = self.doc_type.category
            self.reg_number = DocFlowNumberCounter.generate_number(self.flow_type, year=year)
            if save and self.pk:
                self.save(update_fields=["reg_number", "reg_date", "flow_type", "updated_at"])
        return self.reg_number

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Переопределенный метод сохранения карточки документа СЭД.

        Синхронизирует категорию flow_type с типом документа doc_type при создании.

        Args:
            *args (Any): Позиционные аргументы сохранения Django ORM.
            **kwargs (Any): Именованные аргументы сохранения Django ORM.
        """
        if self.doc_type_id and not self.flow_type:
            self.flow_type = self.doc_type.category
        super().save(*args, **kwargs)


class DocFlowFile(models.Model):
    """Учетная запись файла, прикрепленного к документу СЭД.

    Служит контейнером для версий конкретного документа (например, основного проекта договора,
    технического задания, сметы или приложений).

    Attributes:
        document (ForeignKey): Карточка документа DocFlowDocument.
        title (CharField): Наименование документа/файла.
        is_main (BooleanField): Флаг основного файла документа.
        current_version_number (CharField): Номер актуальной версии.
        created_at (DateTimeField): Дата добавления.
    """

    document = models.ForeignKey(
        DocFlowDocument,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Документ СЭД"
    )
    title = models.CharField(max_length=255, verbose_name="Название документа / файла")
    is_main = models.BooleanField(default=True, verbose_name="Основной файл документа")
    current_version_number = models.CharField(
        max_length=20,
        default="1.0",
        verbose_name="Текущая версия"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата добавления")

    class Meta:
        verbose_name = "Файл документа СЭД"
        verbose_name_plural = "Файлы документов СЭД"
        ordering = ["-is_main", "title"]

    def __str__(self) -> str:
        """Возвращает строковое представление файла."""
        return f"{self.title} (v{self.current_version_number})"

    @property
    def latest_version(self) -> Optional["DocFlowFileVersion"]:
        """Возвращает последнюю загруженную версию файла."""
        return self.versions.order_by("-uploaded_at").first()


class DocFlowFileVersion(models.Model):
    """Конкретная физическая версия файла документа СЭД.

    Обеспечивает неизменяемость истории правок, фиксирует автора загрузки,
    время, контрольную сумму SHA-256 и признаки рецензирования согласующим.

    Attributes:
        doc_file (ForeignKey): Связанный файл DocFlowFile.
        version_number (CharField): Номер редакции (например, '1.0', '1.1', '2.0').
        file (FileField): Физический файл в хранилище MEDIA_ROOT.
        file_size (PositiveBigIntegerField): Размер файла в байтах.
        file_hash (CharField): Контрольный хэш SHA-256 для защиты от подделки.
        uploaded_by (ForeignKey): Сотрудник, загрузивший версию (DataBaseUser).
        change_comment (TextField): Комментарий автора или согласующего к версии.
        is_reviewer_edit (BooleanField): Флаг загрузки версии согласующим лицом.
        uploaded_at (DateTimeField): Точная временная метка загрузки.
    """

    doc_file = models.ForeignKey(
        DocFlowFile,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name="Файл документа"
    )
    version_number = models.CharField(
        max_length=20,
        verbose_name="Номер версии (например, 1.0, 1.1)"
    )
    file = models.FileField(
        upload_to=docflow_file_upload_to,
        verbose_name="Физический файл"
    )
    file_size = models.PositiveBigIntegerField(
        default=0,
        verbose_name="Размер файла (байт)"
    )
    file_hash = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="Контрольная сумма SHA-256"
    )
    uploaded_by = models.ForeignKey(
        DataBaseUser,
        on_delete=models.PROTECT,
        related_name="docflow_uploaded_versions",
        verbose_name="Кем загружен"
    )
    change_comment = models.TextField(
        blank=True,
        verbose_name="Комментарий к версии / замечания"
    )
    is_reviewer_edit = models.BooleanField(
        default=False,
        verbose_name="Правка согласующего лица"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата и время загрузки")

    class Meta:
        verbose_name = "Версия файла СЭД"
        verbose_name_plural = "Версии файлов СЭД"
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        """Возвращает строковое представление версии файла."""
        return f"{self.doc_file.title} v{self.version_number} ({self.uploaded_by})"

    @property
    def file_hash_sha256(self) -> str:
        """Возвращает контрольную сумму SHA-256 (псевдоним для обратной совместимости)."""
        return self.file_hash

    @property
    def comment(self) -> str:
        """Возвращает комментарий к версии файла (псевдоним для обратной совместимости)."""
        return self.change_comment

    @property
    def file_size_formatted(self) -> str:
        """Возвращает форматированный размер файла с единицей измерения (Б, КБ, МБ).

        Returns:
            str: Человекочитаемая строка размера файла (напр. '250.5 КБ', '12.40 МБ').
        """
        size = self.file_size or 0
        if size < 1024:
            return f"{size} Б"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} КБ"
        else:
            return f"{size / (1024 * 1024):.2f} МБ"


class DocFlowRouteTemplate(models.Model):
    """Шаблон маршрута согласования СЭД.

    Определяет типовую цепочку этапов визирования для конкретного типа документа.

    Attributes:
        name (CharField): Название шаблона (например, «Типовой маршрут ученического договора»).
        doc_type (ForeignKey): Тип документа, к которому привязан шаблон.
        is_default (BooleanField): Использовать ли шаблон по умолчанию для данного типа.
        description (TextField): Пояснение логики и участников маршрута.
        created_at (DateTimeField): Дата создания шаблона.
    """

    name = models.CharField(max_length=255, verbose_name="Наименование шаблона")
    doc_type = models.ForeignKey(
        DocFlowDocumentType,
        on_delete=models.CASCADE,
        related_name="route_templates",
        verbose_name="Тип документа"
    )
    is_default = models.BooleanField(
        default=True,
        verbose_name="Использовать по умолчанию для типа"
    )
    description = models.TextField(blank=True, verbose_name="Описание маршрута")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Шаблон маршрута СЭД"
        verbose_name_plural = "Шаблоны маршрутов СЭД"
        ordering = ["doc_type", "name"]

    def __str__(self) -> str:
        """Возвращает строковое представление шаблона."""
        return f"{self.doc_type.name}: {self.name}"


class DocFlowRouteStepTemplate(models.Model):
    """Шаг шаблона маршрута согласования СЭД.

    Определяет исполнителей этапа (пользователь, подразделение или группа),
    тип согласования (последовательное, параллельное «И» / «ИЛИ») и нормативный SLA.

    Attributes:
        route_template (ForeignKey): Шаблон маршрута DocFlowRouteTemplate.
        step_order (PositiveIntegerField): Порядковый номер этапа в цепочке (1, 2, 3...).
        step_name (CharField): Название этапа (например, «Визирование Юротделом»).
        step_type (CharField): Тип выполнения шага (SEQUENTIAL, PARALLEL_AND, PARALLEL_OR, HEAD_OF_DEPARTMENT).
        assigned_division (ForeignKey): Назначенное подразделение.
        assigned_user (ForeignKey): Персонально назначенный сотрудник.
        assigned_users (ManyToManyField): Группа сотрудников для параллельного согласования.
        sla_hours (PositiveIntegerField): Нормативный срок на рассмотрение в часах.
        allow_reviewer_file_edit (BooleanField): Разрешить ли согласующему прикреплять файл с правками.
        can_rollback_to (BooleanField): Разрешить ли целевой откат на этот шаг.
    """

    class StepType(models.TextChoices):
        """Типы шагов маршрута согласования."""
        SEQUENTIAL = "SEQUENTIAL", "Последовательный (Один сотрудник)"
        PARALLEL_AND = "PARALLEL_AND", "Параллельный «И» (Все должны согласовать)"
        PARALLEL_OR = "PARALLEL_OR", "Параллельный «ИЛИ» (Любой из группы)"
        HEAD_OF_DEPARTMENT = "HEAD_OF_DEPARTMENT", "Руководитель подразделения автора"

    route_template = models.ForeignKey(
        DocFlowRouteTemplate,
        on_delete=models.CASCADE,
        related_name="steps",
        verbose_name="Шаблон маршрута"
    )
    step_order = models.PositiveIntegerField(default=1, verbose_name="Порядковый номер этапа")
    step_name = models.CharField(max_length=255, verbose_name="Название этапа")
    step_type = models.CharField(
        max_length=25,
        choices=StepType.choices,
        default=StepType.SEQUENTIAL,
        verbose_name="Тип этапа"
    )
    assigned_division = models.ForeignKey(
        Division,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docflow_step_templates",
        verbose_name="Назначенное подразделение"
    )
    assigned_user = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docflow_user_step_templates",
        verbose_name="Назначенный сотрудник"
    )
    assigned_users = models.ManyToManyField(
        DataBaseUser,
        blank=True,
        related_name="docflow_parallel_step_templates",
        verbose_name="Группа согласующих сотрудников"
    )
    sla_hours = models.PositiveIntegerField(
        default=24,
        verbose_name="Срок на рассмотрение (в часах)"
    )
    allow_reviewer_file_edit = models.BooleanField(
        default=True,
        verbose_name="Разрешить согласующему загружать файл с правками"
    )
    can_rollback_to = models.BooleanField(
        default=True,
        verbose_name="Разрешить откат на данный шаг"
    )

    class Meta:
        verbose_name = "Шаг шаблона маршрута СЭД"
        verbose_name_plural = "Шаги шаблонов маршрутов СЭД"
        ordering = ["route_template", "step_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["route_template", "step_order"],
                name="unique_template_step_order"
            )
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление шага шаблона."""
        return f"Шаг {self.step_order}: {self.step_name} ({self.get_step_type_display()})"


class DocFlowRouteStep(models.Model):
    """Экземпляр этапа маршрута согласования конкретного документа СЭД.

    Хранит состояние согласования этапа, назначенных участников, отметки о завершении
    и контроль сроков SLA.

    Attributes:
        document (ForeignKey): Карточка документа DocFlowDocument.
        step_order (PositiveIntegerField): Порядковый номер этапа в цепочке.
        step_name (CharField): Название этапа.
        step_type (CharField): Тип выполнения шага.
        assigned_division (ForeignKey): Назначенное подразделение.
        assigned_user (ForeignKey): Назначенный сотрудник.
        assigned_users (ManyToManyField): Группа назначенных согласующих.
        approved_users (ManyToManyField): Сотрудники, фактически согласовавшие данный шаг.
        status (CharField): Текущий статус этапа (PENDING, IN_PROGRESS, APPROVED, RETURNED, REJECTED, SKIPPED).
        started_at (DateTimeField): Время поступления документа на этап.
        completed_at (DateTimeField): Время завершения этапа.
        due_date (DateTimeField): Расчетный предельный дедлайн этапа по SLA.
        sla_hours (PositiveIntegerField): Нормативный срок на рассмотрение в часах.
        can_rollback_to (BooleanField): Доступен ли данный шаг для целевого отката.
        allow_reviewer_file_edit (BooleanField): Разрешена ли загрузка правок согласующими.
    """

    class Status(models.TextChoices):
        """Статусы этапа согласования."""
        PENDING = "PENDING", "Ожидает очереди"
        IN_PROGRESS = "IN_PROGRESS", "В процессе согласования"
        APPROVED = "APPROVED", "Согласован"
        RETURNED = "RETURNED", "Возвращен на доработку / Шаг отката"
        REJECTED = "REJECTED", "Отклонен"
        SKIPPED = "SKIPPED", "Пропущен"

    document = models.ForeignKey(
        DocFlowDocument,
        on_delete=models.CASCADE,
        related_name="route_steps",
        verbose_name="Документ СЭД"
    )
    step_order = models.PositiveIntegerField(default=1, verbose_name="Порядковый номер этапа")
    step_name = models.CharField(max_length=255, verbose_name="Название этапа")
    step_type = models.CharField(
        max_length=25,
        choices=DocFlowRouteStepTemplate.StepType.choices,
        default=DocFlowRouteStepTemplate.StepType.SEQUENTIAL,
        verbose_name="Тип этапа"
    )
    assigned_division = models.ForeignKey(
        Division,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docflow_route_steps",
        verbose_name="Назначенное подразделение"
    )
    assigned_user = models.ForeignKey(
        DataBaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="docflow_route_user_steps",
        verbose_name="Назначенный сотрудник"
    )
    assigned_users = models.ManyToManyField(
        DataBaseUser,
        blank=True,
        related_name="docflow_route_parallel_steps",
        verbose_name="Назначенные согласующие (группа)"
    )
    approved_users = models.ManyToManyField(
        DataBaseUser,
        blank=True,
        related_name="docflow_step_approved_by",
        verbose_name="Сотрудники, фактически согласовавшие шаг"
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Статус шага"
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время поступления на этап"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время завершения этапа"
    )
    due_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дедлайн этапа"
    )
    sla_hours = models.PositiveIntegerField(
        default=24,
        verbose_name="Нормативный срок SLA (в часах)"
    )
    can_rollback_to = models.BooleanField(
        default=True,
        verbose_name="Доступен ли шаг для целевого отката"
    )
    allow_reviewer_file_edit = models.BooleanField(
        default=True,
        verbose_name="Разрешить согласующему загружать файл с правками"
    )

    class Meta:
        verbose_name = "Шаг маршрута согласования СЭД"
        verbose_name_plural = "Шаги маршрутов согласования СЭД"
        ordering = ["document", "step_order"]
        indexes = [
            models.Index(fields=["document", "status", "step_order"], name="idx_docstep_doc_stat_order"),
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление этапа маршрута."""
        return f"{self.document.reg_number or 'Документ'} — Шаг {self.step_order}: {self.step_name} [{self.get_status_display()}]"

    @property
    def is_active(self) -> bool:
        """Возвращает True, если данный шаг сейчас активен."""
        return self.status == self.Status.IN_PROGRESS


class DocFlowApprovalLog(models.Model):
    """Журнал аудита, визирования и юридически значимых действий в СЭД.

    Неизменяемый журнал (Audit Trail), фиксирующий наложение виз ПЭП,
    возвраты на доработку, откаты на шаги, загрузку версий и комментарии.

    Attributes:
        document (ForeignKey): Карточка документа DocFlowDocument.
        route_step (ForeignKey): Связанный шаг маршрута DocFlowRouteStep.
        user (ForeignKey): Сотрудник, совершивший действие (DataBaseUser).
        action (CharField): Тип выполненного действия.
        target_step_order (PositiveIntegerField): Номер целевого шага при откате.
        comment (TextField): Текстовая резолюция, замечания или комментарий.
        created_at (DateTimeField): Точная временная метка совершения действия.
        ip_address (GenericIPAddressField): IP-адрес клиентского устройства.
        user_agent (CharField): Браузер / клиентское приложение пользователя.
        pep_signature_hash (CharField): Цифровой криптографический слепок ПЭП (SHA-256).
        pep_certificate_id (CharField): Уникальный номер сертификата ПЭП.
    """

    class Action(models.TextChoices):
        """Типы действий в журнале аудита СЭД."""
        REGISTERED = "REGISTERED", "Документ зарегистрирован"
        STARTED = "STARTED", "Маршрут согласования запущен"
        APPROVED = "APPROVED", "Согласовано (Виза наложена)"
        APPROVED_WITH_COMMENTS = "APPROVED_WITH_COMMENTS", "Согласовано с замечаниями / правками"
        RETURNED_TO_AUTHOR = "RETURNED_TO_AUTHOR", "Возвращено автору на доработку"
        ROLLBACK_TO_STEP = "ROLLBACK_TO_STEP", "Откат на предыдущий шаг"
        REJECTED = "REJECTED", "Документ отклонен"
        DELEGATED = "DELEGATED", "Шаг делегирован другому сотруднику"
        RESTARTED = "RESTARTED", "Маршрут возобновлен / перезапущен"
        NEW_VERSION_UPLOADED = "NEW_VERSION_UPLOADED", "Загружена новая версия файла"
        COMMENTED = "COMMENTED", "Добавлен комментарий"

    document = models.ForeignKey(
        DocFlowDocument,
        on_delete=models.CASCADE,
        related_name="approval_logs",
        verbose_name="Документ СЭД"
    )
    route_step = models.ForeignKey(
        DocFlowRouteStep,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
        verbose_name="Связанный шаг маршрута"
    )
    user = models.ForeignKey(
        DataBaseUser,
        on_delete=models.PROTECT,
        related_name="docflow_action_logs",
        verbose_name="Сотрудник (автор действия)"
    )
    action = models.CharField(
        max_length=35,
        choices=Action.choices,
        verbose_name="Действие"
    )
    target_step_order = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Целевой шаг при откате"
    )
    comment = models.TextField(
        blank=True,
        verbose_name="Резолюция / Замечания / Особое мнение"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Время совершения действия"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="IP-адрес пользователя"
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Клиентское приложение (User Agent)"
    )
    pep_signature_hash = models.CharField(
        max_length=128,
        blank=True,
        verbose_name="Цифровой хэш ПЭП (SHA-256)"
    )
    pep_certificate_id = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="Идентификатор сертификата ПЭП"
    )

    class Meta:
        verbose_name = "Запись аудита и визирования СЭД"
        verbose_name_plural = "Журнал аудита и визирования СЭД"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["document", "created_at"], name="idx_doclog_doc_created"),
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление записи аудита."""
        return f"{self.created_at:%d.%m.%Y %H:%M} — {self.user}: {self.get_action_display()}"


class DocFlowComment(models.Model):
    """Комментарий и внутреннее обсуждение в карточке документа СЭД.

    Позволяет участникам маршрута вести рабочее обсуждение документа,
    прикреплять замечания и отвечать на комментарии коллег.

    Attributes:
        document (ForeignKey): Карточка документа DocFlowDocument.
        author (ForeignKey): Автор комментария (DataBaseUser).
        text (TextField): Текст сообщения.
        parent (ForeignKey): Родительский комментарий (для древовидных ответов).
        created_at (DateTimeField): Дата и время отправки комментария.
    """

    document = models.ForeignKey(
        DocFlowDocument,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name="Документ СЭД"
    )
    author = models.ForeignKey(
        DataBaseUser,
        on_delete=models.PROTECT,
        related_name="docflow_comments",
        verbose_name="Автор комментария"
    )
    text = models.TextField(verbose_name="Текст сообщения / обсуждения")
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
        verbose_name="Родительский комментарий"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата и время отправки")

    class Meta:
        verbose_name = "Комментарий к документу СЭД"
        verbose_name_plural = "Комментарии к документам СЭД"
        ordering = ["created_at"]

    def __str__(self) -> str:
        """Возвращает строковое представление комментария."""
        return f"Комментарий {self.author} ({self.created_at:%d.%m.%Y %H:%M})"


