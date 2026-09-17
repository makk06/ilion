# 이리온 혼잡도 검증 결과 기반 최소 개선

작성일: 2026-09-13 KST. 모델: `heuristic-v1.2`, 프로파일: `profiles-v2`.
기존 `VALIDATION_REPORT.md`의 2026-09-12 검증 결과를 보존하고 최소 개선을 구현했다.
실제 캡처 재생과 합성 반례는 정확도 평가가 아니다. 독립 정답·유효 경험적 분포가 없어 MAE와 정확도 향상률은 UNKNOWN이다.

## 1. Executive Summary

**MODIFY: Baseline + Delta와 전국 예상 5단계를 유지하고 입력·매핑·평가의 결함을 수정했다.**

| 가장 큰 문제 | 적용한 해결책 |
|---|---|
| 121개·일 1,000회로 기준선 70% coverage 확보 불가 | 사용자 선택대로 균등 220분 수집 유지. `crowd_status`에 cadence 부족을 표시하며 조건을 낮추지 않음 |
| POI 예측과 영역 정답 혼합·버전 혼합 | 영역 관측 기반 `area_core` 평가, 발행 입력 고정, 버전·정책별 집계, 경고 전용 |
| 부적합 최신값·날씨 의미·매핑 승인 불확실성 | 마지막 정상 관측 선택, 풍속 결측 제외, 해변 양의 맑음 보정 제거, 승인 충돌 배제 |

수집 범위와 신뢰도를 혼동하지 않는다. 121개 균등 수집과 전국 예상 표시가 확정된 사용자 선택이다.

## 2. Problems Found

근거 구분: **실제**는 캡처 응답, **정적**은 코드 검사, **합성**은 제어된 반례다.

| ID | Problem / Evidence | Severity | Component |
|---|---|---|---|
| P1 | 220분 수집의 이상적 시간 버킷 coverage 27.28%, 필요 70% (합성 일정) | HIGH | DATA |
| P2 | 역사 표본·경험분포 없음, 6개 중 5개가 day_visit (실제·DB) | HIGH | BASELINE |
| P3 | 서울 원천 인구 약 30분 지연 (실제) | HIGH | DATA |
| P4 | 서울 4개 장소 중 3개 polygon 중첩, 홍대·롯데월드 미승인 (실제 기하) | HIGH | MAPPING |
| P5 | 거절 이유 소실, 복수 승인의 ID 순서 선택, verified=True 기본값 (정적) | MEDIUM | MAPPING |
| P6 | 영역 첫 POI와 대표성에 따라 영역 정답에 대한 예측이 달라짐 (정적·합성) | HIGH | VALIDATION |
| P7 | stale 평가 제외·5분 정답 창과 지연·220분 수집 불일치 (정적·합성) | HIGH | VALIDATION |
| P8 | 모델 버전 혼합·전역 horizon 영구 중단 (정적) | HIGH | VALIDATION |
| P9 | 대체 최신값이 정상값을 가림, 과거 재생에서 미래 수신 자료 선택 가능 (정적·합성) | HIGH | DATA |
| P10 | 밤에도 해변 맑음 가점, 풍속 누락을 무풍으로 간주 (정적·합성) | MEDIUM | ALGORITHM |
| P11 | 날짜만 확인한 행사도 야간 보정, 여러 행사가 최대 효과로 포화 (실제·합성) | MEDIUM | ALGORITHM |
| P12 | 현재 하차량은 있으나 동일 정의 baseline 부재, qT=0 (실제) | MEDIUM | BASELINE |
| P13 | 일중 상대 수준·평소 대비 비율·체감 혼잡은 다른 목표 (합성 의미 검사) | HIGH | VALIDATION |
| P14 | 야간·서울 중심 소표본, 독립 정답과 confidence 오차 보정 없음 (검증 범위) | HIGH | CONFIDENCE |

기존 스프린트에서 수정된 신규 해변 분류, 미래 표본 신뢰도, 지연 EWMA 이력, 공개 KTO 표본 선택은 유지하고 회귀검사했다.

## 3. Root Cause Analysis

