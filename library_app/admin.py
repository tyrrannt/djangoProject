from django.contrib import admin

from .models import HashTag, HelpCategory, HelpTopic, DocumentForm, Contest, Poem, Vote, CompanyEvent
from unfold.admin import ModelAdmin


# Register your models here.
@admin.register(HashTag)
class HashTagAdmin(ModelAdmin):
    pass
@admin.register(HelpCategory)
class HelpCategoryAdmin(ModelAdmin):
    pass
@admin.register(HelpTopic)
class HelpTopicAdmin(ModelAdmin):
    pass
@admin.register(DocumentForm)
class DocumentFormAdmin(ModelAdmin):
    pass

@admin.register(Contest)
class ContestAdmin(ModelAdmin):
    pass
@admin.register(Poem)
class PoemAdmin(ModelAdmin):
    pass
@admin.register(Vote)
class VoteAdmin(ModelAdmin):
    pass
@admin.register(CompanyEvent)
class CompanyEventAdmin(ModelAdmin):
    pass
