from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.hashers import make_password
from django.urls import reverse
from contracts_app.templatetags.custom import empty_item


class AccessLevel(models.Model):
    class Meta:
        verbose_name = 'Уровень доступа'
        verbose_name_plural = 'Уровни доступа'

    level = models.PositiveIntegerField(verbose_name='Уровень доступа', default=0)
    name = models.CharField(verbose_name='', max_length=26, blank=True, default='')
    description = models.TextField(verbose_name='Описание категории', blank=True)

    def __str__(self):
        return self.name


class UserAccessMode(models.Model):
    class Meta:
        verbose_name = 'Уровень доступа пользователя'
        verbose_name_plural = 'Уровни доступа пользователей'

    # Права доступа к договорам
    contracts_access_view = models.ForeignKey(AccessLevel, verbose_name='Уровень доступа к договорам', blank=True,
                                              null=True, on_delete=models.CASCADE, related_name='contracts_view')
    contracts_access_add = models.BooleanField(verbose_name='Разрешение на создание договора', default=False)
    contracts_access_edit = models.BooleanField(verbose_name='Разрешение на редактирование договора', default=False)
    contracts_access_agreement = models.BooleanField(verbose_name='Право на публикацию договора', default=False)
    # Права доступа к сообщениям
    posts_access_view = models.ForeignKey(AccessLevel, verbose_name='Уровень доступа к сообщениям', blank=True,
                                          null=True, on_delete=models.CASCADE, related_name='posts_view')
    posts_access_add = models.BooleanField(verbose_name='Разрешение на создание сообщения', default=False)
    posts_access_edit = models.BooleanField(verbose_name='Разрешение на редактирование сообщения', default=False)
    posts_access_agreement = models.BooleanField(verbose_name='Право на публикацию сообщения', default=False)
    # Права доступа к справочникам
    guide_access_view = models.ForeignKey(AccessLevel, verbose_name='Уровень доступа к справочникам', blank=True,
                                          null=True, on_delete=models.CASCADE, related_name='guide_view')
    guide_access_add = models.BooleanField(verbose_name='Разрешение на создание записи в справочнике', default=False)
    guide_access_edit = models.BooleanField(verbose_name='Разрешение на редактирование записи в справочнике',
                                            default=False)
    guide_access_agreement = models.BooleanField(verbose_name='Право на публикацию записи в справочнике', default=False)

    def get_absolute_url(self):
        return reverse('customers_app:staff', kwargs={'pk': self.databaseuser.pk})


class Job(models.Model):
    class Meta:
        verbose_name = 'Должность'
        verbose_name_plural = 'Должности'

    code = models.CharField(verbose_name='код должности', max_length=5, help_text='', default='')
    name = models.CharField(verbose_name='должность', max_length=200, help_text='')

    def __str__(self):
        return f'{self.name}'


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

    parent_category = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(verbose_name='Название категории', max_length=128, unique=True)
    description = models.TextField(verbose_name='Описание категории', blank=True)
    history = models.DateField(verbose_name="Дата создания", auto_created=True, null=True)
    active = models.BooleanField(verbose_name='Активность', default=True)

    def __str__(self):
        return self.name


class Division(Category):
    """
    Класс Division - содержит подразделения компании
    """

    class Meta:
        verbose_name = 'Подразделение'
        verbose_name_plural = 'Подразделения организации'

    def __init__(self, *args, **kwargs):
        super(Division, self).__init__(*args, **kwargs)


class Citizenships(models.Model):
    class Meta:
        verbose_name = 'Гражданство пользователя'
        verbose_name_plural = 'Гражданства пользователей'

    city = models.CharField(verbose_name='Страна', max_length=50)


class IdentityDocuments(models.Model):
    class Meta:
        verbose_name = 'Паспорт пользователя'
        verbose_name_plural = 'Паспорта пользователей'

    series = models.CharField(verbose_name='Серия', max_length=4, default='')
    number = models.CharField(verbose_name='Номер', max_length=6, default='')
    issued_by_whom = models.CharField(verbose_name='Кем выдан', max_length=250, default='')
    date_of_issue = models.DateField(verbose_name='Дата выдачи')
    division_code = models.CharField(verbose_name='Код подразделения', max_length=7, default='')


