# Generated by Django 4.2 on 2023-05-04 20:52

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('hrdepartment_app', '0028_approvaloficialmemoprocess_date_transfer_hr_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='approvaloficialmemoprocess',
            name='date_transfer_accounting',
            field=models.DateField(blank=True, null=True, verbose_name='Дата передачи в бухгалтерию'),
        ),
        migrations.AddField(
            model_name='approvaloficialmemoprocess',
            name='hr_accepted',
            field=models.BooleanField(default=False, verbose_name='Документы проверены'),
        ),
        migrations.AddField(
            model_name='approvaloficialmemoprocess',
            name='person_hr',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='person_hr', to=settings.AUTH_USER_MODEL, verbose_name='Сотрудник ОК'),
        ),
    ]
