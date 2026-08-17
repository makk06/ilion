# 장소·혼잡도 API

전국 장소 데이터와 서울 일부 지역의 최신 혼잡도를 조회하는 MVP용 읽기 전용
API입니다. 모든 응답은 아래 공통 형식을 사용합니다.

```json
{
  "success": true,
  "data": {},
  "message": ""
}
```

오류 응답은 `success=false`, `data=null`이며 `message`에 클라이언트에
보여줄 수 있는 오류 원인을 담습니다. 현재 읽기 API는 인증 없이 호출할 수
있습니다.

## 장소 목록·검색

```http
GET /api/places
```

### 쿼리 파라미터

| 이름 | 기본값 | 설명 |
| --- | --- | --- |
| `keyword` | 빈 값 | 장소명 또는 주소 부분 검색 |
| `category` | 빈 값 | 카테고리 부분 검색 |
| `region_code` | 빈 값 | 지역 코드 앞부분 검색. `11`이면 서울 전체 |
| `crowd_level` | 빈 값 | 최신 혼잡도 필터 |
| `page` | `1` | 1부터 시작하는 페이지 번호 |
| `page_size` | `20` | 페이지당 개수. 최대 100 |

`crowd_level`은 `relaxed`, `normal`, `busy`, `crowded`, `unknown` 중 하나입니다.
혼잡도 필터는 과거 관측 전체가 아니라 장소에 연결된 가장 최근 관측값에
적용됩니다.

### 응답 예시

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "name": "경복궁",
        "category": "관광지",
        "subcategory": "HS010100",
        "region_code": "11-110",
        "address": "서울특별시 종로구 사직로 161 (세종로)",
        "latitude": 37.576031,
        "longitude": 126.976722,
        "indoor_outdoor": "unknown",
        "avg_rating": null,
        "image_url": "https://example.com/gyeongbokgung.jpg",
        "latest_crowd": {
          "area_id": 1,
          "area_external_id": "POI008",
          "area_name": "경복궁",
          "source": "seoul_realtime",
          "level": "normal",
          "message": "개발용 혼잡도 샘플입니다.",
          "score": null,
          "population_min": 12000,
          "population_max": 14000,
          "observed_at": "2026-08-17T12:00:00+09:00",
          "is_replaced": false
        }
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 1,
      "total_pages": 1
    },
    "filters": {
      "keyword": "경복궁",
      "category": "",
      "region_code": "",
      "crowd_level": ""
    }
  },
  "message": ""
}
```

서울 혼잡 영역과 연결되지 않은 전국 장소는 `latest_crowd`가 `null`입니다.
TourAPI에서 비활성화된 장소는 목록과 상세 조회에서 제외합니다. 외부 출처 없이
팀이 직접 등록한 내부 장소는 조회할 수 있습니다.

## 주변 장소 검색

```http
GET /api/places/nearby
```

사용자의 현재 좌표를 기준으로 지정 반경 안의 장소를 가까운 순서로 반환합니다.
각 장소에는 `distance_km`가 추가되며, 서울 혼잡 영역과 연결된 장소는
`latest_crowd`도 함께 반환합니다.

### 쿼리 파라미터

| 이름 | 기본값 | 설명 |
| --- | --- | --- |
| `latitude` | 필수 | 기준 위도. -90 이상 90 이하 |
| `longitude` | 필수 | 기준 경도. -180 이상 180 이하 |
| `radius_km` | `5` | 검색 반경(km). 0 초과 100 이하 |
| `category` | 빈 값 | 카테고리 부분 검색 |
| `crowd_level` | 빈 값 | 최신 혼잡도 필터 |
| `page` | `1` | 1부터 시작하는 페이지 번호 |
| `page_size` | `20` | 페이지당 개수. 최대 100 |

### 응답 예시

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "name": "경복궁",
        "category": "관광지",
        "region_code": "11-110",
        "address": "서울특별시 종로구 사직로 161 (세종로)",
        "latitude": 37.576031,
        "longitude": 126.976722,
        "distance_km": 0.142,
        "latest_crowd": {
          "area_name": "경복궁",
          "level": "normal",
          "population_min": 12000,
          "population_max": 14000
        }
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 1,
      "total_pages": 1
    },
    "search_center": {
      "latitude": 37.575,
      "longitude": 126.977,
      "radius_km": 5.0
    },
    "filters": {
      "category": "",
      "crowd_level": ""
    }
  },
  "message": ""
}
```

성능을 위해 위·경도 경계상자로 DB 후보를 먼저 제한하고, 후보에 하버사인
공식을 적용해 정확한 반경과 거리를 계산합니다. 현재 MVP 최대 반경은 100km이며
운영 데이터 규모와 사용 패턴을 확인한 뒤 공간 인덱스 도입 여부를 재검토합니다.

## 장소 상세

```http
GET /api/places/{place_id}
```

목록의 장소 필드와 최신 혼잡도에 더해 `open_status`, `info`, `created_at`,
`updated_at`을 반환합니다. `info`에는 소개, 전화번호, 홈페이지, 대표 이미지,
운영시간, 휴무일, 태그와 상세정보 출처가 포함됩니다. 아직 상세정보를 보강하지
않은 장소의 `info`는 `null`입니다.

