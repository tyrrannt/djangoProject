# Generated by Django 4.2.1 on 2023-06-17 11:46

from django.db import migrations, models
import library_app.models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('library_app', '0003_alter_hashtag_options_alter_helpcategory_options_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentForm',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ref_key', models.UUIDField(default=uuid.uuid4, unique=True, verbose_name='Уникальный номер')),
                ('title', models.CharField(default='Бланк ', max_length=200, verbose_name='Наименование')),
                ('draft', models.FileField(blank=True, upload_to=library_app.models.draft_directory_path, verbose_name='Черновик')),
                ('scan', models.FileField(blank=True, upload_to=library_app.models.scan_directory_path, verbose_name='Скан копия')),
                ('sample', models.URLField(blank=True, verbose_name='Образец заполнения')),
            ],
            options={
                'verbose_name': 'Бланк документа',
                'verbose_name_plural': 'Бланки документов',
            },
        ),
    ]