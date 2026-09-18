# 회원 탈퇴 기능 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 회원 탈퇴 기능을 만들고, 탈퇴자의 행동 데이터를 복원 불가능하게 익명화해 알고리즘 학습용으로 보존한다.

**Architecture:** `AnonymousActor` 모델을 신설하고 보존 대상 5개 모델의 `user` FK를 nullable로 전환하면서 `actor` FK를 추가한다. 탈퇴 요청은 7일 유예 후 배치가 처리하며, 보존 대상 행은 `user=NULL, actor=<신규 actor>`로 옮기고 `User` 행은 실제로 삭제한다. `user_id ↔ actor_id` 매핑을 저장하는 장소가 존재하지 않아 복원이 구조적으로 불가능하다.

**Tech Stack:** Django 6.0.6, Django REST Framework 3.16.1, djangorestframework-simplejwt 5.5.1, SQLite

**Spec:** `docs/superpowers/specs/2026-09-17-account-withdrawal-design.md`

## Global Constraints

- **Django 6.0.6** — `CheckConstraint`는 `check=`가 아니라 **`condition=`**을 쓴다. `check=`는 5.1에서 deprecated, 6.0에서 제거되었다.
- 유예기간 **7일**, 재가입 방지 해시 **30일**, 익명 행동 데이터 **무기한**.
- 이메일 해시는 반드시 **HMAC-SHA256**이며 키는 `SECRET_KEY`와 분리된 `WITHDRAWAL_HASH_KEY`를 쓴다. 단순 `sha256(email)` 금지.
- `AnonymousActor`에는 **어떤 시각 컬럼도 두지 않는다.** `WithdrawnEmailHash.expires_at`과 `WithdrawalReason.withdrawn_on`은 `DateTimeField`가 아니라 **`DateField`**다. (타임스탬프 상관 공격 차단 — 스펙 §5.2)
- API 응답은 기존 봉투 형식을 따른다: `{'success': bool, 'data': dict, 'message': str}`. `users/views.py`의 `success_response` / `error_response`를 쓴다.
- 테스트는 `django.test.TestCase` + `rest_framework.test.APIClient` + `django.urls.reverse`를 쓴다. 기존 `users/tests.py` 패턴을 따른다.
- 한국어 사용자 메시지를 쓴다. 기존 코드와 동일하게 존댓말 문장으로 끝낸다.
- 테스트 실행: `python manage.py test users` (프로젝트 루트는 `tourist_congestion_backend/`)

---

## File Structure

| 파일 | 책임 |
|------|------|
| `users/models.py` (수정) | `AnonymousActor`·`WithdrawnEmailHash`·`WithdrawalReason` 추가, `User` 필드 2개 추가, 보존 5개 모델 FK 전환 |
| `users/utils.py` (수정) | `hash_email_for_withdrawal()` HMAC 유틸 |
| `users/withdrawal.py` (신규) | 파기 로직. 뷰·명령에서 공유하는 순수 서비스 함수 |
| `users/views.py` (수정) | 탈퇴 요청·철회 뷰, 로그인 `withdrawal_pending` 분기 |
| `users/serializers.py` (수정) | `WithdrawSerializer`, 재가입 차단 검증 |
| `users/urls.py` (수정) | 라우트 2개 추가 |
| `users/activity_views.py` (수정) | 익명 작성자 응답, `is_mine` NULL 결함 수정 |
| `users/management/commands/purge_withdrawn_users.py` (신규) | 운영자 수동 실행용 명령 |
| `places/management/commands/run_data_worker.py` (수정) | 스케줄 루프에서 파기 호출 |
| `config/settings.py` (수정) | `WITHDRAWAL_HASH_KEY` |
| `users/test_withdrawal.py` (신규) | 탈퇴 전용 테스트 — 기존 `tests.py`를 비대하게 만들지 않는다 |

파기 로직을 `views.py`가 아니라 `withdrawal.py`로 분리하는 이유: 뷰(요청)와 배치(파기)가 같은 로직을 쓰지 않으며, 파기는 되돌릴 수 없어 HTTP 계층 없이 단위 테스트할 수 있어야 한다.

---

## Task 1: 신규 모델 3개와 `User` 필드

**Files:**
- Modify: `tourist_congestion_backend/users/models.py`
- Create: `tourist_congestion_backend/users/test_withdrawal.py`

**Interfaces:**
- Consumes: 없음 (첫 작업)
- Produces: `AnonymousActor` (PK `id: UUID`), `WithdrawnEmailHash(email_hash: str, expires_at: date)`, `WithdrawalReason(reason_code: str, withdrawn_on: date)`, `User.purge_at: datetime | None`, `User.withdrawal_reason_code: str | None`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`users/test_withdrawal.py`를 새로 만든다.

```python
from datetime import date

from django.test import TestCase

from .models import AnonymousActor, User, WithdrawalReason, WithdrawnEmailHash


class AnonymousActorTests(TestCase):
    def test_actor_has_no_time_columns(self):
        # 스펙 5.2: actor에 시각 정보가 있으면 탈퇴 이메일 해시와 짝지어 재식별된다.
        names = {field.name for field in AnonymousActor._meta.get_fields()}
        self.assertEqual(names & {'created_at', 'updated_at', 'withdrawn_at'}, set())

    def test_actor_id_is_random_uuid(self):
        first = AnonymousActor.objects.create()
        second = AnonymousActor.objects.create()
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(len(str(first.id)), 36)


class WithdrawalStorageTests(TestCase):
    def test_email_hash_expires_on_a_date_not_a_timestamp(self):
        row = WithdrawnEmailHash.objects.create(email_hash='a' * 64, expires_at=date(2026, 10, 18))
        self.assertIsInstance(row.expires_at, date)
        self.assertEqual(
            WithdrawnEmailHash._meta.get_field('expires_at').get_internal_type(),
            'DateField',
        )

    def test_reason_is_not_linked_to_any_person(self):
        names = {field.name for field in WithdrawalReason._meta.get_fields()}
        self.assertEqual(names & {'user', 'actor', 'email', 'email_hash'}, set())


class UserWithdrawalFieldTests(TestCase):
    def test_new_user_has_no_purge_schedule(self):
        user = User.objects.create_user(email='a@example.com', password='pw12345678', nickname='가입자')
        self.assertIsNone(user.purge_at)
        self.assertIsNone(user.withdrawal_reason_code)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python manage.py test users.test_withdrawal -v 2`
Expected: FAIL — `ImportError: cannot import name 'AnonymousActor' from 'users.models'`

- [ ] **Step 3: 모델을 추가한다**

`users/models.py` 맨 위 import에 `uuid`를 추가한다.

```python
import uuid
```

`User` 클래스의 `is_staff = models.BooleanField(default=False)` 바로 위에 두 필드를 추가한다.

```python
    # 탈퇴 유예 관리. status가 withdrawn일 때만 값이 있고, 철회 시 둘 다 None으로 되돌린다.
    purge_at = models.DateTimeField(null=True, blank=True)
    withdrawal_reason_code = models.CharField(max_length=30, null=True, blank=True)
```

파일 맨 끝에 모델 3개를 추가한다.

```python
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
```

- [ ] **Step 4: 마이그레이션을 만들고 적용한다**

```bash
python manage.py makemigrations users
python manage.py migrate
```

- [ ] **Step 5: 테스트 통과를 확인한다**

Run: `python manage.py test users.test_withdrawal -v 2`
Expected: PASS (5 tests)

- [ ] **Step 6: 커밋**

