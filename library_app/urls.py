from django.urls import path
from . import views
from .views import CompanyEventListView, CompanyEventDetailView, CompanyEventUpdateView, CompanyEventDeleteView, \
    CompanyEventCreateView

app_name = 'library_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('video/', views.video, name='video'),
    path('help/', views.HelpList.as_view(), name='help_list'),
    path('help/<int:pk>/', views.HelpItem.as_view(), name='help'),
    path('help/<int:pk>/update/', views.HelpItemUpdate.as_view(), name='help_update'),
    path('help/add/', views.HelpItemAdd.as_view(), name='help_add'),
    path('blank/', views.DocumentFormList.as_view(), name='blank_list'),
    path('blank/<int:pk>/', views.DocumentFormItem.as_view(), name='blank'),
    path('blank/<int:pk>/update/', views.DocumentFormUpdate.as_view(), name='blank_update'),
    path('blank/add/', views.DocumentFormAdd.as_view(), name='blank_add'),
    path('submit/', views.submit_poem, name='submit_poem'),
    path('vote/', views.vote, name='vote'),
    path('vote/success/', views.vote_success, name='vote_success'),
    path('results/', views.results, name='results'),
    path('check_session_cookie_secure/', views.check_session_cookie_secure, name='check_session_cookie_secure'),
    path('event/', CompanyEventListView.as_view(), name='event_list'),
    path('event/<int:pk>/', CompanyEventDetailView.as_view(), name='event_detail'),
    path('event/<int:pk>/update/', CompanyEventUpdateView.as_view(), name='event_update'),
    path('event/<int:pk>/delete/', CompanyEventDeleteView.as_view(), name='event_delete'),
    path('event/create/', CompanyEventCreateView.as_view(), name='event_create'),
    # Маршруты предпросмотра страниц ошибок
    path('errors/400/', views.show_400, name='error_400'),
    path('errors/403/', views.show_403, name='error_403'),
    path('errors/csrf/', views.csrf_failure, name='error_csrf'),
    path('errors/404/', views.show_404, name='error_404'),
    path('errors/500/', views.show_500, name='error_500'),
    path('errors/503/', views.show_503, name='error_503'),
]
