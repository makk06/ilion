# 여유로 Django 백엔드

실시간 혼잡도 기반 장소 추천 앱의 백엔드 기본 틀입니다.
Django 프레임워크를 사용하며, 개발용 데이터베이스로 SQLite를 사용합니다.

## 포함 구성

- Django 6.0.6
- 프로젝트 설정 패키지: `config`
- Django 관리자 페이지
- 개발용 SQLite 데이터베이스

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

> Windows에서는 3번째 줄의 가상환경 진입 명령어가 작동하지 않습니다. 대신 `.venv\Scripts\activate`를 입력합니다.

서버가 실행되면 <http://127.0.0.1:8000/>에서 Django 웹서버를 확인할 수 있습니다.

웹서버 관리자 계정은 `python manage.py createsuperuser`로 생성할 수 있습니다.

## 실행 방법

가상환경에 진입한 뒤 다음을 실행합니다.

```bash
python manage.py migrate
python manage.py runserver
```

서버가 실행되면 <http://127.0.0.1:8000/>에서 Django 관리자 페이지를 확인할 수 있습니다.

만약 `ModuleNotFoundError`가 뜬다면 `python -m pip install -r requirements.txt`를 입력한 뒤 서버를 재시작해보세요.
