# ILION 프론트엔드 연동 가이드

기준일: **2026-09-15 (KST)** · 추천 버전: **`mvp-7`** · 공개 추천 시안 추가 릴리스 기준

현재 백엔드는 **개발 중인 추천 알고리즘 MVP**다. 전국 장소 탐색과 조건 기반 추천을 연동할 수 있다. 데이터 수집 범위와 추천 품질은 계속 보강 중이며, 전국 실시간 혼잡도나 미래 혼잡도 예측을 제공하는 단계는 아니다. 이 문서는 현재 배포 코드의 동작을 기준으로 작성했으며, 이전 설계 문서의 예정 기능과 구분한다.

## 1. 바로 시작하기

| 항목 | 값 / 사용법 |
|---|---|
| 운영 Base URL | `https://ilion.app.hurdoo.kr` |
| 서버 상태 확인 | `GET /healthz` → `{"status":"ok"}` |
| 장소 검색 | `GET /api/places?keyword=경복궁` |
| 주변 장소 | `GET /api/places/nearby?latitude=37.575&longitude=126.977&radius_km=3` |
| 추천 | `POST /api/recommendations` + JSON 본문 |
| 장소 상세 | `GET /api/places/{place_id}` |
| 브라우저 시연: 추천 MVP 시안 | <https://ilion.app.hurdoo.kr/test/backend/> |
| 인증 | 장소 조회와 비회원 추천에는 토큰 불필요 |
| 시간 / 좌표 / 거리 | ISO 8601 오프셋 포함 시각 / 위도·경도 숫자 / km |

**운영 API는 HTTPS를 사용한다.** 점검 당시 운영 HTTP 주소는 HTTPS 리다이렉트 없이 404를 반환했다. API 경로 끝에는 `/`를 붙이지 않는다. 추천 MVP 시안의 `/test/backend/`는 끝 슬래시를 그대로 쓴다. `/`에 앱 화면이 없는 것은 API 장애가 아니다.

브라우저 시연은 추천 결과·점수 근거와 실제/가상 날씨, 선호·필수 조건을 비교할 수 있는 **추천 MVP 시안**을 기준으로 한다. 운영에서도 `DEBUG=false`로 제공하며 저장된 운영 DB만 읽는다. 가상 날씨는 요청 안에서만 계산하고 DB 저장·외부 호출·보충 작업 등록을 하지 않는다. 일반 추천 API는 필요한 보충 작업을 등록할 수 있어 시안과 갱신 타이밍이 다를 수 있다. 수집 작업·호출 예산과 개발용 검토 사례는 공개 화면에 노출하지 않는다.

