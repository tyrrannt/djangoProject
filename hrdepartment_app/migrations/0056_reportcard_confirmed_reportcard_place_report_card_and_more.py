# Generated by Django 4.2.1 on 2023-07-18 17:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0055_instructions_document_form_provisions_document_form'),
    ]

    operations = [
        migrations.AddField(
            model_name='reportcard',
            name='confirmed',
            field=models.BooleanField(default=False, verbose_name='Подтвержденная СП'),
        ),
        migrations.AddField(
            model_name='reportcard',
            name='place_report_card',
            field=models.ManyToManyField(related_name='place_report_card', to='hrdepartment_app.placeproductionactivity', verbose_name='МПД'),
        ),
        migrations.AlterField(
            model_name='reportcard',
            name='record_type',
            field=models.CharField(blank=True, choices=[('1', 'Явка'), ('2', 'Ежегодный'), ('3', 'Дополнительный ежегодный отпуск'), ('4', 'Отпуск за свой счет'), ('5', 'Дополнительный учебный отпуск (оплачиваемый)'), ('6', 'Отпуск по уходу за ребенком'), ('7', 'Дополнительный неоплачиваемый отпуск пострадавшим в аварии на ЧАЭС'), ('8', 'Отпуск по беременности и родам'), ('9', 'Отпуск без оплаты согласно ТК РФ'), ('10', 'Дополнительный отпуск'), ('11', 'Дополнительный оплачиваемый отпуск пострадавшим в '), ('12', 'Основной'), ('13', 'Ручной ввод'), ('14', 'Служебная поездка'), ('15', 'Командировка'), ('16', 'Больничный'), ('17', 'Мед осмотр')], default='', max_length=100, verbose_name='Тип записи'),
        ),
    ]