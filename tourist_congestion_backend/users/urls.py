from django.urls import path

from . import views

urlpatterns = [
    path('auth/signup', views.SignupView.as_view(), name='auth-signup'),
    path('auth/login', views.LoginView.as_view(), name='auth-login'),
    path('auth/google', views.GoogleLoginView.as_view(), name='auth-google'),
    path('auth/refresh', views.RefreshView.as_view(), name='auth-refresh'),
    path('auth/logout', views.LogoutView.as_view(), name='auth-logout'),
    path('auth/nickname/random', views.RandomNicknameView.as_view(), name='auth-nickname-random'),
    path('favorites', views.FavoriteListCreateView.as_view(), name='favorite-list-create'),
    path('favorites/<int:place_id>', views.FavoriteDeleteView.as_view(), name='favorite-delete'),
    path('feedback', views.FeedbackListCreateView.as_view(), name='feedback-list-create'),
]
