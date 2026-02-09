import datetime
import pathlib
import uuid

from django.apps import apps
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models import ForeignKey
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse, reverse_lazy
from django_ckeditor_5.fields import CKEditor5Field

from contracts_app.templatetags.custom import empty_item
from djangoProject.settings import BASE_DIR
from django.contrib.auth.models import Group, Permission


class Groups(Group):
    class Meta:
        verbose_name = "Группа"
        verbose_name_plural = "Группы"

    def get_data(self):
        permissions = [str(item.name) for item in self.permissions.iterator()]
        for item in self.permissions.iterator():
            print(item.codename, item.content_type.name)
        return {
            "pk": self.pk,
            "name": self.name,
            "permissions": "; ".join(permissions),
        }


class ViewDocumentsPhysical(models.Model):
    class Meta:
        verbose_name = "Вид документа физического лица"
        verbose_name_plural = "Виды документов физических лиц"

    ref_key = models.CharField(
        verbose_name="Уникальный номер", max_length=37, default=""
    )
    codeMVD = models.CharField(verbose_name="Код МВД", max_length=5, default="")
    codePFR = models.CharField(verbose_name="Код ПФР", max_length=5, default="")
    name = models.TextField(verbose_name="Наименование")


class AccessLevel(models.Model):
    """
    Представляет уровень доступа в системе.

    Attributes:
        level (int): Уровень доступа.
        name (str): Имя уровня доступа.
        description (str): Описание уровня доступа.

    Meta:
        verbose_name (str): Имя уровня доступа в единственном числе.
        verbose_name_plural (str): Имя уровня доступа во множественном числе.
    """

    class Meta:
        verbose_name = "Уровень доступа"
        verbose_name_plural = "Уровни доступа"

    level = models.PositiveIntegerField(verbose_name="Уровень доступа", default=0)
    name = models.CharField(verbose_name="", max_length=26, blank=True, default="")
    description = models.TextField(verbose_name="Описание категории", blank=True)

    def __str__(self):
        return self.name


class HarmfulWorkingConditions(models.Model):
    """
    Вредные условия труда
    """

    class Meta:
        verbose_name = "Вредные условия труда"
        verbose_name_plural = "Вредные условия труда"

    ref_key = models.CharField(
        verbose_name="Уникальный номер", max_length=37, default=""
    )
    code = models.CharField(verbose_name="Код", max_length=9, default="")
    name = models.TextField(verbose_name="Наименование")
    frequency_inspection = models.PositiveSmallIntegerField(
        verbose_name="Периодичность осмотров", default=0
    )
    frequency_multiplicity = models.PositiveSmallIntegerField(
        verbose_name="Кратность осмотров", default=0
    )

    def __str__(self):
        return self.code

    def get_data(self):
        return {
            "pk": self.pk,
            "code": self.code,
            "name": self.name,
            "frequency_multiplicity": self.frequency_multiplicity,
            "frequency_inspection": self.frequency_inspection,
        }


class Affiliation(models.Model):
    """
    Модель, представляющая принадлежность к подразделению.

    Поля:
        name (str): Название принадлежности.

    Атрибуты:
        name: (CharField) Имя принадлежности.
    """

    class Meta:
        verbose_name = "Принадлежность к подразделению"
        verbose_name_plural = "Принадлежности к подразделению"

    name = models.CharField(verbose_name="Наименование", max_length=40, help_text="")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        """
        Этот метод возвращает абсолютный URL-адрес для представления «affiliation-list» в приложении
        «customers_app».

        :return: Абсолютный URL-адрес представления «список принадлежности».
        """
        return reverse("customers_app:affiliation-list")


