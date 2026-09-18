from django.urls import path

from . import views

app_name = 'toolbox'
urlpatterns = [
    path('', views.home, name='home'),
    path('add/<slug:slug>/', views.add, name='add'),
    path('remove/<slug:slug>/', views.remove, name='remove'),
    path('setting/<slug:slug>/', views.setting, name='setting'),
    path('token/issue/', views.token_issue, name='token_issue'),
    path('token/', views.token_show, name='token'),
    path('token/revoke/', views.token_revoke, name='token_revoke'),
]
