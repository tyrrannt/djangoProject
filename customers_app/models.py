from django.db import models
from django.contrib.auth.models import AbstractUser


# Create your models here.


class DataBaseUser(AbstractUser):
    avatar = models.ImageField(upload_to='users_avatars', blank=True)
    age = models.PositiveIntegerField(verbose_name='возраст')