class Job(models.Model):
    """
    Класс должностей
    """

    job_type = [
        ("0", "Общий состав"),
        ("1", "Летный состав"),
        ("2", "Инженерный состав"),
        ("3", "Транспортный отдел"),
    ]

    class Meta:
        verbose_name = "Должность"
        verbose_name_plural = "Должности"

    ref_key = models.CharField(
        verbose_name="Уникальный номер", max_length=37, default=""
    )
    code = models.CharField(
        verbose_name="Код должности", max_length=5, help_text="", default=""
    )
    name = models.CharField(verbose_name="Должность", max_length=200, help_text="")
    type_of_job = models.CharField(
        verbose_name="Принадлежность",
        choices=job_type,
        null=True,
        blank=True,
        max_length=18,
    )
    division_affiliation = models.ForeignKey(
        Affiliation,
        verbose_name="Принадлежность",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    date_entry = models.DateField(
        verbose_name="Дата ввода", auto_now_add=True, null=True
    )
    date_exclusions = models.DateField(
        verbose_name="Дата исключения", auto_now_add=True, null=True
    )
    excluded_standard_spelling = models.BooleanField(
        verbose_name="Исключена из штатного расписания", default=True
    )
    employment_function = models.CharField(
        verbose_name="Трудовая функция", max_length=37, default=""
    )
    harmful = models.ManyToManyField(
        HarmfulWorkingConditions, verbose_name="Вредные условия труда", blank=True
    )
    right_to_approval = models.BooleanField(
        verbose_name="Имеет право на согласование", default=False
    )
    group = models.ManyToManyField(Groups, verbose_name="Группы должности")

    def __str__(self):
        return f"{self.name}"

    def get_title(self):
        return f"{self.name}"

    def get_data(self):
        return {
            "pk": self.pk,
            "code": self.code,
            "name": self.name,
            "type_of_job": self.get_type_of_job_display(),
            "harmful": "",  # if not self.parent_category else str(self.parent_category),
        }


class Category(models.Model):
    """Класс Category является родительским классом для таких классов как MainMenu,

    Основное применение - задает общие характеристики дочерним классам

    Attributes
    ----------
    parent_category : ForeignKey
        внешний ключ на себя, служит для организации подкатегорий объекта
    name : str
        содержит название категории
    description : str
        содержит описание категории
    access : ForeignKey
        внешний ключ на модель AccessLevel, служит для определения категории доступа

    Methods
    -------
    __str__(self)
        используется для представления отдельных записей на сайте администрирования
        (и в любом другом месте, где нужно обратиться к экземпляру модели).
    """

    class Meta:
        abstract = True

    """
        Соответствие полей со справочником из 1С:

        ref_key = Ref_Key
        parent_category = Parent_Key; если = "00000000-0000-0000-0000-000000000000" значит нет родительской категории
        code = Code
        name = Description
        history = ДатаСоздания
        okved = КодОКВЭД2
        active = Расформировано

        URL API:
        http://192.168.10.11/hrmnew/odata/standard.odata/Catalog_ПодразделенияОрганизаций?$format=application/json;odata=nometadata

        Десериализация:
        for item in range(0, len(data['value'])):
            if data['value'][item]['DeletionMark'] == False:
                print(data['value'][item])
    """

    ref_key = models.CharField(
        verbose_name="Уникальный номер", max_length=37, default="", help_text=""
    )
    parent_category = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True
    )
    code = models.CharField(
        verbose_name="Код подразделения", max_length=10, default="", help_text=""
    )
    name = models.CharField(
        verbose_name="Название категории", max_length=128, default=""
    )
    description = models.TextField(verbose_name="Описание категории", blank=True)
    history = models.DateField(
        verbose_name="Дата создания", auto_created=True, null=True
    )
    okved = models.CharField(
        verbose_name="Код ОКВЭД2", max_length=8, default="", help_text="", blank=True
    )
    active = models.BooleanField(verbose_name="Активность", default=True)

    def __str__(self):
        return self.name


class Division(Category):
    """
    Класс Division - содержит подразделения компании
    """

    type_of = [("0", "Общий"), ("1", "НО"), ("2", "Кадры"), ("3", "Бухгалтерия")]

    class Meta:
        verbose_name = "Подразделение"
        verbose_name_plural = "Подразделения организации"
        ordering = ["code"]  # сортировка по полю name

    type_of_role = models.CharField(
        verbose_name="Роль подразделения",
        choices=type_of,
        null=True,
        blank=True,
        max_length=11,
    )
    destination_point = models.BooleanField(
        verbose_name="Используется как место назначения", default=False
    )
    address = models.CharField(
        verbose_name="Адрес", max_length=250, default="", blank=True
    )

    def __init__(self, *args, **kwargs):
        super(Division, self).__init__(*args, **kwargs)

    def get_title(self):
        return self.name

    def get_data(self):
        return {
            "pk": self.pk,
            "code": self.code,
            "name": self.name,
            "parent_category": ""
            if not self.parent_category
            else str(self.parent_category),
        }


