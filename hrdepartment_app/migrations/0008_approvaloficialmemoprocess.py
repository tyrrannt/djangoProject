# Generated by Django 4.1.3 on 2022-11-21 19:53

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('hrdepartment_app', '0007_alter_officialmemo_comments'),
    ]

    operations = [
        migrations.CreateModel(
            name='ApprovalOficialMemoProcess',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('process_accepted', models.BooleanField(default=False, verbose_name='Активность')),
                ('document', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='hrdepartment_app.officialmemo', verbose_name='Документ')),
                ('person_agreement', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='person_agreement', to=settings.AUTH_USER_MODEL, verbose_name='Согласующее лицо')),
                ('person_department_staff', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='person_department_staff', to=settings.AUTH_USER_MODEL, verbose_name='Сотрудник ОК')),
                ('person_distributor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='person_distributor', to=settings.AUTH_USER_MODEL, verbose_name='Сотрудник ОНО')),
                ('person_executor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='person_executor', to=settings.AUTH_USER_MODEL, verbose_name='Исполнитель')),
            ],
            options={
                'verbose_name': 'Служебная записка по служебной поездке',
                'verbose_name_plural': 'Служебные записки по служебным поездкам',
            },
        ),
    ]