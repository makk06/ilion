# 개발 To-Do + 사업 준비 항목 — ILION 개인정보 동의

**한 줄 요약**: 코드 작업 **55건**(P0~P7)과 코드로 해결되지 않는 **사업 준비 항목 11건**입니다. P0 3건은 지금 당장입니다.

- 상위 문서: [메인 보고서](../../PRIVACY-CONSENT-REVIEW.md)
- 관련 문서: [동의 항목 분류 상세](consent-matrix.md) · [동의 화면 문안](consent-copy.md) · [보안 결함 상세](security-findings.md)
- 작성 기준일: **2026-09-17** / 분류 기준 커밋 `a011cd6` — **현재 HEAD는 `17bd39d`**

> ⚠ **증분 조사 반영 필요.** 이 문서의 123행 분류는 `a011cd6` 기준입니다. 이후 신규 28건(`PD-N-001~028`)이 발견되었고 **서비스가 공개 운영 중**임이 확인되었습니다. 신규분은 아직 동의 분류가 수행되지 않았습니다 — `_workspace/05_inventory_increment.md`와 [메인 보고서](../../PRIVACY-CONSENT-REVIEW.md)를 함께 보십시오.

> ## ⚠ 면책
> 본 문서는 코드베이스 분석과 공개된 법령 정보를 바탕으로 작성된 내부 검토 자료이며,
> 법률 자문이 아닙니다. 조문 번호와 요건은 국가법령정보센터(law.go.kr) 원문으로 대조가
> 필요하며, 실제 서비스 출시 전 개인정보보호 전문가 검토 또는 개인정보보호위원회·
> 방송통신위원회 사전 상담을 권고합니다.

---

## 경로 기준

| 구분 | 경로 |
|------|------|
| 백엔드 | `tourist_congestion_backend/` |
| 프론트 | `tourist_congestion_frontend/` |

## 우선순위 한눈에

