# Generated by Django 5.0.6 on 2024-11-20 18:06

import chat_app.models
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("chat_app", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="message",
            options={"verbose_name": "Сообщение", "verbose_name_plural": "Сообщения"},
        ),
        migrations.AlterField(
            model_name="message",
            name="message",
            field=chat_app.models.CustomEmojiTextField(),
        ),
    ]