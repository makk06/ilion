# 전국 추천 MVP 계약 (최신 점수 정책 mvp-7)

2026-09-14 `mvp-7`은 기존 실내외 호환 라벨과 별도인 `place.weather_exposure`를 도입했다. 현재 노출 정책, 약한 공식 유형 추정, 엄격 필터 제한, 고정 표본 결과는 [날씨 노출 구현·평가](./weather-exposure-mvp7-2026-09-14.md)를 우선한다. 아래 `mvp-6` 설명은 이전 구현의 근거로 보존한다. 특히 아래의 “실내외 분류로 날씨를 판단” 표현은 현재에는 충분하지 않다. `weather_evidence_required`는 예보와 장소별 유효 근거가 필요하며 유형 추정만으로는 통과하지 않는다. 점수식 자체는 기존과 같지만 날씨 항목의 장소별 근거계수에 유형 추정 `0.35`가 추가됐다.

`mvp-6`는 점수 산식을 유지하면서 실내외 자동 분류에 장소명·설명 문맥의
주된 방문 활동을 추가한 버전이다. 예전 `mvp-5` 점수 설명은 아래와 같이 유지된다.

2026-09-14 실내외 분류와 필수 조건은 [최신 문맥 분류 운영·평가 계약](./place-classification-context-evaluation-2026-09-14.md)을 우선한다. 아래 과거의 `출처 있는 분류` 표현보다 좁게, `required_indoor_outdoor`는 수동 또는 명확한 설명 규칙만 허용한다. 이름·AI 추정은 날씨/실내외 선호의 낮은 비중 근거로만 사용한다.

응답의 `place.indoor_outdoor_source`, `place.indoor_outdoor_evidence_quality`, `place.indoor_outdoor_evidence`를 함께 읽는다. 품질 값은 `manual_label`, `inferred_from_description`, `inferred_from_name`, `inferred_from_luna`, `stale_auto_evidence`, `unattributed`, `unknown` 중 하나다. `stale_auto_evidence`는 기존 라벨 문자열이 남아 있어도 현재 입력과 근거가 맞지 않아 날씨 점수·엄격 필터에 쓰지 않는 상태다. `ranking_policy`에는 세 자동 분류의 영향 계수도 포함된다.

실제 전국 목록 수집, 로컬 HTTP·워커·백업 검증과 실용성 한계는 [2026-09-12 운영 검증](./operation-validation-2026-09-12.md)에 기록했다.

`POST /api/recommendations`는 비회원에게도 열려 있다. JSON 본문은 `latitude`, `longitude`를 필수로 받는다. `radius_km` 기본 10(0.1~100), `limit` 기본 10(1~10)이다. `category`는 선호 점수이며 없으면 로그인 사용자의 `preferred_categories`를 쓴다. 둘 다 없으면 기본 여행 탐색 카테고리 점수를 쓴다. `required_categories`는 엄격한 카테고리 필터다. 여러 필수 카테고리를 지정하고 명시 선호가 없다면 필터 안에서도 기본 여행 점수로 순서를 정한다. `indoor_outdoor`는 선호 점수, `required_indoor_outdoor`는 출처 있는 실내외 분류의 엄격한 필터이며 각각 `indoor`, `outdoor`, `mixed` 중 하나다. `crowd_level`은 `relaxed`, `normal`, `busy`, `crowded`, `any`(기본)이고 `quiet_required=true`는 유효한 현재 관측이 `relaxed`인 곳만 남긴다. `visit_at`은 ISO 8601 오프셋 포함 시각이며 없으면 서버 현재 시각이다.

`weather_aware` 기본값은 `true`이며 사용 가능한 날씨·실내외 근거가 있으면 순위에 반영한다. `weather_aware=false`는 날씨 점수를 끈다. `weather_evidence_required=true`는 별도 필터다. 방문 시각에 쓸 수 있는 예보와 출처 있는 실내외 분류로 날씨 점수를 산출할 수 있는 후보만 남긴다. 두 옵션은 독립적이므로 `weather_aware=false, weather_evidence_required=true`는 날씨 근거로 후보를 거르되 순위에는 날씨를 쓰지 않는다. 둘 다 `false`일 때만 날씨 보충 수집을 요청하지 않으며, 필터가 `true`면 근거 확보를 위해 보충 작업을 요청할 수 있다. 후보가 부족하면 실제 개수를 반환한다. `ranking_basis`, `ranking_factors`, `weather_aware`, `weather_evidence_required`, `preference_source`를 함께 확인해야 실제 순위 정책을 알 수 있다.

