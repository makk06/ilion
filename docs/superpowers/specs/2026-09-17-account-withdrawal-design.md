# 회원 탈퇴 및 탈퇴 후 데이터 보존 설계

- 작성일: **2026-09-17**
- 대상: ILION 백엔드 (`tourist_congestion_backend`)
- 기준 커밋: `8f08fc9`
- 관련 문서: [개인정보 처리방침 초안](../../legal/privacy-policy.md) · [동의 분류표](../../privacy/consent-matrix.md) · [개발 To-Do](../../privacy/dev-todo.md)

> ## ⚠ 면책
> 본 문서는 코드베이스 분석과 공개된 법령 정보를 바탕으로 작성된 내부 설계 자료이며, 법률 자문이 아니다.
> 조문 번호와 요건은 국가법령정보센터(law.go.kr) 원문으로 대조해야 하며, 서비스 출시 전 개인정보보호
> 전문가 검토 또는 개인정보보호위원회 사전 상담을 권고한다.

---

## 1. 배경

탈퇴 기능이 없다. `User.Status.WITHDRAWN` 값만 정의되어 있고 코드 어디에서도 사용되지 않는다.
개인정보 처리방침 초안은 탈퇴 기능을 전제로 작성되어 있어, 탈퇴 없이 서비스를 운영하는 현재 상태는
방침과 실제 처리가 불일치한다.

동시에 백엔드 팀은 탈퇴자의 행동 데이터를 추천·혼잡도 알고리즘 개선에 계속 활용하기를 원한다.
이 두 요구는 충돌한다. 개인정보 보호법 제21조는 목적 달성 시 **지체 없이 파기**를 요구하고,
같은 조는 상태값만 바꾸고 데이터를 계속 보관하는 구현을 방어하지 못한다.

본 설계는 **복원 불가능한 익명화**로 두 요구를 동시에 만족시킨다. 익명화된 데이터는 개인정보가
아니므로 파기 의무가 적용되지 않으면서, 개인 단위 행동 시퀀스는 그대로 보존되어 협업 필터링
학습에 사용할 수 있다.

---

## 2. 확정된 결정

브레인스토밍에서 합의된 사항이다. 구현 중 이 결정을 바꾸려면 다시 합의해야 한다.

| # | 항목 | 결정 |
|---|------|------|
| 1 | 보존 목적 | 익명 행동 시퀀스, 장소 단위 집계, 운영 지표, 재가입 악용 방지, 리뷰 콘텐츠 |
| 2 | 탈퇴자 리뷰 | 작성자만 익명화하고 본문·사진·평점 유지 |
| 3 | 유예기간 | **7일** |
| 4 | 재식별 가능성 | **복원 불가** — `user_id` ↔ `actor_id` 매핑을 저장하지 않는다 |
| 5 | 동행 모집·참여 | 모두 삭제, `member_count` 보정 |
| 6 | 재가입 방지 해시 | **30일** 보존 |
| 7 | 익명 행동 데이터 | **무기한** 보존 |
| 8 | `Feedback.memo` | 익명화 시 **NULL 처리** |
| 9 | 파기 배치 | 기존 `run_data_worker`에 편입 |

### 채택한 접근 (접근 C)

`AnonymousActor` 모델을 신설하고, 보존 대상 모델의 `user` FK를 nullable로 전환하면서 `actor`
FK를 추가한다. 탈퇴 시 보존 대상 행은 `user=NULL, actor=<신규 actor>`로 옮기고 `User` 행은
실제로 삭제한다.

검토했으나 채택하지 않은 대안:

- **접근 A (툼스톤 유저)** — `User` 행을 남기고 식별자만 비운다. 마이그레이션이 거의 없지만,
  `users` 테이블에 탈퇴자 행이 잔존하는 구조를 감사에서 방어해야 하고 `email` unique 제약과
  충돌한다.
- **접근 B (익명 테이블 전량 이관)** — 보존 대상을 별도 테이블로 복사한다. 파기 의무는 가장
  명확하나 리뷰 조회 API가 두 테이블을 UNION 해야 해서 구현량이 가장 크고 조회 성능이 나빠진다.

---

## 3. 상태 머신

`Status.WITHDRAWN`은 **"탈퇴 요청됨, 파기 대기 중"** 단 하나의 의미를 갖는다. 파기가 끝나면 행
자체가 사라지므로 "파기 완료" 상태는 존재하지 않는다.

```
ACTIVE ──POST /users/me/withdraw──▶ WITHDRAWN (purge_at = now + 7일)
   ▲                                    │
   └──POST /users/me/withdraw/cancel────┘
                                        │
                        purge_withdrawn_users 배치
                                        ▼
                                  User 행 삭제
```

