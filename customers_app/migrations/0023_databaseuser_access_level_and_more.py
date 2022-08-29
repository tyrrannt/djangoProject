# Generated by Django 4.0.6 on 2022-08-02 20:33

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0022_useraccessmode'),
    ]

    operations = [
        migrations.AddField(
            model_name='databaseuser',
            name='access_level',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='customers_app.useraccessmode', verbose_name='права доступа'),
        ),
        migrations.AddField(
            model_name='useraccessmode',
            name='posts_access_add',
            field=models.BooleanField(default=False, verbose_name='Разрешение на создание сообщения'),
        ),
        migrations.AddField(
            model_name='useraccessmode',
            name='posts_access_agreement',
            field=models.BooleanField(default=False, verbose_name='Право на публикацию сообщения'),
        ),
        migrations.AddField(
            model_name='useraccessmode',
            name='posts_access_edit',
            field=models.BooleanField(default=False, verbose_name='Разрешение на редактирование сообщения'),
        ),
        migrations.AddField(
            model_name='useraccessmode',
            name='posts_access_view',
            field=models.CharField(blank=True, choices=[('0', 'Административный доступ'), ('1', 'Особой важности'), ('2', 'Совершенно секретные'), ('3', 'Секретные'), ('4', 'Для служебного пользования')], default='4', max_length=1, null=True, verbose_name='Уровень доступа к сообщениям'),
        ),
    ]