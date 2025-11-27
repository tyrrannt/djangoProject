"""djangoProject URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

import library_app.views as library_views

handler403 = library_views.show_403
handler404 = library_views.show_404
handler500 = library_views.show_500

urlpatterns = [
    path('', include('library_app.urls')),
    path('bklproxmoxadmin/', admin.site.urls),
    path('users/', include('customers_app.urls')),
    path('contracts/', include('contracts_app.urls')),
    path('hr/', include('hrdepartment_app.urls')),
    path('logistics/', include('logistics_app.urls')),
    path('chat/', include('chat_app.urls')),
    path('portal/', include('administration_app.urls')),
    path('mirage/', include('telegram_app.urls')),
    path('tasks/', include('tasks_app.urls')),
    path('equipment/', include('ppequipment_app.urls')),
    path('ckeditor5/', include('django_ckeditor_5.urls'), name="ck_editor_5_upload_file"),
    path('__debug__/', include('debug_toolbar.urls')),
    # path('api/', include('customers_app.urls')),  # API (если вы вынесли API в отдельный urls.py)

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
