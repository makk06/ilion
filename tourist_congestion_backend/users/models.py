import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

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

    # 탈퇴 유예 관리. status가 withdrawn일 때만 값이 있고, 철회 시 둘 다 None으로 되돌린다.
    purge_at = models.DateTimeField(null=True, blank=True)
    withdrawal_reason_code = models.CharField(max_length=30, null=True, blank=True)

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
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='favorites')
    actor = models.ForeignKey('AnonymousActor', on_delete=models.CASCADE, null=True, blank=True,
                              related_name='favorites')
    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'place'], name='unique_user_place_favorite'),
            models.UniqueConstraint(fields=['actor', 'place'], name='unique_actor_place_favorite'),
            models.CheckConstraint(
                condition=(Q(user__isnull=False) & Q(actor__isnull=True))
                          | (Q(user__isnull=True) & Q(actor__isnull=False)),
                name='favorite_user_xor_actor',
            ),
        ]

    def __str__(self):
        return f'favorite of place {self.place_id}'


class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    actor = models.ForeignKey('AnonymousActor', on_delete=models.CASCADE, null=True, blank=True,
                              related_name='reviews')
    place = models.ForeignKey(Place, on_delete=models.CASCADE)
    text = models.TextField(max_length=3000)
    rating = models.PositiveSmallIntegerField(default=5)
    photo = models.ImageField(upload_to='reviews/%Y/%m/', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(user__isnull=False) & Q(actor__isnull=True))
                          | (Q(user__isnull=True) & Q(actor__isnull=False)),
                name='review_user_xor_actor',
            ),
        ]


class ReviewLike(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    actor = models.ForeignKey('AnonymousActor', on_delete=models.CASCADE, null=True, blank=True,
                              related_name='review_likes')
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='likes')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'review'], name='unique_review_like'),
            models.UniqueConstraint(fields=['actor', 'review'], name='unique_actor_review_like'),
            models.CheckConstraint(
                condition=(Q(user__isnull=False) & Q(actor__isnull=True))
                          | (Q(user__isnull=True) & Q(actor__isnull=False)),
                name='reviewlike_user_xor_actor',
            ),
        ]


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
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    actor = models.ForeignKey('AnonymousActor', on_delete=models.CASCADE, null=True, blank=True,
                              related_name='recent_places')
    place = models.ForeignKey(Place, on_delete=models.CASCADE)
    viewed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'place'], name='unique_recent_place'),
            models.UniqueConstraint(fields=['actor', 'place'], name='unique_actor_recent_place'),
            models.CheckConstraint(
                condition=(Q(user__isnull=False) & Q(actor__isnull=True))
                          | (Q(user__isnull=True) & Q(actor__isnull=False)),
                name='recentplace_user_xor_actor',
            ),
        ]


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


class Feedback(models.Model):
    class FeedbackType(models.TextChoices):
        CROWD = 'crowd', 'Crowd'
        RECOMMENDATION = 'recommendation', 'Recommendation'
        PLACE = 'place', 'Place'

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='feedbacks')
    actor = models.ForeignKey('AnonymousActor', on_delete=models.CASCADE, null=True, blank=True,
                              related_name='feedbacks')
    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name='feedbacks')
    feedback_type = models.CharField(max_length=14, choices=FeedbackType)
    value = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        null=True,
        blank=True,
    )
    memo = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(user__isnull=False) & Q(actor__isnull=True))
                          | (Q(user__isnull=True) & Q(actor__isnull=False)),
                name='feedback_user_xor_actor',
            ),
        ]

    def __str__(self):
        return f'{self.feedback_type} feedback on place {self.place_id}'


class AnonymousActor(models.Model):
    """탈퇴자의 행동 데이터를 묶는 익명 주체.

    식별 컬럼도 시각 컬럼도 두지 않는다. 원래 user_id와의 매핑을 저장하는 장소가
    존재하지 않으므로 복원이 구조적으로 불가능하다. 여기에 created_at을 추가하면
    WithdrawnEmailHash와 생성 시각으로 짝지어져 익명화가 무효가 된다.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    def __str__(self):
        return f'anonymous actor {self.id}'


class WithdrawnEmailHash(models.Model):
    """재가입 악용 방지용. 30일간 같은 이메일의 재가입을 막는다.

    expires_at이 DateField인 것은 의도적이다. 같은 날 탈퇴한 사람들이 동일한 값을
    갖게 해서 AnonymousActor와 1:1로 짝지어지지 않게 한다.
    """

    email_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateField(db_index=True)

    def __str__(self):
        return f'withdrawn email hash expiring {self.expires_at}'


class WithdrawalReason(models.Model):
    """탈퇴 사유 집계. 어떤 개인·actor와도 연결되지 않는다.

    자유 입력을 받지 않는다. 자유 텍스트를 허용하면 본인을 식별할 수 있는 내용이
    들어와 익명성이 깨진다.
    """

    reason_code = models.CharField(max_length=30)
    withdrawn_on = models.DateField()

    def __str__(self):
        return f'{self.reason_code} on {self.withdrawn_on}'