```bash
git add users/models.py users/migrations/ users/test_withdrawal.py
git commit -m "feat(users): 탈퇴 익명화용 모델과 유예 필드 추가"
```

---

## Task 2: 보존 5개 모델의 FK 전환

**Files:**
- Modify: `tourist_congestion_backend/users/models.py`
- Test: `tourist_congestion_backend/users/test_withdrawal.py`

**Interfaces:**
- Consumes: Task 1의 `AnonymousActor`
- Produces: `Feedback`·`Review`·`ReviewLike`·`Favorite`·`RecentPlace`가 각각 `user: User | None`, `actor: AnonymousActor | None`을 가지며 정확히 하나만 NULL이 아니다

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`users/test_withdrawal.py` 맨 위 import를 아래로 교체한다.

```python
from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase

from places.models import Place

from .models import (AnonymousActor, Favorite, Feedback, RecentPlace, Review, ReviewLike,
                     User, WithdrawalReason, WithdrawnEmailHash)
```

파일 끝에 헬퍼와 테스트를 추가한다.

```python
def create_place(**overrides):
    fields = {
        'name': '테스트 장소',
        'category': '관광지',
        'region_code': '11000',
        'address': '서울 어딘가',
        'latitude': '37.5665',
        'longitude': '126.9780',
        'indoor_outdoor': Place.IndoorOutdoor.OUTDOOR,
    }
    fields.update(overrides)
    return Place.objects.create(**fields)


class UserXorActorConstraintTests(TestCase):
    def setUp(self):
        self.place = create_place()
        self.user = User.objects.create_user(
            email='keeper@example.com', password='pw12345678', nickname='보존자')
        self.actor = AnonymousActor.objects.create()

    def test_row_may_belong_to_a_user(self):
        favorite = Favorite.objects.create(user=self.user, place=self.place)
        self.assertIsNone(favorite.actor)

    def test_row_may_belong_to_an_actor(self):
        favorite = Favorite.objects.create(actor=self.actor, place=self.place)
        self.assertIsNone(favorite.user)

    def test_row_may_not_belong_to_both(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Favorite.objects.create(user=self.user, actor=self.actor, place=self.place)

    def test_row_may_not_be_orphaned(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Favorite.objects.create(place=self.place)

    def test_every_preserved_model_enforces_the_rule(self):
        for model in (Feedback, Review, ReviewLike, Favorite, RecentPlace):
            names = {constraint.name for constraint in model._meta.constraints}
            self.assertIn(
                f'{model.__name__.lower()}_user_xor_actor', names,
                f'{model.__name__}에 XOR 제약이 없습니다',
            )

    def test_actor_may_not_favorite_the_same_place_twice(self):
        Favorite.objects.create(actor=self.actor, place=self.place)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Favorite.objects.create(actor=self.actor, place=self.place)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python manage.py test users.test_withdrawal.UserXorActorConstraintTests -v 2`
Expected: FAIL — `TypeError: Favorite() got unexpected keyword arguments: 'actor'`

- [ ] **Step 3: 모델을 전환한다**

`users/models.py` 상단 import에 `Q`를 추가한다.

```python
from django.db.models import Q
```

5개 모델을 아래로 교체한다. `AnonymousActor` 클래스 정의가 이들보다 **뒤에** 있으므로 문자열 참조 `'AnonymousActor'`를 쓴다.

```python
class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='favorites')
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
```

`Feedback`은 `user` 줄과 `actor` 줄, `Meta`만 바꾼다. 나머지 필드는 그대로 둔다.

```python
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='feedbacks')
    actor = models.ForeignKey('AnonymousActor', on_delete=models.CASCADE, null=True, blank=True,
                              related_name='feedbacks')
```

`Feedback`의 `__str__` 아래에 `Meta`를 추가한다.

```python
    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(user__isnull=False) & Q(actor__isnull=True))
                          | (Q(user__isnull=True) & Q(actor__isnull=False)),
                name='feedback_user_xor_actor',
            ),
        ]
```

- [ ] **Step 4: 마이그레이션을 만들고 적용한다**

```bash
python manage.py makemigrations users
python manage.py migrate
```

기존 행은 모두 `user`가 채워져 있고 `actor`가 NULL이므로 XOR 제약을 이미 만족한다. 백필이 필요 없다.

- [ ] **Step 5: 테스트 통과를 확인한다**

Run: `python manage.py test users -v 2`
Expected: PASS. 기존 `users/tests.py`와 `users/test_activity.py`도 함께 통과해야 한다.

- [ ] **Step 6: 커밋**

```bash
git add users/models.py users/migrations/ users/test_withdrawal.py
git commit -m "feat(users): 보존 대상 모델에 익명 actor 소유권 추가"
```

---

## Task 3: HMAC 이메일 해시

**Files:**
- Modify: `tourist_congestion_backend/users/utils.py`
- Modify: `tourist_congestion_backend/config/settings.py`
- Modify: `tourist_congestion_backend/.env.example`
- Test: `tourist_congestion_backend/users/test_withdrawal.py`

**Interfaces:**
- Consumes: 없음
- Produces: `hash_email_for_withdrawal(email: str) -> str` (64자 hex), `settings.WITHDRAWAL_HASH_KEY`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`users/test_withdrawal.py`에 추가한다. import에 `from django.test import TestCase, override_settings`를 반영하고 `from .utils import hash_email_for_withdrawal`를 추가한다.

```python
class EmailHashTests(TestCase):
    @override_settings(WITHDRAWAL_HASH_KEY='k' * 50)
    def test_hash_is_case_and_space_insensitive(self):
        self.assertEqual(
            hash_email_for_withdrawal('  User@Example.COM '),
            hash_email_for_withdrawal('user@example.com'),
        )

    @override_settings(WITHDRAWAL_HASH_KEY='k' * 50)
    def test_hash_is_sixty_four_hex_characters(self):
        value = hash_email_for_withdrawal('user@example.com')
        self.assertEqual(len(value), 64)
        int(value, 16)

    def test_hash_depends_on_the_secret_key(self):
        # 키 없이 sha256만 쓰면 이메일 후보를 전수 대입해 복원할 수 있다.
        with override_settings(WITHDRAWAL_HASH_KEY='a' * 50):
            first = hash_email_for_withdrawal('user@example.com')
        with override_settings(WITHDRAWAL_HASH_KEY='b' * 50):
            second = hash_email_for_withdrawal('user@example.com')
        self.assertNotEqual(first, second)

    @override_settings(WITHDRAWAL_HASH_KEY='k' * 50)
    def test_hash_is_not_a_plain_sha256(self):
        import hashlib
        plain = hashlib.sha256(b'user@example.com').hexdigest()
        self.assertNotEqual(hash_email_for_withdrawal('user@example.com'), plain)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python manage.py test users.test_withdrawal.EmailHashTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'hash_email_for_withdrawal'`

- [ ] **Step 3: 유틸과 설정을 추가한다**

`users/utils.py` 상단 import를 바꾼다.

```python
import hashlib
import hmac
import secrets

from django.conf import settings
```

파일 끝에 추가한다.

```python
def hash_email_for_withdrawal(email):
    """재가입 차단용 이메일 지문.

    단순 sha256을 쓰면 안 된다. 이메일은 후보 공간이 좁아 전수 대입으로 복원된다.
    서버만 아는 키로 HMAC을 걸어야 실질적 익명성이 생긴다.
    """
    return hmac.new(
        settings.WITHDRAWAL_HASH_KEY.encode(),
        email.strip().lower().encode(),
        hashlib.sha256,
    ).hexdigest()
```

