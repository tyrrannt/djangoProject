from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.hashers import make_password


# Create your models here.
class Country(models.Model):
    code = models.CharField(verbose_name='код', max_length=3, blank=True, null=True, help_text='')
    name = models.CharField(verbose_name='страна', max_length=30, blank=True, null=True, help_text='')

    def __str__(self):
        return self.name


class City(models.Model):
    city_id = models.IntegerField(verbose_name='')
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, help_text='')
    city_name = models.CharField(verbose_name='город', max_length=30, blank=True, null=True, help_text='')

    def __str__(self):
        return self.city_name


class AccessLevel(models.Model):
    level = models.PositiveIntegerField(verbose_name='Уровень доступа', default=0)
    description = models.TextField(verbose_name='Описание категории', blank=True)

    def __str__(self):
        return self.description


class Address(models.Model):
    postal_code = models.CharField(verbose_name='индекс', max_length=6, blank=True, null=True, help_text='')
    country = models.ForeignKey(Country, verbose_name='страна', on_delete=models.SET_NULL, null=True, help_text='')
    region = models.CharField(verbose_name='область', max_length=30, blank=True, null=True, help_text='')
    district = models.CharField(verbose_name='район', max_length=30, blank=True, null=True, help_text='')
    microdistrict = models.CharField(verbose_name='микрорайон', max_length=30, blank=True, null=True, help_text='')
    city = models.ForeignKey(City, verbose_name='город', on_delete=models.SET_NULL, null=True, help_text='')
    street = models.CharField(verbose_name='улица', max_length=60, blank=True, null=True, help_text='')
    house = models.CharField(verbose_name='дом', max_length=6, blank=True, null=True, help_text='')
    apartment = models.CharField(verbose_name='квартира', max_length=3, blank=True, null=True, help_text='')
    history = models.DateField(verbose_name="Дата создания", auto_created=True, null=True)

    def __str__(self):
        result = ''
        if self.postal_code:
            result += f'{self.postal_code}'
        if self.country:
            result += f', {self.country}'
        if self.region:
            result += f', {self.region}'
        if self.city:
            result += f', г. {self.city}'
        if self.street:
            result += f', ул. {self.street}'
        if self.house:
            result += f', д. {self.house}'
        if self.apartment:
            result += f', кв. {self.apartment}'

        return result


class Job(models.Model):
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

    def __init__(self, *args, **kwargs):
        super(Division, self).__init__(*args, **kwargs)


class DataBaseUser(AbstractUser):
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
    access_right = models.ManyToManyField(AccessLevel, verbose_name='права доступа', default=0, help_text='',
                                          blank=True)
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, blank=True, null=True, help_text='')
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
    juridical_address = models.ForeignKey(Address, verbose_name='Юридический адрес', on_delete=models.SET_NULL,
                                          null=True, related_name='juridical')
    physical_address = models.ForeignKey(Address, verbose_name='Физический адрес', on_delete=models.SET_NULL, null=True,
                                         related_name='physical')
    email = models.EmailField(verbose_name='Email', null=True)
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
        return f'{self.short_name}, {self.inn}/{self.kpp}'

class Posts(models.Model):
    creation_date = models.DateField(verbose_name='Дата создания', auto_created=True)
    post_description = models.TextField(verbose_name='Текст поста', blank=True)
    post_divisions = models.ManyToManyField(Division, verbose_name='Подразделения поста', )

    def __str__(self):
        return f'{self.creation_date} / {self.pk}'



