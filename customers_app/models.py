from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.hashers import make_password


class AccessLevel(models.Model):
    class Meta:
        verbose_name = 'Уровень доступа'
        verbose_name_plural = 'Уровни доступа'

    level = models.PositiveIntegerField(verbose_name='Уровень доступа', default=0)
    name = models.CharField(verbose_name='', max_length=26, blank=True)
    description = models.TextField(verbose_name='Описание категории', blank=True)

    def __str__(self):
        return self.name


class UserAccessMode(models.Model):
    class Meta:
        verbose_name = 'Уровень доступа пользователя'
        verbose_name_plural = 'Уровни доступа пользователей'

    access_level = [
        ('0', 'Административный доступ'),
        ('1', 'Особой важности'),
        ('2', 'Совершенно секретные'),
        ('3', 'Секретные'),
        ('4', 'Для служебного пользования')
    ]
    # Права доступа к договорам
    contracts_access_view = models.CharField(verbose_name='Уровень доступа к договорам', choices=access_level,
                                             help_text='', blank=True, null=True, max_length=1, default='4')
    contracts_access_add = models.BooleanField(verbose_name='Разрешение на создание договора', default=False)
    contracts_access_edit = models.BooleanField(verbose_name='Разрешение на редактирование договора', default=False)
    contracts_access_agreement = models.BooleanField(verbose_name='Право на публикацию договора', default=False)
    # Права доступа к сообщениям
    posts_access_view = models.CharField(verbose_name='Уровень доступа к сообщениям', choices=access_level,
                                             help_text='', blank=True, null=True, max_length=1, default='4')
    posts_access_add = models.BooleanField(verbose_name='Разрешение на создание сообщения', default=False)
    posts_access_edit = models.BooleanField(verbose_name='Разрешение на редактирование сообщения', default=False)
    posts_access_agreement = models.BooleanField(verbose_name='Право на публикацию сообщения', default=False)
    # Права доступа к справочникам
    guide_access_view = models.CharField(verbose_name='Уровень доступа к справочникам', choices=access_level,
                                         help_text='', blank=True, null=True, max_length=1, default='4')
    guide_access_add = models.BooleanField(verbose_name='Разрешение на создание записи в справочнике', default=False)
    guide_access_edit = models.BooleanField(verbose_name='Разрешение на редактирование записи в справочнике', default=False)
    guide_access_agreement = models.BooleanField(verbose_name='Право на публикацию записи в справочнике', default=False)

    def __str__(self):
        name = ''
        name += self.contracts_access_view
        if self.contracts_access_add:
            name += '1'
        else:
            name += '0'
        if self.contracts_access_edit:
            name += '1'
        else:
            name += '0'
        if self.contracts_access_agreement:
            name += '1'
        else:
            name += '0'
        return f'{name}'

class Job(models.Model):
    class Meta:
        verbose_name = 'Должность'
        verbose_name_plural = 'Должности'

    code = models.CharField(verbose_name='код должности', max_length=100, help_text='', default='000')
    name = models.CharField(verbose_name='должность', max_length=100, help_text='')

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
    access = models.ForeignKey(AccessLevel, default=0, on_delete=models.SET_DEFAULT, verbose_name='Категория доступа')
    hash_view = models.CharField(max_length=256, blank=True)
    history = models.DateField(verbose_name="Дата создания", auto_created=True, null=True)

    def __str__(self):
        if self.parent_category:
            return f'{self.parent_category}/{self.name}'
        else:
            return self.name

    def save(self, **kwargs):
        some_salt = 'some_salt'
        self.hash_view = make_password(self.name, some_salt)
        super().save(**kwargs)


class Division(Category):
    """
    Класс Division - содержит подразделения компании
    """

    class Meta:
        verbose_name = 'Подразделение'
        verbose_name_plural = 'Подразделения организации'

    def __init__(self, *args, **kwargs):
        super(Division, self).__init__(*args, **kwargs)


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
    surname = models.CharField(verbose_name='отчество', max_length=40, blank=True, null=True, help_text='')
    avatar = models.ImageField(upload_to='users_avatars', blank=True, help_text='')
    birthday = models.DateField(verbose_name='день рождения', blank=True, null=True, help_text='')
    access_right = models.ForeignKey(AccessLevel, verbose_name='права доступа', help_text='',
                                     blank=True, on_delete=models.SET_NULL, null=True)
    access_level = models.OneToOneField(UserAccessMode, verbose_name='права доступа', help_text='',
                                     blank=True, on_delete=models.SET_NULL, null=True)
    address = models.TextField(verbose_name='Адрес', null=True, blank=True)
    type_users = models.CharField(verbose_name='тип пользователя', max_length=40, choices=type_of, help_text='',
                                  blank=True, null=True, )
    internal_phone = models.CharField(verbose_name='Внутренний номер телефона', max_length=3, help_text='', blank=True,
                                      null=True, )
    work_phone = models.CharField(verbose_name='Корпоративный номер телефона', max_length=15, help_text='', blank=True,
                                  null=True, )
    personal_phone = models.CharField(verbose_name='Личный номер телефона', max_length=15, help_text='', blank=True,
                                      null=True, )
    job = models.ForeignKey(Job, verbose_name='должность', on_delete=models.SET_NULL, null=True, help_text='')
    divisions = models.ForeignKey(Division, verbose_name='подразделение', on_delete=models.SET_NULL, null=True,
                                  help_text='')
    gender = models.CharField(verbose_name='пол', max_length=7, blank=True, null=True, choices=type_of_gender,
                              help_text='', default='')

    def __str__(self):
        return f'{self.last_name} {self.first_name} {self.surname}'


class Counteragent(models.Model):
    class Meta:
        verbose_name = 'Контрагент'
        verbose_name_plural = 'Контрагенты'

    short_name = models.CharField(verbose_name='Наименование', max_length=150, default='', help_text='')
    full_name = models.CharField(verbose_name='Полное наименование', max_length=250, default='', help_text='')
    inn = models.CharField(verbose_name='ИНН', max_length=12, blank=True, null=True, help_text='')
    kpp = models.CharField(verbose_name='КПП', max_length=9, blank=True, null=True, help_text='')
    type_of = [
        ('juridical_person', 'юридическое лицо'),
        ('physical_person', 'физическое лицо'),
        ('separate_subdivision', 'обособленное подразделение'),
        ('government_agency', 'государственный орган'),
    ]
    type_counteragent = models.CharField(verbose_name='Тип контрагента', max_length=40, choices=type_of, help_text='')
    juridical_address = models.TextField(verbose_name='Юридический адрес', null=True, blank=True)
    physical_address = models.TextField(verbose_name='Физический адрес', null=True, blank=True)
    email = models.EmailField(verbose_name='Email', null=True, blank=True)
    phone = models.CharField(verbose_name='Корпоративный номер телефона', max_length=15, help_text='', blank=True,
                             null=True, )
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
    post_description = models.TextField(verbose_name='Текст поста', blank=True)
    post_divisions = models.ManyToManyField(Division, verbose_name='Подразделения поста', )
    allowed_placed = models.BooleanField(verbose_name='Разрешение на публикацию', default=False)

    def __str__(self):
        return f'{self.creation_date} / {self.pk}'
