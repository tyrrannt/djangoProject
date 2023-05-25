import datetime
import hashlib
import pathlib

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from contracts_app.templatetags.custom import empty_item
from djangoProject.settings import BASE_DIR
from django.contrib.auth.models import Group, Permission


class Groups(Group):
    class Meta:
        verbose_name = 'Группа'
        verbose_name_plural = 'Группы'

    def get_data(self):
        permissions = [str(item.name) for item in self.permissions.iterator()]
        return {
            'pk': self.pk,
            'name': self.name,
            'permissions': '; '.join(permissions),
        }


class ViewDocumentsPhysical(models.Model):
    class Meta:
        verbose_name = 'Вид документа физического лица'
        verbose_name_plural = 'Виды документов физических лиц'

    ref_key = models.CharField(verbose_name='Уникальный номер', max_length=37, default='')
    codeMVD = models.CharField(verbose_name='Код МВД', max_length=5, default='')
    codePFR = models.CharField(verbose_name='Код ПФР', max_length=5, default='')
    name = models.TextField(verbose_name='Наименование')


class AccessLevel(models.Model):
    class Meta:
        verbose_name = 'Уровень доступа'
        verbose_name_plural = 'Уровни доступа'

    level = models.PositiveIntegerField(verbose_name='Уровень доступа', default=0)
    name = models.CharField(verbose_name='', max_length=26, blank=True, default='')
    description = models.TextField(verbose_name='Описание категории', blank=True)

    def __str__(self):
        return self.name


class HarmfulWorkingConditions(models.Model):
    class Meta:
        verbose_name = 'Вредные условия труда'
        verbose_name_plural = 'Вредные условия труда'

    ref_key = models.CharField(verbose_name='Уникальный номер', max_length=37, default='')
    code = models.CharField(verbose_name='Код', max_length=9, default='')
    name = models.TextField(verbose_name='Наименование')
    frequency_inspection = models.PositiveSmallIntegerField(verbose_name='Периодичность осмотров', default=0)
    frequency_multiplicity = models.PositiveSmallIntegerField(verbose_name='Кратность осмотров', default=0)

    def __str__(self):
        return self.code

    def get_data(self):
        return {
            'pk': self.pk,
            'code': self.code,
            'name': self.name,
            'frequency_multiplicity': self.frequency_multiplicity,
            'frequency_inspection': self.frequency_inspection,

        }


