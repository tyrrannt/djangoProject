from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse

from django.views.generic import ListView
from loguru import logger

from administration_app.models import PortalProperty
from customers_app.models import DataBaseUser, Groups, Job

logger.add("debug.json", format="{time} {level} {message}", level="DEBUG", rotation="10 MB", compression="zip",
           serialize=True)

# Create your views here.

def index(request):
    pass


class PortalPropertyList(LoginRequiredMixin, ListView):
    model = PortalProperty

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['Group'] = Groups.objects.all()
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Настройки портала'
        return context

    def get(self, request, *args, **kwargs):
        if self.request.user.is_superuser:
            # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                property_list = PortalProperty.objects.all()
                data = [property_item.get_data() for property_item in property_list]
                response = {'data': data}
                return JsonResponse(response)
            # Установка общих прав пользователя наследованием из групп
            if request.GET.get('update') == '0':
                group_list = [unit for unit in Groups.objects.filter(name__contains='Общая')]
                job_list = Job.objects.all()
                for item in job_list:
                    for unit in group_list:
                        item.group.add(unit.id)
            # Установка прав пользователя наследованием из групп
            if request.GET.get('update') == '1':
                users_list = DataBaseUser.objects.all()
                for user_obj in users_list:
                    try:
                        user_obj.groups.clear()
                        for item in user_obj.user_work_profile.job.group.all():
                            user_obj.groups.add(item)
                        user_obj.save()
                    except AttributeError:
                        logger.info(f"У пользователя {user_obj} отсутствуют группы!")
        return super().get(request, *args, **kwargs)