- P1·P2: 표본 수집 속도와 승격 조건의 불일치다. 더 오래 모으거나 관측 없는 지역별 계층을 추가해도 해결되지 않는다.
- P3·P7: 원천 시각, 수신 시각, 발행 시각의 목적이 다르며 평가 가능성을 표시용 stale에 묶으면 안 된다.
- P4·P5: 기하 포함과 시설 대표성은 다르다. 중첩은 기하 오류가 아니라 승인 근거 부족이다.
- P6·P8: 평가 단위·모델 경계가 없어 POI 선택과 과거 모델이 새 모델 평가를 오염시킨다.
- P9: 최신 행과 최신 사용 가능한 관측을 혼동했다.
- P10·P11: 구름 상태·날짜가 주간 일조·실제 행사 시간을 의미하지 않는다.
- P12~P14: API 연동, 계산 안정성과 실제 예측 정확도를 구분해야 한다.

## 4. Proposed Fixes

| 문제 | Option A | Option B | 선택·영향·비용 |
|---|---|---|---|
| P1 | 소수 영역 집중 | 전체 균등 유지 | B: 사용자 선택, 범위 유지·정확도 평가 제약, 낮음 |
| P2 | 추정 지역×유형 계층 | 근거 있는 분류와 기존 prior | B: 가상 장소 차이 생성 방지, 낮음 |
| P3·P7 | TTL·정답 창 확대 | freshness와 평가 자격 분리 | B: 지연을 숨기지 않고 기록, 중간 |
| P4·P5 | 최소 면적·최근접 자동 승인 | 후보 진단·명시적 승인 | B: 다른 공간 인구 오용 방지, 낮음 |
| P6 | 대표 POI 고정 | 영역 관측 기반 평가 | B: POI 순서·환경·대표성 독립, 중간 |
| P8 | 전역 MAE·영구 중단 | 버전·정책별 경고 | B: 평가가 운영을 잘못 중단하지 않음, 낮음 |
| P9 | 즉시 prior 전환 | TTL 내 정상 관측 선택 | B: 정상 근거 보존·시점 누수 차단, 낮음 |
| P10 | 임의 낮 시간·결측 계수 | 양의 보정 제거·필수 성분 검사 | B: 일조·무풍 가정 제거, 낮음 |
| P11 | 날짜 행사 새 상한 | 약한 기존 계수·한계 표시 | B: 근거 없는 새 계수 보류, 낮음 |
| P12 | 월간 역 자료를 분모로 사용 | 동일 집계 관측 축적 | B: 통계 정의 혼합 방지, 낮음 |
| P13·P14 | 소표본 계수 최적화 | 의미 명시·순방향 평가 | B: 야간 과적합 방지, 중간 |

추가 API, ML, Redis, Celery, fuzzy matching 라이브러리, 공간 서비스는 추가하지 않았다.

## 5. Algorithm Changes

**CrowdScore는 장소 유형·시간 가정과 사용 가능한 주변 영역 관측을 결합한 상대 방문 수준 추정 지수이며, 현재 방문객 수·물리적 밀도·체감 혼잡의 측정값이 아니다.**

유지한 식:

```text
B = 경험적 시간대 기준 점수 또는 명시적 prior
uP=.8qP, uT=.2qT
δ=(uP(PopulationScore−B)+uTδT)/(uP+uT); 분모 0이면 δ=0
a=min(.9,.85qP+.30qT)
Context=clip(12qE(E−Ebaseline)+10qW(W−Wbaseline),−20,20)
Score=round(clip(B+a·EWMA(δ)+(1−a)Context,0,100))
```

기존 percentile·교통 log-ratio 제한·EWMA·5단계 경계·confidence 계수는 그대로다. `relative_to_normal`은 별도 비율이며 2배라고 반드시 HIGH가 되지 않는다.

인구 선택은 `최신 행→품질 검사`에서 `수신≤발행 ∧ 비대체 ∧ 비개발 ∧ 유효 범위 ∧ age<60분`인 행 중 최신 원천 시각으로 바꿨다. fetched_at이 없는 기존 행은 실제 created_at을 수신 대안으로 사용한다. 정상값 재사용 시 시각을 갱신하지 않는다. 교통·달력에도 미래 수신 제외를 적용했다.

```text
Before Wbeach=clip(+.4·I(SKY=1 ∧ 24≤T≤32)−.9R−.5C−.4V,−1,1)
After  Wbeach=clip(−.9R−.5C−.4V,−1,1)
```

실외 day_visit/park/beach는 유한한 기온·강수형태·풍속을 요구한다. 누락이면 qW=0과 이유를 제공한다. 정상 성분 일부도 포기하는 보수적 선택이며, 성분별 보정 가중치는 새로 만들지 않았다.

