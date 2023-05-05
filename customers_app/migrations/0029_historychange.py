# Generated by Django 4.2 on 2023-05-02 19:47

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('customers_app', '0028_databaseuser_telegram_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='HistoryChange',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('body', models.TextField(blank=True)),
                ('object_id', models.PositiveIntegerField()),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='author_changes', to=settings.AUTH_USER_MODEL, verbose_name='Автор')),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype')),
            ],
            options={
                'verbose_name': 'История',
                'verbose_name_plural': 'Список истории',
            },
        ),
    ]