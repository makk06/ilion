# 여유로 Django 백엔드

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
전국 8개 지역의 장소 10개, 서울 혼잡 영역 2개와 장소-영역 매핑 1개를 동일하게
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

실제 운영 주기 실행은 아직 포함하지 않습니다. 호출 한도와 최초 대상 지역을
확정한 뒤 cron 또는 별도 스케줄러가 위 명령을 호출하도록 구성합니다.

서울 열린데이터광장 실시간 API는 공식적으로 `openapi.seoul.go.kr:8088`의
HTTP 엔드포인트를 제공합니다. 키가 URL에 포함되므로 애플리케이션은 요청 URL과
외부 라이브러리 예외를 로그에 출력하지 않습니다.