## 6. Data Architecture Changes

| 구조 | 결정 |
|---|---|
| 모든 입력을 가정하는 전국 공통 합산 | 결측 조건과 불일치 |
| 가용성별 별도 모델 3개 | 검증 표본 없이 코드·정책 중복 증가 |
| 공통 Baseline+Delta + 기존 kind/tier | 채택·유지 |

`observation_assisted`, `historical_based`, `prior_based`, A/B/C를 유지한다. 서울 인구를 현장 실측으로 이름 바꾸지 않는다.

수집: 121개 균등, 승인1,000/정규800회, 계산 주기220분, 이상적 평균792회/일. 실제 시도는 기존 예산 차감으로 제한한다. 정상 수집만의 이상적 coverage도 약27.28%이므로 `crowd_status.baseline_readiness.status=CADENCE_INSUFFICIENT`다. 28일·70%·조건부4일 조건을 완화하지 않는다. 추가 승인·OS 스케줄러 등록은 이 변경에 포함하지 않는다.

ForecastEvaluation 확장: nullable place, scope, baseline_version, input_snapshot, pending/matched/missing, actual_observed_at/actual_received_at. 기존 행은 `legacy_place`로 보존하고 평가에서 제외한다. 새 `area_core`는 POI 프로파일·행사·날씨·대표성·개폐장·평활 이력을 제거한 결정적 관측 기반 실험이다. 버전 접미사 `:area-core-v1`로 공개 POI 모델과 구분한다.

현재 경험적 기준선과 각 horizon의 기준선이 있을 때만 해당 horizon을 기록한다. 지연된 유효 인구는 stale 상태 그대로 허용한다. 영역/시간/모델마다 첫 발행을 고정하며 같은 입력으로 재계산한 값으로 덮어쓰지 않는다. 정답은 목표시각~+5분의 실제 비대체 관측, 수신은 목표시각+24시간까지다. 정답이 없으면 missing이고 모델값으로 채우지 않는다.

**구현 중 정합성 보완:** 기준선 데이터 버전은 매일 바뀌므로 날짜 버전별로 평가를 나누면 7일 표본 조건이 불가능하다. 각 발행의 일별 분포·버전은 그대로 고정하고, 같은 모델·scope·horizon·`84d-median-v1` 계산 정책 안에서 집계한다. 사용된 일별 버전 목록도 보고한다. 다른 정책·모델은 혼합하지 않는다. 영역별 오차를 균등 평균한다.

평가 보고는 `metrics` 목록과 `warnings_only=true`. 최소100대응표본/7일/2영역/평일·주말을 요구하며, 충분한 경우 baseline MAE 대비10% 악화는 경고만 한다. API의 자동 horizon 중단 연결은 삭제했다. 명시적 운영 설정은 유지한다.

## 7. Place Resolver Changes

- 공유 `select_mapping`: 유효 승인 manual/source 우선, 후보 하나 또는 유일 primary만 채택. 충돌은 APPROVAL_CONFLICT이며 ID 순서로 해소하지 않는다.
- `polygon_diagnostics`: NO_COORDINATE/OUTSIDE/HOLE/BOUNDARY/OVERLAP과 후보 코드·거리·geometry 버전. 최근접 강제 연결 없음.
- 신규 매핑 verified 기본값 False. polygon 승인 경로만 조건 통과 후 명시 승인.
- 수동 명령은 검토자·근거·미래 만료일 필수. `--primary`를 명시할 때만 기존 primary를 원자적으로 변경한다.
- evidence JSON에 장소·영역 ID, 출처/판단 사유, 검토자·시각을 보존한다. 이전 행은 migration에서 legacy로 표시하며 승인 상태·대표성은 보존한다.
- 읽기 전용 `diagnose_crowd_mappings` 명령으로 후보 검토 자료를 출력한다. 신규 검토 UI를 만들지 않는다.

실제 재검토: 성수는 단일 내부195.34m. 경복궁은 기존 승인·대표성.65 유지. 홍대와 롯데월드는 미승인 상태 유지. 롯데월드 POI005/119와005/120은 동일 polygon이 아니며 IoU는 각각 .11050/.37318이다. 겹치는 인구를 합치지 않는다.

프로파일은 기존 공식 NA020900 해변 보강을 유지했다. 홍대·성수의 야간 시간표와 롯데월드 운영시간은 자유문장·이름만으로 확정하지 않고 검토 대기다.