추천 대상 카테고리는 `관광지`, `문화시설`, `축제/공연/행사`, `레포츠`, `쇼핑`, `음식점`이다. 숙박과 여행코스는 포함하지 않는다.

```http
POST /api/recommendations
Content-Type: application/json

{"latitude":35.16,"longitude":129.16,"radius_km":10,"category":"관광지","indoor_outdoor":"outdoor","visit_at":"2026-09-12T14:00:00+09:00","limit":10}
```

응답은 기존 `{success,data,message}` 형식이다. `data.items`는 실제 후보만 포함하고 `rank`, `place`, `distance_km`, `distance_type=straight_line`, `travel_time_minutes=null`, `recommendation_score`, `score_breakdown`, `score_effective_breakdown`, `distance_adjustment`, `score_contributors`, `data_coverage`, `ranking_coverage`, `missing_data`, `reasons`, `crowd`, `weather`, `weather_status`를 반환한다. `data.generated_at`, `visit_at`, `algorithm_version`, `candidate_count`, `ranking_basis`, `ranking_factors`, `preference_source`, `ranking_policy`도 포함한다. `score_breakdown`은 원점수이고 결측은 `null`이다. `score_effective_breakdown`은 이름 추론·지연 관측의 영향 축소 후 점수다. `score_contributors`는 실제 근거가 있고 활성화된 항목이다. `data_coverage`는 다섯 가능 항목 전체 가중치 중 근거 보유분, `ranking_coverage`는 이 요청에서 활성화된 항목의 근거 보유분이다. 둘 다 통계적 정확도가 아니다. 결과가 부족하면 빈 배열이나 실제 개수를 200으로 반환하며 반경·필수 필터는 늘리지 않는다. 잘못된 입력은 400이다.

행사·공연은 TourAPI 상세의 `eventstartdate`와 `eventenddate`가 모두 유효하고 한국 날짜 기준 방문일을 포함할 때만 추천한다. 목록에 날짜가 없거나 상세가 아직 없는 행사는 추천하지 않는다. 종료된 행사를 현재 열리는 장소처럼 반환하지 않기 위한 제한이다.

현재 직선거리만 사용한다. TMAP 이동시간은 승인 후 별도 경로 서비스로 넣는다. 서울 혼잡도는 매핑된 영역의 마지막 관측이 45분 이하이며 방문 시각이 현재와 5분 이내일 때만 사용한다. 15분 초과 관측은 `is_stale=true`, 30분 초과 관측은 `is_delayed=true`다. 30~45분 지연 관측의 점수 효과는 절반으로 줄이고, `quiet_required=true`의 한산함 근거로 쓰지 않는다. 45분 초과나 미래 방문에는 현재 관측을 쓰지 않는다. 기본 `crowd_level=any`에서는 여유·보통 관측에 보너스를 주지 않고 혼잡·매우 혼잡만 약하게 감점한다. 명시적 혼잡 선호에서는 요청 적합도만 적용해 기본 위험 감점을 중복하지 않는다.

날씨는 장소 좌표의 기상청 격자, 방문 시간의 예보 대상 시각, 요청 시점까지 발표된 최신 발표본으로 고른다. 발표 시각이 요청 시점보다 **5시간 넘게 오래되면 제외**하고 갱신 작업을 요청한다. 3시간 발표 간격에서 한 회 누락을 허용하는 개발 기본값이며 공급자 지연 실측 기준은 아니다. 미래 방문 시각이 멀어도 발표 나이는 현재 요청 시각으로 판단한다. `fetched_at`을 다시 기록해 유효기간을 늘리지 않는다. 강수형태·기온·풍속이 모두 있을 때만 좋은 야외 날씨로 판단한다. 일부 값만 있으면 확인된 비·눈·강풍·극단기온만 반영하고, 문제 없는 일부 값으로 야외 적합성을 주장하지 않는다. 분류 출처가 `manual`이면 수동 라벨, `reviewed_name_rule_*`이면 장소명 규칙 추론이다. 후자는 날씨·실내외 점수의 중립 대비 효과를 절반으로 줄인다. 출처가 비어 있거나 알 수 없는 라벨은 날씨 점수와 필수 실내외 조건에 쓰지 않는다. 수동 라벨도 현장 독립 검증 정확도를 뜻하지 않는다.

가중치는 거리 .30, 카테고리 .15, 혼잡 .20, 날씨 .25, 실내외 선호 .10이며 `config/settings.py`에서 변경할 수 있다. 기본 여행 점수는 관광지·문화시설 90, 레포츠·유효한 행사 85, 음식점 60, 쇼핑 45다. 이 값은 사용자 취향의 측정치가 아니라 여행 탐색의 약한 초기 정책이다. 명시 카테고리 또는 프로필 선호는 100/0 적합도로 이를 대체한다. 카테고리 자체가 잘못 분류된 장소는 이 정책으로 교정되지 않는다.

