from django.contrib import admin

from .models import HashTag, HelpCategory, HelpTopic

admin.site.register(HashTag)
admin.site.register(HelpCategory)
admin.site.register(HelpTopic)
