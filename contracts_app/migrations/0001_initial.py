# Generated by Django 4.0.6 on 2022-07-17 12:18

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('customers_app', '0014_delete_tasks'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TypeContract',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type_contract', models.CharField(blank=True, max_length=50, null=True, verbose_name='Тип договора')),
            ],
        ),
        migrations.CreateModel(
            name='TypeProperty',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type_property', models.CharField(blank=True, max_length=50, null=True, verbose_name='Тип имущества')),
            ],
        ),
        migrations.CreateModel(
            name='Estate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('release_date', models.DateField(verbose_name='дата выпуска')),
                ('type_property', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                    to='contracts_app.typeproperty')),
            ],
        ),
        migrations.CreateModel(
            name='Contract',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('internal_number',
                 models.CharField(blank=True, max_length=50, null=True, verbose_name='Номер в папке')),
                ('contract_number',
                 models.CharField(blank=True, max_length=50, null=True, verbose_name='Номер договора')),
                ('date_conclusion', models.DateField(verbose_name='Дата заключения договора')),
                ('subject_contract', models.TextField(blank=True, verbose_name='Предмет договора')),
                ('cost', models.FloatField(default=0, verbose_name='Стоимость')),
                ('closing_date', models.DateField(verbose_name='Дата закрытия договора')),
                ('prolongation',
                 models.CharField(blank=True, choices=[('auto', 'Автоматическая пролонгация'), ('ag', 'Оформление ДС')],
                                  max_length=40, null=True, verbose_name='Пролонгация')),
                ('comment', models.TextField(blank=True, verbose_name='Примечание')),
                ('date_entry', models.DateField(auto_now_add=True, verbose_name='Дата ввода информации')),
                ('doc_file', models.FileField(blank=True, upload_to='library', verbose_name='Файл документа')),
                ('contract_counteragent', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                            to='customers_app.counteragent',
                                                            verbose_name='Сторона договора')),
                ('employee', models.ManyToManyField(to=settings.AUTH_USER_MODEL, verbose_name='Ответственное лицо')),
                ('type_of_contract', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                       to='contracts_app.typecontract', verbose_name='Тип договора')),
                ('type_property', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                    to='contracts_app.typeproperty')),
            ],
        ),
    ]
