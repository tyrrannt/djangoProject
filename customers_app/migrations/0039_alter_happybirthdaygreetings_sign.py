# Generated by Django 4.2.1 on 2023-06-11 20:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0038_alter_happybirthdaygreetings_sign'),
    ]

    operations = [
        migrations.AlterField(
            model_name='happybirthdaygreetings',
            name='sign',
            field=models.TextField(default='Генеральный директор<br>ООО Авиакомпания "БАРКОЛ"<br>Бархотов В.С.<br>и весь коллектив!!!', verbose_name='Подпись'),
        ),
    ]
