# 여유로 Django 백엔드

프론트엔드 연동은 [프론트엔드 전달 가이드](./FRONTEND_HANDOFF.md)에서 시작합니다. 현재 배포의 구현 범위, API 요청·응답, 추천 점수 산식, 데이터 결측 처리, Flutter 연동 예제와 Web CORS 제약을 정리했습니다.

전국 최대 10개 추천과 날씨·실내외 수집 기반은 [추천 MVP 계약](./docs/recommendation-mvp.md)에 실행 명령과 API 형식이 있습니다. Pi 배포는 SQLite `/data`와 단일 운영 수집 워커를 사용합니다. [Pi 배포 안내](./docs/pi-deployment.md)에 초기 데이터, Secrets, 예약과 검증 절차를 정리했습니다. 추천 알고리즘은 개발 중인 MVP입니다.

전국 목록 전체 수집과 로컬 운영 검증의 결과·한계는 [2026-09-12 검증 기록](./docs/operation-validation-2026-09-12.md)에 있습니다.
제품 실용성 판단과 다음 개선 순서는 [백엔드 실용성 보고서](../BACKEND_PRACTICALITY_REPORT.md)에 있습니다.
서울·부산·제주 시범군의 상세 수집과 추천 품질 재측정은 [시범군 개선 검증](./docs/pilot-improvement-2026-09-12.md)에 기록했습니다.
테스트 페이지의 기본 추천 상위 장소 설명 보강은 [상위 장소 상세 보강 기록](./docs/top-recommendation-detail-2026-09-12.md)에 있습니다.
서울 혼잡도 재수집과 추천 반영의 지속성 검증은 [혼잡도 재수집 기록](./docs/crowd-refresh-validation-2026-09-12.md)에 있습니다.
서울 공식 혼잡 영역 121곳 수집 범위 확대와 실호출 결과는 [121곳 확대 검증](./docs/seoul-121-collection-2026-09-13.md)에 있습니다.
45분 시험 기준과 일회성 재수집 결과는 [혼잡도 45분 검증](./docs/crowd-45min-trial-2026-09-13.md)에 있습니다.

실시간 혼잡도 기반 장소 추천 앱의 백엔드 기본 틀입니다.
Django 프레임워크를 사용하며, 개발용 데이터베이스로 SQLite를 사용합니다.

## 포함 구성

- Django 6.0.6
- 프로젝트 설정 패키지: `config`
- Django 관리자 페이지
- 개발용 SQLite 데이터베이스
- 상태 확인 API: `GET /healthz`
- 전국 장소·서울 혼잡도 조회 API: `GET /api/places`

## 초기 설치 방법

Python 3.13이 설치된 환경에서 아래 명령을 실행합니다.

```bash
cd tourist_congestion_backend
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## 환경 변수

외부 API 키와 Django 비밀값은 `tourist_congestion_backend/.env`에 저장합니다.
실제 `.env`는 Git에서 제외하며, 변수 이름만 담은 `.env.example`을 공유합니다.

```bash
cd tourist_congestion_backend
cp .env.example .env
```

생성한 `.env`에 발급받은 키를 입력합니다.

```dotenv
TOUR_API_SERVICE_KEY=발급받은_한국관광공사_서비스키
SEOUL_OPEN_API_KEY=발급받은_서울_열린데이터광장_일반키
KMA_SERVICE_KEY=발급받은_기상청_서비스키
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
```

`python-dotenv`가 백엔드 루트의 `.env`를 읽습니다. 서버 환경에 같은 이름의
환경 변수가 이미 설정되어 있으면 서버 환경 변수 값을 우선합니다.

한국관광공사 키는 공공데이터포털이 제공하는 Encoding/Decoding 키 중 어느
형태를 입력해도 클라이언트가 한 번 정규화한 뒤 요청합니다.

> Windows에서는 3번째 줄의 가상환경 진입 명령어가 작동하지 않습니다. 대신 `.venv\Scripts\activate`를 입력합니다.

서버가 실행되면 <http://127.0.0.1:8000/>에서 Django 웹서버를 확인할 수 있습니다.

웹서버 관리자 계정은 `python manage.py createsuperuser`로 생성할 수 있습니다.

## 실행 방법

가상환경에 진입한 뒤 다음을 실행합니다.

```bash
python manage.py migrate
python manage.py runserver
```

서버가 실행되면 <http://127.0.0.1:8000/healthz>에서 API 응답을 확인할 수 있습니다.

현재 SQLite의 추천을 직접 클릭하며 확인하려면
<http://127.0.0.1:8000/test/backend/>를 엽니다. 이 페이지는 **개발 중인 추천 MVP 시안**입니다. 별도 설치 없이 운영 데이터로 시연하려면
<https://ilion.app.hurdoo.kr/test/backend/>를 바로 엽니다. 운영에서도 `DJANGO_DEBUG=false`로 제공됩니다. 일곱 도시/자유 위치 실제 추천, 같은 장소의
가상 맑음·비·강풍, 기본 여행·음식점·쇼핑 선호, 날씨 근거·실내·한산함 필수 조건,
거리순과 개선 모델을 비교할 수 있습니다. 첫 화면에 실제 추천이 바로 나타납니다.
가상 날씨는 실제 예보가 아니며 요청 내 메모리에서만 사용합니다. 테스트베드는
외부 API 호출, 수집 작업 등록, DB 변경을 하지 않습니다. 수집 작업·예산과 개발용 사례 표시는
`DJANGO_DEBUG=true`인 개발 환경에만 나타납니다. 해당 수치도 DB에 기록된 범위이므로 서비스 품질 지표로 해석하지 않습니다.

같은 네트워크의 다른 기기에서 접속하려면 먼저 개발 PC의 로컬 IP를 확인하고,
개인 `.env`의 `DJANGO_ALLOWED_HOSTS`에 해당 IP를 추가합니다.

```dotenv
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,내_로컬_IP
```

그런 다음 모든 네트워크 인터페이스에서 개발 서버를 실행합니다.

```bash
python manage.py runserver 0.0.0.0:8000
```

다른 기기에서는 `http://내_로컬_IP:8000/`으로 접속합니다. `내_로컬_IP`는
실제 주소(예: `192.168.0.10`)로 바꿔 입력합니다.