`mvp-5`는 후보 전체에 같은 활성 항목과 분모를 사용한다. 거리·카테고리는 항상 활성화한다. 날씨는 `weather_aware=true`이고 점수 근거가 하나라도 있을 때, 혼잡은 명시 선호의 관측이나 기본 모드의 혼잡 위험 관측이 있을 때, 실내외 선호는 유효한 분류가 있을 때 활성화한다. 결측 후보의 해당 항목은 원점수 `null`, `score_contributors` 미포함으로 유지하고, **순위 계산에만 중립 기준 50**을 적용한다. 이는 관측치나 실제 한산함·좋은 날씨를 뜻하지 않는다. 따라서 미확인 장소가 확인된 악조건 장소보다 앞설 수 있다. 날씨·혼잡이 부족한 지역에서는 결과의 `missing_data`를 읽고 위험이 없다고 해석하지 않아야 한다.

거리 원점수는 `100 / (1 + 직선거리_km / 2.5)`다. 각 활성 항목의 유효 점수는 `50 + (원점수 - 50) × 근거계수`다. 근거계수는 일반 관측·수동 라벨 1, 30~45분 지연 관측·이름 추론 0.5다. 기본 점수는 `Σ(활성 항목 가중치 × 유효 점수) / Σ(활성 항목 가중치)`이며 결측 항목의 유효 점수만 순위 계산에서 50으로 간주한다. 최종 `recommendation_score`는 기본 점수에 거리 보정계수 `1 / (1 + max(0, 직선거리_km - 5) / 20)`을 곱한다. 이 보정은 반경 100km처럼 넓은 검색에서 날씨만으로 수십 km 먼 후보가 갑자기 선두가 되는 현상을 줄인다. 응답의 `distance_adjustment`와 `ranking_policy.weights`로 계산을 재구성할 수 있다. 같은 카테고리·근거·날씨라면 가까운 장소의 점수가 높다. 동일한 점수는 명시적 혼잡 선호가 있을 때만 최신 유효 관측을 먼저 보고, 이후 짧은 거리·작은 장소 ID로 정렬한다.

날씨 위험 기준은 강수형태 `PTY>0`, 풍속 `WSD>=9m/s`, 기온 `TMP>=33°C` 또는 `<=-10°C`다. 세 값이 모두 있으면 야외 점수는 85에서 위험 조건당 35를 빼고, 실내는 평상시 65·위험 시 95다. 일부 값에서 악조건만 확인되면 야외는 50에서 조건당 35를 빼고 실내는 85다. 혼합은 두 점수의 평균이다. 이는 추천 품질 실험용 초기값이며 기상청의 안전 기준이나 예측 정확도를 주장하지 않는다. 이름 추론 감쇠, 기본 관광 prior, 거리 보정도 정답 데이터와 사용자 평가가 쌓이면 조정해야 한다.

### 방문 시각과 발표본 선택

보충 수집은 `발표시각+10분<=요청시각`과 `발표시각+1시간<=방문 대상 정시`를 각각 확인해 그 방문 시간대를 포함할 수 있는 가장 최신 발표본을 요청한다. 발표 직후 최신 본이 현재 시각 예보를 아직 포함하지 않을 수 있기 때문이다. 작업이 지연되면 워커가 같은 방문 시간 기준으로 발표본을 다시 선택하고, 저장 캐시와 실제 API 응답에 요청 대상 시간이 있는지 확인한다. 정기 수집은 별도 방문 시간이 없으므로 최신 이용 가능 발표본을 유지한다. 2026-09-13 실호출에서는 한국시간 14시 발표본의 첫 예보 대상이 15시였고, 14시 방문에는 11시 발표본이 필요했다. 실제 제공 지연·첫 대상 시간은 지속 관측해 이 초기 정책을 재검증해야 한다.

## 데이터 수집·개발 실행

```bash
cd tourist_congestion_backend
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_dev_data
.venv/bin/python manage.py runserver
```

개발 시드는 서울 외 부산·제주·강릉 등 전국 10곳의 장소, 명시적 서울 영역 매핑, 격자별 4시간 예보를 키 없이 만든다. 실제 출처 데이터는 시드로 덮어쓰지 않는다. 자동 삭제는 없다. `seed_dev_data --clear`는 명시적으로 실행한 개발 시드만 정리하는 기존 명령이다.

