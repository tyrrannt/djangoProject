# Generated by Django 4.0.6 on 2022-07-14 19:38

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0010_tasks'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='tasks',
            name='owner',
        ),
        migrations.AddField(
            model_name='tasks',
            name='creator',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='creator_person', to=settings.AUTH_USER_MODEL, verbose_name='Создатель задачи'),
        ),
        migrations.AddField(
            model_name='tasks',
            name='executor',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='executor_person', to=settings.AUTH_USER_MODEL, verbose_name='Исполнитель задачи'),
        ),
    ]