| 단계 | 내용 | 건수 | 담당 |
|------|------|-----|------|
| [P0](#p0--즉시-다른-모든-작업에-선행) | 즉시 — 다른 모든 작업에 선행 | 3 | 백엔드 + 프론트 |
| [P1](#p1--동의-기능의-선행-조건) | 동의 기능의 선행 조건 | 6 | 백엔드 |
| [P2](#p2--고지-구현) | 고지 구현 | 6 | 프론트 |
| [P3](#p3--동의-ui-구현) | 동의 UI 구현 | 8 | 프론트 + 백엔드 |
| [P4](#p4--안전조치-29) | 안전조치 (§29) | 11 | 백엔드 + 프론트 |
| [P5](#p5--수집-중단-stop-collect-14건) | 수집 중단 | 17 | 백엔드 + 프론트 |
| [P6](#p6--동행-안전-조치) | 동행 안전 조치 | 2 | 프론트 |
| [P7](#p7--개별-삭제-경로) | 개별 삭제 경로 | 2 | 백엔드 |
| **합계** | | **55** | |

---

## P0 — 즉시. 다른 모든 작업에 선행

| # | 작업 | 파일 | 왜 |
|---|------|------|-----|
| 1 | `SECRET_KEY`·`DEBUG` 기본값 제거 → 미설정 시 기동 실패. `SIMPLE_JWT['SIGNING_KEY']` 분리 | `config/settings.py:28-31`, `:34`, `:163-167`, `.env.example` | `PD-R-001`. 토큰 위조 가능 상태 |
| 2 | 위치 측정 호출 경로 차단 — 홈·지도 버튼 비활성화 | `services/place_location.dart:10-20`, `screens/home_screen.dart`, `screens/map_screen.dart` | 무동의 개인위치정보 처리 중단 |
| 3 | 기존 배포가 있었다면 전 토큰 무효화 + 전수 점검 | 운영 | `PD-R-001`. 유출 시 §34 대상 |

**#1 상세** — [보안 결함 상세 §1](security-findings.md). 동의를 아무리 잘 받아도 토큰을 위조할 수 있으면 의미가 없습니다.

**#2 상세** — `place_location.dart`가 OS 권한 팝업만 거쳐 `getCurrentPosition()`을 호출하고, `api_client.dart:65-67`이 모든 요청에 `Authorization: Bearer`를 붙여 **좌표가 신원과 결합된 상태로 전송**됩니다. OS 권한 허용은 위치정보법상 동의가 아닙니다. **지역 선택 경로만으로 서비스는 정상 동작합니다.**

---

## P1 — 동의 기능의 선행 조건

**이것 없이는 동의를 "받을 수 없습니다."**

| # | 작업 | 파일 / 모델 | 왜 |
|---|------|-----------|-----|
| 4 | **동의 이력 모델 신설** | `users/models.py` (신규 `Consent`) + 마이그레이션 | 동의 사실의 **입증 책임이 사업자에게** 있음 |
| 5 | 동의 조회·생성·철회 API | `users/urls.py`, `users/views.py` | 철회권 보장 (§37) |
| 6 | 연령 확인 필드·로직 | `users/models.py`, `users/serializers.py`, `screens/auth_screen.dart` | §22의2. **방식 결정이 선행** |
| 7 | 회원 탈퇴 API + 항목별 처리 | `users/urls.py`, `users/views.py`, `users/models.py` | §21·§36·§37 |
| 8 | 파기 배치 + 후기 삭제 시 사진 파일 동시 삭제 | `users/activity_views.py:94-100`, 관리 명령(신규) | §21 |
| 9 | 접속기록 구조화 로깅 도입 | `config/settings.py`(`LOGGING`), 미들웨어(신규) | §29 + 고시 |

### #4 동의 이력 모델 설계안

```python
class Consent(models.Model):
    class Type(models.TextChoices):
        LBS_TERMS          = 'lbs_terms'           # 위치기반서비스 이용약관
        LOCATION           = 'location'            # 개인위치정보 이용
        PERSONALIZATION    = 'personalization'     # 개인화·서비스 개선
        OVERSEAS_GOOGLE    = 'overseas_google'     # 국외 이전(구글)
        MARKETING_EMAIL    = 'marketing_email'     # 마케팅 — 이메일
        MARKETING_PUSH     = 'marketing_push'      # 마케팅 — 푸시
        MARKETING_NIGHT    = 'marketing_night'     # 마케팅 — 야간 21~08시

    user           = models.ForeignKey(settings.AUTH_USER_MODEL, ...)
    consent_type   = models.CharField(choices=Type.choices, ...)
    granted        = models.BooleanField()
    granted_at     = models.DateTimeField(null=True)   # 동의 일시
    revoked_at     = models.DateTimeField(null=True)   # 철회 일시
    notice_version = models.CharField(max_length=32)   # 문안 버전 "2026-09-17.v1"
    source         = models.CharField(max_length=64)   # 어느 화면에서 받았는지
    created_at     = models.DateTimeField(auto_now_add=True)
```

| 설계 포인트 | 이유 |
|-----------|------|
| **불리언 하나가 아니라 이력 테이블** | "언제·어떤 문안으로" 받았는지가 없으면 **동의 사실 입증 불가** |
| `granted_at` / `revoked_at` 분리 | 철회 이력이 남아야 합니다. 레코드를 지우면 안 됩니다 |
| `notice_version` | 문안이 바뀌면 **재동의 필요 여부를 판단**해야 합니다 |
| **마케팅을 채널별 + 야간 별도 타입으로** | 망법 §50 야간 전송 요건. **하나의 필드로 합치면 안 됩니다** |
| 위치는 약관 동의와 이용 동의를 분리 | 위치정보법상 "이용약관에 명시한 후" 동의 |

### #6~#8 주의사항

**#6** — 방식(가입 차단 / 법정대리인 동의)이 결정되기 전에는 착수할 수 없습니다. [결정 필요 사항](#사업-준비-항목) 참조.

**#7** — `PointEntry.place`가 `PROTECT`라 **단순 CASCADE로 해결되지 않습니다.** 보유기간·보존 결정이 선행합니다.

**#8** — 현재 `ReviewDetailView.delete`가 `item.delete()`만 호출해 **업로드 사진이 파일시스템에 잔존**합니다.

### #9 구현 제약

| 제약 | 내용 |
|------|------|
| 현재 상태 | `logging`·`logger`·`print` 사용처 **0건**, `LOGGING` 블록 없음 |
| 기록할 것 | 이용자 식별자·시각·수행 업무·접근 대상 |
| **기록하지 말 것** | **요청 URL 전문**과 예외 메시지 (외부 API 키 보호 방침과 양립) |
| 특히 주의 | `GET /api/places/nearby`는 좌표가 URL에 있으므로 **URL 전체를 남기지 말 것** |
| 보관기간 | **[검증 필요]** 「개인정보의 안전성 확보조치 기준」 고시 |

---

## P2 — 고지 구현

**27행의 `NO-CONSENT` 판정이 여기에 달려 있습니다.** 고지가 없으면 "구조상 공개" 논리의 전제가 무너집니다.

| # | 작업 | 파일 |
|---|------|------|
| 10 | 후기 작성 화면 상단 공개범위 고지 | `screens/review_form_screen.dart` |
| 11 | 동행 게시 직전 확인 화면 (날짜·시각·장소 명시) | `screens/companion_form_screen.dart` |
| 12 | 닉네임 입력란 아래 공개범위 고지 | `screens/auth_screen.dart`, `screens/profile_subscreens.dart` |
| 13 | 좋아요·동행 신청·길찾기 버튼 근처 고지 | `screens/place_detail_screen.dart`, `screens/companion_detail_screen.dart` |
| 14 | 자유서술 입력란 하단 민감정보 안내 고정 | 후기·동행·문의·피드백 입력 화면 4곳 |
| 15 | **최근 본 장소 끄기 토글 + 최초 1회 고지** | `screens/profile_subscreens.dart`, `screens/place_detail_screen.dart:71` |

문구 전문은 [동의 화면 문안 — 문안 E](consent-copy.md)에 있습니다.

**#13 배경** — 현재 앱 UI가 집계만 보여 **익명을 시사**하나, 서버는 작성자에게 닉네임을 알림으로 전달합니다.

**#15 효과** — 구현하면 `PD-B-028(a)`·`PD-F-030(a)`가 `OPT-CONSENT` → `NO-CONSENT`로 복귀할 수 있습니다.

---

## P3 — 동의 UI 구현

| # | 작업 | 파일 |
|---|------|------|
| 16 | 회원가입 화면에 문안 A 반영 | `screens/auth_screen.dart` |
| 17 | 온보딩에 개인정보 처리 안내 삽입 | `screens/onboarding_screen.dart` |
| 18 | **위치 동의 블록(문안 C)** — 위치 기능 첫 사용 시점에 노출 | `screens/home_screen.dart`, `screens/map_screen.dart`, 신규 위젯 |
| 19 | **OS 권한 팝업을 앱 내 동의 뒤로 이동** | `services/place_location.dart` |
| 20 | **앱 내 위치 일시중지 토글** (OS 권한과 별개) | `screens/profile_subscreens.dart` |
| 21 | 위치정보 이용·제공 사실 확인자료 기록 | `places/views.py`, 로깅 설계 (#9와 같은 구조 안에서) |
| 22 | 구글 로그인 국외 이전 동의 (문안 B) | `screens/auth_screen.dart` |
| 23 | 설정 화면에 동의 현황·철회 경로 | `screens/profile_subscreens.dart` |

**#17 현재 상태** — 온보딩은 `시작하기` 버튼 하나뿐입니다.

**#18 주의** — **가입 화면에 넣지 마십시오.** 위치는 근거 법률이 달라 독립 블록이어야 합니다.

**#19 주의** — **OS 권한 허용은 법적 동의를 갈음하지 않습니다.** 앱 내 동의가 권한 요청보다 **먼저** 와야 합니다.

**#21** — **[검증 필요]** 위치정보법상 보존기간·기록 항목. #9와 같은 로깅 설계 안에서 함께 구현해야 하므로 **설계 착수 전에 확정이 필요합니다.**

**#22** — **[검증 필요]** §28의8 확인 후 확정. 예외가 인정되면 이 작업 자체가 "고지"로 축소됩니다.

---

## P4 — 안전조치 (§29)

**처리방침 §9 "안전성 확보 조치" 절의 전제입니다.** 상세는 [보안 결함 상세](security-findings.md).

| # | 작업 | 파일 | 근거 |
|---|------|------|------|
| 24 | 인증 엔드포인트 요청 제한 | `config/settings.py`(`REST_FRAMEWORK`), `users/urls.py` | `PD-R-003` |
| 25 | 가입 오류 메시지 통일 (계정·닉네임 열거 차단) | `users/serializers.py:17-20` | `PD-R-003` |
| 26 | 구글 로그인 `email_verified` 검증 + 자동 병합 중단 | `users/views.py:125`, `:138-139` | `PD-B-043` |
| 27 | admin `list_display`·`search_fields`에서 이메일 제거 | `users/admin.py:7`, `:9` | `PD-B-031`/`063` |
| 28 | 비밀번호 변경·재설정 API 추가 | `users/urls.py`, `users/views.py` | `PD-B-002` |
| 29 | access token 무효화 수단 | `users/views.py` | `PD-B-015` |
| 30 | 업로드 미디어 서명 URL·만료 토큰 | `users/activity_views.py`, 배포 구성 | `PD-B-048` |
| 31 | 릴리스 빌드에서 `https` 이외 거부하는 assert | `services/api_client.dart:22` | `PD-F-048` |
| 32 | `IOSOptions(accessibility:)` 백업 제외 + `AndroidOptions` 암호화 명시 | `services/app_session.dart:11` | `PD-F-012`/`013` |
| 33 | `SESSION_COOKIE_AGE` 명시(1일) + 만료 세션 정리 명령 | `config/settings.py` | `PD-B-036` |
| 34 | `replay_pipeline.py` 화이트리스트 전환 + 기존 산출물 파기 | `scripts/crowd-validation/replay_pipeline.py:17-18`, `:45-46` | `PD-B-056` |

**#28 순서** — 재설정 토큰 서명이 `PD-R-001`에 직결되므로 **P0 #1을 먼저 해소한 뒤 착수**하십시오.

**#34 범위** — `sqlite3.backup()`이 파일 전체를 복사해 **비밀번호 해시와 리프레시 토큰 해시까지 복제**됩니다.

---

## P5 — 수집 중단 (`STOP-COLLECT` 14건)

| # | 작업 | 파일 | 비용 |
|---|------|------|------|
| 35 | 공개 응답에서 `author_id` 제거 + 페이지네이션 강제 | `users/activity_views.py:17-35`, `:55-65`, `:117-127` | 낮음 |
| 36 | 동행 닉네임 자유검색 제외 | `screens/recommend_screen.dart:117` | **1줄** |
| 37 | `GET /api/companions` 비로그인 조회 차단 | `users/activity_views.py` | 1줄 |
| 38 | 사진 EXIF — **서버측 재인코딩**(주) + 프론트 제거(보조) | `users/activity_serializers.py:26-31`, `screens/review_form_screen.dart:105-106` | 중간 |
| 39 | 업로드 파일명 UUID 치환 | 업로드 경로 | **1줄** |
| 40 | `LocationSettings(accuracy: low/medium)` 명시 | `services/place_location.dart:19-20` | 1줄 |
| 41 | Android `ACCESS_FINE_LOCATION` 선언 제거 | `android/app/src/main/AndroidManifest.xml` | 1줄 |
| 42 | iOS 카메라 권한 선언 제거 | `ios/Runner/Info.plist` | 1줄 |
| 43 | 구글 프로필 이미지 URL — 모델 필드 + **응답 필드에서도** 제거 | `users/models.py`, `users/activity_serializers.py:13` | 낮음 |
| 44 | `/me` 응답 필드를 4개로 축소 | `users/activity_serializers.py` | 낮음 |
| 45 | 마케팅 수신 선호 스위치 제거 + 저장값 파기 | `screens/profile_subscreens.dart`, `users/models.py` | 낮음 |
| 46 | `preferences` 허용 키 화이트리스트 + **키별 타입·길이 제한** | `users/activity_serializers.py:9` | 낮음 |
| 47 | `Feedback.memo` 현 형태 제거 | `users/models.py`, `users/serializers.py:59` | 낮음 |
| 48 | OpenFreeMap 에셋 제거 + 미사용 의존성·데드코드 처리 결정 | `assets/maps/simple.json`, `pubspec.yaml`, `services/centerline_tile_provider.dart`, `services/road_centerline.dart` | 낮음 |
| 49 | `.vscode/settings.json` 제거 + gitignore, `ops` 경로를 환경변수로 | `.vscode/settings.json`, `ops/collect-crowd.ps1:2-3`, `premium-audit.json` | 낮음 |
| 50 | 좌표를 쿼리스트링 → POST 바디/헤더로 전환 | `places/views.py`, `services/place_service.dart` | 중간 |
| 51 | 루트 `.gitignore`에 `*.sqlite3` 추가 | `.gitignore` | **1줄** |

### 판정이 까다로웠던 항목 4건

**#40 / #41 순서에 주의** — `ACCESS_FINE_LOCATION` 선언 제거는 **Android 매니페스트 항목이라 iOS에 아무 효과가 없습니다**(iOS는 정밀도 축소 키가 없어 기본 전체 정확도로 동작). **#40이 주 조치, #41이 보조입니다.** 매니페스트만 고치고 끝내지 마십시오.

**#38 순서에 주의** — 클라이언트 측 제거를 주 조치로 삼을 수 없습니다. `pickImage(maxWidth:1600)`은 **원본이 1600px를 초과할 때만** 리사이즈하고, 클라이언트 제거는 **변조된 클라이언트가 우회**할 수 있습니다. 실기기 EXIF 검증 결과와 **무관하게** 서버측 조치는 필수입니다.

**#43 범위** — 앱 전수 grep 0건이지만 `ProfileSerializer.fields`에 있어 **`/me` 응답으로 클라이언트까지 전송 중**입니다. 모델 필드만 지우면 부족합니다.

**#46 범위** — 화이트리스트만으로는 부족합니다. `DictField(required=False)`는 `child`도 길이 제한도 없어 **요청 한도(2.5MB)까지 임의 데이터를 반복 저장**할 수 있습니다. 같은 시리얼라이저의 `preferred_categories`가 `max_length=30`·원소 `max_length=100`으로 제한된 것과 대비됩니다.

### #47 재도입 조건

`Feedback.memo`는 **앱에 `POST /api/feedback` 호출이 0건**이라 UI도 클라이언트도 없는 순수 쓰기 가능 필드입니다. 다음 3가지를 갖추면 `OPT-CONSENT`로 재도입할 수 있습니다.

1. 500자 길이 제한
2. 입력란 하단 "건강·신념 등 민감한 정보는 입력하지 말아 주세요" 고정 안내
3. 유입 탐지·삭제 절차와 담당자 지정

---

## P6 — 동행 안전 조치

**분류(`NO-CONSENT`)와 무관하게 필수입니다.**

| # | 작업 | 파일 |
|---|------|------|
| 52 | 시각 정밀도 하향(오전/오후/저녁) 또는 `날짜 미정`/`시간 미정` 기본값화 | `screens/companion_form_screen.dart` |
| 53 | 참여 확정 전 정확한 만남 지점 비공개 + 본문 힌트 문구 변경 | `screens/companion_form_screen.dart:183-184` |

> **P6은 P5의 #35~37과 함께 처리해야 효과가 있습니다.** 따로 하면 어느 쪽도 위험을 줄이지 못합니다.
> 배경은 [보안 결함 상세 §4](security-findings.md).

---

## P7 — 개별 삭제 경로

| # | 작업 | 파일 | 왜 |
|---|------|------|-----|
| 54 | `InquiriesView`·`FeedbackListCreateView`에 DELETE 추가 | `users/views.py`, `users/activity_views.py` | §36은 보유기간과 무관하게 삭제 요구권을 규정 |
| 55 | 삭제 요구 접수 창구를 처리방침에 명시하고 운영 절차 수립 | [처리방침 §8](privacy-policy-outline.md) | §36·§37 |

현재 `InquiriesView`는 GET·POST만, `FeedbackListCreateView`는 GET·POST만, `PointsView`는 GET만 제공합니다.

---

# 사업 준비 항목

> **이 절의 항목을 위 개발 To-Do와 섞지 마십시오. 코드 백로그에 들어가면 누락됩니다.**

## 🔴 위치기반서비스사업자 신고 — 출시를 막는 행정 요건

| 항목 | 내용 |
|------|------|
| **근거** | 위치정보법 **§9** **[검증 필요]** 조문번호 — 의무의 존재 자체는 확실 |
| **현재 상태** | `GET /api/places/nearby`가 단말 측정 좌표를 수신 — **신고 없이 이미 동작 중** |
| **시기** | **서비스 개시 전.** 출시 후 소급 치유 불가 |
| **리드타임** | **깁니다.** 사업계획서·위치정보시스템 구성·설비 내역 제출 필요 |
| **미이행 시** | 미신고 위치기반서비스사업 영위는 **제재(벌칙) 대상** |
| **확인처** | **방송통신위원회에 직접 확인** |
| **회피 경로** | 이용자 좌표 수신을 전면 제거하고 지역 선택만으로 운영 |

### 면제 특례에 관한 경고

**1인 창조기업·소상공인 신고 면제 특례는 개정 이력이 있습니다.**

> **블로그·요약글 같은 2차 자료를 신뢰하면 안 됩니다. 방송통신위원회에 직접 확인하십시오.**
> 학생 팀 프로젝트라도 실제 출시·운영 시에는 확인이 필요합니다.

### 실행

**출시 일정의 전제 조건으로 등록하고 담당자·기한을 지정하십시오.** 리드타임이 길어 출시 직전에 시작하면 늦습니다.

---

## 그 밖의 사업 준비 항목 10건

| # | 항목 | 근거 | 왜 코드가 아닌가 |
|---|------|------|----------------|
| 1 | **개인정보 보호책임자(CPO) 지정** | §31 | 사람을 정하는 일. **문서 작성의 선행 조건** |
| 2 | **만 14세 미만 대응 방식 결정** | §22의2 | 코드 이전에 제품 결정 |
| 3 | **항목별 보유기간 확정** | §21, §15②3 | 법무·제품 판단 |
| 4 | **탈퇴 시 항목별 처리 결정** (삭제/익명화/보존) | §21, §36 | 탈퇴 로직 설계의 입력값 |
| 5 | **위치 기능 유지 여부 결정** | 위치정보법 | 유지하면 사업자 신고가 따라옵니다 |
| 6 | **마케팅 발송 여부 결정** | 망법 §50 | 하지 않는다면 지금 수집 중단이 옳습니다 |
| 7 | **동행 모집 공개 범위 결정** (비로그인 노출 차단) | §3, §16 | 제품 결정 |
| 8 | **민감정보 유입 탐지·삭제 절차와 담당자 지정** | §23 | 처리방침 문장을 실제와 일치시킬 운영 절차 |
| 9 | **문서 3종 작성** — 이용약관 / 처리방침 / 위치기반서비스 이용약관 | §30, 위치정보법 | #1·#3이 선행 |
| 10 | **인프라 확인 5건** | §26, §29 | 저장소 밖 |

### #2 만 14세 미만 — 선택지 두 가지

| 안 | 내용 | 비용 |
|----|------|------|
| ① | 생년월일 입력 → 만 14세 미만 **가입 차단** | 낮음. 단순하고 일반적 |
| ② | **법정대리인 동의 절차** 구현 | 높음 |

> **"아무것도 안 하기"는 선택지가 아닙니다.** 위치 기능을 유지하면 위치정보법 아동 특례가 추가로 걸려 **이중 의무**가 됩니다.
> **자기신고형 체크박스 한 줄로 갈음할 수 없습니다.**

### #3 보유기간 — 병목 항목

**`PD-B-023`(포인트 원장)이 병목입니다.** `PointEntry.place`가 `PROTECT`라 **보존/파기 결정 없이는 탈퇴 로직 자체를 짤 수 없습니다.** 전자상거래법 보존 의무 해당 여부를 **최우선으로** 확인하십시오.

### #10 인프라 확인 5건

| # | 확인 사항 | 미확인 시 |
|---|----------|----------|
| 1 | 운영 배포에서 `DJANGO_SECRET_KEY`·`DJANGO_DEBUG`가 설정되어 있는가 | **미설정이면 `PD-R-001`은 현재 진행형** |
| 2 | 웹서버·리버스프록시 액세스 로그 존재·보존기간 | 좌표가 남는다고 가정 |
| 3 | 릴리스 빌드 `API_BASE_URL`이 `https`인가 | 아니라고 가정 → §29 위반 |
| 4 | 미디어 파일을 어떤 호스트가 어떤 권한으로 서빙하는가 | 무인증 공개로 가정 |
| 5 | `replay.sqlite3`가 실제로 생성된 이력이 있는가 | 실행되었다고 가정 → 즉시 파기 |

---

## 관련 문서

| 문서 | 내용 |
|------|------|
| [메인 보고서](../../PRIVACY-CONSENT-REVIEW.md) | 결론·역할별 안내·즉시 시정 16건 |
| [동의 항목 분류 상세](consent-matrix.md) | 각 작업의 법적 근거 |
| [동의 화면 문안](consent-copy.md) | P2·P3이 구현할 문구 |
| [처리방침 골격](privacy-policy-outline.md) | P1·P4의 결과물이 들어갈 곳 |
| [보안 결함 상세](security-findings.md) | 🔴 P0·P4의 배경. 공개 저장소 업로드 금지 |
| [서비스 이용약관 초안](../legal/terms-of-service.md) | 제품에 넣을 약관 초안 |
| [위치기반서비스 이용약관 초안](../legal/location-service-terms.md) | 제품에 넣을 위치 약관 초안 |
| [개인정보 처리방침 초안](../legal/privacy-policy.md) | 제품에 넣을 처리방침 초안 |