실제 수집 전 `.env`의 `TOUR_API_SERVICE_KEY`, `SEOUL_OPEN_API_KEY`, `KMA_SERVICE_KEY`와 공급자별 일일 한도 `TOUR_API_DAILY_LIMIT`, `SEOUL_DAILY_LIMIT`, `KMA_DAILY_LIMIT`를 설정한다. 공공데이터포털에서 발급한 같은 서비스키를 TourAPI와 기상청의 두 변수에 넣어도 된다. 기본 한도 0은 외부 호출을 막는다. 서울 `citydata_ppltn`에 일일 한도가 없는 일반 인증키를 쓰면 `SEOUL_DAILY_LIMIT=-1`로 설정한다. 이 경우에도 호출 횟수는 기록한다. 양의 일일 한도는 정기 70%, 보충 20%, 예비 10%로 나뉘며 실제 시도/페이지마다 차감한다. 공급자 내장 HTTP 재시도는 꺼져 있고 작업 단위에서 최대 2회 재시도한다. 인증 설정 실패는 중단, 예산 소진은 다음 한국 날짜로 연기한다. 작업 상태·페이지 커서는 SQLite에 남고 5분 넘게 실행 중인 작업은 재시작 뒤 회수한다. 워커는 파일 잠금으로 한 프로세스만 실행한다. 외부 네트워크 호출은 DB 쓰기 트랜잭션 밖에서 이루어진다. `MVP_AUTO_TOUR_SYNC=true`를 명시한 경우에만 한국시간 매일 03:00 전일 변경 조회와 일요일 04:00 전체 대조를 예약한다. `TOUR_SYNC_MAX_PAGES`는 사전 예상 호출량에 맞춰 정한다.