class Citizenships(models.Model):
    """
    Класс Citizenship - содержит гражданство пользователя
    """

    class Meta:
        verbose_name = "Гражданство пользователя"
        verbose_name_plural = "Гражданства пользователей"

    city = models.CharField(verbose_name="Страна", max_length=50)

    def __str__(self):
        return self.city


class IdentityDocuments(models.Model):
    """
    Класс IdentityDocuments - содержит документы пользователя
    """

    class Meta:
        verbose_name = "Паспорт пользователя"
        verbose_name_plural = "Паспорта пользователей"

    ref_key = models.CharField(
        verbose_name="Уникальный номер", max_length=37, default=""
    )
    series = models.CharField(verbose_name="Серия", max_length=5, default="")
    number = models.CharField(verbose_name="Номер", max_length=6, default="")
    issued_by_whom = models.CharField(
        verbose_name="Кем выдан", max_length=250, default=""
    )
    date_of_issue = models.DateField(verbose_name="Дата выдачи", null=True)
    division_code = models.CharField(
        verbose_name="Код подразделения", max_length=7, default=""
    )

    def __str__(self):
        return f"{self.series} {self.number}, {self.issued_by_whom}, {self.date_of_issue.strftime('%d.%m.%Y')}, {self.division_code}"


class DataBaseUserProfile(models.Model):
    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"

    ref_key = models.CharField(
        verbose_name="Уникальный номер", max_length=37, default=""
    )
    citizenship = models.ForeignKey(
        Citizenships,
        verbose_name="Гражданство",
        blank=True,
        on_delete=models.SET_NULL,
        null=True,
    )
    passport = models.OneToOneField(
        IdentityDocuments,
        verbose_name="Паспорт",
        blank=True,
        on_delete=models.SET_NULL,
        null=True,
    )
    snils = models.CharField(
        verbose_name="СНИЛС", max_length=14, blank=True, default=""
    )
    oms = models.CharField(
        verbose_name="Полис ОМС", max_length=24, blank=True, default=""
    )
    inn = models.CharField(verbose_name="ИНН", max_length=12, blank=True, default="")


def get_time(text):
    """
    Преобразует строковое представление времени в формате «ЧЧ:ММ:СС» в объект времени Python.
    :param text: Строка, представляющая время в формате "ЧЧ:ММ:СС"
    :return: Объект времени, представляющий время ввода
    """
    return datetime.datetime.strptime(text, "%H:%M:%S").time()


class DataBaseUserWorkProfile(models.Model):
    """
    Модель рабочего профиля пользователя
    """

    class Meta:
        verbose_name = "Рабочий профиль пользователя"
        verbose_name_plural = "Рабочие профили пользователей"

    ref_key = models.CharField(
        verbose_name="Уникальный номер", max_length=37, default=""
    )
    date_of_employment = models.DateField(
        verbose_name="Дата приема на работу", blank=True, null=True
    )
    internal_phone = models.CharField(
        verbose_name="Внутренний номер телефона",
        max_length=3,
        help_text="",
        blank=True,
        default="",
    )
    job = models.ForeignKey(
        Job,
        verbose_name="Должность",
        on_delete=models.SET_NULL,
        null=True,
        help_text="",
        blank=True,
    )
    divisions = models.ForeignKey(
        Division,
        verbose_name="Подразделение",
        on_delete=models.SET_NULL,
        null=True,
        help_text="",
        blank=True,
    )
    work_email_password = models.CharField(
        verbose_name="Пароль от корпоративной почты",
        max_length=50,
        blank=True,
        default="",
    )
    work_application_password = models.CharField(
        verbose_name="Пароль приложения от корпоративной почты",
        max_length=100,
        blank=True,
        default="",
    )
    personal_work_schedule_start = models.TimeField(
        verbose_name="Начало рабочего времени", default=get_time("9:30:00")
    )
    personal_work_schedule_end = models.TimeField(
        verbose_name="Окончание рабочего времени", default=get_time("18:00:00")
    )