**시연 방법:** [운영 추천 MVP 시안](https://ilion.app.hurdoo.kr/test/backend/)을 브라우저에서 바로 열면 된다. 별도 설치나 로그인은 필요 없다. 로컬 데이터로 시연하려면 [백엔드 실행 안내](./README.md)에 따라 서버를 실행한 뒤 `http://127.0.0.1:8000/test/backend/`를 사용한다.

```bash
curl --fail-with-body 'https://ilion.app.hurdoo.kr/healthz'

curl --fail-with-body 'https://ilion.app.hurdoo.kr/api/recommendations' \
  -H 'Content-Type: application/json' \
  --data '{"latitude":37.575,"longitude":126.977,"radius_km":3,"limit":3,"weather_aware":true}'

curl --fail-with-body -G 'https://ilion.app.hurdoo.kr/api/places' \
  --data-urlencode 'keyword=경복궁' \
  --data-urlencode 'page_size=10'
```

첫 연동은 비회원 추천 → 카드 표시 → `place.id`로 상세 조회 순서로 진행한다. 로그인·즐겨찾기는 이후 연결해도 추천을 사용할 수 있다. 프론트엔드에는 TourAPI·서울시·기상청 키나 DB 접근 정보가 필요 없다.

### 플랫폼별 연결 조건

| 실행 환경 | 현재 연결 조건 |
|---|---|
| curl / 서버 측 HTTP 클라이언트 | 위 HTTPS 주소 직접 호출 가능 |
| Flutter Android / iOS 네이티브 | HTTPS 주소 직접 호출. 인터넷 연결·위치 권한은 앱에서 처리 |
| Flutter Web / 다른 도메인의 웹앱 | **현재 CORS 미설정으로 브라우저 직접 호출 불가** |
| 운영 추천 MVP 시안 `/test/backend/` | 같은 origin에서 HTML 폼으로 시연 가능. 추천 자료와 조건별 비교를 서버에서 렌더링 |

2026-09-15 운영에서 `Origin: http://localhost:5173`을 붙인 GET 및 추천 POST용 OPTIONS를 확인했다. HTTP 200이지만 `Access-Control-Allow-Origin` 등 CORS 응답 헤더가 없다. **인터넷 공개와 브라우저 교차 출처 허용은 별도 설정**이다.

웹을 연결하려면 프론트엔드와 같은 origin의 서버/개발 프록시에서 `/api/*`를 운영 백엔드로 전달하거나, 백엔드에 합의한 프론트 origin과 필요한 메서드·헤더를 허용하는 CORS 변경을 구현·배포해야 한다. 현재 저장소에는 이 프록시나 CORS 설정이 준비되어 있지 않다. 공개 범위 변경, `DJANGO_ALLOWED_HOSTS` 변경, `fetch`의 `mode: "no-cors"`만으로 해결되지 않는다. 브라우저 보안 해제나 인증서 검증 해제도 사용하지 않는다.

Android 현재 저장소는 `INTERNET` 권한이 debug/profile manifest에만 있다. 릴리스 앱에서는 `android/app/src/main/AndroidManifest.xml`의 `<manifest>` 바로 아래에 다음 권한을 추가한다.

```xml
<uses-permission android:name="android.permission.INTERNET" />
```

위치 권한 거부 시 사용자가 도시/지도 중심을 선택하도록 하고 그 좌표를 전송한다. 백엔드는 기기 위치를 알아내거나 주소를 좌표로 변환하지 않는다.

## 2. 구현된 범위와 연결 보류 범위

| 기능 | 현재 구현 / 프론트 사용 범위 |
|---|---|
| 전국 장소 검색·상세·주변 검색 | 구현. 현재 적재된 유효 장소만 반환, 페이지 단위 조회 |
| 조건 기반 추천 | 구현. 거리·카테고리·가용 혼잡도·날씨·실내외 선호로 최대 10개 |
| 조건 필터 | 반경, 필수 카테고리, 근거가 확인된 실내외, 한산함 필수, 날씨 근거 필수 |
| 추천 설명 | 점수, 반영 항목, 결측 항목, 근거 출처, 이유, 자료 시각 반환 |
| 정기 수집 | Pi의 단일 워커가 목록·상세·서울 혼잡도·기상청 예보 수집 |
| 이메일 회원가입·로그인·JWT 갱신·로그아웃 | 코드 구현. 이번 운영 점검에서는 실제 계정 생성·전체 인증 흐름을 시험하지 않음 |
| 즐겨찾기 | 인증된 사용자 기준 추가·ID 목록·삭제 구현. 운영에서 무인증 401 확인, 쓰기 흐름 미시험 |
| Google 로그인 | 엔드포인트 구현. 현재 운영 `GOOGLE_CLIENT_ID`가 비어 있어 **연동 보류** |
| 사용자 선호 | DB에 있는 `preferred_categories`를 추천이 읽음. 프론트에서 수정하는 API 없음 |
| 내 프로필 조회/수정·비밀번호 재설정·이메일 인증·회원 탈퇴 | 현재 공개 라우트 없음 |
| 후기·평점 작성·추천 피드백·개인 행동 학습 | API 없음. `avg_rating` 필드는 있어도 추천에 사용하지 않음 |
| 실제 이동 경로·도보/차량 소요시간·지오코딩 | 미구현. 거리는 직선거리, 소요시간은 `null` |
| 전국 실시간 혼잡도·미래 혼잡 예측 | 미제공. 서울 일부 매핑 장소에 현재 영역 관측만 연결 |
| 유사/대체 장소·코스 추천·실시간 푸시·공급자 작업 상태 API | 공개 라우트 없음 |
| 추천 MVP 시안 | `/test/backend/`에서 읽기 전용 시연. 공개 릴리스는 운영 디버그 모드를 켜지 않아도 제공 |

목록과 추천은 다르다. 목록은 검색 조건에 맞는 장소를 보여주고, 추천은 폐쇄 상태·행사 기간·필수 조건 등을 추가로 검사한다. 목록에서 보이는 장소가 추천에서는 빠질 수 있다. `open_status`는 현재 영업시간을 실시간 판정하는 값이 아니다.

### 지금 운영 데이터의 상태

운영은 테스트 DB를 복사하지 않고 새 SQLite에 수집을 시작했다. 테스트 DB의 장소 ID, 수동/AI 검토 결과, 상세정보 보유량은 운영과 같지 않다. **장소 ID를 하드코딩하지 말고 현재 API 응답에서 얻는다.**

배포 직후 점검에서 장소가 1,406 → 3,084개로 증가했고, 이 가이드 작성 중 추가 조회에서는 8,877개였다. 모두 시점별 관측값이며 전체 수집 완료를 뜻하지 않는다. 서울·부산·제주 추천이 각각 3개를 반환했고 서울·제주 예보 반영을 확인했다. 최초 혼잡도 필터 조회는 모두 0건이어서 서울시 수집 성공 여부는 확정하지 못했다. 일부 장소의 상세정보·날씨·혼잡도는 비어 있을 수 있다.

`/healthz` 정상은 DB 접근과 수집 워커 생존을 뜻한다. 모든 공급자 호출 성공, 수집 완료, 추천 품질을 보증하지 않는다.

## 3. 공통 응답과 오류 처리

대부분의 성공 응답은 다음 형태다. `/healthz`는 예외로 단순 `{status}`를 반환한다.

```json
{"success":true,"data":{"items":[]},"message":""}
```

오류는 아직 완전히 통일되어 있지 않다. HTTP 상태와 본문을 모두 확인한다.

| 발생 지점 | 예시 |
|---|---|
| 장소·추천 검증 실패 | `{"success":false,"data":null,"message":...}` |
| 인증·즐겨찾기 뷰의 오류 | `{"success":false,"data":{},"message":...}` |
| JWT 인증 / DRF 권한 오류 | `{"detail":"..."}` 또는 `detail`, `code`, `messages` 등 |
| 프록시·없는 경로·일부 서버 오류 | JSON 대신 HTML/텍스트일 수 있음 |

`message`는 문자열뿐 아니라 `{필드명: [오류문구]}` 형태도 가능하다. JSON 파싱에 실패해도 앱이 죽지 않도록 처리한다. 인증 뷰의 응답에서 `data: {}`를 성공으로 오인하지 않는다.

| HTTP | 처리 |
|---|---|
| 200 / 201 | 성공 형식 확인 후 사용. 추천 0개도 정상 200일 수 있음 |
| 400 | 입력 오류 표시. 같은 본문을 자동 반복하지 않음 |
| 401 | 보호 API는 토큰 갱신 1회 후 원요청 1회 재시도. 갱신도 실패하면 로그인 유도 |
| 404 | 장소가 사라졌거나 경로 오류. 상세는 삭제/비활성 안내 |
| 405 | HTTP 메서드 확인 |
| 429 / 5xx / 타임아웃 | 재시도 버튼과 기존 화면 유지. 무한 반복 호출하지 않음 |

비회원 추천에는 `Authorization`을 생략한다. 만료되거나 잘못된 Bearer 토큰을 보내면 비회원에게 열린 추천도 JWT 인증 단계에서 401이 날 수 있다. 회원가입·로그인·갱신에도 기존 만료 access token을 자동 부착하지 않는다.

추천 응답은 초기 수집·보충 작업에 따라 수 초 걸릴 수 있다. 배포 직후 표본은 기본 추천 약 0.15초, 날씨 고려 추천 약 2.15~3.77초였으며 지연 상한이나 부하 성능 보장은 아니다. 클라이언트 타임아웃은 시작값 15초 정도로 두고 로딩·재시도 UI를 마련한다. 입력 변경은 디바운스하고 마지막 요청 응답만 화면에 적용한다. 추천 POST는 보충 수집 작업을 등록할 수 있으므로 자동 고빈도 폴링하지 않는다.

## 4. 장소 API

### `GET /api/places`

| 쿼리 | 기본값 | 의미 |
|---|---|---|
| `keyword` | 빈 문자열 | 이름 또는 주소 부분 검색 |
| `category` | 빈 문자열 | 카테고리 부분 검색 |
| `region_code` | 빈 문자열 | 코드 접두어 검색. 예: `11` 서울 |
| `crowd_level` | 미지정 | `relaxed`, `normal`, `busy`, `crowded`, `unknown` |
| `page` | 1 | 양의 정수 |
| `page_size` | 20 | 1~100 |

응답의 `data.items`는 이름·ID 순서다. `data.pagination`에는 `page`, `page_size`, `total`, `total_pages`가 있다. 마지막 페이지를 넘으면 빈 배열이며 전체 0건이면 `total_pages=0`이다. `filters`는 적용된 검색 조건이다. 혼잡도 필터는 미래 관측을 제외한 최근 45분 이내 자료만 대상으로 한다.

### `GET /api/places/nearby`

필수 쿼리 `latitude`(-90~90), `longitude`(-180~180). `radius_km` 기본 5, **0 초과~100 이하**. `category`, `crowd_level`, `page`, `page_size`는 목록과 같다. `keyword`와 `region_code` 검색은 지원하지 않는다.

`data.items`는 직선거리 → 이름 → ID 순서이며 `distance_km`가 추가된다. `pagination`, `search_center`, `filters`도 반환한다. 위치 숫자로 NaN/Infinity를 보내지 않는다.

### `GET /api/places/{place_id}`

`data`가 장소 객체다. 목록과 달리 `data.items`로 감싸지 않는다. 아래 공통 장소 필드에 `indoor_outdoor_source`, `indoor_outdoor_evidence`, `open_status`, `info`, `created_at`, `updated_at`이 추가된다.

| 필드 | 타입 / UI 용도 |
|---|---|
| `id` | 정수. 상세·즐겨찾기 키. TourAPI 외부 ID가 아님 |
| `name`, `category`, `region_code`, `address` | 문자열 |
| `subcategory` | 문자열 또는 null. 공식 세부분류 코드이며 표시명으로 사용하지 않음 |
| `latitude`, `longitude` | JSON 숫자. Dart에서 `(value as num).toDouble()` 사용 |
| `indoor_outdoor` | `indoor`, `outdoor`, `mixed`, `unknown`. 단독으로 검증 완료 라벨 취급하지 않음 |
| `avg_rating` | 숫자 또는 null. 미수집이면 별점 0으로 표시하지 않음 |
| `image_url` | URL 또는 null. 실패/없음 placeholder 필요 |
| `latest_crowd` | 영역 혼잡도 객체 또는 null |
| `info` (상세) | 객체 또는 null. 없으면 “상세정보 준비 중” |
| `open_status` (상세) | `OPEN`, `CLOSED`, null. “지금 영업 중” 판정용이 아님 |

`info` 필드: `description`, `phone`, `homepage_url`, `first_image_url`, `opening_hours`, `holiday_info`, `tags`(배열), `source`, `updated_at`. 설명·영업시간은 문자열이고 구조화된 시간표 API가 아니다. 빈 문자열과 null을 모두 처리한다. 외부 설명을 임의 HTML로 실행하지 않는다. 외부 이미지가 HTTP이거나 로딩 실패하면 HTTPS 화면에서 대체 이미지를 사용한다.

`latest_crowd` 필드: `area_id`, `area_external_id`, `area_name`, `source`, `level`, `message`, `score`, `population_min`, `population_max`, `observed_at`, `is_stale`, `is_delayed`, `is_expired`, `is_replaced`. 인구수는 **주변 영역의 범위값**이며 해당 시설 내부 인원이나 대기시간이 아니다. `score`는 null일 수 있고 추천 점수와도 다르다.

## 5. 추천 API 입력

### `POST /api/recommendations`

```json
{
  "latitude": 37.575,
  "longitude": 126.977,
  "radius_km": 3,
  "limit": 3,
  "weather_aware": true
}
```

| 필드 | 기본값 / 범위 | 동작 |
|---|---|---|
| `latitude`, `longitude` | 필수 숫자, -90~90 / -180~180 | 검색 기준 좌표 |
| `radius_km` | 10, **0.1~100** | 후보의 최대 직선거리. 주변 검색 API의 최소값과 다름 |
| `limit` | 10, 정수 1~10 | 최대 결과 수. 페이지 기능 없음 |
| `category` | 미지정, 문자열 최대 100자 | 카테고리 **선호 점수**, 제외 필터 아님 |
| `required_categories` | 미지정, 문자열 배열 | 정확히 일치하는 카테고리만 남김. 여러 값은 OR, 빈 배열은 제한 없음 |
| `crowd_level` | `any` | `relaxed`, `normal`, `busy`, `crowded`, `any`. 혼잡 선호이며 엄격 필터 아님 |
| `quiet_required` | false | 현재 유효한 한산 관측이 있는 장소만. `crowd_level`은 `relaxed` 또는 `any`여야 함 |
| `indoor_outdoor` | 미지정 | `indoor`, `outdoor`, `mixed`. 실내외 **선호** |
| `required_indoor_outdoor` | 미지정 | 같은 enum. 해당 라벨이며 수동/현재 유효한 설명 규칙 근거가 있는 곳만 |
| `weather_aware` | true | 가용 날씨 점수를 순위에 반영 |
| `weather_evidence_required` | false | 가용 예보와 장소별 날씨 근거로 점수 산출 가능한 곳만. 유형 추정만 있는 곳은 제외 |
| `visit_at` | 서버 현재 시각 | 오프셋 포함 ISO 8601. 예: `2026-09-15T14:00:00+09:00` |

지원 추천 카테고리: **관광지, 문화시설, 축제/공연/행사, 레포츠, 쇼핑, 음식점**. 숙박·여행코스는 추천 대상이 아니다. 카테고리는 한글 값을 그대로 보낸다. 추천의 카테고리 일치는 정확 일치이며 장소 검색의 부분 검색과 다르다. 임의 카테고리도 문자열 검증을 통과할 수 있으므로 프론트 선택지는 위 목록으로 제한한다.

선택값이 없으면 필드를 생략한다. 선택 enum에 `unknown`·`null`·빈 문자열을 보내지 않는다. 목록의 `crowd_level=unknown`과 추천의 `crowd_level=any`를 혼동하지 않는다.

| UI 선택 | 요청 예시 | 주의 |
|---|---|---|
| 음식점 위주 추천 | `"category":"음식점"` | 다른 카테고리도 나올 수 있음 |
| 음식점만 | `"required_categories":["음식점"]` | 필터 |
| 실내 선호 | `"indoor_outdoor":"indoor"` | 불명/실외도 후보에 남음 |
| 확인된 실내만 | `"required_indoor_outdoor":"indoor"` | 이름·AI 추정만으로 통과하지 못함 |
| 한산한 곳만 | `"quiet_required":true,"crowd_level":"relaxed"` | 서울 매핑·신선한 관측이 부족하면 0개 가능 |
| 날씨 반영 끄기 | `"weather_aware":false` | 저장된 날씨가 응답에 있어도 순위에는 안 씀 |
| 날씨 근거로 거르기만 | `"weather_evidence_required":true,"weather_aware":false` | 필터와 점수 반영은 독립 |

`visit_at`을 생략하면 현재 추천이다. 미래 시각을 지정해도 미래 혼잡도를 예측하지 않는다. 예보 범위를 벗어나면 날씨가 없을 수 있다. 프론트는 고정 예제 날짜를 실제 요청에 계속 사용하지 않는다. Dart `DateTime.toUtc().toIso8601String()` 결과처럼 `Z`가 있는 값을 사용한다.

## 6. 추천 응답과 카드 구성

[실제 운영 추천 응답 예제](./docs/examples/recommendations-mvp7-response.json)는 배포 직후 서울 좌표에서 `weather_aware=false`, `limit=3`으로 받은 전체 응답이다. 기록 시각의 정적 fixture이며 최신 예보나 현재 장소 순위를 뜻하지 않는다. 테스트 시 서버가 같은 ID/순위를 반환한다고 단정하지 않는다.

| `data` 필드 | 의미 |
|---|---|
| `items` | 추천 카드 배열. 요청 개수보다 적거나 비어 있을 수 있음 |
| `candidate_count` | 필수 조건을 통과해 실제 점수를 계산한 후보 수. 전체 DB 개수 아님 |
| `algorithm_version` | 현재 `mvp-7` |
| `generated_at`, `visit_at` | 생성 시각과 방문 기준 시각 |
| `ranking_basis` | `travel_discovery`, `weather_and_travel_discovery`, `requested_preferences`, `weather_and_preferences` |
| `ranking_factors` | 이번 결과 전체에서 활성화한 점수 항목 |
| `preference_source` | `request`, `profile`, `default_travel_intent` |
| `weather_aware`, `weather_evidence_required` | 적용 옵션 |
| `ranking_policy` | 이번 점수에 사용한 가중치·중립점·거리 보정·근거 계수 |

| `items[]` 필드 | 의미 / UI 처리 |
|---|---|
| `rank` | 1부터 시작. **서버 순서 유지** |
| `place` | 장소 요약. `id`, 이름, 분류, 주소, 좌표, 실내외 근거, `weather_exposure` |
| `distance_km`, `distance_type` | 직선거리 / `straight_line`. “도보 거리”로 표시하지 않음 |
| `travel_time_minutes` | 현재 null |
| `recommendation_score` | 정책 점수. 확률·만족도·혼잡 백분율 아님 |
| `distance_adjustment` | 거리 보정 `factor`, 보정 전 `base_score` |
| `crowd` | 추천에 유효한 현재/지연 관측 또는 null. 목록의 `latest_crowd`와 구조가 다름 |
| `weather`, `weather_status` | 예보 객체와 사용 상태 |
| `score_breakdown` | 원점수. 사용 가능한 값이 있어도 이번 순위 항목이 아닐 수 있음 |
| `score_effective_breakdown` | 근거 계수를 적용한 점수. null 유지 |
| `score_contributors` | **이 장소의 순위에 실제 사용한 관측/근거 항목** |
| `data_coverage`, `ranking_coverage` | 가중 근거 보유량 / 활성 점수 항목 기준 근거 보유 비율. 정확도 아님 |
| `missing_data` | 원점수가 없는 항목. 선택하지 않은 실내외 선호도 포함될 수 있어 모두 장애로 표시하지 않음 |
| `reasons` | 카드에 표시할 설명 문자열 배열 |

추천의 `place`에는 사진·소개·평점이 없다. `GET /api/places/{id}`로 필요할 때 보강하고 ID별로 캐시한다. 즐겨찾기 역시 서버가 반환한 내부 `place.id`를 사용한다. `recommendation_score`를 프론트에서 다시 계산하거나 반올림 점수로 재정렬하지 않는다.

### 혼잡도 표시 규칙

| 서버 level | 표시 예 | 현재 3단계 UI를 유지할 때 |
|---|---|---|
| `relaxed` | 여유 | low |
| `normal` | 보통 | medium |
| `busy` | 약간 붐빔 | high (텍스트는 유지) |
| `crowded` | 매우 붐빔 | high (텍스트는 유지) |
| `unknown` / 객체 null | 혼잡도 정보 없음 | **unknown 상태 추가** |

목록·상세는 만료 관측도 `latest_crowd`로 보여줄 수 있다. 추천은 만료 자료를 `crowd=null`로 제외한다. 추천 `crowd`에는 `type`(`realtime`/`delayed_observation`), `level`, `source`, `observed_at`, `is_stale`, `is_delayed`, `score_weight_factor`가 있다.

- 관측 나이 0~15분: 신선, 15분 초과: `is_stale=true`.
- 30분까지: 추천 혼잡 근거 계수 1. 30분 초과~45분: `is_delayed=true`, 계수 0.5.
- 45분 초과/미래 관측: 추천에서 제외. `quiet_required`는 지연 관측도 제외한다.
- 방문 시각이 현재에서 ±5분을 벗어나면 현재 혼잡도는 추천 근거로 사용하지 않는다.

`null`을 여유/0명으로 표시하지 않는다. 시각과 “서울시 영역 관측” 출처를 함께 표시한다. 미래 방문 카드에 현재 혼잡도를 미래 예측처럼 붙이지 않는다.

### 날씨·실내외 표시 규칙

`weather` 필드: `source=kma_vilage`, `issued_at`(발표), `target_at`(예보 대상), `precipitation_type`, `temperature_c`, `wind_mps`, `completeness`. `target_at`은 방문 시각이 속한 정각이다. 기온은 °C, 풍속은 m/s. 강수 코드를 프론트에서 자체 확률로 해석하지 않는다. 현재 점수는 `precipitation_type > 0`을 비/눈 악조건으로 취급한다.

| `weather_status` | 처리 |
|---|---|
| `complete` | 강수형태·기온·풍속 모두 있는 가용 예보와 장소 노출 근거 |
| `partial_hazard` | 일부 예보만 있고 악조건은 확인됨. “일부 예보 기준” 안내 |
| `partial_uninformative` | 일부 예보만 있으며 날씨 적합도를 판단할 근거 부족 |
| `unavailable` | 유효 예보 또는 장소 노출 근거 없음 |

`weather` 객체가 있어도 `weather_aware=false`이면 순위에 반영되지 않는다. `score_contributors`를 기준으로 “날씨 반영” 배지를 표시한다. `unavailable`은 공급자 장애뿐 아니라 장소 노출 근거 없음도 뜻한다.

`place.weather_exposure`는 주된 방문 활동의 날씨 영향 추정이다. `level`은 `high`/`medium`/`low`/`unknown`이며 실측 비율이 아니다. `activity`, `source`, `reason`, `weight_factor`, `conflict`, `conflict_reason`, `type_code`, `type_name`, `policy_version`, `persisted`를 함께 제공한다. `persisted=false`는 요청에서 계산했다는 뜻이며 그 자체로 오류가 아니다. `low`를 “확인된 실내”로 바꾸어 표시하지 않는다.

실내외 라벨에는 `indoor_outdoor_evidence_quality`를 함께 읽는다. `manual_label`, `inferred_from_description`, `inferred_from_name`, `inferred_from_luna`, `stale_auto_evidence`, `unattributed`, `unknown`이 가능하다. 이름/AI 기반이면 “추정”, 오래된 근거이면 “미확인”으로 구분한다. 근거 충돌 시 서버의 `reason`·`conflict_reason`을 설명에 사용한다.

## 7. 추천에 쓰는 외부 API와 데이터

아래는 **현재 코드가 호출하는 서비스**다. 프론트는 이 서비스를 직접 호출하지 않고 ILION API만 사용한다.

| 공급자 / 코드의 호출 경로 | 저장 데이터 | 추천에서의 용도와 한계 |
|---|---|---|
| 한국관광공사 `KorService2/areaBasedSyncList2` | 전국 목록, 외부 ID, 좌표, 카테고리·세부분류, 주소·활성 상태 | 후보 구성, 거리, 기본 여행 선호, 약한 유형별 날씨 노출 추정 |
| 한국관광공사 `detailCommon2`, `detailIntro2` | 소개·이미지·연락처·운영시간·행사기간 등 | 상세 표시, 설명 기반 분류, 방문일의 행사 유효성 검사. 점진 수집 |
| 서울시 `citydata_ppltn` | 영역별 혼잡 단계, 인구 최소/최대, 관측 시각 | 명시적으로 연결한 장소의 현재 혼잡 근거. 시설 단위 계측 아님 |
| 기상청 `VilageFcstInfoService_2.0/getVilageFcst` | 격자·발표시각·대상시각별 PTY/TMP/WSD | 장소 활동의 날씨 노출과 조합해 적합도 계산 |
| 사용자/로컬 정책 | 명시 선호, 저장된 선호 카테고리, 이름·설명 규칙, 기존 검토 자료 | 추천은 설명 가능한 규칙·가중 점수 모델. 요청마다 LLM 호출 없음 |

장소는 `Place`, 원본/매칭은 `PlaceSource`, 상세는 `PlaceInfo`, 영역 연결은 `PlaceCrowdArea`, 혼잡 관측은 `CrowdData`, 예보는 `WeatherForecast`에 저장한다. 추천은 DB의 저장본을 사용한다. 누락 자료가 있으면 공통 작업 큐에 날씨 최대 5개 격자 및 가까운 후보의 서울 영역 보충을 요청할 수 있다. 이미 실행 중인 작업만 최대 2초 기다리며, 보충 성공을 무조건 기다리지는 않는다. **202 작업 ID나 완료 알림 API는 없다.**

서울 정기 수집 대상은 공식 **121개 영역**이지만 현재 버전 관리된 장소 연결은 **13개 관계 / 12개 영역**이다. 121개 영역을 수집한다고 모든 주변 장소에 혼잡도가 붙지는 않는다. 연결이 없는 장소는 null을 유지한다.

### 운영 갱신 주기와 데이터 준비 속도

| 작업 | 현재 Pi 설정 (KST) |
|---|---|
| 초기 목록 | 시작 직후 수집, 1,000행/페이지·최대 100페이지 |
| 목록 변경분 | 매일 03시 이후. 놓친 날짜를 포함하도록 마지막 성공 기준 중첩 조회 |
| 전체 목록 대조 | 일요일 04시 이후 |
| 상세 보강 | 첫 목록 성공 후 매일 04:30 이후, 누락/오래된 자료 최대 150개/일 |
| 서울 혼잡도 | 매시 00·15·30·45분 창 |
| 기상청 | 02·05·08·11·14·17·20·23시 발표본 기준, 코드상 발표 후 10분부터 시도. 7개 도시 중심+최근 요청, 정기 최대 35격자 |

워커는 1분마다 예약 여부를 확인한다. 실제 완료 시각은 초기 수집·큐 대기·공급자 응답에 따라 늦어진다. 발표 후 10분은 구현의 수집 시도 기준이며 공급자 제공 SLA가 아니다. 예보는 발표 후 **5시간 이내**이며 요청한 방문 시각의 정각과 정확히 맞는 저장본만 쓴다. 다시 수집했다고 낡은 발표본의 유효기간이 늘지 않는다. 보충 예보 요청 범위는 현재에서 1시간 전~5일 후이며 그 범위도 자료 존재를 보장하지 않는다.

앱 일일 상한은 TourAPI 1,000회, 서울 18,000회, 기상청 10,000회다. 70% 정기·20% 보충·10% 예비로 나누며, 기상청은 격자 수가 아닌 페이지별로 차감한다. 이는 앱 설정으로 공급자 계정 승인량을 보증하지 않는다. 한도가 소진되면 수집이 다음 한국 날짜로 미뤄질 수 있다. 프론트 개발을 위해 같은 키로 로컬 수집 워커를 추가 실행하지 않는다.

## 8. 추천 산출 방법 (`mvp-7`)

### 8.1 후보 선정

1. 현재 유효한 장소 중 지원 카테고리, 위·경도 경계상자, 명시 필수 조건으로 1차 검색한다. `open_status=CLOSED`는 제외한다.
2. 행사는 상세 원본의 시작일~종료일에 방문일(KST)이 들어오는 경우만 남긴다. 기간 미확인 행사도 제외한다.
3. 하버사인 직선거리로 실제 반경을 검사한다. 필수 실내외는 라벨 일치에 더해 수동/유효한 설명 규칙 근거가 필요하다.
4. `quiet_required`, `weather_evidence_required`를 검사하고 남은 후보에 점수를 계산한다. 후보가 부족해도 필수 조건을 자동 완화하지 않는다.

### 8.2 항목별 원점수

| 항목 | 원점수 (0~100) |
|---|---|
| 거리 | `100 / (1 + 직선거리_km / 2.5)` |
| 카테고리: 요청/프로필 선호 있음 | 선호 카테고리와 정확 일치 100, 불일치 0 |
| 카테고리: 선호 없음 | 관광지·문화시설 90, 행사·레포츠 85, 음식점 60, 쇼핑 45 |
| 실내외 선호 | 유효 근거가 있을 때 일치 100, 불일치하되 장소가 mixed면 60, 그 외 0. 선호 미지정/근거 없으면 null |
| 혼잡 | 아래 표. 유효한 현재 관측이 없으면 null |
| 날씨 | 아래 악조건·노출 산식. 가용 근거 없으면 null |

카테고리 선호 우선순위는 요청 `category` → 로그인 사용자의 저장 `preferred_categories` → 기본 여행 탐색 점수다. 프로필 수정 API가 없으므로 초기 프론트에서는 요청 `category`로 전달한다.

혼잡 원점수는 **행=요청 선호, 열=관측 단계**다.

| 요청 / 관측 | relaxed | normal | busy | crowded |
|---|---:|---:|---:|---:|
| `relaxed` | 100 | 65 | 25 | 0 |
| `normal` | 70 | 100 | 65 | 20 |
| `busy` | 20 | 70 | 100 | 60 |
| `crowded` | 0 | 30 | 70 | 100 |
| `any` (기본) | 50 | 50 | 40 | 25 |

기본 `any`는 혼잡 회피 경고만 제한적으로 반영한다. 한산 관측이 있는 소수 장소에 자료가 있다는 이유만으로 기본 가점을 주지 않는다.

날씨 악조건 개수 `n`은 다음을 각각 1개로 센다: 강수형태 > 0, 풍속 ≥ 9m/s, 기온 ≥ 33°C 또는 ≤ -10°C.

| 예보 상태 | 노출 high | 노출 low | 노출 medium |
|---|---|---|---|
| 세 필드 모두 있음 | `max(0, 85 - 35n)` | 악조건 있으면 95, 없으면 65 | high와 low 점수의 평균 |
| 일부 필드 + 악조건 확인 | `max(0, 50 - 35n)` | 85 | high와 low 점수의 평균 |
| 일부 필드 + 악조건 미확인 | null | null | null |

노출 unknown 또는 유효 예보 없음도 null이다. 실내 활동에 불리한 날씨가 상대적으로 높은 점수를 주는 것은 현재 정책이며 만족도 실측 결과가 아니다.

### 8.3 근거 강도, 활성 항목, 최종 점수

기본 가중치는 거리 **0.30**, 카테고리 **0.15**, 혼잡 **0.20**, 날씨 **0.25**, 실내외 **0.10**이다. 항상 다섯 항목을 모두 쓰지는 않는다.

- 거리·카테고리는 항상 활성화한다.
- 혼잡은 결과 중 유효 관측이 있고 명시적 혼잡 선호가 있거나, 기본 `any`에서 busy/crowded 위험 관측이 있을 때 활성화한다.
- 날씨는 `weather_aware=true`이고 결과 중 날씨 점수가 있는 후보가 있을 때 활성화한다.
- 실내외는 선호를 지정했고 결과 중 유효한 분류 점수가 있을 때 활성화한다.

활성 항목 집합은 **이번 요청의 전체 후보에 공통**이다. 어느 후보에 자료가 없는 활성 항목은 중립점 50으로 계산하되, 응답의 원점수 null은 그대로 유지한다.

근거 계수 `f`는 거리·카테고리 1, 현재 혼잡 1, 지연 혼잡 0.5, 수동 분류 1, 설명 규칙 0.75, 이름/AI 추정 0.5다. 날씨의 공식 유형만 이용한 추정은 0.35이며 일부 혼합 근거에도 보수적인 계수를 적용한다. 실제 날씨 계수는 `place.weather_exposure.weight_factor`를 읽는다. 이 값은 예측 신뢰확률이 아니다.

```text
유효 항목 점수 E = 50 + (원점수 S - 50) × 근거 계수 f
원점수가 없는 활성 항목의 계산값 = 50

보정 전 점수 B = Σ(활성 항목의 가중치 × 계산값) / Σ(활성 항목의 가중치)
거리 보정 G = 1 / (1 + max(0, 직선거리_km - 5) / 20)
최종 점수 = B × G  → 응답에는 소수 둘째 자리 반올림
```

예: 1km의 문화시설, 선호 미지정, 날씨 끔, 혼잡 위험 근거 없음이면 활성 항목은 거리·카테고리다. 거리 점수는 약 71.43, 카테고리는 90, 거리가 5km 이내라 G=1이므로 `(71.42857×0.30 + 90×0.15) / 0.45 ≈ 77.62`점이다.

정렬은 반올림 전 최종 점수 내림차순이다. 동점이면 명시 혼잡 선호가 있는 경우 관측 최신순, 다음 거리순, ID순으로 정렬한다. 데이터 갱신이나 후보 집합이 달라지면 활성 항목·점수·순서도 바뀔 수 있으므로 다른 요청 간 점수를 절대적 품질 척도로 비교하지 않는다.

`data_coverage = Σ(원점수가 있는 항목 가중치 × 근거 계수)`이고, `ranking_coverage`는 실제 활성·기여 항목의 같은 합을 활성 가중치 합으로 나눈 값이다. 날씨 반영을 꺼도 저장된 날씨 근거가 `data_coverage`에는 포함될 수 있다. 두 값 모두 추천 정확도나 데이터베이스 완성률이 아니다.

## 9. 인증·즐겨찾기 API

인증은 쿠키 세션 대신 JSON으로 받은 JWT를 `Authorization: Bearer <access_token>`에 넣는다. access 30분, refresh 14일이다. 토큰은 로그·소스·공유 문서에 기록하지 않는다. 아래는 구현 계약이며 운영 계정 생성부터 로그아웃까지의 검증 완료를 뜻하지 않는다.

| 메서드 / 경로 | 요청 | 성공 data / 상태 |
|---|---|---|
| `POST /api/auth/signup` | `email`, `password`, `nickname` | `access_token`, `refresh_token` / 201 |
| `POST /api/auth/login` | `email`, `password` | 같은 토큰 두 개 / 200 |
| `POST /api/auth/google` | `id_token` | 같은 토큰 두 개 / 200 또는 201. 운영 설정 전 사용 보류 |
| `POST /api/auth/refresh` | `refresh_token` | `access_token`만 / 200 |
| `POST /api/auth/logout` | Bearer 필수, 본문 불필요 | `{}` / 200 |
| `GET /api/auth/nickname/random` | 없음 | `nickname` / 200 |
| `GET /api/favorites` | Bearer 필수 | `{"place_ids":[...]}` / 200, 최근 저장순 |
| `POST /api/favorites` | Bearer + `{"place_id":123}` | `{"place_id":123}` / 최초 201, 기존 항목이면 200 |
| `DELETE /api/favorites/{place_id}` | Bearer 필수 | `{}` / 200, 내 저장 내역 없으면 404 |

회원가입은 고유 이메일·고유 닉네임(최대 30자)과 서버 비밀번호 검증을 적용한다. 로그인 응답에는 사용자 프로필이 없다. 랜덤 닉네임 응답은 예약이 아니므로 실제 회원가입 시 중복 검증 오류를 처리한다.

로그인/회원가입으로 새 토큰을 발급하면 해당 계정의 기존 refresh token은 폐기된다. refresh 갱신은 새 access만 반환하며 기존 refresh를 유지한다. 로그아웃은 해당 계정의 refresh들을 폐기하지만 **이미 발급된 access는 만료 전까지 살아 있다**. 프론트에서도 두 토큰을 제거한다. 동시에 여러 401이 발생해도 갱신 요청은 하나로 합친다.

저장 목록은 장소 객체가 아닌 ID 배열이다. 각 ID의 상세를 조회·캐시하고 비활성 장소의 상세 404는 “현재 조회할 수 없는 장소”로 처리한다. 저장 동작이 추천 학습이나 선호 프로필 갱신으로 이어지지는 않는다.

## 10. Flutter 호출 예제

현재 프론트는 `lib/src/data/mock_places.dart`와 표시용 `Place` 모델을 사용하며 `pubspec.yaml`에 HTTP 패키지가 없다. 아래 코드는 **연동 담당자가 추가할 예제**이며 이번 문서 작업에서 앱 코드/의존성을 변경하지 않았다.

```bash
cd tourist_congestion_frontend
flutter pub add http
flutter run --dart-define=API_BASE_URL=https://ilion.app.hurdoo.kr
```

프로젝트 SDK와 호환되는 의존성을 설치하고 lockfile을 함께 관리한다. 예제의 `http.Client` 및 UTF-8 응답 처리는 [Dart 팀 HTTP 패키지 문서](https://pub.dev/packages/http)를 따른다. Web 대상으로 실행할 때는 1절의 CORS 조건을 먼저 해결해야 한다.

`lib/src/services/ilion_api.dart`에 둘 수 있는 최소 예제다. UI에서는 예외를 받아 입력 오류/인증 필요/네트워크 재시도 상태로 나눈다.

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiException implements Exception {
  const ApiException(this.statusCode, this.message);
  final int statusCode;
  final String message;
  @override
  String toString() => message;
}

class IlionApi {
  IlionApi({http.Client? client}) : _client = client ?? http.Client();
  final http.Client _client;
  static const _base = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://ilion.app.hurdoo.kr',
  );

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('${_base.replaceFirst(RegExp(r"/+$"), "")}$path')
          .replace(queryParameters: query);

  Map<String, dynamic> _data(http.Response response) {
    dynamic decoded;
    try {
      decoded = jsonDecode(utf8.decode(response.bodyBytes));
    } catch (_) {
      throw ApiException(response.statusCode, '서버 응답을 읽을 수 없습니다.');
    }
    if (decoded is! Map<String, dynamic>) {
      throw ApiException(response.statusCode, '예상하지 못한 응답입니다.');
    }
    if (response.statusCode < 200 || response.statusCode >= 300 ||
        decoded['success'] != true) {
      final error = decoded['message'] ?? decoded['detail'] ?? '요청 실패';
      throw ApiException(response.statusCode,
          error is String ? error : jsonEncode(error));
    }
    return decoded['data'] as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> recommendations({
    required double latitude,
    required double longitude,
    String? accessToken,
  }) async {
    final response = await _client.post(
      _uri('/api/recommendations'),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        if (accessToken != null && accessToken.isNotEmpty)
          'Authorization': 'Bearer $accessToken',
      },
      body: jsonEncode({
        'latitude': latitude,
        'longitude': longitude,
        'radius_km': 3,
        'limit': 3,
        'weather_aware': true,
      }),
    ).timeout(const Duration(seconds: 15));
    return _data(response);
  }

  Future<Map<String, dynamic>> placeDetail(int id) async {
    final response = await _client.get(
      _uri('/api/places/$id'),
      headers: {'Accept': 'application/json'},
    ).timeout(const Duration(seconds: 15));
    return _data(response);
  }

  Future<Map<String, dynamic>> search(String keyword) async {
    final response = await _client.get(
      _uri('/api/places', {'keyword': keyword, 'page_size': '20'}),
      headers: {'Accept': 'application/json'},
    ).timeout(const Duration(seconds: 15));
    return _data(response);
  }

  void close() => _client.close();
}
```

서비스를 화면 rebuild마다 만들지 말고 수명에 맞춰 재사용·종료한다. 위 `_data`는 성공 시 `data`만 돌려주는 최소 예제이므로 후보 부족 안내는 `items.length`로 처리하거나 envelope 모델을 추가해 최상위 `message`도 보존한다. `healthz`는 공통 envelope가 없어 이 파서에 넣지 않는다. 토큰 저장·갱신, 타입별 DTO, 요청 취소, 상태 관리는 별도로 구현해야 한다. 이 환경에는 Flutter/Dart SDK가 없어 예제 컴파일 검증은 수행하지 않았다.

### 현재 mock 모델에서 바꿀 부분

| 현재 필드 | 연동 모델 방향 |
|---|---|
| ID 없음 | `int id` 추가. 이름으로 상세/즐겨찾기를 연결하지 않음 |
| `distance` 문자열 | API DTO는 nullable 숫자 `distanceKm`, 표시 때 km/m 포맷 |
| 3단계 `CrowdLevel` | 서버 4단계와 unknown을 보존하거나 3단계 색상+원문 단계 텍스트로 표시 |
| 필수 `description` | 상세 로드 전/누락을 허용. 추천에는 없음 |
| `area` | API `address`를 사용하거나 표시용 행정구역을 별도 생성 |
| `icon` | 카테고리 기반 로컬 UI 아이콘. 서버 아이콘 필드 없음 |

`PlaceSummary`, `PlaceDetail`, `RecommendationItem`은 중첩 구조가 다르므로 하나의 mock `Place`에 무리하게 직접 파싱하지 않는다. 날짜는 ISO 시각으로 파싱한 후 UI 시간대로 변환한다. 카드에 사진·평점·혼잡도가 없더라도 mock의 그럴듯한 값으로 메우지 않는다.

## 11. 프론트 인수 확인 목록

- 비회원으로 장소 검색·주변 검색·추천·상세가 연결된다.
- UTF-8 한글, 정수/실수 숫자, 빈 문자열/null, 이미지 실패를 처리한다.
- 추천은 0개/요청보다 적은 개수도 정상 화면으로 보여준다. 필수 조건을 조용히 완화하지 않는다.
- 서버 순위·직선거리·혼잡도 관측 시각·날씨 발표/대상 시각을 구분한다.
- 날씨 미반영, 근거 추정, 혼잡도 미확인 상태를 실제 관측과 다르게 표시한다.
- 좌표 누락·limit 11의 400, 상세 404, 보호 API 401, HTML 오류·타임아웃을 처리한다.
- 로그인 이후 저장·중복 저장·삭제·갱신 실패를 전용 테스트 계정으로 별도 검증한다.
- Android release 인터넷 권한을 확인한다. Web은 실제 origin의 CORS/프록시를 먼저 검증한다.
- 반복 탭/검색에서 중복 요청과 늦게 도착한 이전 응답이 화면을 덮지 않도록 한다.
- Google 로그인·프로필 수정·후기·예측 혼잡도·이동시간은 준비 완료로 표시하지 않는다.

## 12. 구현 근거와 추가 문서

이 문서의 서버 계약은 다음 코드에서 확인했다. 이후 배포 시 `algorithm_version`과 소스 변경을 함께 확인한다.

- [라우트](./config/urls.py), [장소 API 구현](./places/views.py), [추천 입력 검증](./recommendations/serializers.py)
- [추천 계산·응답](./recommendations/service.py), [가중치·시간 기준·JWT 설정](./config/settings.py)
- [날씨 노출 정책](./places/services/weather_exposure.py), [예보 저장·선택](./places/services/weather.py)
- [운영 예약](./places/services/scheduling.py), [인증·즐겨찾기](./users/views.py)
- [장소 API 상세](./API.md), [Pi 배포·수집 운영](./docs/pi-deployment.md)
- [mvp-7 날씨 노출 평가](./docs/weather-exposure-mvp7-2026-09-14.md), [분류 근거 평가](./docs/place-classification-context-evaluation-2026-09-14.md)

과거 `recommendation-mvp.md`에는 이전 mvp 설명과 개발 워커 설정도 보존되어 있다. 현재 프론트 계약은 이 문서와 배포 코드, Pi 운영 예약은 `pi-deployment.md`를 기준으로 한다. 소스 계약 `deploy.json`의 접근 범위는 운영 설정과 같은 `public`이다. 운영 디버그 모드는 `false`를 유지한다.
