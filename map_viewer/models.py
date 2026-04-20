import os
from django.conf import settings
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class MapSource(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название карты")
    # Указываем относительный путь внутри media/maps/
    db_filename = models.CharField(
        max_length=255,
        verbose_name="Имя файла БД (например, city.sqlite)"
    )
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='maps')
    is_active = models.BooleanField(default=True)

    @property
    def full_path(self):
        return os.path.join(settings.MEDIA_ROOT, 'maps', self.db_filename)

    def __str__(self):
        return self.name