class Apartments(models.Model):
    class Meta:
        verbose_name = "Квартира"
        verbose_name_plural = "Квартиры"

    title = models.CharField(
        verbose_name="Наименование", max_length=200, default="", blank=True
    )
    place = models.ForeignKey('hrdepartment_app.PlaceProductionActivity', on_delete=models.CASCADE)
    address = models.CharField(
        verbose_name="Адрес", max_length=250, default="", blank=True
    )
    contracts = models.ForeignKey(
        'contracts_app.Contract',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name='Договор',
        limit_choices_to={'parent_category__isnull': True, 'type_of_contract__type_contract': 'Аренда квартир'}
    )
    validity_period = models.DateField(verbose_name="Срок действия", null=True, blank=True)
    beds_number = models.IntegerField(verbose_name="Количество мест", default=0)
    type_description = models.CharField(verbose_name="Описание", max_length=250, default="", blank=True)

    occupied_beds = models.IntegerField(
        verbose_name="Занято мест",
        default=0
    )

    def clean(self):
        """Проверка корректности occupied_beds при сохранении через форму или админку"""
        if self.occupied_beds < 0:
            raise ValidationError("Занято мест не может быть меньше 0.")
        if self.occupied_beds > self.beds_number:
            raise ValidationError("Занято мест не может превышать общее количество мест.")

    def save(self, *args, **kwargs):
        self.full_clean()  # вызывает clean()
        super().save(*args, **kwargs)

    def increase_occupied(self, amount=1):
        """Увеличивает занятое количество мест на `amount` (по умолчанию 1)"""
        if amount <= 0:
            raise ValueError("Amount must be positive.")
        new_value = self.occupied_beds + amount
        if new_value > self.beds_number:
            raise ValueError(f"Нельзя занять больше {self.beds_number} мест. Текущее: {self.occupied_beds}.")
        self.occupied_beds = new_value
        self.save(update_fields=['occupied_beds'])

    def decrease_occupied(self, amount=1):
        """Уменьшает занятое количество мест на `amount` (по умолчанию 1)"""
        if amount <= 0:
            raise ValueError("Amount must be positive.")
        new_value = self.occupied_beds - amount
        if new_value < 0:
            raise ValueError("Занято мест не может быть меньше 0.")
        self.occupied_beds = new_value
        self.save(update_fields=['occupied_beds'])

    def __str__(self):
        if self.title:
            return self.title
        else:
            return f"{self.place} {self.address}"


class RoleType(models.TextChoices):
    COMMON = "0", "Общий"
    NO = "1", "Наземное обеспечение"
    HR = "2", "Отдел кадров"
    ACCOUNTING = "3", "Бухгалтерия"


