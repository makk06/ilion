# ILION Pi 배포와 운영 수집

이 배포는 **개발 중인 추천 알고리즘 MVP**다. 추천 품질 완성이나 운영 부하 검증을 의미하지 않는다.

## Git과 이미지

- 원본 `origin`: `https://github.com/makk06/ilion.git` 유지.
- 배포용 `deploy`: `https://github.com/hurdoo/ilion.git`.
- 배포 소스는 `feature/be-recommendation-core`의 검증된 커밋이다. 원본/포크의 main을 자동으로 병합하지 않는다.
- 이미지 저장소: `ghcr.io/hurdoo/ilion`, ARM64, 커밋 태그와 immutable digest 사용.
- 앱 ID: `ilion`, URL: `https://ilion.app.hurdoo.kr`, 접근 범위는 사용자 설정에 맞춘 `public`.
- 소스의 `deploy.json`은 빌드 계약이다. 대시보드에 붙여넣는 것은 `deployctl publish`가 출력한 **release/digest 포함 JSON**이다.

GHCR 패키지가 없으면 `.github/workflows/bootstrap-ilion-image.yml`을 먼저 기본 브랜치에 반영하고 사용자가 검토한 전체 커밋 SHA로 수동 실행한다. 이 워크플로는 해당 커밋의 테스트를 통과한 후 저장소에 연결된 패키지를 만든다. 원본 main에 있는 다른 앱 코드나 테스트를 대신 배포하지 않는다. 최초 패키지 생성은 별도 승인 후 실행한다. 패키지 공개 범위와 Pi pull 권한도 확인해야 한다.

그 후 프로젝트가 깨끗한 커밋 상태에서 Mac의 `deployctl plan/publish feature-be-recommendation-core`를 사용한다. GHCR 발행에는 deploy-project의 `with-ghcr-auth` wrapper를 사용한다. 대시보드 등록·배포 버튼은 사용자가 직접 누른다.

## 첫 시작과 Secrets

필수 secret은 `DJANGO_SECRET_KEY`다. 50자 이상의 무작위 운영용 값을 대시보드 Secrets에 등록한다. 개발 기본값은 실행이 거부된다. 값은 Git, Docker build, 명령 인수, handoff JSON에 넣지 않는다.

다음 값은 선택 secret이지만 **실제 자동 수집에는 모두 필요**하다:

- `TOUR_API_SERVICE_KEY`: 전국 목록 및 상세
- `SEOUL_OPEN_API_KEY`: 서울 혼잡도
- `KMA_SERVICE_KEY`: 기상청 단기예보

없는 키의 정기 작업은 예약하지 않는다. 추천 요청에서 생긴 해당 공급자의 보충 작업은 설정 오류로 기록될 수 있다. 키를 추가해도 실행 중 컨테이너에는 즉시 반영되지 않으므로 등록 후 배포를 다시 실행한다. Google 로그인에는 공개 설정 `GOOGLE_CLIENT_ID`도 별도로 채운다.

신규 앱은 등록 전 Secrets 대상이 없다. 첫 JSON을 제출하면 앱 등록 후 필수 secret 누락으로 첫 릴리스가 멈출 수 있다. 앱 Secrets에 위 네 값을 등록하고 같은 이미지로 배포를 재시도한다. 이는 예상된 초기 등록 순서이며 이미지 재발행은 필요 없다.

## 데이터 초기화

현재 deployd JSON에는 DB 업로드/복원 기능이 없어, 사용자 선택에 따라 **빈 운영 DB에서 재구축**한다. 로컬 테스트 DB는 변경하지 않으며 이미지에 포함하지 않는다. 기존 수동/AI 분류 검토 결과는 자동으로 이전되지 않는다. 새로 받은 목록·상세에는 현재 코드의 이름·설명 분류가 적용된다. AI 분류 호출은 자동 실행하지 않는다.

`STORAGE_DIR=/data` 아래 SQLite, WAL, 잠금 파일, 워커 heartbeat를 저장한다. DB가 아예 없을 때만 staging DB에 현재 스키마를 만든 뒤 설치한다. 기존 DB에서는 미적용 migration 검사를 하고 변경이 필요하면 시작을 거부한다. 향후 schema migration은 백업과 별도 승인이 필요하다. 이미지 롤백은 SQLite를 되돌리지 않는다.

기존 테스트 SQLite를 이전하려면 별도의 운영 DB 복원 절차를 마련해야 한다. 실행 중 파일을 단순 복사하지 말고 SQLite backup으로 일관된 복사본을 만든다. 현재 배포에는 사용자·세션·테스트 시드를 옮기는 절차가 포함되지 않는다.

## 예약과 호출 예산

웹 서버(Gunicorn 1 worker/4 threads)와 수집 워커 한 개를 컨테이너가 함께 시작한다. 별도 host cron, Redis, Celery는 필요 없다. 워커는 1분마다 예약 여부를 점검하고 작업 사이에 1초 간격을 둔다. 한국시간을 기준으로 하고 같은 예약은 DB 키로 중복 방지한다.

HTTPS 전달 헤더, 보안 쿠키와 정확한 앱 호스트의 HSTS를 사용한다. 임의 하위 도메인과 브라우저 preload 등록은 배포 계약 범위가 아니므로 Django 검사 W005/W021만 명시적으로 제외한다. 다른 운영 보안 경고는 검증 실패로 처리한다.

