Класс DeleteView в Django является частью Django Generic Class-Based Views и предназначен для создания представлений, которые удаляют объекты. Вот основные методы класса DeleteView с примерами:

1. `get_object(self, queryset=None)`
Этот метод возвращает объект, который будет удален. По умолчанию он использует self.queryset и фильтрует его по self.kwargs.

Пример:
```python
from django.views.generic.edit import DeleteView
from django.urls import reverse_lazy
from myapp.models import MyModel

class MyModelDeleteView(DeleteView):
    model = MyModel
    success_url = reverse_lazy('myapp:mymodel_list')

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        # Дополнительная логика, если нужно
        return obj
```


2. `get_success_url(self)`
Этот метод возвращает URL, на который будет перенаправлен пользователь после успешного удаления объекта.

Пример:

```python
class MyModelDeleteView(DeleteView):
    model = MyModel

    def get_success_url(self):
        return reverse_lazy('myapp:mymodel_list')
```

3. `delete(self, request, *args, **kwargs)`
Этот метод выполняет фактическое удаление объекта. По умолчанию он вызывает метод delete модели.

Пример:

```python
class MyModelDeleteView(DeleteView):
    model = MyModel
    success_url = reverse_lazy('myapp:mymodel_list')

    def delete(self, request, *args, **kwargs):
        # Дополнительная логика перед удалением
        self.object = self.get_object()
        success_url = self.get_success_url()
        self.object.delete()
        # Дополнительная логика после удаления
        return HttpResponseRedirect(success_url)
```

4. `get_context_data(self, **kwargs)`
Этот метод используется для добавления дополнительных данных в контекст шаблона.

Пример:

```python
class MyModelDeleteView(DeleteView):
    model = MyModel
    success_url = reverse_lazy('myapp:mymodel_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['additional_data'] = 'Some additional data'
        return context
```

5. `dispatch(self, request, *args, **kwargs)`
Этот метод обрабатывает запрос и определяет, какой метод (get или post) должен быть вызван.

Пример:

```python
class MyModelDeleteView(DeleteView):
    model = MyModel
    success_url = reverse_lazy('myapp:mymodel_list')

    def dispatch(self, request, *args, **kwargs):
        # Дополнительная логика перед dispatch
        return super().dispatch(request, *args, **kwargs)
```

6. `post(self, request, *args, **kwargs)`
Этот метод обрабатывает POST-запросы. По умолчанию он вызывает метод delete.

Пример:

```python
class MyModelDeleteView(DeleteView):
    model = MyModel
    success_url = reverse_lazy('myapp:mymodel_list')

    def post(self, request, *args, **kwargs):
        # Дополнительная логика перед удалением
        return self.delete(request, *args, **kwargs)
```

Эти методы позволяют настроить поведение класса DeleteView в соответствии с вашими требованиями.