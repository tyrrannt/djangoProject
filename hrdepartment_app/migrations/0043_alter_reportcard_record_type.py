# Generated by Django 4.2 on 2023-05-23 16:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0042_reportcard_doc_ref_key_reportcard_manual_input_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reportcard',
            name='record_type',
            field=models.CharField(blank=True, choices=[('1', 'Явка'), ('2', 'Ежегодный'), ('3', 'Дополнительный ежегодный отпуск'), ('4', 'Отпуск за свой счет'), ('5', 'Дополнительный учебный отпуск (оплачиваемый)'), ('6', 'Отпуск по уходу за ребенком'), ('7', 'Дополнительный неоплачиваемый отпуск пострадавшим в аварии на ЧАЭС'), ('8', 'Отпуск по беременности и родам'), ('9', 'Отпуск без оплаты согласно ТК РФ'), ('10', 'Дополнительный отпуск'), ('11', 'Дополнительный оплачиваемый отпуск пострадавшим в '), ('12', 'Основной')], default='', max_length=100, verbose_name='Тип записи'),
        ),
    ]
