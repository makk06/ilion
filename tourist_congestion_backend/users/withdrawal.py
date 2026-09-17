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
    멱등하다 — 성공한 계정은 User 행이 사라져 다음 실행의 대상에 잡히지 않는다.
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
