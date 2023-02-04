# Generated by Django 4.1.5 on 2023-02-04 20:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0008_job_right_to_approval'),
    ]

    operations = [
        migrations.AddField(
            model_name='division',
            name='type_of_role',
            field=models.CharField(blank=True, choices=[('1', 'НО'), ('2', 'Кадры'), ('3', 'Бухгалтерия')], max_length=11, null=True, verbose_name='Роль подразделения'),
        ),
    ]
