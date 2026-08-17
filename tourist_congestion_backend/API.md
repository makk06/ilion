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

## 장소 상세

```http
GET /api/places/{place_id}
```

목록의 장소 필드와 최신 혼잡도에 더해 `open_status`, `created_at`,
`updated_at`을 반환합니다. 조회 가능한 장소가 없으면 HTTP 404와 아래 응답을
반환합니다.

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
```

실제 API 데이터로 시연할 때는 `sync_tour_places`, `sync_seoul_crowd`,
`map_place_crowd_area` 순서로 적재·연결한 뒤 같은 조회 API를 사용합니다.