class Job(models.Model):
    job_type = [
        ('0', 'Общий состав'),
        ('1', 'Летный состав'),
        ('2', 'Инженерный состав'),
        ('3', 'Транспортный отдел'),
    ]

    class Meta:
        verbose_name = 'Должность'
        verbose_name_plural = 'Должности'

    ref_key = models.CharField(verbose_name='Уникальный номер', max_length=37, default='')
    code = models.CharField(verbose_name='Код должности', max_length=5, help_text='', default='')
    name = models.CharField(verbose_name='Должность', max_length=200, help_text='')
    type_of_job = models.CharField(verbose_name="Принадлежность", choices=job_type, null=True, blank=True,
                                   max_length=18)
    date_entry = models.DateField(verbose_name='Дата ввода', auto_now_add=True, null=True)
    date_exclusions = models.DateField(verbose_name='Дата исключения', auto_now_add=True, null=True)
    excluded_standard_spelling = models.BooleanField(verbose_name='Исключена из штатного расписания', default=True)
    employment_function = models.CharField(verbose_name='Трудовая функция', max_length=37, default='')
    harmful = models.ManyToManyField(HarmfulWorkingConditions, verbose_name='Вредные условия труда', blank=True)
    right_to_approval = models.BooleanField(verbose_name='Имеет право на согласование', default=False)
    group = models.ManyToManyField(Groups, verbose_name='Группы должности')

    def __str__(self):
        return f'{self.name}'

    def get_title(self):
        return f'{self.name}'

    def get_data(self):
        return {
            'pk': self.pk,
            'code': self.code,
            'name': self.name,
            'type_of_job': self.get_type_of_job_display(),
            'harmful': '',  # if not self.parent_category else str(self.parent_category),
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

    ref_key = models.CharField(verbose_name='Уникальный номер', max_length=37, default='', help_text='')
    parent_category = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    code = models.CharField(verbose_name='Код подразделения', max_length=10, default='', help_text='')
    name = models.CharField(verbose_name='Название категории', max_length=128, default='')
    description = models.TextField(verbose_name='Описание категории', blank=True)
    history = models.DateField(verbose_name="Дата создания", auto_created=True, null=True)
    okved = models.CharField(verbose_name='Код ОКВЭД2', max_length=8, default='', help_text='', blank=True)
    active = models.BooleanField(verbose_name='Активность', default=True)

    def __str__(self):
        return self.name


class Division(Category):
    """
    Класс Division - содержит подразделения компании
    """
    type_of = [
        ('0', 'Общий'),
        ('1', 'НО'),
        ('2', 'Кадры'),
        ('3', 'Бухгалтерия')
    ]

    class Meta:
        verbose_name = 'Подразделение'
        verbose_name_plural = 'Подразделения организации'

    type_of_role = models.CharField(verbose_name="Роль подразделения", choices=type_of, null=True, blank=True,
                                    max_length=11)
    destination_point = models.BooleanField(verbose_name='Используется как место назначения', default=False)
    address = models.CharField(verbose_name='Адрес', max_length=250, default='', blank=True)

    def __init__(self, *args, **kwargs):
        super(Division, self).__init__(*args, **kwargs)

    def get_title(self):
        return self.name

    def get_data(self):
        return {
            'pk': self.pk,
            'code': self.code,
            'name': self.name,
            'parent_category': '' if not self.parent_category else str(self.parent_category),
        }


class Citizenships(models.Model):
    class Meta:
        verbose_name = 'Гражданство пользователя'
        verbose_name_plural = 'Гражданства пользователей'

    city = models.CharField(verbose_name='Страна', max_length=50)

    def __str__(self):
        return self.city


class IdentityDocuments(models.Model):
    class Meta:
        verbose_name = 'Паспорт пользователя'
        verbose_name_plural = 'Паспорта пользователей'

    ref_key = models.CharField(verbose_name='Уникальный номер', max_length=37, default='')
    series = models.CharField(verbose_name='Серия', max_length=5, default='')
    number = models.CharField(verbose_name='Номер', max_length=6, default='')
    issued_by_whom = models.CharField(verbose_name='Кем выдан', max_length=250, default='')
    date_of_issue = models.DateField(verbose_name='Дата выдачи', null=True)
    division_code = models.CharField(verbose_name='Код подразделения', max_length=7, default='')

    def __str__(self):
        return f'{self.series} {self.number}, {self.issued_by_whom}, {self.date_of_issue}, {self.division_code}'


class DataBaseUserProfile(models.Model):
    class Meta:
        verbose_name = 'Профиль пользователя'
        verbose_name_plural = 'Профили пользователей'

    ref_key = models.CharField(verbose_name='Уникальный номер', max_length=37, default='')
    citizenship = models.ForeignKey(Citizenships, verbose_name='Гражданство', blank=True, on_delete=models.SET_NULL,
                                    null=True)
    passport = models.OneToOneField(IdentityDocuments, verbose_name='Паспорт', blank=True, on_delete=models.SET_NULL,
                                    null=True)
    snils = models.CharField(verbose_name='СНИЛС', max_length=14, blank=True, default='')
    oms = models.CharField(verbose_name='Полис ОМС', max_length=24, blank=True, default='')
    inn = models.CharField(verbose_name='ИНН', max_length=12, blank=True, default='')

def get_time(text):
    return datetime.datetime.strptime(text, '%H:%M:%S').time()

class DataBaseUserWorkProfile(models.Model):
    class Meta:
        verbose_name = 'Рабочий профиль пользователя'
        verbose_name_plural = 'Рабочие профили пользователей'

    ref_key = models.CharField(verbose_name='Уникальный номер', max_length=37, default='')
    date_of_employment = models.DateField(verbose_name='Дата приема на работу', blank=True, null=True)
    internal_phone = models.CharField(verbose_name='Внутренний номер телефона', max_length=3, help_text='', blank=True,
                                      default='', )
    job = models.ForeignKey(Job, verbose_name='Должность', on_delete=models.SET_NULL, null=True, help_text='',
                            blank=True)
    divisions = models.ForeignKey(Division, verbose_name='Подразделение', on_delete=models.SET_NULL, null=True,
                                  help_text='', blank=True)
    work_email_password = models.CharField(verbose_name='Пароль от корпоративной почты', max_length=50, blank=True,
                                           default='')
    personal_work_schedule_start = models.TimeField(verbose_name='Начало рабочего времени', default=get_time('9:30:00'))
    personal_work_schedule_end = models.TimeField(verbose_name='Окончание рабочего времени', default=get_time('18:00:00'))


class DataBaseUser(AbstractUser):
    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    type_of = [
        ('natural_person', 'физическое лицо'),
        ('staff_member', 'штатный сотрудник'),
        ('freelancer', 'внештатный сотрудник')
    ]
    type_of_gender = [
        ('male', 'мужской'),
        ('female', 'женский')
    ]
    ref_key = models.CharField(verbose_name='Уникальный номер', max_length=37, default='')
    person_ref_key = models.CharField(verbose_name='Уникальный номер физ лица', max_length=37, default='')
    service_number = models.CharField(verbose_name='Табельный номер', max_length=10, default='', blank=True)
    surname = models.CharField(verbose_name='Отчество', max_length=40, blank=True, default='', help_text='')
    avatar = models.ImageField(upload_to='users_avatars', blank=True, help_text='')
    birthday = models.DateField(verbose_name='День рождения', blank=True, null=True, help_text='')

    user_access = models.ForeignKey(AccessLevel, verbose_name='Права доступа', help_text='',
                                        blank=True, on_delete=models.SET_NULL, null=True)
    address = models.TextField(verbose_name='Адрес', null=True, blank=True)
    type_users = models.CharField(verbose_name='Тип пользователя', max_length=40, choices=type_of, help_text='',
                                  blank=True, default='')
    personal_phone = models.CharField(verbose_name='Личный номер телефона', max_length=15, help_text='', blank=True,
                                      default='', )
    gender = models.CharField(verbose_name='Пол', max_length=7, blank=True, choices=type_of_gender,
                              help_text='', default='')
    user_profile = models.OneToOneField(DataBaseUserProfile, verbose_name='Личный профиль пользователя',
                                        on_delete=models.SET_NULL, null=True, blank=True)
    user_work_profile = models.OneToOneField(DataBaseUserWorkProfile, verbose_name='Рабочий профиль пользователя',
                                             on_delete=models.SET_NULL, null=True, blank=True)
    passphrase = models.CharField(verbose_name='Парольная фраза', max_length=256, default='', blank=True)
    telegram_id = models.CharField(verbose_name='Telegram ID', max_length=20, blank=True)

    def __str__(self):
        return f'{empty_item(self.last_name)} {empty_item(self.first_name)} {empty_item(self.surname)}'

    def get_title(self):
        return f'{empty_item(self.last_name)} {empty_item(self.first_name)} {empty_item(self.surname)}'

    def get_data(self):
        return {
            'pk': self.pk,
            'number': self.service_number,
            'person': self.get_title(),
            'division': str(self.user_work_profile.divisions),
            'job': str(self.user_work_profile.job),
            'phone': str(self.user_work_profile.internal_phone),
            'email': self.email,
            'password': str(self.user_work_profile.work_email_password),
        }

    def get_absolute_url(self):
        return reverse('customers_app:staff_list')


def rename(file_name, path_name, instance, pfx):
    try:
        if instance.avatar:
            # Получаем расширение файла
            ext = file_name.split('.')[-1]
            # Формируем уникальное окончание файла. Длинна в 7 символов. В окончании номер записи: рк, спереди дополняющие нули
            filename = f'{instance.username}.{ext}'
            if file_name:
                try:
                    pathlib.Path.rename(pathlib.Path.joinpath(BASE_DIR, 'media', path_name, file_name),
                                        pathlib.Path.joinpath(BASE_DIR, 'media', path_name, filename))
                except Exception as _ex0:
                    print(_ex0)
            instance.avatar = f'users_avatars/{filename}'
            if file_name != filename:
                instance.save()

    except Exception as _ex:
        print(_ex)


@receiver(post_save, sender=DataBaseUser)
def change_filename(sender, instance, **kwargs):
    try:
        # Получаем имя сохраненного файла
        file_name = pathlib.Path(instance.avatar.name).name
        # Получаем путь к файлу
        path_name = pathlib.Path(instance.avatar.name).parent
        rename(file_name, path_name, instance, '')

    except Exception as _ex:
        print(_ex)


class Counteragent(models.Model):
    class Meta:
        verbose_name = 'Контрагент'
        verbose_name_plural = 'Контрагенты'

    type_of = [
        ('juridical_person', 'юридическое лицо'),
        ('physical_person', 'физическое лицо'),
        ('separate_subdivision', 'обособленное подразделение'),
        ('government_agency', 'государственный орган'),
    ]

    ref_key = models.CharField(verbose_name='Уникальный номер', max_length=37, default='')
    short_name = models.CharField(verbose_name='Наименование', max_length=150, default='', help_text='')
    full_name = models.CharField(verbose_name='Полное наименование', max_length=250, default='', help_text='')
    inn = models.CharField(verbose_name='ИНН', max_length=12, blank=True, default='', help_text='')
    kpp = models.CharField(verbose_name='КПП', max_length=9, blank=True, default='', help_text='')
    ogrn = models.CharField(verbose_name='ОГРН', max_length=15, blank=True, default='', help_text='')
    type_counteragent = models.CharField(verbose_name='Тип контрагента', max_length=40, choices=type_of, help_text='',
                                         default='')
    juridical_address = models.TextField(verbose_name='Юридический адрес', default='', blank=True)
    physical_address = models.TextField(verbose_name='Физический адрес', default='', blank=True)
    email = models.EmailField(verbose_name='Email', default='', blank=True)
    phone = models.CharField(verbose_name='Корпоративный номер телефона', max_length=15, help_text='', blank=True,
                             default='', )
    base_counteragent = models.BooleanField(verbose_name='Основная организация', default=False)
    director = models.ForeignKey(DataBaseUser, verbose_name='Директор', on_delete=models.SET_NULL, null=True,
                                 blank=True, related_name='direct')
    accountant = models.ForeignKey(DataBaseUser, verbose_name='Бухгалтер', on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name='account')
    contact_person = models.ForeignKey(DataBaseUser, verbose_name='Контактное лицо', on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='contact')

    def __str__(self):
        return f'{self.short_name}'

    def get_data(self):
        return {
            'pk': self.pk,
            'short_name': self.full_name,
            'inn': self.inn,
            'kpp': self.kpp,
        }


class Posts(models.Model):
    class Meta:
        verbose_name = 'Новость'
        verbose_name_plural = 'Сообщения'

    creation_date = models.DateField(verbose_name='Дата создания', auto_now_add=True)
    post_description = models.TextField(verbose_name='Текст сообщения', blank=True, default='')
    post_divisions = models.ManyToManyField(Division, verbose_name='Подразделения поста', )
    allowed_placed = models.BooleanField(verbose_name='Разрешение на публикацию', default=False)
    responsible = models.ForeignKey(DataBaseUser, verbose_name='Ответственное лицо',
                                    on_delete=models.SET_NULL,
                                    null=True, related_name='responsible_person')
    post_date_start = models.DateField(verbose_name='Дата начала отображения', blank=True, null=True)
    post_date_end = models.DateField(verbose_name='Дата окончания отображения', blank=True, null=True)

    def __str__(self):
        return f'{self.creation_date} / {self.pk}'


class HistoryChange(models.Model):
    """
    Модель HistoryChange - введена для возможности отследить изменения моделей.
    """

    class Meta:
        verbose_name = 'История'
        verbose_name_plural = 'Список истории'

    date_add = models.DateTimeField(verbose_name='Время добавления', auto_now_add=True)
    author = models.ForeignKey(DataBaseUser, verbose_name='Автор', on_delete=models.SET_NULL, null=True, blank=True, related_name='author_changes')
    body = models.TextField(blank=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    def __str__(self):
        return f"{str(self.content_type.name)} : {str(self.content_object)}"