`config/settings.py`에서 `SECRET_KEY` 검증 블록(38~39행) 바로 아래에 추가한다.

```python
# 탈퇴 이메일 해시 전용 키. SECRET_KEY와 분리한다 —— SECRET_KEY가 교체되면
# 재가입 차단이 조용히 무력화되기 때문이다.
WITHDRAWAL_HASH_KEY = os.environ.get('WITHDRAWAL_HASH_KEY', '')
if not DEBUG and len(WITHDRAWAL_HASH_KEY) < 50:
    raise ImproperlyConfigured('Set a production WITHDRAWAL_HASH_KEY of at least 50 characters.')
if not WITHDRAWAL_HASH_KEY:
    WITHDRAWAL_HASH_KEY = SECRET_KEY
```

`.env.example`에 한 줄 추가한다.

```
# 탈퇴 이메일 해시 키. 운영에서는 50자 이상, DJANGO_SECRET_KEY와 다른 값을 쓴다.
WITHDRAWAL_HASH_KEY=
```

- [ ] **Step 4: 테스트 통과를 확인한다**

Run: `python manage.py test users.test_withdrawal.EmailHashTests -v 2`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add users/utils.py config/settings.py .env.example users/test_withdrawal.py
git commit -m "feat(users): 재가입 차단용 HMAC 이메일 해시 추가"
```

---

## Task 4: 파기 서비스

**Files:**
- Create: `tourist_congestion_backend/users/withdrawal.py`
- Test: `tourist_congestion_backend/users/test_withdrawal.py`

**Interfaces:**
- Consumes: Task 1의 모델 3개, Task 2의 `actor` FK, Task 3의 `hash_email_for_withdrawal`
- Produces: `WITHDRAWAL_GRACE_PERIOD: timedelta`, `WITHDRAWN_EMAIL_RETENTION: timedelta`, `purge_withdrawn_users(now=None) -> int`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`users/test_withdrawal.py`의 import 블록 전체를 아래로 교체한다. Task 5~8은 import를 더 손대지 않아도 되도록 여기서 한 번에 갖춘다.

```python
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from places.models import Place

from .models import (AnonymousActor, Companion, CompanionMember, Favorite, Feedback, Plan,
                     RecentPlace, RefreshToken, Review, ReviewLike, User, WithdrawalReason,
                     WithdrawnEmailHash)