```json
{
  "info": {
    "description": "조선 왕조의 법궁입니다.",
    "phone": "02-3700-3900",
    "homepage_url": "https://royal.khs.go.kr/",
    "first_image_url": "https://example.com/gyeongbokgung.jpg",
    "opening_hours": "09:00~18:00",
    "holiday_info": "매주 화요일",
    "tags": ["관광지"],
    "source": "tour_api",
    "updated_at": "2026-08-17T13:30:00+09:00"
  }
}
```

조회 가능한 장소가 없으면 HTTP 404와 아래 응답을 반환합니다.

```json
{
  "success": false,
  "data": null,
  "message": "Place not found."
}
```

## 로컬 시연

API 키가 없어도 결정적인 개발 시드로 전체 흐름을 시연할 수 있습니다.

```bash
cd tourist_congestion_backend
source .venv/bin/activate
python manage.py migrate
python manage.py seed_dev_data
python manage.py runserver
```

개발 시드는 10개 장소에 API 키가 필요 없는 샘플 상세정보를 포함합니다. 실제
TourAPI 상세정보로 선택한 장소를 보강하려면 다음 명령을 사용합니다. 기본 10개,
최대 100개만 처리하며 장소 하나당 공통정보와 소개정보 요청을 각각 한 번
사용합니다.

```bash
# DB에 반영하지 않고 호출·정규화 시험
python manage.py sync_tour_place_details 126508 --dry-run

# 매칭된 장소 10개를 실제 상세정보로 보강
python manage.py sync_tour_place_details --limit 10

# 서울 장소 중 20개를 공통정보만 보강(장소당 1회 호출)
python manage.py sync_tour_place_details \
  --region-code 11 --limit 20 --skip-intro
```

다른 터미널에서 다음 요청을 실행합니다.

```bash
# 전국 장소 목록
curl "http://127.0.0.1:8000/api/places?page_size=10"

# 서울 장소만 조회
curl "http://127.0.0.1:8000/api/places?region_code=11"

# 장소명 검색과 최신 혼잡도 결합
curl -G "http://127.0.0.1:8000/api/places" \
  --data-urlencode "keyword=경복궁"

# 혼잡한 장소만 조회
curl "http://127.0.0.1:8000/api/places?crowd_level=busy"

# 경복궁 인근 3km 장소를 거리순으로 조회
curl "http://127.0.0.1:8000/api/places/nearby?latitude=37.576031&longitude=126.976722&radius_km=3"
```

실제 API 데이터로 시연할 때는 `sync_tour_places`,
`sync_tour_place_details`, `sync_seoul_crowd_catalog`,
`apply_seoul_crowd_mappings` 순서로 적재·연결한 뒤 같은 조회 API를 사용합니다.

## 서울 혼잡도 카탈로그 운영

서울시 공식 121개 영역 중 초기 운영 대상 12개와 TourAPI 대표 장소 매핑 13개를
버전 관리합니다.

```text
places/data/seoul_crowd_areas.json
places/data/seoul_place_mappings.json
```

설정 파일에는 영역 코드와 매핑 규칙만 저장합니다. API에서 받은 실제 혼잡
관측값과 로컬 SQLite 파일은 Git에 저장하지 않습니다. 서울시 API는 한 번에 한
장소만 호출하므로 전체 카탈로그를 실행하면 12번 요청합니다.

### 개발 환경

```bash
# 장소 10개, 혼잡 영역 3개, 검증된 매핑 2개 생성
python manage.py seed_dev_data

# 현재 DB에 적용 가능한 카탈로그 매핑을 적용하고 누락 현황 표시
python manage.py apply_seoul_crowd_mappings

# 12개 실제 호출을 시험하지만 DB에는 반영하지 않음
python manage.py sync_seoul_crowd_catalog --dry-run
```

개발 시드는 경복궁과 광장시장만 카탈로그 매핑이 가능합니다. 출력되는 나머지
`missing_places`, `missing_areas`는 개발 DB가 작아서 생기는 정상적인 차이입니다.

### 스테이징·운영 환경

```bash
# 전국 장소가 적재된 뒤 선택한 12개 혼잡도를 저장
python manage.py sync_seoul_crowd_catalog

# TourAPI 외부 ID를 기준으로 장소-혼잡 영역 매핑 적용
python manage.py apply_seoul_crowd_mappings
```

특정 영역만 점검하거나 호출 수를 제한할 수도 있습니다.

```bash
python manage.py sync_seoul_crowd_catalog \
  --area-code POI008 --area-code POI060 --dry-run
python manage.py sync_seoul_crowd_catalog --limit 3 --dry-run
```

일괄 수집은 한 영역이 실패해도 나머지 영역을 계속 처리한 뒤 실패 개수를 오류로
반환합니다. 따라서 운영 스케줄러는 부분 성공 데이터를 보존하면서도 실패 알림을
발생시킬 수 있습니다.