### 로그인 차단은 이미 동작한다

`User.is_active`는 `status == ACTIVE`를 반환한다. `status`를 `withdrawn`으로 바꾸는 순간 Django
인증이 로그인을 거부하므로 인증 계층은 수정하지 않는다.

### 그 결과 생기는 문제와 대응

로그인이 막히면 유예기간 중 철회도 불가능하다. 로그인 실패를 401로 끝내지 말고, 대상 계정이
`withdrawn`이면 다음을 반환한다.

```
403 Forbidden
{ "code": "withdrawal_pending", "purge_at": "2026-09-24T10:00:00Z" }
```

앱은 이 응답을 받아 복구 안내를 띄우고, 이용자가 동의하면 철회 엔드포인트를 호출한다. 철회
엔드포인트는 로그인 없이 호출되므로 **이메일 + 비밀번호(또는 소셜 재인증)를 다시 검증**한다.

---

## 4. 데이터 모델

### 4.1 신규 모델

```python
class AnonymousActor(models.Model):
    """탈퇴자의 행동 데이터를 묶는 익명 주체.

    식별 컬럼을 두지 않는다. 원래 user_id와의 매핑을 저장하는 장소가 존재하지 않으므로
    복원이 구조적으로 불가능하다.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
```

```python
class WithdrawnEmailHash(models.Model):
    """재가입 악용 방지용. 30일간 동일 이메일 재가입을 차단한다."""
    email_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateField(db_index=True)   # 날짜 단위 — 5.2 참조
```

```python
class WithdrawalReason(models.Model):
    """탈퇴 사유 집계. 어떤 개인·actor와도 연결되지 않는다."""
    reason_code = models.CharField(max_length=30)   # 사전 정의된 코드만 허용
    withdrawn_on = models.DateField()               # 날짜 단위
```

`WithdrawalReason`은 자유 입력을 받지 않는다. 자유 텍스트를 허용하면 본인을 식별할 수 있는 내용이
들어와 익명성이 깨진다. 사유 코드는 앱이 제시하는 선택지에서만 고른다.

### 4.2 `User` 변경

두 필드를 추가한다. 둘 다 `status`가 `withdrawn`일 때만 값이 채워지고, 철회 시 NULL로 되돌린다.

```python
purge_at = models.DateTimeField(null=True, blank=True)
withdrawal_reason_code = models.CharField(max_length=30, null=True, blank=True)
```

`withdrawal_reason_code`는 **유예기간 동안의 임시 보관 자리**다. 탈퇴 사유는 요청 시점에 받지만
`WithdrawalReason` 집계 행은 파기 시점에 만든다. 요청 시점에 만들면 철회한 사람의 사유까지
집계에 섞여 지표가 부풀려지기 때문이다.

### 4.3 보존 대상 5개 모델 변경

`Review`, `ReviewLike`, `Feedback`, `Favorite`, `RecentPlace`에 동일하게 적용한다.

```python
user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, ...)
actor = models.ForeignKey(AnonymousActor, on_delete=models.CASCADE, null=True, blank=True, ...)
```

불변식: `user`와 `actor` 중 **정확히 하나만** NULL이 아니다. DB 제약으로 강제한다.

```python
models.CheckConstraint(
    condition=(Q(user__isnull=False) & Q(actor__isnull=True))
              | (Q(user__isnull=True) & Q(actor__isnull=False)),
    name='<model>_user_xor_actor',
)
```

> 이 프로젝트는 **Django 6.0.6**이다. `CheckConstraint`의 `check=` 인자는 5.1에서 deprecated,
> 6.0에서 제거되었으므로 반드시 `condition=`을 쓴다.

`Favorite`과 `RecentPlace`의 기존 `UniqueConstraint(fields=['user', 'place'])`는 `user`가 NULL이
되면 무력화된다(SQL에서 NULL은 서로 같지 않다). `actor` + `place` 조합에도 동일한 유니크 제약을
추가해 actor 단위 중복을 막는다.

---

## 5. 익명화 규칙 — 재식별 방어

결정 4(복원 불가)는 스키마만으로 달성되지 않는다. 아래 세 가지를 지켜야 실질적 익명성이 성립한다.

### 5.1 이메일 해시는 HMAC이어야 한다

단순 `sha256(email)`은 쓰지 않는다. 이메일은 후보 공간이 좁아 전수 대입으로 복원된다. 서버
시크릿을 키로 하는 **HMAC-SHA256**을 사용한다.

