from django.urls import path

from . import views
from . import activity_views as activity

urlpatterns = [
    path('notifications', activity.NotificationsView.as_view()),
    path('me', activity.MeView.as_view()),
    path('reviews', activity.ReviewsView.as_view()),
    path('reviews/<int:pk>', activity.ReviewDetailView.as_view()),
    path('reviews/<int:pk>/like', activity.ReviewLikeView.as_view()),
    path('companions', activity.CompanionsView.as_view()),
    path('companions/<int:pk>', activity.CompanionDetailView.as_view()),
    path('companions/<int:pk>/join', activity.CompanionJoinView.as_view()),
    path('points', activity.PointsView.as_view()),
    path('rewards', activity.RewardsView.as_view()),
    path('recent-places', activity.RecentPlacesView.as_view()),
    path('plans', activity.PlansView.as_view()),
    path('plans/<int:pk>', activity.PlanDetailView.as_view()),
    path('inquiries', activity.InquiriesView.as_view()),
    path('auth/signup', views.SignupView.as_view(), name='auth-signup'),
    path('auth/login', views.LoginView.as_view(), name='auth-login'),
    path('auth/google', views.GoogleLoginView.as_view(), name='auth-google'),
    path('auth/refresh', views.RefreshView.as_view(), name='auth-refresh'),
    path('auth/logout', views.LogoutView.as_view(), name='auth-logout'),
    path('auth/nickname/random', views.RandomNicknameView.as_view(), name='auth-nickname-random'),
    path('favorites', views.FavoriteListCreateView.as_view(), name='favorite-list-create'),
    path('favorites/<int:place_id>', views.FavoriteDeleteView.as_view(), name='favorite-delete'),
]