class DataBaseUser(AbstractUser):
    """
    Класс DataBaseUser - модель пользователя
    """

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ["last_name"]

    type_of = [
        ("natural_person", "физическое лицо"),
        ("staff_member", "штатный сотрудник"),
        ("freelancer", "внештатный сотрудник"),
    ]

    type_of_gender = [("male", "мужской"), ("female", "женский")]

    type_of_role = models.CharField(
        verbose_name="Роль подразделения",
        max_length=1,  # максимум 1 символ
        choices=RoleType.choices,
        null=True,
        blank=True,
    )

    ref_key = models.CharField(
        verbose_name="Уникальный номер", max_length=37, default=""
    )
    title = models.CharField(
        verbose_name="Наименование", max_length=200, default="", blank=True
    )
    person_ref_key = models.CharField(
        verbose_name="Уникальный номер физ лица", max_length=37, default=""
    )
    service_number = models.CharField(
        verbose_name="Табельный номер", max_length=10, default="", blank=True
    )
    surname = models.CharField(
        verbose_name="Отчество", max_length=40, blank=True, default="", help_text=""
    )
    avatar = models.ImageField(upload_to="users_avatars", blank=True, help_text="")
    birthday = models.DateField(
        verbose_name="День рождения", blank=True, null=True, help_text=""
    )

    user_access = models.ForeignKey(
        AccessLevel,
        verbose_name="Права доступа",
        help_text="",
        blank=True,
        on_delete=models.SET_NULL,
        null=True,
    )
    address = models.TextField(verbose_name="Адрес", null=True, blank=True)
    type_users = models.CharField(
        verbose_name="Тип пользователя",
        max_length=40,
        choices=type_of,
        help_text="",
        blank=True,
        default="",
    )
    personal_phone = models.CharField(
        verbose_name="Личный номер телефона",
        max_length=15,
        help_text="",
        blank=True,
        default="",
    )
    gender = models.CharField(
        verbose_name="Пол",
        max_length=7,
        blank=True,
        choices=type_of_gender,
        help_text="",
        default="",
    )
    user_profile = models.OneToOneField(
        DataBaseUserProfile,
        verbose_name="Личный профиль пользователя",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    user_work_profile = models.OneToOneField(
        DataBaseUserWorkProfile,
        verbose_name="Рабочий профиль пользователя",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    passphrase = models.CharField(
        verbose_name="Парольная фраза", max_length=256, default="", blank=True
    )
    telegram_id = models.CharField(
        verbose_name="Telegram ID", max_length=20, blank=True
    )
    is_ppa = models.BooleanField(default=False, verbose_name="МПД")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_title(self):
        """
        Возвращает наименование пользователя
        :return:
        """
        return self.title

    def get_data(self):
        """
        Возврат пользовательских данных в формате словаря.

        :return: Dictionary containing the following keys:
            - 'pk': The primary key of the user.
            - 'number': The service number of the user.
            - 'person': ФИО пользователя.
            - 'division': Подразделение пользователя, если оно присутствует, или пустая строка.
            - 'job': Должность пользователя, если она присутствует, или пустая строка.
            - 'phone': Внутренний номер телефона пользователя, если он есть, или пустая строка.
            - 'email': Электронный адрес пользователя.
            - 'password': Пароль рабочей электронной почты пользователя, если он есть, или пустая строка.
            - 'telegram_id': Telegram ID пользователя.

        """
        return {
            "pk": self.pk,
            "number": self.service_number,
            "person": self.title,
            "division": str(self.user_work_profile.divisions)
            if self.user_work_profile
            else "",
            "job": str(self.user_work_profile.job) if self.user_work_profile else "",
            "phone": str(self.user_work_profile.internal_phone)
            if self.user_work_profile
            else "",
            "email": self.email,
            "password": str(self.user_work_profile.work_email_password)
            if self.user_work_profile
            else "",
            "telegram_id": str(self.telegram_id),
            "rules": self.user_access.name if self.user_access else "",
        }

    def get_absolute_url(self):
        return reverse("customers_app:staff_list")


def rename(file_name, path_name, instance, pfx):
    """

    :param file_name: The name of the file being renamed.
    :param path_name: The directory path where the file is located.
    :param instance: The instance of the model where the file is being renamed.
    :param pfx: The prefix for the renamed file.
    :return: None

    """
    try:
        if instance.avatar:
            # Получаем расширение файла
            ext = file_name.split(".")[-1]
            # Формируем уникальное окончание файла. Длинна в 7 символов. В окончании номер записи: рк, спереди дополняющие нули
            filename = f"{instance.username}.{ext}"
            if file_name:
                try:
                    pathlib.Path.rename(
                        pathlib.Path.joinpath(BASE_DIR, "media", path_name, file_name),
                        pathlib.Path.joinpath(BASE_DIR, "media", path_name, filename),
                    )
                except Exception as _ex0:
                    print(_ex0)
            instance.avatar = f"users_avatars/{filename}"
            if file_name != filename:
                instance.save()

    except Exception as _ex:
        print(_ex)


@receiver(post_save, sender=DataBaseUser)
def change_filename(sender, instance, **kwargs):
    """
    :param sender: Объект отправителя.
    :param instance: Сохраняемый объект экземпляра.
    :param kwargs: Дополнительные аргументы ключевого слова, если таковые имеются.
    :return: None

    Этот метод представляет собой приемник сигнала, который запускается после сохранения объекта `DataBaseUser`.
    Он выполняет следующие действия:
    1. Создает новый заголовок, используя значения полей `last_name`, `first_name` и `surname` объекта `instance`.
    2. Проверяет, отличается ли поле «заголовок» «экземпляра» от созданного нового заголовка.
        - Если отличается, обновляет поле «заголовок» «экземпляра» новым заголовком и сохраняет экземпляр.
        - Если не отличается, никаких действий не предпринимается.
    3. Попытки получить имя сохраненного файла из поля «аватар» объекта «экземпляр».
    4. Попытки получить путь к сохраненному файлу из поля «аватар» объекта «экземпляр».
    5. Вызывает функцию «переименовать» с полученным именем файла, путем, «экземпляром» и пустой строкой в качестве параметров.

    """
    new_title = f"{empty_item(instance.last_name)} {empty_item(instance.first_name)} {empty_item(instance.surname)}"
    if instance.title != new_title:
        instance.title = new_title
        instance.save()
    try:
        # Получаем имя сохраненного файла
        file_name = pathlib.Path(instance.avatar.name).name
        # Получаем путь к файлу
        path_name = pathlib.Path(instance.avatar.name).parent
        rename(file_name, path_name, instance, "")

    except Exception as _ex:
        print(_ex)


class UserStats(models.Model):
    user = models.ForeignKey(DataBaseUser, on_delete=models.CASCADE, related_name='stats')
    score = models.IntegerField(default=0)
    level = models.IntegerField(default=1)
    lines_cleared = models.IntegerField(default=0)
    games_played = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - Score: {self.score}"


class Counteragent(models.Model):
    """
    Контрагенты
    """

    class Meta:
        verbose_name = "Контрагент"
        verbose_name_plural = "Контрагенты"
        ordering = ["short_name"]
        indexes = [
            models.Index(fields=['inn', 'kpp']),
            models.Index(fields=['inn']),
        ]

    type_of = [
        ("juridical_person", "юридическое лицо"),
        ("physical_person", "физическое лицо"),
        ("separate_subdivision", "обособленное подразделение"),
        ("government_agency", "государственный орган"),
    ]

    ref_key = models.CharField(
        verbose_name="Уникальный номер", max_length=37, default=""
    )
    short_name = models.CharField(
        verbose_name="Наименование", max_length=400, default="", help_text="", blank=True,
    )
    full_name = models.CharField(
        verbose_name="Полное наименование", max_length=400, default="", help_text="", blank=True,
    )
    natural_person = models.CharField(
        verbose_name="Физическое лицо", max_length=400, default="", help_text="", blank=True,
    )
    inn = models.CharField(
        verbose_name="ИНН", max_length=12, blank=True, default="", help_text=""
    )
    kpp = models.CharField(
        verbose_name="КПП", max_length=9, blank=True, default="", help_text=""
    )
    ogrn = models.CharField(
        verbose_name="ОГРН", max_length=15, blank=True, default="", help_text=""
    )
    type_counteragent = models.CharField(
        verbose_name="Тип контрагента",
        max_length=40,
        choices=type_of,
        help_text="",
        default="",
    )
    juridical_address = models.TextField(
        verbose_name="Юридический адрес", default="", blank=True
    )
    physical_address = models.TextField(
        verbose_name="Физический адрес", default="", blank=True
    )
    email = models.EmailField(verbose_name="Email", default="", blank=True)
    phone = models.CharField(
        verbose_name="Корпоративный номер телефона",
        max_length=15,
        help_text="",
        blank=True,
        default="",
    )
    base_counteragent = models.BooleanField(
        verbose_name="Основная организация", default=False
    )
    director = models.ForeignKey(
        DataBaseUser,
        verbose_name="Директор",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="direct",
    )
    accountant = models.ForeignKey(
        DataBaseUser,
        verbose_name="Бухгалтер",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="account",
    )
    contact_person = models.ForeignKey(
        DataBaseUser,
        verbose_name="Контактное лицо",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact",
    )

    @classmethod
    def find_duplicates_by_inn_kpp(cls):
        """
        Находит все дубликаты по ИНН и КПП
        Возвращает словарь: {'инн_кпп': [список_объектов]}
        """
        # Находим все записи с заполненными ИНН (не пустыми)
        with_inn_kpp = cls.objects.exclude(inn='')

        # Группируем по ИНН+КПП и находим дубликаты
        duplicates = {}

        # Сначала группируем по ИНН
        for counteragent in with_inn_kpp:
            key = (counteragent.inn, counteragent.kpp)
            if key not in duplicates:
                duplicates[key] = []
            duplicates[key].append(counteragent)

        # Убираем уникальные записи (где только 1 объект в группе)
        duplicates = {k: v for k, v in duplicates.items() if len(v) > 1}

        return duplicates

    @classmethod
    def find_duplicates_by_inn(cls):
        """
        Находит дубликаты только по ИНН (без учета КПП)
        """
        # Используем аннотацию для более эффективного запроса
        from django.db.models import Count

        duplicate_inns = cls.objects.values('inn') \
            .exclude(inn='') \
            .annotate(count=Count('id')) \
            .filter(count__gt=1) \
            .values_list('inn', flat=True)

        duplicates = {}
        for inn in duplicate_inns:
            duplicates[inn] = cls.objects.filter(inn=inn)

        return duplicates

    @classmethod
    def get_potential_duplicates(cls, counteragent):
        """
        Находит потенциальные дубликаты для конкретного контрагента
        """
        if not counteragent.inn:
            return cls.objects.none()

        # Ищем по ИНН
        same_inn = cls.objects.filter(inn=counteragent.inn).exclude(id=counteragent.id)

        # Если есть КПП, ищем точное совпадение ИНН+КПП
        if counteragent.kpp:
            exact_matches = same_inn.filter(kpp=counteragent.kpp)
            if exact_matches.exists():
                return exact_matches

        return same_inn

    def has_duplicates(self):
        """Проверяет, есть ли у текущего контрагента дубликаты"""
        return self.get_potential_duplicates(self).exists()

    def __str__(self):
        if self.short_name == "":
            if self.full_name == "":
                self.short_name = self.natural_person
            else:
                self.short_name = self.full_name
            self.save()

        return f"{self.short_name}"

    def get_data(self):
        return {
            "pk": self.pk,
            "short_name": self.short_name,
            "inn": self.inn,
            "kpp": self.kpp,
            "address": self.juridical_address,
        }

    def get_related_documents(self):
        """
        Возвращает список всех документов, ссылающихся на этот контрагент
        """
        related_docs = []

        # Получаем все модели приложения
        all_models = apps.get_models()

        for model in all_models:
            # Проверяем все поля модели
            for field in model._meta.get_fields():
                if (isinstance(field, ForeignKey) and
                        field.related_model == Counteragent):

                    # Находим все объекты этой модели, ссылающиеся на этот контрагент
                    related_objects = model.objects.filter(**{field.name: self})

                    for obj in related_objects:
                        # Пытаемся получить URL для детального просмотра
                        try:
                            # Имя URL обычно строится как 'modelname-detail'
                            url_name = f'{model._meta.model_name}-detail'
                            url = reverse_lazy(url_name, kwargs={'pk': obj.pk})
                        except:
                            # Если нет детального представления, используем список
                            try:
                                url_name = f'{model._meta.model_name}-list'
                                url = reverse_lazy(url_name)
                            except:
                                url = None

                        related_docs.append({
                            'model_name': model._meta.verbose_name,
                            'model_name_plural': model._meta.verbose_name_plural,
                            'object': obj,
                            'url': url,
                            'count': related_objects.count()
                        })

        return related_docs


def document_directory_path(instance, filename):
    name = uuid.uuid4()
    ext = pathlib.Path(instance.document.name).suffix
    filename = f"{name}{ext}"
    return f"hr/counteragent/{instance.package.pk}/{filename}"


class CounteragentDocuments(models.Model):
    class Meta:
        verbose_name = "Документ контрагента"
        verbose_name_plural = "Документы контрагента"
        ordering = ["-date_of_creation"]

    date_of_creation = models.DateField(verbose_name='Дата и время создания', auto_now_add=True)
    document = models.FileField(verbose_name='Документ', upload_to=document_directory_path)
    description = models.CharField(verbose_name='Описание', max_length=400, default='')
    package = models.ForeignKey(Counteragent, verbose_name='Контрагент', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.document.file}"

    def get_data(self):
        return {
            "pk": self.pk,
            "document": self.document.name,
            "description": self.description,
            "package": self.package.short_name,
        }

    def get_absolute_url(self):
        return reverse("customers_app:documents_list")


class Posts(models.Model):
    """
    Класс для хранения постов
    """

    class Meta:
        """
        Meta class: определяет метаданные модели
        """

        verbose_name = "Новость"
        verbose_name_plural = "Сообщения"

    post_title = models.CharField(verbose_name="Заголовок", max_length=100, blank=True)
    creation_date = models.DateField(verbose_name="Дата создания", auto_now_add=True)
    post_description = CKEditor5Field("Содержание", config_name="extends", blank=True)
    post_divisions = models.ManyToManyField(
        Division,
        verbose_name="Подразделения поста",
    )
    allowed_placed = models.BooleanField(
        verbose_name="Разрешение на публикацию", default=False
    )
    responsible = models.ForeignKey(
        DataBaseUser,
        verbose_name="Ответственное лицо",
        on_delete=models.SET_NULL,
        null=True,
        related_name="responsible_person",
    )
    post_date_start = models.DateField(
        verbose_name="Дата начала отображения", blank=True, null=True
    )
    post_date_end = models.DateField(
        verbose_name="Дата окончания отображения", blank=True, null=True
    )
    email_send = models.BooleanField(verbose_name="Письмо отправлено", default=False)

    def __str__(self):
        return f"{self.creation_date} / {self.pk}"


class HistoryChange(models.Model):
    """
    Модель HistoryChange - введена для возможности отследить изменения моделей.
    """

    class Meta:
        verbose_name = "История"
        verbose_name_plural = "Список истории"

    date_add = models.DateTimeField(verbose_name="Время добавления", auto_now_add=True)
    author = models.ForeignKey(
        DataBaseUser,
        verbose_name="Автор",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="author_changes",
    )
    body = models.TextField(blank=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    def __str__(self):
        return f"{str(self.content_type.name)} : {str(self.content_object)}"


class HappyBirthdayGreetings(models.Model):
    """
    Класс для хранения сообщений дня рождения
    """

    type_of_gender = [("male", "мужской"), ("female", "женский")]

    class Meta:
        verbose_name = "Поздравление"
        verbose_name_plural = "Поздравления"

    age_from = models.IntegerField(verbose_name="", default=0)
    age_to = models.IntegerField(verbose_name="", default=0)
    gender = models.CharField(
        verbose_name="Пол",
        max_length=7,
        blank=True,
        choices=type_of_gender,
        help_text="",
        default="",
    )
    greetings = models.TextField(blank=True)
    sign = models.TextField(
        verbose_name="Подпись",
        default='Генеральный директор<br>ООО Авиакомпания "БАРКОЛ"<br>Бархотов В.С.<br>и весь коллектив!!!',
    )

    def __str__(self):
        if self.age_from == self.age_to:
            return f"{self.get_gender_display()} на {self.age_to} летие"
        else:
            return f"{self.get_gender_display()} c {self.age_from} по {self.age_to}"


class VacationScheduleList(models.Model):
    """
    Класс для хранения расписания отпусков
    """

    class Meta:
        verbose_name = "Номер документа графика отпусков"
        verbose_name_plural = "Номера документов графиков отпусков"

    document_number = models.CharField(
        verbose_name="Номер документа", max_length=100,
    )
    document_year = models.IntegerField(
        verbose_name="Год документа", default=0,
    )

    def __str__(self):
        return f"{self.pk}"


class VacationSchedule(models.Model):
    """
    Класс для хранения расписания отпусков
    """
    VACATION_TYPE = [
        ("dd940e62-cfaf-11e6-bad8-902b345cadc2", "Отпуск за свой счет"),
        ("b51bdb10-8fb9-11e9-80cc-309c23d346b4", "Дополнительный оплачиваемый отпуск пострадавшим на ЧАЭС"),
        ("c3e8c3e8-cfb6-11e6-bad8-902b345cadc2", "Дополнительный неоплачиваемый отпуск пострадавшим на ЧАЭС"),
        ("c3e8c3e7-cfb6-11e6-bad8-902b345cadc2", "Дополнительный учебный отпуск (оплачиваемый)"),
        ("dd940e63-cfaf-11e6-bad8-902b345cadc2", "Дополнительный учебный отпуск без оплаты"),
        ("6f4631a7-df12-11e6-950a-0cc47a7917f4", "Дополнительный отпуск КЛО, ЗКЛО, начальник ИБП"),
        ("56f643c6-bf49-11e9-a3dc-0cc47a7917f4", "Дополнительный оплачиваемый отпуск пострадавшим в аварии на ЧАЭС"),
        ("dd940e60-cfaf-11e6-bad8-902b345cadc2", "Дополнительный ежегодный отпуск"),
        ("ebbd9c67-cfaf-11e6-bad8-902b345cadc2", "Основной"),
    ]

    class Meta:
        verbose_name = "Расписание отпусков"
        verbose_name_plural = "Расписание отпусков"

    employee = models.ForeignKey(DataBaseUser, on_delete=models.CASCADE)
    start_date = models.DateField(verbose_name="Начало отпуска")
    end_date = models.DateField(verbose_name="Конец отпуска")
    type_vacation = models.CharField(
        verbose_name="Тип отпуска", max_length=100, choices=VACATION_TYPE
    )
    days = models.IntegerField(verbose_name="Количество дней", default=0)
    years = models.IntegerField(verbose_name="Год графика", default=0)
    comment = models.TextField(verbose_name="Комментарий", blank=True)