```python
hmac.new(
    settings.WITHDRAWAL_HASH_KEY.encode(),
    email.lower().encode(),
    hashlib.sha256,
).hexdigest()
```

`WITHDRAWAL_HASH_KEY`는 `SECRET_KEY`와 **분리된 별도 시크릿**이어야 한다. `SECRET_KEY`는 운영 중
교체될 수 있고, 교체되면 재가입 차단이 조용히 무력화된다.

### 5.2 타임스탬프 상관 공격을 차단한다

`WithdrawnEmailHash`와 `AnonymousActor`는 조인 키가 없지만, 두 행이 같은 트랜잭션에서 생성되면
`created_at`이 초 단위로 일치해 짝을 맞출 수 있다. 이 경로로 "어떤 이메일의 사람이 어떤 행동
이력을 남겼는지"가 복원된다.

따라서 **`AnonymousActor`에는 어떤 시각 컬럼도 두지 않는다.** `WithdrawnEmailHash`는 `expires_at`
하나만 가지며, 타입을 `DateTimeField`가 아니라 **`DateField`로 둔다.**

`expires_at = (탈퇴 요청일 + 30일)의 날짜 부분`이다. 같은 날 탈퇴한 사람은 모두 동일한 값을
가지므로, 그날 생성된 `AnonymousActor` 중 누가 어느 해시와 짝인지 구별할 수 없다. 하루 탈퇴자가
한 명뿐이면 이 방어는 무력하지만, 그 경우 `AnonymousActor`에 시각 정보가 아예 없어 애초에
짝지을 기준이 없다.

`WithdrawalReason.withdrawn_on`도 같은 이유로 `DateField`다.

### 5.3 자유 텍스트

`Feedback.memo`는 익명화 시 NULL로 비운다(결정 8). 알고리즘이 사용하는 것은 `value`(0~100)이며
메모는 내부 참고용이므로 손실이 없다.

`Review.text`는 결정 2에 따라 본문을 유지한다. 본문에 작성자를 식별할 수 있는 내용이 남을 수
있으므로, 이 데이터는 **"완전한 익명정보"라고 단정할 수 없다.** 수용된 잔여 위험으로 기록한다.
리뷰 사진의 EXIF 위치·기기 정보도 같은 성격의 잔여 위험이다.

> 잔여 위험 대응은 본 설계의 범위 밖이다. 별도 과제로 [개발 To-Do](../../privacy/dev-todo.md)에
> 남긴다.

---

## 6. 모델별 처분표

| 모델 | 처분 | 방법 |
|------|------|------|
| `Feedback` | 익명 유지 | `user=NULL`, `actor` 지정, `memo=NULL` |
| `Review` | 익명 유지 | `user=NULL`, `actor` 지정 |
| `ReviewLike` | 익명 유지 | `user=NULL`, `actor` 지정 |
| `Favorite` | 익명 유지 | `user=NULL`, `actor` 지정 |
| `RecentPlace` | 익명 유지 | `user=NULL`, `actor` 지정 |
| `Companion` | 삭제 | 명시적 `delete()` |
| `CompanionMember` | 삭제 + 카운터 보정 | 삭제 전 각 `Companion.member_count`를 `F('member_count') - 1` |
| `Plan` | 삭제 | `User` 삭제 시 CASCADE |
| `Inquiry` | 삭제 | CASCADE |
| `PointEntry` | 삭제 | CASCADE |
| `RefreshToken` | **탈퇴 요청 즉시 삭제** | 유예를 기다리지 않는다 |
| `User` | 삭제 | 배치에서 `delete()` |

`ReviewLike`를 보존하는 이유: 삭제하면 남아 있는 이용자의 리뷰 좋아요 수가 줄어 노출 순위가
흔들린다. 탈퇴자의 행위가 타인의 콘텐츠 평가를 소급 변경해서는 안 된다.

`member_count`는 비정규화 카운터이며 CASCADE 삭제로는 갱신되지 않는다. 보정하지 않으면 남의
모집글 인원수가 영구히 부풀려진 채 남는다.

---

## 7. 처리 흐름

### 7.1 탈퇴 요청 (`POST /users/me/withdraw`)

인증 필요. 하나의 트랜잭션에서 수행한다.

1. 비밀번호 재확인. 소셜 계정은 소셜 재인증 토큰을 검증한다.
2. `status = WITHDRAWN`, `purge_at = now + 7일`
3. 해당 사용자의 `RefreshToken` 전량 삭제 — 모든 기기에서 세션 종료
4. 탈퇴 사유 코드(선택 입력)를 `User.withdrawal_reason_code`에 임시 저장

