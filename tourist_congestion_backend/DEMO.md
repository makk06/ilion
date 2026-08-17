# ILION 백엔드 미팅 데모

`/demo/`는 장소·혼잡도 백엔드의 현재 가능성을 팀 미팅에서 빠르게 확인하기 위한
Django 테스트 화면입니다. 별도 목 데이터를 쓰지 않고 아래 읽기 API를 같은
출처의 DB에서 호출합니다.

- `GET /api/places`: 전국 장소 목록, 검색, 필터
- `GET /api/places/nearby`: 좌표 기준 주변 장소와 거리
- `GET /api/places/{id}`: 장소 상세정보와 최신 혼잡도

운영용 프런트엔드는 Flutter이며, 이 화면은 사용자·인증·추천 화면을 대신하지
않습니다. 백엔드 API와 공공데이터 구조를 설명하는 시연 도구로만 유지합니다.

## 1. 시연 데이터 준비

`.env`의 API 키가 없어도 결정적인 개발 시드만으로 시연할 수 있습니다.

```bash
cd tourist_congestion_backend
source .venv/bin/activate
python manage.py migrate
python manage.py seed_dev_data
python manage.py runserver
```

브라우저에서 <http://127.0.0.1:8000/demo/>를 엽니다. 개발 시드는 전국 10개
장소, 서울 혼잡 영역 3개, 혼잡도가 연결된 장소 2개를 만듭니다. 기존에 실제
TourAPI 상세정보를 받은 장소가 있으면 시드는 그 데이터를 덮어쓰지 않습니다.

실제 키가 준비된 환경에서는 선택한 장소의 상세정보와 서울 혼잡도를 미리
갱신할 수 있습니다. 외부 API 상태와 호출 한도를 고려해 필요한 범위만
실행합니다.

```bash
# 현재 DB의 장소 최대 10개를 TourAPI 상세정보로 보강
python manage.py sync_tour_place_details --limit 10

# 초기 카탈로그 중 최대 3개 서울 영역만 호출·저장
python manage.py sync_seoul_crowd_catalog --limit 3

# 외부 ID 기준으로 장소와 혼잡 영역 연결
python manage.py apply_seoul_crowd_mappings
```

## 2. 미팅 시연 순서

1. 첫 화면의 `검색된 장소`, `혼잡도 제공`, `포함 지역` 숫자를 보여줍니다.
2. 검색창에 `경복궁`을 입력해 전국 장소 API의 검색 결과를 보여줍니다.
3. 경복궁 카드를 열어 TourAPI 소개·운영정보와 서울 최신 혼잡도가 하나의
   상세 응답으로 결합된 모습을 보여줍니다.
4. `경복궁 주변 3km`를 눌러 장소가 거리순으로 반환되는 것을 보여줍니다.
5. `혼잡도 제공`을 눌러 현재 혼잡 영역에 연결된 장소만 비교합니다.
6. 마지막의 데이터 흐름에서 `공공데이터 수집 → 내부 구조화 → 앱 API 제공`을
   설명합니다.

현재 개발 시드 기준 예상값은 전체 10곳, 혼잡도 제공 2곳, 경복궁 주변 2곳입니다.
실제 데이터 동기화 후에는 숫자가 달라지는 것이 정상입니다.

## 3. 시연 전 점검

```bash
python manage.py check
python manage.py test
```

- API 상태가 `API 연결됨`인지 확인합니다.
- 경복궁과 광장시장 카드에 혼잡도 배지가 표시되는지 확인합니다.
- 상세 모달에서 이미지, 소개, 혼잡 인구 범위가 표시되는지 확인합니다.
- `.env`, `db.sqlite3`, 실제 API 응답 덤프는 화면 공유나 Git에 포함하지 않습니다.
