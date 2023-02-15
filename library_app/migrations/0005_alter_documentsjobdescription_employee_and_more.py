# Generated by Django 4.1.6 on 2023-02-15 22:45

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import library_app.models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('contracts_app', '0002_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('customers_app', '0011_posts_post_date_end_posts_post_date_start_and_more'),
        ('library_app', '0004_documentsjobdescription_document_job_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documentsjobdescription',
            name='employee',
            field=models.ManyToManyField(blank=True, related_name='%(app_label)s_%(class)s_employee', to=settings.AUTH_USER_MODEL, verbose_name='Ответственное лицо'),
        ),
        migrations.AlterField(
            model_name='documentsjobdescription',
            name='executor',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_executor', to=settings.AUTH_USER_MODEL, verbose_name='Исполнитель'),
        ),
        migrations.CreateModel(
            name='DocumentsOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ref_key', models.UUIDField(default=uuid.uuid4, unique=True, verbose_name='Уникальный номер')),
                ('date_entry', models.DateField(auto_now_add=True, verbose_name='Дата ввода информации')),
                ('document_date', models.DateField(default='', verbose_name='Дата документа')),
                ('document_name', models.CharField(default='', max_length=200, verbose_name='Наименование документа')),
                ('document_number', models.CharField(default='', max_length=10, verbose_name='Номер документа')),
                ('doc_file', models.FileField(blank=True, upload_to=library_app.models.document_directory_path, verbose_name='Файл документа')),
                ('allowed_placed', models.BooleanField(default=False, verbose_name='Разрешение на публикацию')),
                ('validity_period_start', models.DateField(default='', verbose_name='Документ действует с')),
                ('validity_period_end', models.DateField(default='', verbose_name='Документ действует по')),
                ('actuality', models.BooleanField(default=False, verbose_name='Актуальность')),
                ('previous_document', models.URLField(blank=True, verbose_name='Предшествующий документ')),
                ('document_order_type', models.CharField(choices=[('1', 'Общая деятельность'), ('2', 'Личный состав')], max_length=18, verbose_name='Тип приказа')),
                ('access', models.ForeignKey(default=5, null=True, on_delete=django.db.models.deletion.SET_NULL, to='customers_app.accesslevel', verbose_name='Уровень доступа к документу')),
                ('document_division', models.ManyToManyField(to='customers_app.division', verbose_name='Принадлежность к подразделению')),
                ('employee', models.ManyToManyField(blank=True, related_name='%(app_label)s_%(class)s_employee', to=settings.AUTH_USER_MODEL, verbose_name='Ответственное лицо')),
                ('executor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_executor', to=settings.AUTH_USER_MODEL, verbose_name='Исполнитель')),
                ('type_of_document', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='contracts_app.typedocuments', verbose_name='Тип документа')),
            ],
            options={
                'verbose_name': 'Приказ',
                'verbose_name_plural': 'Приказы',
            },
        ),
    ]
