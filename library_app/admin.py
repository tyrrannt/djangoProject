from django.contrib import admin

from .models import HashTag, HelpCategory, HelpTopic, DocumentForm

admin.site.register(HashTag)
admin.site.register(HelpCategory)
admin.site.register(HelpTopic)
admin.site.register(DocumentForm)
