# Generated by Django 4.1 on 2022-08-16 14:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0023_databaseuser_access_level_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='useraccessmode',
            name='guide_access_add',
            field=models.BooleanField(default=False, verbose_name='Разрешение на создание записи в справочнике'),
        ),
        migrations.AddField(
            model_name='useraccessmode',
            name='guide_access_agreement',
            field=models.BooleanField(default=False, verbose_name='Право на публикацию записи в справочнике'),
        ),
        migrations.AddField(
            model_name='useraccessmode',
            name='guide_access_edit',
            field=models.BooleanField(default=False, verbose_name='Разрешение на редактирование записи в справочнике'),
        ),
        migrations.AddField(
            model_name='useraccessmode',
            name='guide_access_view',
            field=models.CharField(blank=True, choices=[('0', 'Административный доступ'), ('1', 'Особой важности'), ('2', 'Совершенно секретные'), ('3', 'Секретные'), ('4', 'Для служебного пользования')], default='4', max_length=1, null=True, verbose_name='Уровень доступа к справочникам'),
        ),
    ]