> **발송 차단은 구현할 대상이 없다.** 이 저장소에는 푸시·이메일·마케팅 발송 인프라가 존재하지
> 않는다(FCM·메일 발송 코드 없음). `User.preferences`의 `notifications` 플래그는 저장만 되고
> 읽는 곳이 없다. 발송 기능을 나중에 만들 때 **`status=withdrawn` 계정을 수신 대상에서 제외**
> 하는 것을 그 작업의 요건으로 넘긴다.

이 시점에는 **개인정보를 파기하지 않는다.** 7일 내 철회하면 원상 복구되어야 하기 때문이다.
탈퇴자의 공개 콘텐츠(리뷰·동행글)도 유예기간 동안 그대로 노출된다.

### 7.2 철회 (`POST /users/me/withdraw/cancel`)

인증 없이 이메일 + 비밀번호(또는 소셜 재인증)로 본인을 확인한 뒤 `status = ACTIVE`,
`purge_at = NULL`로 되돌린다. 유예기간 중에는 아무것도 파기하지 않았으므로 복구할 데이터가 없다.

`purge_at`이 이미 지났는데 배치가 아직 돌지 않은 계정은 철회를 **거부**한다. 배치 실행 시각에
따라 결과가 달라지는 것을 막기 위해서다.

### 7.3 파기 (`purge_withdrawn_users` 배치)

`status=WITHDRAWN AND purge_at <= now`인 계정을 **사용자 단위 트랜잭션**으로 처리한다. 한 사용자
처리 실패가 다른 사용자를 막지 않는다.

```python
for user in 대상:
    with transaction.atomic():
        actor = AnonymousActor.objects.create()
        Feedback.objects.filter(user=user).update(user=None, actor=actor, memo=None)
        Review.objects.filter(user=user).update(user=None, actor=actor)
        ReviewLike.objects.filter(user=user).update(user=None, actor=actor)
        Favorite.objects.filter(user=user).update(user=None, actor=actor)
        RecentPlace.objects.filter(user=user).update(user=None, actor=actor)

        # 남의 모집글 인원수 보정 후 참여 이력 삭제
        joined = list(
            CompanionMember.objects.filter(user=user).values_list('companion_id', flat=True)
        )
        Companion.objects.filter(id__in=joined).update(member_count=F('member_count') - 1)
        CompanionMember.objects.filter(user=user).delete()

        Companion.objects.filter(user=user).delete()

        WithdrawnEmailHash.objects.get_or_create(
            email_hash=hmac_email(user.email),
            defaults={'expires_at': (now + timedelta(days=30)).date()},
        )

        if user.withdrawal_reason_code:
            WithdrawalReason.objects.create(
                reason_code=user.withdrawal_reason_code,
                withdrawn_on=now.date(),
            )

        user.delete()   # Plan·Inquiry·PointEntry·RefreshToken CASCADE
```

같은 명령에서 `expires_at < 오늘`인 `WithdrawnEmailHash`도 삭제한다.

**멱등성**: 배치를 중복 실행해도 결과가 같아야 한다. `user.delete()`가 마지막에 있으므로 성공한
사용자는 다음 실행의 대상 쿼리에 잡히지 않는다. 트랜잭션이 중간에 실패하면 전부 롤백되어 다음
실행에서 처음부터 다시 처리된다.

### 7.4 재가입 차단

회원가입 시 이메일의 HMAC이 `expires_at >= 오늘`인 `WithdrawnEmailHash`에 존재하면 거부한다. 응답은 "30일 이내에
탈퇴한 이메일입니다"가 아니라 **가입 불가 사유를 특정하지 않는** 형태여야 한다. 특정하면 그
이메일의 탈퇴 사실이 제3자에게 노출된다.

---

## 8. 수정이 필요한 기존 코드

`user`가 nullable이 되면서 기존 접근이 전부 잠재 크래시가 된다.

| 위치 | 내용 | 수정 |
|------|------|------|
| `users/activity_views.py:19` | `item.user.nickname` — 리뷰 작성자 | `user`가 NULL이면 `"탈퇴한 사용자"` |
| `users/activity_views.py:24` | `'is_mine': request.user.id == item.user_id` | **아래 참조 — 보안 결함** |
| `users/activity_views.py:259` | `like.user.nickname` — 좋아요 알림 | NULL 행을 조회에서 제외 |

`user`가 NULL이면 `author_id`는 `None`, `author_nickname`은 `"탈퇴한 사용자"`로 응답한다.
프론트엔드에 이 계약을 전달해야 한다.

### `is_mine` NULL 동등 비교 결함

