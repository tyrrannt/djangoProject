# Generated by Django 4.0.6 on 2022-07-26 18:35

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contracts_app', '0019_typedocuments_alter_contract_doc_file'),
    ]

    operations = [
        migrations.AddField(
            model_name='contract',
            name='type_of_document',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='contracts_app.typedocuments', verbose_name='Тип документа'),
        ),
    ]
