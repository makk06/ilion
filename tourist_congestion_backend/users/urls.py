from django.urls import path

from . import views

urlpatterns = [
    path('signup', views.SignupView.as_view(), name='auth-signup'),
    path('login', views.LoginView.as_view(), name='auth-login'),
    path('google', views.GoogleLoginView.as_view(), name='auth-google'),
    path('refresh', views.RefreshView.as_view(), name='auth-refresh'),
    path('logout', views.LogoutView.as_view(), name='auth-logout'),
    path('nickname/random', views.RandomNicknameView.as_view(), name='auth-nickname-random'),
]