class DataBaseUserProfile(models.Model):
    class Meta:
        verbose_name = 'Профиль пользователя'
        verbose_name_plural = 'Профили пользователей'

    citizenship = models.ForeignKey(Citizenships, verbose_name='Гражданство', blank=True, on_delete=models.CASCADE)
    passport = models.OneToOneField(IdentityDocuments, verbose_name='Паспорт', blank=True, on_delete=models.CASCADE)
    snils = models.CharField(verbose_name='СНИЛС', max_length=14, blank=True, default='')
    oms = models.CharField(verbose_name='Полис ОМС', max_length=24, blank=True, default='')
    inn = models.CharField(verbose_name='ИНН', max_length=12, blank=True, default='')


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
    surname = models.CharField(verbose_name='Отчество', max_length=40, blank=True, default='', help_text='')
    avatar = models.ImageField(upload_to='users_avatars', blank=True, help_text='')
    birthday = models.DateField(verbose_name='День рождения', blank=True, null=True, help_text='')
    access_level = models.OneToOneField(UserAccessMode, verbose_name='Права доступа', help_text='',
                                        blank=True, on_delete=models.SET_NULL, null=True)
    address = models.TextField(verbose_name='Адрес', null=True, blank=True)
    type_users = models.CharField(verbose_name='Тип пользователя', max_length=40, choices=type_of, help_text='',
                                  blank=True, default='')
    internal_phone = models.CharField(verbose_name='Внутренний номер телефона', max_length=3, help_text='', blank=True,
                                      default='', )
    work_phone = models.CharField(verbose_name='Корпоративный номер телефона', max_length=15, help_text='', blank=True,
                                  default='', )
    personal_phone = models.CharField(verbose_name='Личный номер телефона', max_length=15, help_text='', blank=True,
                                      default='', )
    job = models.ForeignKey(Job, verbose_name='Должность', on_delete=models.SET_NULL, null=True, help_text='',
                            blank=True)
    divisions = models.ForeignKey(Division, verbose_name='Подразделение', on_delete=models.SET_NULL, null=True,
                                  help_text='', blank=True)
    gender = models.CharField(verbose_name='Пол', max_length=7, blank=True, choices=type_of_gender,
                              help_text='', default='')
    user_profile = models.OneToOneField(DataBaseUserProfile, verbose_name='Личный профиль пользователя',
                                        on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f'{empty_item(self.last_name)} {empty_item(self.first_name)} {empty_item(self.surname)}'


class Counteragent(models.Model):
    class Meta:
        verbose_name = 'Контрагент'
        verbose_name_plural = 'Контрагенты'

    short_name = models.CharField(verbose_name='Наименование', max_length=150, default='', help_text='')
    full_name = models.CharField(verbose_name='Полное наименование', max_length=250, default='', help_text='')
    inn = models.CharField(verbose_name='ИНН', max_length=12, blank=True, default='', help_text='')
    kpp = models.CharField(verbose_name='КПП', max_length=9, blank=True, default='', help_text='')
    type_of = [
        ('juridical_person', 'юридическое лицо'),
        ('physical_person', 'физическое лицо'),
        ('separate_subdivision', 'обособленное подразделение'),
        ('government_agency', 'государственный орган'),
    ]
    type_counteragent = models.CharField(verbose_name='Тип контрагента', max_length=40, choices=type_of, help_text='',
                                         default='')
    juridical_address = models.TextField(verbose_name='Юридический адрес', default='', blank=True)
    physical_address = models.TextField(verbose_name='Физический адрес', default='', blank=True)
    email = models.EmailField(verbose_name='Email', default='', blank=True)
    phone = models.CharField(verbose_name='Корпоративный номер телефона', max_length=15, help_text='', blank=True,
                             default='', )
    base_counteragent = models.BooleanField(verbose_name='Основная организация', default=False)
    director = models.ForeignKey(DataBaseUser, verbose_name='Директор', on_delete=models.SET_NULL, null=True,
                                 blank=True,
                                 related_name='direct')
    accountant = models.ForeignKey(DataBaseUser, verbose_name='Бухгалтер', on_delete=models.SET_NULL, null=True,
                                   blank=True,
                                   related_name='account')
    contact_person = models.ForeignKey(DataBaseUser, verbose_name='Контактное лицо', on_delete=models.SET_NULL,
                                       null=True,
                                       blank=True, related_name='contact')

    def __str__(self):
        return f'{self.short_name}'


class Posts(models.Model):
    class Meta:
        verbose_name = 'Новость'
        verbose_name_plural = 'Сообщения'

    creation_date = models.DateField(verbose_name='Дата создания', auto_now_add=True)
    post_description = models.TextField(verbose_name='Текст поста', blank=True, default='')
    post_divisions = models.ManyToManyField(Division, verbose_name='Подразделения поста', )
    allowed_placed = models.BooleanField(verbose_name='Разрешение на публикацию', default=False)

    def __str__(self):
        return f'{self.creation_date} / {self.pk}'
