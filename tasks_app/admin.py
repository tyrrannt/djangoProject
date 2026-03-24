from django.contrib import admin

from tasks_app.models import Category, Task
from unfold.admin import ModelAdmin


# Register your models here.
@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    pass
@admin.register(Task)
class TaskAdmin(ModelAdmin):
    pass

