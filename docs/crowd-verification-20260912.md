# 혼잡도 구현 검증 기록 — 2026-09-12

브랜치: `codex/nationwide-crowd-estimation`. 기존 작업 중인 사용자 변경을 보존하여 확장했다. 배포·원격 push·스케줄러 설치는 수행하지 않았다.

## 완료한 검증

| 검증 | 실제 결과 |
|---|---|
| Django 전체 테스트 | **106 통과** |
| 최종 매핑 우선순위 변경 후 API·수집 회귀 테스트 | **14 통과** |
| Django 시스템 검사 | 오류 없음 |
| 마이그레이션 누락 검사 | No changes detected |
| Flutter analyze | No issues found |
| Flutter 전체 테스트 | **83 통과** |
| Flutter web build | 성공 |
| Flutter Android debug APK | 성공, 기존 Android SDK XML 버전 경고 있음 |
| UI strict audit | 오류·위반 0 |
| 공식 DESIGN.md lint | 오류 0, Flutter 런타임 토큰의 컴포넌트 참조 경고 9 |
| 10만 POI·121개 영역, 30회 warm 조회 | 상세 p95 54.11ms / 일반 목록 p95 368.35ms |
| 서울 공개 sample XML 실제 호출 | POI009 인구 및 지하철·버스 하차 파싱 성공; 두 교통 시각은 collection_only |
| 실제 계정 소량 인증 검사 | 네 공급자 모두 키/승인 쿼터 미설정으로 blocked, 대량 요청 없음 |

성능 수치는 Django test client, 단일 로컬 프로세스 및 폐기 가능한 SQLite DB 기준이다. 동시 수집 쓰기·네트워크·전국 estimate_level 전체 스캔의 p95 보장은 아니다. 재현 명령은 `scripts/benchmark_crowd.py`에 있다.

## DB와 공간 자료

- 기존 로컬 DB를 SQLite backup API로 `.integration-artifacts/before-crowd-20260912-211157.sqlite3`에 백업했다.
- additive migration `places.0004`~`0006`을 적용했다. 기존 장소 10개는 유지하고 공식 영역 121개를 적재·해석했다.
- 원본 GeoJSON을 보존한다. 공식 POI070의 자기 교차는 가져오기에서 `make_valid`로 보정하고 표식으로 기록한다.
- 실제 운영 관측이 없는 상태에서 관측이나 방문객 수를 만들지 않았다. 기존 개발 샘플은 그대로 샘플로 표시하며 학습에서 제외한다.

## 실제 브라우저 확인

설치된 Edge headless, Flutter web, 390×844 화면으로 시작 화면 → 홈 지도 → 목록 → 상세를 탐색했다. JavaScript page error는 없었다.

- 공통 카드와 지도에서 예상 단계·낮은 신뢰도 표시 확인.
- 개발 샘플·오래된 정보, 지도 키 부재 시 배경 재시도 상태 확인.
- 상세 스크롤에서 영역 proxy 설명·근거 품질·현재 점수·출처·1/2/3시간 예측 확인.
- 혼잡 필터의 실제 열린 화면에서 매우 여유/여유/보통/혼잡/매우 혼잡 확인. 방향키·Escape·Tab 입력도 수행.
- 320px 카드의 긴 저신뢰·샘플·stale 라벨은 Flutter widget test에서 overflow 없이 확인.
- 기존 로딩·오류·검색 없음·키보드·저장·탭 이동은 전체 Flutter 회귀 테스트로 확인.

로컬 스크린샷: `.integration-artifacts/crowd-browser-home-final.png`, `crowd-browser-detail.png`, `crowd-browser-filter-open.png`.

## 활성화 전 남은 조건

1. `.env`의 공급자 키와 실제 승인 일일 한도를 설정하고 `verify_crowd_providers`의 성공을 확인한다. 서울 sample 성공은 정식 계정의 121개 권한 검증이 아니다.
2. `ops/`의 OS 스케줄 템플릿 경로를 배포 환경에 맞춰 등록한다. 웹 서버 내부 스케줄러는 없다.
3. 실제 수집 주기 완주·SQLite 동시 쓰기 부하를 확인한다. 무료 한도 부족 시 전체 서울 범위를 유지하면서 주기를 늘린다.
4. 최소 28일 관측과 충분한 동일 요일 표본이 쌓이기 전에는 경험적 percentile 정확도를 주장하지 않는다. 실제 현장·POI 내부 정확도는 별도 평가한다.
5. iOS 빌드·기기 시험은 macOS/Xcode 환경에서 수행한다.

실행·알고리즘·API·롤백: [운영 안내](crowd-estimation.md).