`request.user.id == item.user_id`는 익명화된 리뷰(`user_id IS NULL`)를 **비로그인 방문자**
(`AnonymousUser.id is None`)가 조회할 때 `None == None`으로 참이 된다. 탈퇴자 리뷰 전부가
"내 리뷰"로 표시되어 수정·삭제 UI가 노출된다.

```python
'is_mine': item.user_id is not None and request.user.id == item.user_id,
```

동일한 패턴이 다른 곳에도 있는지 구현 시 `user_id ==` 로 전수 검색한다.

### 수정이 필요 없는 곳

`companion_data`(`:30`)와 동행 참여 알림(`:261`)의 `user` 접근은 그대로 둔다. `Companion`과
`CompanionMember`는 탈퇴 시 삭제되므로(§6) `user`가 NULL이 되는 경로가 없다.

구현 착수 시 `\.user\.` 패턴을 전수 검색해 누락을 확인한다. 위 4곳은 현재 확인된 것이며 구현
시점에 더 늘어날 수 있다.

---

## 9. 테스트

파기는 되돌릴 수 없다. 구현 전에 테스트를 먼저 작성한다(TDD).

| # | 검증 내용 |
|---|----------|
| 1 | 탈퇴 요청 후 로그인이 차단되고 `withdrawal_pending` 코드가 반환된다 |
| 2 | 유예 중 철회하면 모든 데이터가 온전하고 로그인이 복구된다 |
| 3 | `purge_at` 경과 후 철회는 거부된다 |
| 4 | 파기 후 `User` 행이 존재하지 않는다 |
| 5 | 파기 후 리뷰가 살아 있고 `user IS NULL`이며 `actor`가 지정되어 있다 |
| 6 | 파기 후 `Feedback.memo`가 NULL이고 `value`는 보존된다 |
| 7 | 파기 후 남의 모집글 `member_count`가 정확히 1 감소한다 |
| 8 | 30일 내 동일 이메일 재가입이 차단되고, 30일 경과 후에는 허용된다 |
| 9 | 배치를 2회 연속 실행해도 결과가 동일하다 (멱등) |
| 10 | `user` XOR `actor` 제약이 위반 시 DB 레벨에서 거부된다 |
| 11 | 탈퇴자 리뷰 조회 시 `author_nickname`이 `"탈퇴한 사용자"`로 응답된다 |
| 12 | 철회한 사용자의 탈퇴 사유는 `WithdrawalReason`에 남지 않는다 |
| 13 | 재가입 거부 응답이 탈퇴 사실을 드러내지 않는다 (다른 가입 실패와 응답이 구별되지 않는다) |

---

## 10. 문서 갱신 (구현 범위에 포함)

설계와 처리방침이 어긋나면 그 자체가 개인정보 보호법 제30조 위반이다.

| 문서 | 필요한 수정 |
|------|------------|
| `docs/legal/privacy-policy.md:133` | "즐겨찾기·선호 설정·알림 설정 / 회원 탈퇴 시 파기" → 즐겨찾기는 익명으로 보존되므로 사실과 다르다. 익명화 후 보존으로 수정 |
| `docs/legal/privacy-policy.md:127` | 계정 정보 "탈퇴 시 지체 없이 파기" → 7일 유예를 반영 |
| `docs/legal/privacy-policy.md` 제3조 | 익명 행동 데이터(actor 단위) 행 추가 — 무기한 보존 및 그 근거 |
| `docs/legal/privacy-policy.md:128` | 재가입 방지 해시 30일 — 현행 문구 유지 (수정 불필요) |
| `docs/privacy/dev-todo.md` | 탈퇴 기능 항목 완료 처리, 잔여 위험(자유 텍스트·EXIF) 신규 등록 |

---

## 11. 범위 밖

- 이용자 본인의 데이터 내보내기(PIPA 제35조의2 전송 요구) — 별도 과제
- 리뷰 본문·사진의 식별 내용 제거 — 잔여 위험으로 기록, 별도 과제
- 탈퇴 사유 통계의 분석·리포팅 화면 — 백엔드는 수집만 담당
- 만 14세 미만 가입 차단, CPO 지정 등 처리방침의 다른 선행 조치

---

## 12. 검증 필요

- 가명정보 특례 조문(제28조의2 계열)의 정확한 조문 번호와 요건. 본 설계는 **익명정보** 경로를
  택했으므로 해당 조문에 의존하지 않으나, 감사 대응 시 인용이 필요할 수 있다.
- "지체 없이 파기"의 구체적 기한에 대한 시행령·해설서 기준. 7일 유예가 이 기준 안에 드는지 원문
  확인이 필요하다.
