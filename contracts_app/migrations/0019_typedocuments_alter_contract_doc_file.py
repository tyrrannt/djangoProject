# Generated by Django 4.0.6 on 2022-07-26 18:33

import contracts_app.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contracts_app', '0018_alter_contract_cost'),
    ]

    operations = [
        migrations.CreateModel(
            name='TypeDocuments',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type_document', models.CharField(blank=True, max_length=50, null=True, verbose_name='Тип документа')),
                ('file_name_prefix', models.CharField(max_length=3, verbose_name='')),
            ],
            options={
                'verbose_name': 'Тип документа',
                'verbose_name_plural': 'Тип документов',
            },
        ),
        migrations.AlterField(
            model_name='contract',
            name='doc_file',
            field=models.FileField(blank=True, upload_to=contracts_app.models.contract_directory_path, verbose_name='Файл документа'),
        ),
    ]