만약 `ModuleNotFoundError`가 뜬다면 `python -m pip install -r requirements.txt`를 입력한 뒤 서버를 재시작해보세요.

## 샘플 API

서버 상태는 `GET /healthz`로 확인합니다.

```json
{
  "status": "ok"
}
```

장소 목록·검색과 상세 조회는 다음 경로를 사용합니다.

```text
GET /api/places
GET /api/places/{place_id}
```

검색·필터 파라미터, 응답 필드와 로컬 시연 순서는 [API.md](./API.md)를
확인합니다.

## 공공데이터 동기화

### 팀 공용 개발 데이터

전체 공공데이터를 팀원마다 다시 호출하지 않습니다. 로컬에서는 API 키 없이
전국 8개 지역의 장소 10개, 서울 혼잡 영역 3개와 장소-영역 매핑 2개를 동일하게
생성합니다.

```bash
python manage.py migrate
python manage.py seed_dev_data
```

`seed_dev_data`는 여러 번 실행해도 중복을 만들지 않으며 `DEBUG=true`에서만
동작합니다. 개발 데이터를 초기화하려면 다음을 실행합니다.

```bash
python manage.py seed_dev_data --clear
```

샘플은 실제 TourAPI 식별자를 사용합니다. 이후 같은 장소를 실제 API로
동기화하면 별도 장소를 만들지 않고 샘플 `PlaceSource`를 최신 원본으로
교체합니다. 이미 실제 API로 갱신된 장소는 개발 데이터 명령이 덮어쓰지 않습니다.

### 실제 외부 API 동기화

명령을 처음 시험할 때는 DB에 반영하지 않는 `--dry-run`과 작은 범위 제한을
함께 사용합니다.

```bash
# TourAPI 한 페이지만 시험
python manage.py sync_tour_places --max-pages 1 --page-size 20 --dry-run

# 전국 장소 수집
python manage.py sync_tour_places --page-size 100

# 특정 법정동 시도 코드만 수집
python manage.py sync_tour_places --region-code 11 --max-pages 5

# 변경분 수집(YYYYMMDD)
python manage.py sync_tour_places --modified-since 20260801 --max-pages 5

# 선택한 서울 지역 혼잡도 수집: AREA_CD 또는 장소명 사용
python manage.py sync_seoul_crowd POI009 "광화문·덕수궁" --dry-run
python manage.py sync_seoul_crowd POI009 POI002
```

TourAPI 필수 값이 빠진 레코드는 버리지 않고 `PlaceSource`에
`manual_review` 상태로 저장합니다. 서울 혼잡도는 개별 장소가 아니라 영역
단위이므로, 수집 후 내부 장소와 명시적으로 연결합니다.

```bash
python manage.py map_place_crowd_area PLACE_ID AREA_CD
```

Pi 운영에서는 `run_data_worker --scheduled`가 컨테이너와 함께 시작됩니다.
위 직접 수집 명령을 cron에 추가하지 않습니다. 운영 수집은 공통 작업 큐로 일원화하며
예약·한도·최초 등록 순서는 [Pi 배포 안내](./docs/pi-deployment.md)를 따릅니다.

서울 열린데이터광장 실시간 API는 공식적으로 `openapi.seoul.go.kr:8088`의
HTTP 엔드포인트를 제공합니다. 키가 URL에 포함되므로 애플리케이션은 요청 URL과
외부 라이브러리 예외를 로그에 출력하지 않습니다.
