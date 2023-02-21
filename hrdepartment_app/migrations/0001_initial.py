# Generated by Django 4.1.6 on 2023-02-21 07:41

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import hrdepartment_app.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('customers_app', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MedicalOrganisation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ref_key', models.CharField(default='', max_length=37, verbose_name='Уникальный номер')),
                ('description', models.CharField(default='', max_length=200, verbose_name='Наименование')),
                ('ogrn', models.CharField(default='', max_length=13, verbose_name='ОГРН')),
                ('address', models.CharField(default='', max_length=250, verbose_name='Адрес')),
                ('email', models.EmailField(default='0', max_length=254, verbose_name='Email')),
                ('phone', models.CharField(default='0', max_length=15, verbose_name='Телефон')),
            ],
            options={
                'verbose_name': 'Медицинская организация',
                'verbose_name_plural': 'Медицинскик организации',
            },
        ),
        migrations.CreateModel(
            name='Purpose',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=300, verbose_name='Наименование')),
            ],
            options={
                'verbose_name': 'Цель служебной записки',
                'verbose_name_plural': 'Цели служебной записки',
            },
        ),
        migrations.CreateModel(
            name='OfficialMemo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_of_creation', models.DateTimeField(auto_now_add=True, verbose_name='Дата и время создания')),
                ('official_memo_type', models.CharField(choices=[('1', 'Направление'), ('2', 'Продление')], default='1', max_length=9, verbose_name='Тип СП')),
                ('period_from', models.DateField(null=True, verbose_name='Дата начала')),
                ('period_for', models.DateField(null=True, verbose_name='Дата окончания')),
                ('other_place_production_activity', models.CharField(blank=True, default='', max_length=20, verbose_name='Другое место назначения')),
                ('accommodation', models.CharField(blank=True, choices=[('1', 'Квартира'), ('2', 'Гостиница')], default='', max_length=9, verbose_name='Проживание')),
                ('type_trip', models.CharField(blank=True, choices=[('1', 'Служебная поездка'), ('2', 'Командировка')], default='', max_length=9, verbose_name='Тип поездки')),
                ('order_number', models.CharField(blank=True, default='', max_length=20, null=True, verbose_name='Номер приказа')),
                ('order_date', models.DateField(blank=True, null=True, verbose_name='Дата приказа')),
                ('comments', models.CharField(blank=True, default='', max_length=250, verbose_name='Примечание')),
                ('document_accepted', models.BooleanField(default=False, verbose_name='Документ принят')),
                ('person', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employee', to=settings.AUTH_USER_MODEL, verbose_name='Сотрудник')),
                ('place_production_activity', models.ManyToManyField(to='customers_app.division', verbose_name='МПД')),
                ('purpose_trip', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='hrdepartment_app.purpose', verbose_name='Цель')),
                ('responsible', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='responsible', to=settings.AUTH_USER_MODEL, verbose_name='Сотрудник')),
            ],
            options={
                'verbose_name': 'Служебная записка',
                'verbose_name_plural': 'Служебные записки',
            },
        ),
        migrations.CreateModel(
            name='Medical',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ref_key', models.CharField(default='', max_length=37, verbose_name='Уникальный номер')),
                ('number', models.CharField(default='', max_length=4, verbose_name='Номер')),
                ('date_entry', models.DateField(auto_now_add=True, null=True, verbose_name='Дата ввода информации')),
                ('date_of_inspection', models.DateField(auto_now_add=True, null=True, verbose_name='Дата осмотра')),
                ('working_status', models.CharField(blank=True, choices=[('1', 'Поступающий на работу'), ('2', 'Работающий')], default='', max_length=40, verbose_name='Статус')),
                ('view_inspection', models.CharField(blank=True, choices=[('1', 'Медицинский осмотр'), ('2', 'Психиатрическое освидетельствование')], default='', max_length=40, verbose_name='Вид осмотра')),
                ('type_inspection', models.CharField(blank=True, choices=[('1', 'Предварительный'), ('2', 'Периодический'), ('3', 'Внеплановый')], default='', max_length=15, verbose_name='Тип осмотра')),
                ('medical_direction', models.FileField(blank=True, upload_to=hrdepartment_app.models.contract_directory_path, verbose_name='Файл документа')),
                ('harmful', models.ManyToManyField(to='customers_app.harmfulworkingconditions', verbose_name='Вредные условия труда')),
                ('organisation', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='hrdepartment_app.medicalorganisation', verbose_name='Медицинская организация')),
                ('person', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Сотрудник')),
            ],
            options={
                'verbose_name': 'Медицинское направление',
                'verbose_name_plural': 'Медицинские направления',
            },
        ),
        migrations.CreateModel(
            name='BusinessProcessDirection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('business_process_type', models.CharField(blank=True, choices=[('1', 'SP')], default='', max_length=5, verbose_name='Тип бизнес процесса')),
                ('date_start', models.DateField(blank=True, null=True, verbose_name='Дата начала')),
                ('date_end', models.DateField(blank=True, null=True, verbose_name='Дата окончания')),
                ('clerk', models.ManyToManyField(related_name='clerk', to='customers_app.job', verbose_name='Делопроизводитель')),
                ('person_agreement', models.ManyToManyField(related_name='person_agreement', to='customers_app.job', verbose_name='Согласующее лицо')),
                ('person_executor', models.ManyToManyField(related_name='person_executor', to='customers_app.job', verbose_name='Исполнитель')),
            ],
            options={
                'verbose_name': 'Направление бизнес процесса',
                'verbose_name_plural': 'Направления бизнес процессов',
            },
        ),
        migrations.CreateModel(
            name='ApprovalOficialMemoProcess',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_of_creation', models.DateTimeField(auto_now_add=True, verbose_name='Дата и время создания')),
                ('submit_for_approval', models.BooleanField(default=False, verbose_name='Передан на согласование')),
                ('comments_for_approval', models.CharField(blank=True, default='', max_length=200, verbose_name='Комментарий для согласования')),
                ('document_not_agreed', models.BooleanField(default=False, verbose_name='Документ согласован')),
                ('reason_for_approval', models.CharField(blank=True, default='', max_length=200, verbose_name='Примечание к согласованию')),
                ('location_selected', models.BooleanField(default=False, verbose_name='Выбрано место проживания')),
                ('process_accepted', models.BooleanField(default=False, verbose_name='Активность')),
                ('accommodation', models.CharField(blank=True, choices=[('1', 'Квартира'), ('2', 'Гостиница')], default='', max_length=9, verbose_name='Проживание')),
                ('order_number', models.CharField(blank=True, default='', max_length=20, null=True, verbose_name='Номер приказа')),
                ('order_date', models.DateField(blank=True, null=True, verbose_name='Дата приказа')),
                ('document', models.OneToOneField(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='docs', to='hrdepartment_app.officialmemo', verbose_name='Документ')),
                ('person_agreement', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='person_agreement', to=settings.AUTH_USER_MODEL, verbose_name='Согласующее лицо')),
                ('person_department_staff', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='person_department_staff', to=settings.AUTH_USER_MODEL, verbose_name='Сотрудник ОК')),
                ('person_distributor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='person_distributor', to=settings.AUTH_USER_MODEL, verbose_name='Сотрудник ГСМ и НТ')),
                ('person_executor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='person_executor', to=settings.AUTH_USER_MODEL, verbose_name='Исполнитель')),
            ],
            options={
                'verbose_name': 'Служебная записка по служебной поездке',
                'verbose_name_plural': 'Служебные записки по служебным поездкам',
            },
        ),
    ]
