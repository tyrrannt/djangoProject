from django.urls import path
from . import views
from .views import lock_screen

# from .views import (
#     AffiliationListView,
#     AffiliationDetailView,
#     AffiliationCreateView,
#     AffiliationUpdateView,
#     AffiliationDeleteView,
# )

app_name = "customers_app"

urlpatterns = [
    path("", views.index, name="index"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("register/", views.SignUpView.as_view(), name="register"),
    path(
        "profile/<int:pk>/", views.DataBaseUserProfileDetail.as_view(), name="profile"
    ),
    path("post/add/", views.PostsAddView.as_view(), name="post_add"),
    path("post/", views.PostsListView.as_view(), name="post_list"),
    path("post/<int:pk>/", views.PostsDetailView.as_view(), name="post"),
    path("post/<int:pk>/update/", views.PostsUpdateView.as_view(), name="post_update"),
    # path('profile/<int:pk>/update/', views.DataBaseUserUpdate.as_view(), name='profile_update'),
    path(
        "counteragent/", views.CounteragentListView.as_view(), name="counteragent_list"
    ),
    path("counteragent/add/", views.CounteragentAdd.as_view(), name="counteragent_add"),
    path(
        "counteragent/<int:pk>/",
        views.CounteragentDetail.as_view(),
        name="counteragent",
    ),
    path("documents/", views.CounteragentDocumentsList.as_view(), name="documents_list"),
    path("documents/add/", views.CounteragentDocumentsAdd.as_view(), name="documents_add"),
    path("documents/<int:pk>/update/", views.CounteragentDocumentsUpdate.as_view(), name="documents_update"),
    path(
        "counteragent/<int:pk>/update/",
        views.CounteragentUpdate.as_view(),
        name="counteragent_update",
    ),
    path("staff/", views.StaffListView.as_view(), name="staff_list"),
    path("staff/<int:pk>/", views.StaffDetail.as_view(), name="staff"),
    path("staff/<int:pk>/update/", views.StaffUpdate.as_view(), name="staff_update"),
    path("divisions/", views.DivisionsList.as_view(), name="divisions_list"),
    path("divisions/add/", views.DivisionsAdd.as_view(), name="divisions_add"),
    path("divisions/<int:pk>/", views.DivisionsDetail.as_view(), name="divisions"),
    path(
        "divisions/<int:pk>/update/",
        views.DivisionsUpdate.as_view(),
        name="divisions_update",
    ),
    path("jobs/", views.JobsList.as_view(), name="jobs_list"),
    path("jobs/add/", views.JobsAdd.as_view(), name="jobs_add"),
    path("jobs/<int:pk>/", views.JobsDetail.as_view(), name="jobs"),
    path("jobs/<int:pk>/update/", views.JobsUpdate.as_view(), name="jobs_update"),
    path(
        "harmful/", views.HarmfulWorkingConditionsList.as_view(), name="harmfuls_list"
    ),
    path("group/", views.GroupListView.as_view(), name="group_list"),
    path("group/add/", views.GroupCreateView.as_view(), name="group_add"),
    path(
        "group/<int:pk>/update/", views.GroupUpdateView.as_view(), name="group_update"
    ),
    path(
        "passphrase/<int:pk>/update/",
        views.ChangePassPraseUpdate.as_view(),
        name="passphrase_update",
    ),
    path(
        "avatar/<int:pk>/update/",
        views.ChangeAvatarUpdate.as_view(),
        name="avatar_update",
    ),
    path('lock-screen/', lock_screen, name='lock_screen'),
    path('generate_qr_code/<path:current_url>/', views.generate_qr_code, name='generate_qr_code'),
    path('auth_with_token/', views.auth_with_token, name='auth_with_token'),
    path('generate-config/', views.generate_config_file, name='generate_config_file'),
    path('generate-employee-file/<int:pk>/', views.generate_employee_file, name='generate_employee_file'),
    path('game/', views.game, name='game'),
    path('save_stats/', views.save_stats, name='save_stats'),
    path('get_leaderboard/', views.get_leaderboard, name='get_leaderboard'),
    # path(
    #     "password/<int:pk>/update/",
    #     views.ChangeAvatarUpdate.as_view(),
    #     name="avatar_update",
    # ),
    # path("affiliation/", AffiliationListView.as_view(), name="affiliation-list"),
    # path(
    #     "affiliation/<int:pk>",
    #     AffiliationDetailView.as_view(),
    #     name="affiliation-detail",
    # ),
    # path(
    #     "affiliation/create/",
    #     AffiliationCreateView.as_view(),
    #     name="affiliation-create",
    # ),
    # path(
    #     "affiliation/<int:pk>/update/",
    #     AffiliationUpdateView.as_view(),
    #     name="affiliation-update",
    # ),
    # path(
    #     "affiliation/<int:pk>/delete/",
    #     AffiliationDeleteView.as_view(),
    #     name="affiliation-delete",
    # ),
]
