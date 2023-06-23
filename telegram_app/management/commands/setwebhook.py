from django.core.management.base import BaseCommand, CommandError
from telegram_app.bot.loader import bot
from djangoProject.settings import WEBHOOK_URL, WEBHOOK_SSL_CERTIFICATE
from asgiref.sync import async_to_sync


class Command(BaseCommand):
    help = 'Setting webhook'

    def handle(self, *args, **options):
        webhook = async_to_sync(bot.get_webhook_info)()
        if webhook.url != WEBHOOK_URL:
            async_to_sync(bot.set_webhook)(WEBHOOK_URL, certificate=open(WEBHOOK_SSL_CERTIFICATE, 'r'), drop_pending_updates=True)
            self.stdout.write(self.style.SUCCESS('Webhook was successfully setted!'))
        else:
            self.stdout.write(self.style.WARNING('Webhook already setted!'))