## 8. Confidence Changes

계수·tier 상한 유지. 품질 지수는 적중 확률이 아니다.

- weather_at가 발표·수신 시점과 현재 유효시각/미래 정확한 대상 시간을 검사한다.
- factors.unavailable_reason으로 신호 제외 이유를 전달한다.
- 경험적 기준선 부족·행사 시간 미확인·매핑 충돌은 limitations로 표시한다.
- 원천 시각 감쇠·개발 표본·폐장·stale 추천 제외와 confidence 추천 감쇠 유지.
- snake_case/envelope/기존 latest_crowd 4단계/새 예상5단계를 유지한다. 숫자·방문객 추정 필드를 새로 만들지 않았다.

## 9. Re-validation Results

재현: 저장된 API 응답만 읽으며 외부 HTTP 호출이나 원본 관측 DB 적재가 없다.

```powershell
.integration-venv/Scripts/python.exe scripts/crowd-validation/improvement_checks.py
```

결과는 `.integration-artifacts/crowd-validation/improvement_checks.json`에 저장된다. 실제 캡처는 `improvement_actual.json`, 합성 입력은 `improvement_synthetic.json`에도 각각 저장한다. 고정시각2026-09-12T23:26:14.771409+09:00.

| 장소 | FULL | −인구 | −교통 | −날씨 | −행사 | B→50 진단 |
|---|---:|---:|---:|---:|---:|---:|
| 경복궁 |21.530|23.234|21.530|21.530|18.867|45.418|
| 성수 |19.606|20.661|19.606|19.606|18.968|44.118|
| 해운대 |25.814|25.814|25.814|25.814|25.814|50.000|
| 전주 |20.348|20.348|20.348|20.348|19.876|50.472|
| 잠실 |19.876|19.876|19.876|19.876|19.876|50.000|
| 홍대 |20.060|20.060|20.060|20.060|19.876|50.184|

기준선 완전 삭제는 δP의 의미를 없애므로 B=50은 의존성 진단일 뿐 후보 모델이 아니다. 경험적 기준선만 삭제하면 원래 없어서 변화0이다. 가중치±20% 최대변화 .533점. 교통qT=0/날씨W=0이어서 이번 제거 효과0은 유용성 부정 근거가 아니다.

실제6개 정수 출력은 기존22/20/26/20/20/20→동일. 합성 실외 해변28℃맑음은12시62→58,23시32→28. 맑음과 강수가 함께 주어진 경우12시53→49,23시23→19. 의미상 가점을 제거한 것이며 정확도 향상이 아니다.

날짜만 확인한 동일 위치 행사20개는 E=.978666, qE=1에서11.744점 보정이다. 새 상한은 정하지 않았다.

입력·평가·매핑 회귀검사는 실제 Django 테스트 DB에서 수행했다. 미래 수신·대체·만료·null 수신·조회수 불변·외부요청 금지, POI 순서·버전 분리·늦은 정답·결측 horizon·승인 충돌을 포함한다.

최종 검증(2026-09-13): **Django 전체132개 PASS**(14.483초), `check` PASS, `makemigrations --check --dry-run` 변경 없음. Flutter `crowd_estimate_test.dart` **3개 PASS**: 5단계/구계약 분리, 낮은 confidence 추천 감쇠와 demo/closed/stale 제외, 좁은 화면 배지·근거 표시. 프런트엔드 production 코드는 변경하지 않았다.

로컬DB 백업 후0007 migration을 적용했다. 기존 장소10개, 관측3개(전체 행 digest 비교), 매핑2개(원래 승인·대표성·primary·ID 비교)가 보존됐다. 백업 경로와 검증 결과는 `migration_verification.json`, 테스트 요약은 `implementation_verification.json`에 남긴다. 이번 구현의 외부 API 호출은0회다.

새로운 손실도 확인했다. 합성 풍속 누락·강수 사례는 날씨 전체를 제외하므로12시53→58,23시23→28점으로 바뀌고 confidence는.23→.14로 낮아진다. 이는 정상 기온·강수 정보 일부도 포기한 결과이며 정확도 개선으로 주장하지 않는다.

## 10. Remaining Limitations

