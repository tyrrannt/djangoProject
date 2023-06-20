# Generated by Django 4.2.1 on 2023-06-19 13:23

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('library_app', '0004_documentform'),
    ]

    operations = [
        migrations.AddField(
            model_name='documentform',
            name='employee',
            field=models.ManyToManyField(blank=True, related_name='%(app_label)s_%(class)s_employee', to=settings.AUTH_USER_MODEL, verbose_name='Ответственное лицо'),
        ),
        migrations.AddField(
            model_name='documentform',
            name='executor',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_executor', to=settings.AUTH_USER_MODEL, verbose_name='Исполнитель'),
        ),
    ]
