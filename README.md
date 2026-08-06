# ILION

한국관광공사 API를 활용하는 **실시간 혼잡도 기반 장소 추천 앱**입니다.

- 프런트엔드: Flutter
- 백엔드: Django
- GitHub: <https://github.com/makk06/ilion>
- 상세 협업 규칙: [DEVELOPMENT_GUIDE.md](./DEVELOPMENT_GUIDE.md)

## 프로젝트 구조

```text
2026_tourist_congestion_app/
├─ tourist_congestion_frontend/   # Flutter 앱
├─ tourist_congestion_backend/    # 백엔드 서버
├─ README.md                      # 프로젝트 첫 안내
└─ DEVELOPMENT_GUIDE.md           # 개발·Git 협업 규칙
```

## 새 팀원이 처음 시작할 때

기존 저장소를 새로 `clone`하여 시작합니다. 각자 만든 빈 폴더에서 `git init`을 다시 실행하지 않습니다.

```bash
cd D:\dev_project
git clone https://github.com/makk06/ilion.git
cd ilion
```

VS Code에서는 방금 생성된 `ilion` 폴더 전체를 엽니다.

## 프런트엔드 실행

```bash
cd tourist_congestion_frontend
flutter pub get
flutter run -d chrome
```

Windows에서는 iOS 앱을 실행할 수 없습니다. 우선 Chrome 또는 Android 기기로 확인합니다.

## 백엔드 실행

> 먼저 백엔드 폴더의 README.md를 따라 초기 설치 후 실행해야 합니다.

```bash
cd tourist_congestion_backend

# 가상환경 진입 (Mac/Linux)
source .venv/bin/activate

# 가상환경 진입 (Windows)
.venv\Scripts\activate

# 서버 실행
python manage.py migrate
python manage.py runserver
```

## 작업 시작 순서

`main`에서 직접 개발하지 않고, 최신 `main`에서 기능별 브랜치를 만듭니다.

```bash
git switch main
git pull origin main
git switch -c feature/home-ui
```

브랜치 이름의 예시는 다음과 같습니다.

- 새 기능: `feature/기능명`
- 오류 수정: `fix/오류명`
- 디자인 수정: `design/화면명`
- 문서 수정: `docs/문서명`

## 작업 내용을 올릴 때

```bash
git add .
git commit -m "feat: 홈 화면 기본 UI 구현"
git push -u origin feature/home-ui
```

처음 올린 뒤에는 GitHub에서 Pull Request를 만들고, 다른 팀원의 확인을 받은 후 `main`에 병합합니다. 같은 브랜치의 두 번째 `push`부터는 `git push`만 사용해도 됩니다.

## 병합 후 다음 작업을 시작할 때

```bash
git switch main
git pull origin main
git branch -d feature/home-ui
```

그다음 최신 `main`에서 새로운 작업 브랜치를 만듭니다.

## 자주 보는 Git 메시지

### `warning: LF will be replaced by CRLF`

Windows 줄바꿈 방식에 관한 안내로, 오류가 아닙니다.

### `rejected (fetch first)`

다른 사람이 먼저 변경 사항을 올려 내 브랜치가 이전 상태일 때 나타납니다.

```bash
git pull
git push
```

`CONFLICT`가 나오면 강제로 올리지 말고 충돌 파일을 팀원과 함께 확인합니다. 팀 저장소에서는 기존 기록이나 파일을 지울 수 있는 `git push --force`를 사용하지 않습니다.

### `refusing to merge unrelated histories`

서로 별도로 만든 두 Git 저장소를 처음 합칠 때 나타나는 메시지입니다. 프로젝트 최초 연결 과정에서 이미 한 번 합쳤다면 다시 발생하지 않습니다. 새 팀원이 GitHub에서 정상적으로 `clone`하면 이 옵션을 사용할 필요가 없습니다.

## 반드시 지킬 규칙

1. `main`에서 직접 개발하거나 `push`하지 않습니다.
2. 작업 전 최신 `main`을 받고 새 브랜치를 만듭니다.
3. 기능 하나당 브랜치 하나를 사용합니다.
4. 작업 완료 후 Pull Request로 검토하고 병합합니다.
5. API 키, 비밀번호, `.env` 파일은 GitHub에 올리지 않습니다.

브랜치·커밋·PR·프런트엔드·백엔드의 전체 규칙은 [개발 가이드](./DEVELOPMENT_GUIDE.md)에서 확인합니다.