| 작업 | 실행 시점/범위 |
|---|---|
| 최초 전국 목록 | 키가 있으면 즉시, 페이지 크기 1,000, 최대 100페이지 |
| 목록 변경분 | 매일 03시 이후, 마지막 성공 작업의 시작일 전날부터 겹쳐 조회 |
| 전체 대조 | 일요일 04시 이후, 미완료 목록과 겹치지 않게 실행 |
| 장소 상세 | 목록 초기화 성공 후 매일 04:30 이후, 누락/7일 지난 자료 최대 150건/일 |
| 서울 혼잡도 | 공식 121개 영역, 매시 00·15·30·45분 창, 정상 시 11,616회/일 |
| 기상청 | 이용 가능한 발표본별, 7개 공개 도시 중심 격자 + 최근 요청 격자, 정기 최대 35격자 |
| 장소-혼잡 영역 매핑 | 현재 버전 관리된 13개 관계를 DB에서 재적용, 외부 호출 없음 |

상세 수집은 현재 로컬의 407건을 그대로 복제하는 것이 아니다. 누락 장소부터 순서대로 보강하므로 초기 추천 결과와 근거 보유량은 로컬과 다를 수 있다. 한도와 대상은 대시보드의 visible environment에서 조절한다.

앱의 기본 일일 총 상한은 TourAPI 1,000, 서울 18,000, 기상청 10,000이다. 서울 값은 앱이 정한 상한이며 공급자가 보장한 승인 한도가 아니다. 실제 계정 승인량이 작으면 배포 전에 낮춘다. 70% 정기, 20% 보충, 10% 예비로 나누므로 정기 TourAPI는 700회다. 상세 150곳은 최대 300회, 목록 100페이지는 최대 100회이며 재시도도 예산에서 차감한다. 기상청은 **격자 수가 아니라 응답 페이지별**로 차감한다.

한도 소진 시 다음 한국 날짜까지 미룬다. 목록은 페이지 cursor를 유지하며 끝까지 받지 못하고 페이지 제한에 걸리면 `PageLimitExceeded`로 실패 처리한다. 다음 예약은 마지막 성공 기준을 유지한다. 15분 지난 미실행 혼잡 작업과 5시간 지난 예보 작업은 `ExpiredWindow`로 끝내 오래된 큐가 다음 날 예산을 소모하지 않게 한다. 인증 오류는 실패로 기록하며 같은 작업을 무한 재시도하지 않는다.

**같은 키의 실수집은 Pi로 일원화한다.** 개발 머신에서 `run_data_worker --dev`, 실제 키로 직접 `sync_tour_*`/`sync_seoul_*` 명령을 함께 실행하지 않는다. 기존 직접 수집 명령은 공통 큐 예산을 거치지 않는다. 테스트는 `PYTHON_DOTENV_DISABLED=1`, 모의 응답/개발 시드를 쓴다. 외부 포털에서 같은 키를 수동 호출한 사용량은 앱 카운터에 자동 합산되지 않는다.

## 공개 추천 시안

`https://ilion.app.hurdoo.kr/test/backend/`는 공개 시안 릴리스부터 운영 `DEBUG=false`에서도 열린다. 기본 추천과 가상 날씨·선호·필수 조건·거리순 비교를 제공한다. 저장된 자료만 읽으며 외부 API 호출이나 보충 작업 등록을 하지 않는다. 가상 날씨는 요청 메모리 안에서만 사용한다. POST는 기존 CSRF 검증을 유지하고 응답은 캐시하지 않는다. 수집 작업·호출 예산·개발용 고정 사례는 DEBUG 환경에만 표시한다. 화면을 열기 위해 운영 DEBUG를 켜지 않는다.

## 상태와 복구

`/healthz`는 운영 DB와 180초 이내 워커 heartbeat를 확인한다. 외부 공급자 장애 자체로 웹을 내리지는 않는다. 정상 health가 최신 관광 데이터 확보를 뜻하지 않으며 `DataJob`의 status/error_code/finished_at, `ProviderCallBudget` 및 응답의 자료 시각을 함께 확인한다. 워커가 종료되거나 heartbeat가 멎으면 supervisor도 웹과 함께 종료해 컨테이너 재시작 정책이 작동하게 한다. SIGTERM에서는 두 프로세스가 종료되도록 기다린다. 중단된 작업은 5분 lease 만료 후 재개한다.

관측/예보/작업 이력의 자동 삭제는 활성화하지 않았다. 저장량과 백업 정책은 실제 운영 자료량에 맞춰 후속으로 확정해야 한다. 대시보드 이미지 롤백은 데이터 복원이나 외부 API 호출 취소가 아니다.

## 로컬 검증

```sh
sh scripts/check-backend.sh
docker build --platform linux/arm64 -t ilion-backend-smoke .
python3 scripts/smoke-backend.py
```

검증은 외부 네트워크가 없는 컨테이너, 가짜 키, 임시 SQLite만 사용한다. smoke는 UID/GID 0:0, cap-drop ALL, no-new-privileges, read-only root, /tmp tmpfs, /data bind, 1GiB 메모리와 128 PID 제한으로 실행한다. 최초 스키마, 단일 워커 잠금, 추천 API, 워커 강제 종료에 따른 전체 종료, 컨테이너 재생성 후 데이터 보존 및 정상 종료를 확인한다. `/private/tmp/ilion-runtime-smoke-*`는 사용자 지침에 따라 보존한다.