현재 균등 수집으로 경험적 승격을 보장할 수 없다. 전국 동일 정의 실시간 방문 관측·POI 내부 현장 정답·혼잡 영향계수 보정은 없다. 6곳 야간 검증은 우천·낮·행사 피크·계절을 대표하지 않는다. area_core MAE는 전체 POI 모델/시설 체감 정확도가 아니다. 미확인 행사 규모·시간, 생활인구/역별 통계의 다른 정의를 숨기지 않는다. 테스트 통과는 예측 정확도 증명이 아니다.

## 11. MVP Decision

Status는 혼잡 추정 근거 수준이며 API 연동 성공 여부와 별개다.

| Feature | Status | Decision | Reason |
|---|---|---|---|
| KTO POI | PARTIALLY_VALIDATED | KEEP | 대표 장소 원장·좌표 확인 |
| Population | PARTIALLY_VALIDATED | MODIFY | 최신 정상·시점 선택 수정 |
| Transit | PARTIALLY_VALIDATED | EXPERIMENTAL | 비교 기준선 없음 |
| Weather | UNVALIDATED | MODIFY | 혼잡 효과 미검증, 의미·결측 수정 |
| Event | UNVALIDATED | EXPERIMENTAL | 시각·규모 불명 |
| Historical Baseline | PARTIALLY_VALIDATED | KEEP | 계산 조건 유지, 실제 자료 부족 |
| Cold-start | UNVALIDATED | KEEP | 전국 낮은 신뢰도 예상 제공 |
| Resolver | PARTIALLY_VALIDATED | MODIFY | 승인 충돌·진단·근거 |
| Confidence | PARTIALLY_VALIDATED | MODIFY | 계수 유지, 입력 유효성 개선 |
| 해변 맑음 가점 | UNVALIDATED | REMOVE | 주간·일조 근거 없음 |
| 전역 자동 중단 | REJECTED | REMOVE | 잘못된 평가의 운영 개입 |
| 중첩 영역 인구 합산 | REJECTED | REMOVE | 원래 제외 정책 유지 |
| 새 API·ML | UNVALIDATED | EXPERIMENTAL | 이번 구현 범위 밖 |

## 12. Priority Fixes

| 시점 | 작업 | Impact / Cost | 상태 |
|---|---|---|---|
| Fix Now | 정상 관측·시점 가용성 | 높음/낮음 | 구현 |
| Fix Now | 자동 전역 중단 제거 | 높음/낮음 | 구현 |
| Fix Now | 해변·필수 기상 성분 | 중간/낮음 | 구현 |
| Fix Now | cadence 미충족 진단 | 높음/낮음 | 구현 |
| Fix Next | 영역·버전별 순방향 평가 | 높음/중간 | 구현, 실제 표본 대기 |
| Fix Next | 매핑 근거·진단 | 높음/낮음 | 구현, 미승인 장소 유지 |
| Fix Next | 대표 POI 분류·운영시간 검토 | 중간/낮음 | 캡처 출처 검토, 미확인 운영정보 대기 |
| Later | 실제 자료로 영향계수 검증 | 불확실/중간 | 후속 |
| Later | 현장 평가·계층 기준선·추가 공급자 | 불확실/높음 | 후속 |

## 13. Next Experiment

1. **정상 근거 보존.** 가설: 무효 최신값이 정상값을 가리는 문제를 제거한다. 방법: 대체·범위 누락·지연·TTL 경계 재생. 성공: 올바른 시점의 정상값 선택, 미래누수0. 실패: freshness 회복·만료값 사용. 구현된 회귀검사로 검증한다.
2. **평가 오염 제거.** 가설: POI 선택·모델 혼합에 영향을 받지 않는다. 방법: POI 순서·대표성 변경, 버전·정책·지연 도착 재생. 성공: 같은 영역 입력의 예측 불변, 버전 간 개입0. 실패: 첫 POI나 다른 모델 때문에 평가 변경. 구현된 회귀검사로 검증한다.
3. **실제 예측 가치.** 가설: area_core가 baseline-only와 persistence보다 낫다. 방법: 경험분포 준비 후 horizon별100개 대응 표본/7일/2영역/평일·주말, 발행 입력 고정 MAE 및 날짜 단위 재표집 오차 차이 비교. 성공: 두 기준보다 낮은 MAE와 개선 방향의 재표집 구간. 실패: 표본 부족 BLOCKED/UNKNOWN, 열화는 해당 모델·horizon 경고. **현재 220분 수집 조건에서는 실행 조건 미충족이며 성공으로 표시하지 않는다.**