from .utils import hash_email_for_withdrawal
from .withdrawal import purge_withdrawn_users
```

그다음 파일 끝에 테스트를 추가한다.

```python
class PurgeTests(TestCase):
    def setUp(self):
        self.place = create_place()
        self.leaver = User.objects.create_user(
            email='leaver@example.com', password='pw12345678', nickname='떠나는사람')
        self.stayer = User.objects.create_user(
            email='stayer@example.com', password='pw12345678', nickname='남는사람')

    def _request_withdrawal(self, user, reason_code='etc'):
        user.status = User.Status.WITHDRAWN
        user.purge_at = timezone.now() - timedelta(seconds=1)
        user.withdrawal_reason_code = reason_code
        user.save(update_fields=['status', 'purge_at', 'withdrawal_reason_code', 'updated_at'])

    def test_user_row_is_actually_deleted(self):
        self._request_withdrawal(self.leaver)
        purge_withdrawn_users()
        self.assertFalse(User.objects.filter(email='leaver@example.com').exists())

    def test_review_survives_without_its_author(self):
        review = Review.objects.create(user=self.leaver, place=self.place, text='좋았습니다', rating=5)
        self._request_withdrawal(self.leaver)
        purge_withdrawn_users()

        review.refresh_from_db()
        self.assertIsNone(review.user_id)
        self.assertIsNotNone(review.actor_id)
        self.assertEqual(review.text, '좋았습니다')

    def test_feedback_keeps_its_value_but_loses_its_memo(self):
        Feedback.objects.create(user=self.leaver, place=self.place,
                                feedback_type=Feedback.FeedbackType.CROWD, value=70,
                                memo='제가 사는 동네라 잘 압니다')
        self._request_withdrawal(self.leaver)
        purge_withdrawn_users()

        feedback = Feedback.objects.get(place=self.place)
        self.assertEqual(feedback.value, 70)
        self.assertIsNone(feedback.memo)
        self.assertIsNone(feedback.user_id)

    def test_all_preserved_rows_share_one_actor(self):
        Review.objects.create(user=self.leaver, place=self.place, text='글', rating=4)
        Favorite.objects.create(user=self.leaver, place=self.place)
        RecentPlace.objects.create(user=self.leaver, place=self.place)
        self._request_withdrawal(self.leaver)
        purge_withdrawn_users()

        actors = {
            Review.objects.get().actor_id,
            Favorite.objects.get().actor_id,
            RecentPlace.objects.get().actor_id,
        }
        self.assertEqual(len(actors), 1)

    def test_companion_membership_is_deleted_and_counter_is_corrected(self):
        companion = Companion.objects.create(
            user=self.stayer, place=self.place, title='같이 가요', text='본문',
            capacity=4, member_count=2)
        CompanionMember.objects.create(user=self.leaver, companion=companion)
        self._request_withdrawal(self.leaver)
        purge_withdrawn_users()

        companion.refresh_from_db()
        self.assertEqual(companion.member_count, 1)
        self.assertEqual(CompanionMember.objects.count(), 0)

    def test_own_companion_is_removed(self):
        Companion.objects.create(user=self.leaver, place=self.place, title='내 모임',
                                 text='본문', capacity=4)
        self._request_withdrawal(self.leaver)
        purge_withdrawn_users()
        self.assertEqual(Companion.objects.count(), 0)

    def test_private_records_are_cascade_deleted(self):
        Plan.objects.create(user=self.leaver, title='일정', date=date(2026, 10, 1))
        RefreshToken.objects.create(user=self.leaver, token_hash='t' * 64,
                                    expires_at=timezone.now() + timedelta(days=1))
        self._request_withdrawal(self.leaver)
        purge_withdrawn_users()

        self.assertEqual(Plan.objects.count(), 0)
        self.assertEqual(RefreshToken.objects.count(), 0)

    def test_email_hash_is_recorded_with_a_date_only_expiry(self):
        self._request_withdrawal(self.leaver)
        now = timezone.now()
        purge_withdrawn_users(now=now)

        row = WithdrawnEmailHash.objects.get()
        self.assertEqual(row.email_hash, hash_email_for_withdrawal('leaver@example.com'))
        self.assertEqual(row.expires_at, (now + timedelta(days=30)).date())

    def test_reason_is_recorded_without_any_link(self):
        self._request_withdrawal(self.leaver, reason_code='no_longer_needed')
        purge_withdrawn_users()

        reason = WithdrawalReason.objects.get()
        self.assertEqual(reason.reason_code, 'no_longer_needed')

    def test_user_not_yet_due_is_untouched(self):
        self.leaver.status = User.Status.WITHDRAWN
        self.leaver.purge_at = timezone.now() + timedelta(days=7)
        self.leaver.save(update_fields=['status', 'purge_at', 'updated_at'])

        self.assertEqual(purge_withdrawn_users(), 0)
        self.assertTrue(User.objects.filter(email='leaver@example.com').exists())

    def test_running_twice_changes_nothing(self):
        Review.objects.create(user=self.leaver, place=self.place, text='글', rating=4)
        self._request_withdrawal(self.leaver)

        self.assertEqual(purge_withdrawn_users(), 1)
        snapshot = (User.objects.count(), Review.objects.count(),
                    WithdrawnEmailHash.objects.count(), WithdrawalReason.objects.count())
        self.assertEqual(purge_withdrawn_users(), 0)
        self.assertEqual(
            (User.objects.count(), Review.objects.count(),
             WithdrawnEmailHash.objects.count(), WithdrawalReason.objects.count()),
            snapshot,
        )

    def test_expired_email_hashes_are_swept(self):
        WithdrawnEmailHash.objects.create(email_hash='b' * 64,
                                          expires_at=timezone.now().date() - timedelta(days=1))
        purge_withdrawn_users()
        self.assertEqual(WithdrawnEmailHash.objects.count(), 0)

    def test_actor_cannot_be_traced_back_to_the_user(self):
        # 스펙 결정 4: 매핑을 저장하는 컬럼이 어디에도 없어야 한다.
        Review.objects.create(user=self.leaver, place=self.place, text='글', rating=4)
        self._request_withdrawal(self.leaver)
        purge_withdrawn_users()

        actor = AnonymousActor.objects.get()
        column_names = {field.name for field in AnonymousActor._meta.get_fields()}
        self.assertEqual(column_names & {'user', 'user_id', 'email', 'email_hash'}, set())
        self.assertNotIn(str(self.leaver.pk), str(actor.id))
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python manage.py test users.test_withdrawal.PurgeTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'purge_withdrawn_users'`

- [ ] **Step 3: 서비스를 구현한다**

`users/withdrawal.py`를 새로 만든다.

```python
"""회원 탈퇴 파기 로직.

뷰와 배치가 함께 쓴다. 파기는 되돌릴 수 없으므로 HTTP 계층 없이 단위 테스트할 수
있도록 순수 함수로 분리한다.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import (AnonymousActor, Companion, CompanionMember, Favorite, Feedback,
                     RecentPlace, Review, ReviewLike, User, WithdrawalReason,
                     WithdrawnEmailHash)
from .utils import hash_email_for_withdrawal

# 탈퇴 요청 후 실제 파기까지의 유예. 이 기간에는 아무것도 파기하지 않는다.
WITHDRAWAL_GRACE_PERIOD = timedelta(days=7)
# 재가입 악용 방지용 이메일 지문의 보존 기간.
WITHDRAWN_EMAIL_RETENTION = timedelta(days=30)


def purge_withdrawn_users(now=None):
    """유예가 끝난 탈퇴 계정을 파기한다. 파기한 계정 수를 돌려준다.

    사용자 단위 트랜잭션이라 한 명의 실패가 다른 사람을 막지 않는다.
    멱등하다 —— 성공한 계정은 User 행이 사라져 다음 실행의 대상에 잡히지 않는다.
    """
    now = now or timezone.now()
    purged = 0
    due = User.objects.filter(status=User.Status.WITHDRAWN, purge_at__lte=now)
    for user in due.iterator():
        with transaction.atomic():
            _purge_one(user, now)
        purged += 1

    WithdrawnEmailHash.objects.filter(expires_at__lt=now.date()).delete()
    return purged


def _purge_one(user, now):
    actor = AnonymousActor.objects.create()

    # 보존 대상: 소유자를 익명 주체로 바꾼다. user와 actor를 한 번에 써야
    # XOR 제약을 만족한다.
    Feedback.objects.filter(user=user).update(user=None, actor=actor, memo=None)
    Review.objects.filter(user=user).update(user=None, actor=actor)
    ReviewLike.objects.filter(user=user).update(user=None, actor=actor)
    Favorite.objects.filter(user=user).update(user=None, actor=actor)
    RecentPlace.objects.filter(user=user).update(user=None, actor=actor)

    # 남의 모집글 인원수를 먼저 확보한 뒤 참여 이력을 지운다. member_count는
    # 비정규화 카운터라 CASCADE로는 갱신되지 않는다.
    joined = list(CompanionMember.objects.filter(user=user).values_list('companion_id', flat=True))
    CompanionMember.objects.filter(user=user).delete()
    if joined:
        Companion.objects.filter(id__in=joined).update(member_count=F('member_count') - 1)

    Companion.objects.filter(user=user).delete()

    WithdrawnEmailHash.objects.get_or_create(
        email_hash=hash_email_for_withdrawal(user.email),
        defaults={'expires_at': (now + WITHDRAWN_EMAIL_RETENTION).date()},
    )
    if user.withdrawal_reason_code:
        WithdrawalReason.objects.create(
            reason_code=user.withdrawal_reason_code,
            withdrawn_on=now.date(),
        )

    # Plan·Inquiry·PointEntry·RefreshToken이 CASCADE로 함께 사라진다.
    user.delete()
```

- [ ] **Step 4: 테스트 통과를 확인한다**

Run: `python manage.py test users.test_withdrawal.PurgeTests -v 2`
Expected: PASS (13 tests)

- [ ] **Step 5: 커밋**

```bash
git add users/withdrawal.py users/test_withdrawal.py
git commit -m "feat(users): 탈퇴 계정 파기·익명화 서비스 추가"
```

---

## Task 5: 탈퇴 요청 API

**Files:**
- Modify: `tourist_congestion_backend/users/serializers.py`
- Modify: `tourist_congestion_backend/users/views.py`
- Modify: `tourist_congestion_backend/users/urls.py`
- Test: `tourist_congestion_backend/users/test_withdrawal.py`

**Interfaces:**
- Consumes: Task 4의 `WITHDRAWAL_GRACE_PERIOD`
- Produces: `POST /users/me/withdraw` (라우트명 `withdraw`), `WithdrawSerializer`, `verify_google_identity(id_token: str) -> dict | None`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

```python
class WithdrawRequestTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='leaver@example.com', password='pw12345678', nickname='떠나는사람')
        self.client.force_authenticate(user=self.user)

    def test_withdraw_schedules_purge_seven_days_out(self):
        response = self.client.post(reverse('withdraw'), {'password': 'pw12345678'})

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.status, User.Status.WITHDRAWN)
        delta = self.user.purge_at - timezone.now()
        self.assertGreater(delta, timedelta(days=6, hours=23))
        self.assertLess(delta, timedelta(days=7))

    def test_withdraw_requires_the_correct_password(self):
        response = self.client.post(reverse('withdraw'), {'password': 'wrong-password'})

        self.assertEqual(response.status_code, 401)
        self.user.refresh_from_db()
        self.assertEqual(self.user.status, User.Status.ACTIVE)

    def test_withdraw_ends_every_session(self):
        RefreshToken.objects.create(user=self.user, token_hash='t' * 64,
                                    expires_at=timezone.now() + timedelta(days=1))
        self.client.post(reverse('withdraw'), {'password': 'pw12345678'})
        self.assertEqual(RefreshToken.objects.filter(user=self.user).count(), 0)

    def test_withdraw_stores_the_reason_on_the_user_until_purge(self):
        self.client.post(reverse('withdraw'),
                         {'password': 'pw12345678', 'reason_code': 'no_longer_needed'})

        self.user.refresh_from_db()
        self.assertEqual(self.user.withdrawal_reason_code, 'no_longer_needed')
        # 철회한 사람의 사유가 집계에 섞이면 안 되므로 아직 만들지 않는다.
        self.assertEqual(WithdrawalReason.objects.count(), 0)

    def test_withdraw_rejects_an_unknown_reason_code(self):
        response = self.client.post(reverse('withdraw'),
                                    {'password': 'pw12345678', 'reason_code': '제가 이사를 가서요'})
        self.assertEqual(response.status_code, 400)

    def test_withdraw_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(reverse('withdraw'), {'password': 'pw12345678'})
        self.assertIn(response.status_code, (401, 403))
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python manage.py test users.test_withdrawal.WithdrawRequestTests -v 2`
Expected: FAIL — `NoReverseMatch: Reverse for 'withdraw' not found`

- [ ] **Step 3: 시리얼라이저를 추가한다**

`users/serializers.py` 끝에 추가한다.

```python
# 탈퇴 사유는 앱이 제시하는 선택지에서만 고른다. 자유 입력을 허용하면 본인을
# 식별할 수 있는 내용이 들어와 집계의 익명성이 깨진다.
WITHDRAWAL_REASON_CODES = (
    'no_longer_needed',
    'few_places',
    'inaccurate_crowd',
    'privacy_concern',
    'switched_service',
    'etc',
)


class WithdrawSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    id_token = serializers.CharField(required=False, allow_blank=True)
    reason_code = serializers.ChoiceField(choices=WITHDRAWAL_REASON_CODES, required=False)
```

- [ ] **Step 4: 구글 본인 확인 헬퍼를 분리한다**

`users/views.py`의 `GoogleLoginView.post` 안에 있는 `try/except ValueError` 블록을 모듈 수준 함수로 꺼낸다. `issue_tokens` 정의 아래에 추가한다.

```python
def verify_google_identity(raw_id_token):
    """구글 id_token을 검증해 payload를 돌려준다. 실패하면 None."""
    try:
        return google_id_token.verify_oauth2_token(
            raw_id_token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except ValueError:
        return None
```

`GoogleLoginView.post`의 해당 블록을 아래로 교체한다.

```python
        payload = verify_google_identity(serializer.validated_data['id_token'])
        if payload is None:
            return error_response('구글 인증에 실패했습니다.', http_status.HTTP_401_UNAUTHORIZED)
```

- [ ] **Step 5: 뷰를 추가한다**

`users/views.py` 상단 import에 추가한다.

```python
from django.db import transaction

from .serializers import WithdrawSerializer
from .withdrawal import WITHDRAWAL_GRACE_PERIOD
```

본인 확인 헬퍼와 뷰를 파일 끝에 추가한다.

```python
def _identity_confirmed(user, data):
    """탈퇴·철회 직전 본인 확인. 가입 경로에 맞는 수단만 인정한다."""
    if user.provider == User.Provider.GOOGLE:
        payload = verify_google_identity(data.get('id_token') or '')
        return payload is not None and payload.get('sub') == user.provider_user_id
    return user.check_password(data.get('password') or '')


class WithdrawView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = WithdrawSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(serializer.errors)

        user = request.user
        if not _identity_confirmed(user, serializer.validated_data):
            return error_response('본인 확인에 실패했습니다.', http_status.HTTP_401_UNAUTHORIZED)

        with transaction.atomic():
            user.status = User.Status.WITHDRAWN
            user.purge_at = timezone.now() + WITHDRAWAL_GRACE_PERIOD
            user.withdrawal_reason_code = serializer.validated_data.get('reason_code') or None
            user.save(update_fields=['status', 'purge_at', 'withdrawal_reason_code', 'updated_at'])
            # 모든 기기에서 즉시 로그아웃시킨다. 유예를 기다리지 않는다.
            RefreshToken.objects.filter(user=user).delete()

        return success_response(
            {'purge_at': user.purge_at.isoformat()},
            '탈퇴가 접수되었습니다. 7일 이내에 로그인하시면 취소할 수 있습니다.',
        )
```

- [ ] **Step 6: 라우트를 추가한다**

`users/urls.py`의 `urlpatterns`에서 `path('me', ...)` 바로 아래에 추가한다.

```python
    path('me/withdraw', views.WithdrawView.as_view(), name='withdraw'),
```

- [ ] **Step 7: 테스트 통과를 확인한다**

Run: `python manage.py test users -v 2`
Expected: PASS. 기존 구글 로그인 테스트도 통과해야 한다(헬퍼 분리는 동작을 바꾸지 않는다).

- [ ] **Step 8: 커밋**

```bash
git add users/serializers.py users/views.py users/urls.py users/test_withdrawal.py
git commit -m "feat(users): 회원 탈퇴 요청 API 추가"
```

---

## Task 6: 로그인 차단 안내와 철회 API

**Files:**
- Modify: `tourist_congestion_backend/users/views.py`
- Modify: `tourist_congestion_backend/users/urls.py`
- Test: `tourist_congestion_backend/users/test_withdrawal.py`

**Interfaces:**
- Consumes: Task 5의 `_identity_confirmed`
- Produces: `POST /users/me/withdraw/cancel` (라우트명 `withdraw-cancel`), 로그인 실패 시 `403 {'code': 'withdrawal_pending', 'purge_at': ...}`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

```python
class WithdrawalPendingLoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='leaver@example.com', password='pw12345678', nickname='떠나는사람')
        self.user.status = User.Status.WITHDRAWN
        self.user.purge_at = timezone.now() + timedelta(days=7)
        self.user.save(update_fields=['status', 'purge_at', 'updated_at'])

    def test_login_reports_withdrawal_pending(self):
        response = self.client.post(reverse('auth-login'),
                                    {'email': 'leaver@example.com', 'password': 'pw12345678'})

        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body['success'])
        self.assertEqual(body['data']['code'], 'withdrawal_pending')
        self.assertIn('purge_at', body['data'])

    def test_wrong_password_does_not_reveal_withdrawal(self):
        response = self.client.post(reverse('auth-login'),
                                    {'email': 'leaver@example.com', 'password': 'wrong'})

        self.assertEqual(response.status_code, 401)
        self.assertNotIn('withdrawal_pending', response.content.decode())

    def test_unknown_email_stays_a_plain_401(self):
        response = self.client.post(reverse('auth-login'),
                                    {'email': 'nobody@example.com', 'password': 'pw12345678'})
        self.assertEqual(response.status_code, 401)


class WithdrawCancelTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.place = create_place()
        self.user = User.objects.create_user(
            email='leaver@example.com', password='pw12345678', nickname='떠나는사람')
        Review.objects.create(user=self.user, place=self.place, text='글', rating=5)
        self.user.status = User.Status.WITHDRAWN
        self.user.purge_at = timezone.now() + timedelta(days=7)
        self.user.withdrawal_reason_code = 'etc'
        self.user.save(update_fields=['status', 'purge_at', 'withdrawal_reason_code', 'updated_at'])

    def test_cancel_restores_the_account_and_returns_tokens(self):
        response = self.client.post(reverse('withdraw-cancel'),
                                    {'email': 'leaver@example.com', 'password': 'pw12345678'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('access_token', response.json()['data'])
        self.user.refresh_from_db()
        self.assertEqual(self.user.status, User.Status.ACTIVE)
        self.assertIsNone(self.user.purge_at)
        self.assertIsNone(self.user.withdrawal_reason_code)

    def test_cancelled_withdrawal_never_reaches_the_reason_statistics(self):
        # 스펙 §9 검증 12: 철회한 사람의 사유가 집계를 부풀리면 안 된다.
        self.client.post(reverse('withdraw-cancel'),
                         {'email': 'leaver@example.com', 'password': 'pw12345678'})
        purge_withdrawn_users()
        self.assertEqual(WithdrawalReason.objects.count(), 0)
        self.assertTrue(User.objects.filter(email='leaver@example.com').exists())

    def test_cancel_leaves_every_row_intact(self):
        self.client.post(reverse('withdraw-cancel'),
                         {'email': 'leaver@example.com', 'password': 'pw12345678'})

        review = Review.objects.get()
        self.assertEqual(review.user_id, self.user.pk)
        self.assertIsNone(review.actor_id)

    def test_cancel_is_refused_once_the_purge_is_due(self):
        self.user.purge_at = timezone.now() - timedelta(seconds=1)
        self.user.save(update_fields=['purge_at', 'updated_at'])

        response = self.client.post(reverse('withdraw-cancel'),
                                    {'email': 'leaver@example.com', 'password': 'pw12345678'})

        self.assertEqual(response.status_code, 409)
        self.user.refresh_from_db()
        self.assertEqual(self.user.status, User.Status.WITHDRAWN)

    def test_cancel_requires_the_correct_password(self):
        response = self.client.post(reverse('withdraw-cancel'),
                                    {'email': 'leaver@example.com', 'password': 'wrong'})
        self.assertEqual(response.status_code, 401)

    def test_cancel_does_nothing_for_an_active_account(self):
        self.user.status = User.Status.ACTIVE
        self.user.purge_at = None
        self.user.save(update_fields=['status', 'purge_at', 'updated_at'])

        response = self.client.post(reverse('withdraw-cancel'),
                                    {'email': 'leaver@example.com', 'password': 'pw12345678'})
        self.assertEqual(response.status_code, 401)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python manage.py test users.test_withdrawal.WithdrawCancelTests -v 2`
Expected: FAIL — `NoReverseMatch: Reverse for 'withdraw-cancel' not found`

- [ ] **Step 3: 조회 헬퍼를 추가한다**

`users/views.py`의 `_identity_confirmed` 아래에 추가한다.

```python
def _pending_withdrawal_account(data):
    """탈퇴 유예 중이면서 본인 확인에 성공한 계정을 돌려준다. 아니면 None.

    본인 확인이 끝난 뒤에만 탈퇴 사실을 알려 준다. 먼저 알려 주면 남의 이메일로
    탈퇴 여부를 캐낼 수 있다.
    """
    email = (data.get('email') or '').strip().lower()
    if not email:
        return None
    user = User.objects.filter(email__iexact=email, status=User.Status.WITHDRAWN).first()
    if user is None or not _identity_confirmed(user, data):
        return None
    return user
```

- [ ] **Step 4: 로그인 뷰에 분기를 넣는다**

`users/views.py`의 `LoginView.post`를 아래로 교체한다.

```python
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            # authenticate()는 is_active가 False인 탈퇴 유예 계정도 거부한다.
            # 본인이 맞다면 일반 401 대신 복구 안내를 준다.
            pending = _pending_withdrawal_account(request.data)
            if pending is not None:
                return Response(
                    {
                        'success': False,
                        'data': {
                            'code': 'withdrawal_pending',
                            'purge_at': pending.purge_at.isoformat(),
                        },
                        'message': '탈퇴 예정 계정입니다. 복구할 수 있습니다.',
                    },
                    status=http_status.HTTP_403_FORBIDDEN,
                )
            return error_response(
                '이메일 또는 비밀번호가 올바르지 않습니다.',
                http_status.HTTP_401_UNAUTHORIZED,
            )

        user = serializer.validated_data['user']
        tokens = issue_tokens(user)
        return success_response(tokens, '로그인되었습니다.')
```

- [ ] **Step 5: 철회 뷰를 추가한다**

`users/views.py` 끝에 추가한다.

```python
class WithdrawCancelView(APIView):
    # 유예 중에는 로그인이 막혀 있어 인증 헤더를 받을 수 없다. 자격 증명을 직접 받는다.
    permission_classes = [AllowAny]

    def post(self, request):
        user = _pending_withdrawal_account(request.data)
        if user is None:
            return error_response(
                '이메일 또는 비밀번호가 올바르지 않습니다.',
                http_status.HTTP_401_UNAUTHORIZED,
            )
        if user.purge_at is None or user.purge_at <= timezone.now():
            # 배치 실행 시각에 따라 결과가 달라지지 않도록, 기한이 지나면 거부한다.
            return error_response(
                '이미 파기 절차가 시작되어 복구할 수 없습니다.',
                http_status.HTTP_409_CONFLICT,
            )

        user.status = User.Status.ACTIVE
        user.purge_at = None
        user.withdrawal_reason_code = None
        user.save(update_fields=['status', 'purge_at', 'withdrawal_reason_code', 'updated_at'])

        tokens = issue_tokens(user)
        return success_response(tokens, '탈퇴가 취소되었습니다.')
```

- [ ] **Step 6: 라우트를 추가한다**

`users/urls.py`의 `path('me/withdraw', ...)` 바로 아래에 추가한다.

```python
    path('me/withdraw/cancel', views.WithdrawCancelView.as_view(), name='withdraw-cancel'),
```

- [ ] **Step 7: 테스트 통과를 확인한다**

Run: `python manage.py test users -v 2`
Expected: PASS

- [ ] **Step 8: 커밋**

```bash
git add users/views.py users/urls.py users/test_withdrawal.py
git commit -m "feat(users): 탈퇴 유예 안내와 철회 API 추가"
```

---

## Task 7: 재가입 차단

**Files:**
- Modify: `tourist_congestion_backend/users/serializers.py`
- Test: `tourist_congestion_backend/users/test_withdrawal.py`

**Interfaces:**
- Consumes: Task 3의 `hash_email_for_withdrawal`, Task 1의 `WithdrawnEmailHash`
- Produces: 없음 (기존 `SignupSerializer` 동작 변경)

- [ ] **Step 1: 실패하는 테스트를 작성한다**

```python
class RejoinBlockTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _block(self, email, days=30):
        WithdrawnEmailHash.objects.create(
            email_hash=hash_email_for_withdrawal(email),
            expires_at=timezone.now().date() + timedelta(days=days),
        )

    def _signup(self, email):
        return self.client.post(reverse('auth-signup'), {
            'email': email, 'password': 'pw12345678', 'nickname': '재가입자',
        })

    def test_recently_withdrawn_email_cannot_sign_up(self):
        self._block('leaver@example.com')
        self.assertEqual(self._signup('leaver@example.com').status_code, 400)
        self.assertFalse(User.objects.filter(email='leaver@example.com').exists())

    def test_block_ignores_case(self):
        self._block('leaver@example.com')
        self.assertEqual(self._signup('Leaver@Example.com').status_code, 400)

    def test_expired_block_allows_sign_up(self):
        WithdrawnEmailHash.objects.create(
            email_hash=hash_email_for_withdrawal('leaver@example.com'),
            expires_at=timezone.now().date() - timedelta(days=1),
        )
        self.assertEqual(self._signup('leaver@example.com').status_code, 201)

    def test_rejection_does_not_reveal_that_the_account_was_withdrawn(self):
        self._block('leaver@example.com')
        body = self._signup('leaver@example.com').content.decode()
        for leak in ('탈퇴', '30일', 'withdraw'):
            self.assertNotIn(leak, body)

    def test_unrelated_email_is_unaffected(self):
        self._block('leaver@example.com')
        self.assertEqual(self._signup('newcomer@example.com').status_code, 201)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python manage.py test users.test_withdrawal.RejoinBlockTests -v 2`
Expected: FAIL — `test_recently_withdrawn_email_cannot_sign_up`이 400 대신 201을 받는다

- [ ] **Step 3: 검증을 추가한다**

`users/serializers.py` 상단 import에 추가한다.

```python
from django.utils import timezone

from .models import WithdrawnEmailHash
from .utils import hash_email_for_withdrawal
```

`SignupSerializer`에 `validate_email`을 추가한다. `validate_nickname` 바로 위에 둔다.

```python
    def validate_email(self, value):
        blocked = WithdrawnEmailHash.objects.filter(
            email_hash=hash_email_for_withdrawal(value),
            expires_at__gte=timezone.now().date(),
        ).exists()
        if blocked:
            # 탈퇴 사실을 밝히지 않는다. 밝히면 남의 이메일로 탈퇴 여부를 캐낼 수 있다.
            raise serializers.ValidationError('지금은 이 이메일로 가입할 수 없습니다.')
        return value
```

- [ ] **Step 4: 테스트 통과를 확인한다**

Run: `python manage.py test users -v 2`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add users/serializers.py users/test_withdrawal.py
git commit -m "feat(users): 탈퇴 후 30일 재가입 차단"
```

---

## Task 8: 익명 작성자 응답과 `is_mine` 결함 수정

**Files:**
- Modify: `tourist_congestion_backend/users/activity_views.py:17-24`
- Modify: `tourist_congestion_backend/users/activity_views.py:259`
- Test: `tourist_congestion_backend/users/test_withdrawal.py`

**Interfaces:**
- Consumes: Task 2의 nullable `user`
- Produces: 리뷰 응답 계약 — `author_id: int | None`, `author_nickname: str`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

```python
ANONYMOUS_AUTHOR_NAME = '탈퇴한 사용자'


class AnonymisedReviewResponseTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.place = create_place()
        self.leaver = User.objects.create_user(
            email='leaver@example.com', password='pw12345678', nickname='떠나는사람')
        self.review = Review.objects.create(user=self.leaver, place=self.place,
                                            text='좋았습니다', rating=5)
        self.leaver.status = User.Status.WITHDRAWN
        self.leaver.purge_at = timezone.now() - timedelta(seconds=1)
        self.leaver.save(update_fields=['status', 'purge_at', 'updated_at'])
        purge_withdrawn_users()

    def _fetch(self):
        response = self.client.get(reverse('reviews'), {'place_id': self.place.pk})
        self.assertEqual(response.status_code, 200)
        return response.json()['data']['items'][0]

    def test_author_is_shown_as_withdrawn(self):
        item = self._fetch()
        self.assertIsNone(item['author_id'])
        self.assertEqual(item['author_nickname'], ANONYMOUS_AUTHOR_NAME)

    def test_anonymous_visitor_does_not_own_the_review(self):
        # request.user.id도 None, item.user_id도 None이라 == 비교가 참이 된다.
        # 이 버그가 살아 있으면 비로그인 방문자에게 수정·삭제 UI가 노출된다.
        item = self._fetch()
        self.assertFalse(item['is_mine'])

    def test_signed_in_visitor_does_not_own_the_review(self):
        other = User.objects.create_user(
            email='other@example.com', password='pw12345678', nickname='다른사람')
        self.client.force_authenticate(user=other)
        self.assertFalse(self._fetch()['is_mine'])


class NotificationTests(TestCase):
    def test_anonymised_likes_are_not_listed(self):
        client = APIClient()
        place = create_place()
        author = User.objects.create_user(
            email='author@example.com', password='pw12345678', nickname='작성자')
        liker = User.objects.create_user(
            email='liker@example.com', password='pw12345678', nickname='좋아요한사람')
        review = Review.objects.create(user=author, place=place, text='글', rating=4)
        ReviewLike.objects.create(user=liker, review=review)

        liker.status = User.Status.WITHDRAWN
        liker.purge_at = timezone.now() - timedelta(seconds=1)
        liker.save(update_fields=['status', 'purge_at', 'updated_at'])
        purge_withdrawn_users()

        client.force_authenticate(user=author)
        response = client.get(reverse('notifications'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['items'], [])
```

`reverse('reviews')`와 `reverse('notifications')`가 동작하려면 라우트에 `name`이 있어야 한다. `users/urls.py`에서 두 줄에 이름을 붙인다.

```python
    path('notifications', activity.NotificationsView.as_view(), name='notifications'),
    path('reviews', activity.ReviewsView.as_view(), name='reviews'),
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python manage.py test users.test_withdrawal.AnonymisedReviewResponseTests -v 2`
Expected: FAIL — `AttributeError: 'NoneType' object has no attribute 'nickname'`

- [ ] **Step 3: `review_data`를 고친다**

`users/activity_views.py`의 `review_data`를 아래로 교체한다.

```python
# 탈퇴자가 남긴 글의 작성자 표기. 원 작성자는 복원할 수 없다.
ANONYMOUS_AUTHOR_NAME = '탈퇴한 사용자'


def review_data(item, request):
    return {'id': item.id, 'place_id': item.place_id, 'place_name': item.place.name,
            'author_id': item.user_id,
            'author_nickname': item.user.nickname if item.user_id else ANONYMOUS_AUTHOR_NAME,
            'text': item.text, 'rating': item.rating,
            'photo_url': request.build_absolute_uri(item.photo.url) if item.photo else None,
            'created_at': item.created_at, 'like_count': item.likes.count(),
            'is_liked': request.user.is_authenticated and item.likes.filter(user=request.user).exists(),
            # item.user_id가 None이고 비로그인 방문자의 request.user.id도 None이라
            # 단순 == 비교는 탈퇴자 글을 전부 '내 글'로 만든다.
            'is_mine': item.user_id is not None and request.user.id == item.user_id,
            'visit_verified': False}
```

- [ ] **Step 4: 알림 조회에서 익명 행을 제외한다**

`users/activity_views.py:259`의 `ReviewLike` 조회에 `filter(user__isnull=False)`를 추가한다.

```python
        for like in ReviewLike.objects.filter(review__user=request.user, user__isnull=False).exclude(user=request.user).select_related('user', 'review__place').order_by('-created_at')[:50]:
```

- [ ] **Step 5: 같은 결함이 더 있는지 확인한다**

```bash
grep -rn "user_id ==\|== .*user_id" --include=*.py users/ places/ recommendations/
```

`review_data` 외에 나온 곳이 있으면 같은 방식으로 고친다. `companion_data`의 `is_mine`은 고치지 않는다 —— `Companion.user`는 nullable이 아니다.

- [ ] **Step 6: 테스트 통과를 확인한다**

Run: `python manage.py test users -v 2`
Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add users/activity_views.py users/urls.py users/test_withdrawal.py
git commit -m "fix(users): 익명 작성자 응답 처리와 is_mine NULL 비교 결함 수정"
```

---

## Task 9: 파기 명령과 워커 편입

**Files:**
- Create: `tourist_congestion_backend/users/management/__init__.py`
- Create: `tourist_congestion_backend/users/management/commands/__init__.py`
- Create: `tourist_congestion_backend/users/management/commands/purge_withdrawn_users.py`
- Modify: `tourist_congestion_backend/places/management/commands/run_data_worker.py`
- Test: `tourist_congestion_backend/users/test_withdrawal.py`

**Interfaces:**
- Consumes: Task 4의 `purge_withdrawn_users`
- Produces: `python manage.py purge_withdrawn_users` 명령

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`users/test_withdrawal.py` import 블록 맨 위에 두 줄을 추가한다.

```python
from io import StringIO

from django.core.management import call_command
```

```python
class PurgeCommandTests(TestCase):
    def test_command_purges_due_accounts_and_reports_the_count(self):
        user = User.objects.create_user(
            email='leaver@example.com', password='pw12345678', nickname='떠나는사람')
        user.status = User.Status.WITHDRAWN
        user.purge_at = timezone.now() - timedelta(seconds=1)
        user.save(update_fields=['status', 'purge_at', 'updated_at'])

        out = StringIO()
        call_command('purge_withdrawn_users', stdout=out)

        self.assertFalse(User.objects.filter(email='leaver@example.com').exists())
        self.assertIn('1', out.getvalue())

    def test_command_is_safe_when_nothing_is_due(self):
        out = StringIO()
        call_command('purge_withdrawn_users', stdout=out)
        self.assertIn('0', out.getvalue())
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python manage.py test users.test_withdrawal.PurgeCommandTests -v 2`
Expected: FAIL — `CommandError: Unknown command: 'purge_withdrawn_users'`

- [ ] **Step 3: 명령을 만든다**

빈 `users/management/__init__.py`와 `users/management/commands/__init__.py`를 만든다.

`users/management/commands/purge_withdrawn_users.py`:

```python
from django.core.management.base import BaseCommand

from users.withdrawal import purge_withdrawn_users


class Command(BaseCommand):
    help = 'Purge accounts whose withdrawal grace period has elapsed.'

    def handle(self, *args, **options):
        purged = purge_withdrawn_users()
        self.stdout.write(f'purged={purged}')
```

- [ ] **Step 4: 워커에 편입한다**

`places/management/commands/run_data_worker.py`의 `schedule()` 호출 블록을 아래로 교체한다.

```python
                    if minute != last_schedule:
                        from places.services.scheduling import schedule
                        from users.withdrawal import purge_withdrawn_users
                        schedule()
                        # 파기 실패가 데이터 수집 스케줄을 멈추지 않게 분리한다.
                        # 대상이 없으면 인덱스 조회 한 번으로 끝나므로 매분 호출해도 무방하다.
                        try:
                            purged = purge_withdrawn_users()
                            if purged:
                                self.stdout.write(f'purged_withdrawn_users={purged}')
                        except Exception as error:
                            self.stderr.write(f'purge_withdrawn_users failed: {error}')
                        last_schedule = minute
```

- [ ] **Step 5: 테스트 통과를 확인한다**

Run: `python manage.py test -v 2`
Expected: PASS (users·places·recommendations 전체)

- [ ] **Step 6: 커밋**

```bash
git add users/management/ places/management/commands/run_data_worker.py users/test_withdrawal.py
git commit -m "feat(users): 파기 배치 명령과 데이터 워커 편입"
```

---

## Task 10: 문서 갱신

**Files:**
- Modify: `docs/legal/privacy-policy.md`
- Modify: `docs/privacy/dev-todo.md`
- Modify: `tourist_congestion_backend/API.md`

**Interfaces:**
- Consumes: Task 1~9의 확정된 동작
- Produces: 없음 (문서)

설계와 처리방침이 어긋나면 그 자체가 개인정보 보호법 제30조 위반이다. 이 작업은 선택이 아니다.

- [ ] **Step 1: 처리방침 제3조 표를 고친다**

`docs/legal/privacy-policy.md`의 보유 기간 표에서 세 행을 바꾼다.

| 기존 | 변경 |
|------|------|
| `계정 정보(...) \| **회원 탈퇴 시 지체 없이 파기**` | `계정 정보(...) \| 탈퇴 신청 후 **7일**이 지나면 파기. 7일 안에는 취소하실 수 있습니다` |
| `즐겨찾기·선호 설정·알림 설정 \| 회원 탈퇴 시 파기` | `선호 설정·알림 설정 \| 회원 탈퇴 시 파기` |
| (없음) | `즐겨찾기·최근 본 장소·후기·서비스 피드백 \| 탈퇴하시면 **누구의 것인지 알 수 없는 형태로 바꾸어** 보관합니다. 되돌릴 수 없으며, 통계와 추천 품질 개선에만 씁니다` |

재가입 방지용 이메일 정보 행(최대 30일)은 그대로 둔다.

- [ ] **Step 2: 처리방침에 익명화 설명을 추가한다**

제3조 표 아래, "위치 정보의 보관에 관한 안내" 절 바로 앞에 넣는다.

```markdown
### 탈퇴하시면 남는 것과 사라지는 것

탈퇴하시면 계정 정보와 여행 일정, 1:1 문의, 동행 모집 글은 모두 지워집니다.

후기와 즐겨찾기처럼 **서비스에 남는 기록**은 지우는 대신 **누가 남겼는지 알 수 없게** 바꿉니다.
바꾼 뒤에는 회사도 그것이 누구의 기록이었는지 알아낼 수 없습니다. 되돌리는 열쇠를 아예 만들지
않기 때문입니다. 이렇게 바꾼 기록은 개인을 알아볼 수 없으므로 기간 제한 없이 보관하며,
혼잡도 예측과 추천 품질을 높이는 데에만 씁니다.

후기는 작성자 이름만 "탈퇴한 사용자"로 바뀌고 글과 사진은 남습니다. 다른 이용자에게 도움이 되는
장소 정보이기 때문입니다. 탈퇴 전에 직접 지우시면 사진 파일까지 함께 사라집니다.
```

- [ ] **Step 3: 선행 조치 표를 갱신한다**

`docs/legal/privacy-policy.md`의 "공개 전 선행 조치" 표에서 1번과 2번 행의 현재 상태를 `❌ 없음`에서 `✅ 구현`으로 바꾼다.

- [ ] **Step 4: 개발 To-Do를 갱신한다**

`docs/privacy/dev-todo.md`에서 탈퇴·파기 관련 항목을 완료 처리하고, 잔여 위험 두 건을 새로 등록한다.

```markdown
- [ ] 후기 본문의 식별 내용 — 익명화해도 "저는 OO동 사는데" 같은 문장이 남는다.
      탈퇴 기능 설계에서 수용된 잔여 위험. 별도 과제로 검토한다.
      근거: `docs/superpowers/specs/2026-09-17-account-withdrawal-design.md` §5.3
- [ ] 후기 사진 EXIF — 업로드 시 위치·기기 정보를 제거하지 않고 있다. 탈퇴 후에도 남는다.
```

- [ ] **Step 5: API 문서에 엔드포인트를 추가한다**

`tourist_congestion_backend/API.md`에 두 엔드포인트와 로그인 403 응답을 기존 서술 형식에 맞춰 추가한다. 프론트엔드가 알아야 할 계약을 빠뜨리지 않는다.

- `POST /users/me/withdraw` — 인증 필요. 이메일 가입자는 `password`, 구글 가입자는 `id_token`. 선택 입력 `reason_code`. 응답 `data.purge_at`
- `POST /users/me/withdraw/cancel` — 인증 불필요. `email` + (`password` | `id_token`). 성공 시 토큰 발급. 기한 경과 시 409
- `POST /users/auth/login` — 탈퇴 유예 중이면 403, `data.code = "withdrawal_pending"`, `data.purge_at`
- 리뷰 응답 변경 — `author_id`가 `null`일 수 있고, 그때 `author_nickname`은 `"탈퇴한 사용자"`

- [ ] **Step 6: 커밋**

```bash
git add docs/legal/privacy-policy.md docs/privacy/dev-todo.md tourist_congestion_backend/API.md
git commit -m "docs: 탈퇴 기능 반영해 처리방침·API 문서 갱신"
```

---

## 완료 확인

- [ ] `python manage.py test` 전체 통과
- [ ] `python manage.py makemigrations --check --dry-run` 이 "No changes detected" 를 출력한다
- [ ] 스펙 §9의 검증 항목 13개가 모두 테스트로 존재한다
- [ ] `grep -rn "sha256(.*email" users/` 결과가 없다 (HMAC이 아닌 해시 잔존 확인)
