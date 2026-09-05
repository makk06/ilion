from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from places.models import Place

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    class Provider(models.TextChoices):
        EMAIL = 'email', 'Email'
        GOOGLE = 'google', 'Google'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACTIVE = 'active', 'Active'
        WITHDRAWN = 'withdrawn', 'Withdrawn'

    email = models.EmailField(unique=True)
    nickname = models.CharField(max_length=30, unique=True)
    provider = models.CharField(max_length=10, choices=Provider, default=Provider.EMAIL)
    provider_user_id = models.CharField(max_length=255, null=True, blank=True)
    profile_image_url = models.URLField(null=True, blank=True)
    preferred_categories = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nickname']

    objects = UserManager()

    def __str__(self):
        return self.email

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE


class RefreshToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='refresh_tokens')
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'refresh token for user {self.user_id}'


class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')
    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'place'], name='unique_user_place_favorite'),
        ]

    def __str__(self):
        return f'user {self.user_id} favorite of place {self.place_id}'


class Feedback(models.Model):
    class FeedbackType(models.TextChoices):
        CROWD = 'crowd', 'Crowd'
        RECOMMENDATION = 'recommendation', 'Recommendation'
        PLACE = 'place', 'Place'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feedbacks')
    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name='feedbacks')
    feedback_type = models.CharField(max_length=14, choices=FeedbackType)
    value = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        null=True,
        blank=True,
    )
    memo = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'user {self.user_id} {self.feedback_type} feedback on place {self.place_id}'
