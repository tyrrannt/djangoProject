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


class PhoneNumber(models.Model):
    number = models.CharField(verbose_name='Номер телефона', max_length=15)

    def __str__(self):
        return f'{self.number}'


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

    def __init__(self, *args, **kwargs):
        super(Division, self).__init__(*args, **kwargs)


class Work(models.Model):
    job = models.ForeignKey(Job, verbose_name='должность', on_delete=models.SET_NULL, null=True, help_text='')
    divisions = models.ForeignKey(Division, verbose_name='подразделение', on_delete=models.SET_NULL, null=True,
                                  help_text='')

    def __str__(self):
        return f'{self.job} / {self.divisions}'


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
    access_right = models.ManyToManyField(AccessLevel, verbose_name='права доступа', default=0, help_text='')
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, help_text='')
    type_users = models.CharField(verbose_name='тип пользователя', max_length=40, choices=type_of, help_text='', blank=True, null=True,)
    phone = models.OneToOneField(PhoneNumber, verbose_name='номер телефона', on_delete=models.SET_NULL, null=True,
                                 related_name='cell')
    corp_phone = models.OneToOneField(PhoneNumber, verbose_name='корпоративный номер', on_delete=models.SET_NULL,
                                      null=True, related_name='corp')
    works = models.ForeignKey(Work, verbose_name='занятость', on_delete=models.SET_NULL, blank=True, null=True)
    gender = models.CharField(verbose_name='пол', max_length=7, blank=True, choices=type_of_gender, help_text='')

    def __str__(self):
        return f'{self.last_name} {self.first_name} {self.surname}'
