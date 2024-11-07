from django.contrib import admin

from .models import HashTag, HelpCategory, HelpTopic, DocumentForm, Contest, Poem, Vote

admin.site.register(HashTag)
admin.site.register(HelpCategory)
admin.site.register(HelpTopic)
admin.site.register(DocumentForm)

admin.site.register(Contest)
admin.site.register(Poem)
admin.site.register(Vote)
