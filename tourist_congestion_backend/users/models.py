from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
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
    preferences = models.JSONField(default=dict, blank=True)
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


class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    place = models.ForeignKey(Place, on_delete=models.CASCADE)
    text = models.TextField(max_length=3000)
    rating = models.PositiveSmallIntegerField(default=5)
    photo = models.ImageField(upload_to='reviews/%Y/%m/', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ReviewLike(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='likes')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'review'], name='unique_review_like')]


class PointEntry(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    place = models.ForeignKey(Place, on_delete=models.PROTECT)
    amount = models.IntegerField()
    reason = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'place', 'reason'], name='unique_place_point_award')]


class Companion(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    place = models.ForeignKey(Place, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    text = models.TextField(max_length=3000)
    date = models.DateField(null=True, blank=True, default=None)
    time = models.TimeField(null=True, blank=True, default=None)
    capacity = models.PositiveSmallIntegerField()
    member_count = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)


class CompanionMember(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    companion = models.ForeignKey(Companion, on_delete=models.CASCADE, related_name='members')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'companion'], name='unique_companion_member')]


class RecentPlace(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    place = models.ForeignKey(Place, on_delete=models.CASCADE)
    viewed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'place'], name='unique_recent_place')]


class Plan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    date = models.DateField()
    stops = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)


class Inquiry(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subject = models.CharField(max_length=100)
    text = models.TextField(max_length=3000)
    status = models.CharField(max_length=20, default='received')
    answer = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