공개된 개발계정 기본 한도는 [TourAPI 일 1,000회](https://www.data.go.kr/data/15101578/openapi.do), [기상청 단기예보 일 10,000회](https://www.data.go.kr/tcs/dss/selectApiDataDetailView.do?publicDataPk=15084084)다. 로컬 `.env`에 이 두 값을 적어 두었다. [서울 포털의 인증키 안내](https://data.seoul.go.kr/together/mypage/actkeyMain.do)는 1회 최대 1,000건을 명시하고, 일일 1,000회 제한은 실시간 **지하철** API에 대해서만 명시한다. 사용자가 확인한 서울 일반 키의 일일 한도 없음에 따라 로컬 `SEOUL_DAILY_LIMIT=-1`로 설정한다. 서울 실시간 인구 요청은 한 영역의 1~5행만 요청한다. 계정별 승인값이 다르면 `.env`를 실제 승인값으로 수정해야 한다.

```bash
# 먼저 한 페이지로 공급자 totalCount와 예상 페이지 수를 확인 (1회 호출)
.venv/bin/python manage.py sync_mvp_data --estimate-tour --page-size 1000
# 최대 한 페이지의 전국 기본 목록만 큐에 등록
.venv/bin/python manage.py sync_mvp_data --tour --max-pages 1
# 좌표의 날씨 격자 한 개만 큐에 등록
.venv/bin/python manage.py sync_mvp_data --weather-at 35.16 129.16
# 내부 장소 ID 한 곳의 상세정보를 큐에 등록 (최대 2회 호출)
.venv/bin/python manage.py sync_mvp_data --detail-place-id 1
# 별도 터미널에서 단일 워커 실행. --once는 작업 1개만 처리
.venv/bin/python manage.py run_data_worker --dev
# 서울 공식 121개 영역을 한 번 수집 (상주 워커는 시작하지 않음)
.venv/bin/python manage.py sync_seoul_crowd_catalog
```

`--tour --max-pages N`은 전국 `areaBasedSyncList2`의 최대 N페이지를 이어서 읽고 카테고리 12/14/15/28/38/39만 장소로 반영한다. `--region-code`/`--modified-since`로 범위를 제한할 수 있다. 2026-09-12 목록 응답의 `totalCount`는 68,993건으로, 1000건/페이지라면 전체 조회에 약 69회가 필요하다. 이 값은 변할 수 있으므로 실제 수집 직전에 `--estimate-tour`로 다시 확인한다. 상세는 `--detail-place-id` 또는 기존 `sync_tour_place_details`로 필요한 장소부터 수집한다. `--dev` 워커는 서울 공식 카탈로그 121개 영역을 15분 단위로, 누락·7일 이상 경과한 상세 최대 20개를 하루 단위로, 최근 요청 격자 최대 5개를 최신 발표본에 맞춰 예약한다. 서울 영역만 121 × 96 = **하루 11,616회**이므로 상주 워커를 켜기 전에 실제 호출량·보존량·공급자 상태를 확인한다. 현재 개발 서버에는 상주 워커가 없다. 웹 서버 시작은 전국 수집을 하지 않는다.

새 목록은 장소명과 카테고리가 함께 뒷받침하는 좁은 규칙으로 실내외를 즉시 분류한다. 기존에 적재된 미분류 장소는 `.venv/bin/python manage.py backfill_place_classification`으로 보강하며 이미 확인된 수동 분류는 바꾸지 않는다.

시범군 수집은 [2026-09-12 개선 검증](./pilot-improvement-2026-09-12.md)의 고정 명단을 사용한다. `prepare_pilot_cohort --manifest docs/pilot-cohort-2026-09-12.json --enqueue-limit 150`은 오늘 남은 TourAPI 정기 예산을 확인하고 최대 150곳의 상세 작업을 예약한다. `--weather-grids 40`은 실내외가 확인된 시범군 격자만 최신 발표본에 맞춰 예약한다. `run_data_worker --max-jobs N`은 유한한 작업 수를 처리하고 종료한다. `PILOT_COHORT_MANIFEST`를 설정하면 `--dev` 워커의 상세 예약은 기존 목록 순서 20곳 대신 고정 시범군 순서를 사용하며, `PILOT_DETAIL_DAILY_PLACES`가 그날 전체 예약 상한(최대 200)을 정한다. 워커 실행 자체가 예약·호출의 조건이다.

추천 요청은 근처 후보를 찾은 뒤 부족한 격자 최대 5개와 서울 영역을 공통 큐에 넣는다. 이미 실행 중인 작업이 있을 때만 총 2초까지 기다리고, 이어서 저장된 자료로 응답한다. 워커가 없거나 실패해도 결측으로 정상 응답한다.

## 확인한 명세와 미확인 계약

- [기상청 API허브 단기예보 문서](https://apihub.kma.go.kr/apiList.do?seqApi=10): `getVilageFcst`의 `base_date`, `base_time`, `nx`, `ny`, `fcstDate`, `fcstTime`, `category`, `fcstValue` 및 위경도→격자 공식 변환 서비스의 범위를 확인했다. [공공데이터포털 데이터셋](https://www.data.go.kr/data/15084084/openapi.do)은 전국 5km 격자와 JSON/XML 제공을 명시한다. 발표 시각 뒤 10분은 이 구현의 초기 수집 지연값이며 실 제공 지연 검증이 필요하다.
- 기존 TourAPI 코드와 고정 fixture의 `areaBasedSyncList2`, `detailCommon2`, `detailIntro2`, 출처 ID와 페이지 구조를 재사용한다. [한국관광공사 공개 소개](https://api.visitkorea.or.kr/#/cmsNoticeDetail?no=207)는 국문 관광정보의 전국 제공을 설명한다. 목록·활성 장소 상세는 실호출로 확인했으며, 계정별 트래픽과 변경 조회 동작은 미검증이다.
- 서울 공식 121개 영역을 수집 대상으로 두되 TourAPI 장소에 연결된 검증 매핑은 기존 13곳만 유지한다. 영역 수집 확대만으로 추천 적용 장소가 늘지는 않으며, 전국 실시간 혼잡도를 뜻하지 않는다. [서울 열린데이터광장의 공통 API 오류 명세](https://data.seoul.go.kr/dataList/OA-20504/A/1/datasetView.do)에 따라 `INFO-100`은 인증 거부로 처리한다.
- 2026-09-12 세 공급자 모두 로컬 키로 실호출을 확인했다. 첫 1페이지 메모리 SQLite 검증 뒤 실제 로컬 DB에 전국 목록 69페이지를 적재하고 같은 범위를 다시 실행해 중복·무결성을 확인했다. 상세 20곳, 서울 12개 영역, 수요 기반 기상청 예보도 수집했다. 수치와 한계는 [운영 검증](./operation-validation-2026-09-12.md)을 참조한다. 기상청 격자 변환 공식 서비스와 로컬 변환의 교차 검증, 발표 지연·제공 주기 검증은 완료하지 못했다. 실패·빈 예보는 기존 저장본을 덮어쓰지 않는다.

관련·대체 장소 추천, 관광지 관계/방문 집중 예측 계약, 사용자 선호 수정과 피드백은 다음 구현 단위다. 추천 계산은 별도 서비스이므로 관계 후보 선정과 거리 경로 서비스가 붙을 수 있다. 위치·행동 기록은 정책 확정 전 저장하지 않는다. 운영 DB 선택과 보존·삭제 정책도 미정이다.
