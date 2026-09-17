# 과거 평균 기반 구역 혼잡도 예측

이 모델은 공급자가 관측한 **구역 인구 추정치**의 1·2·3시간 뒤 값을 예측한다. 개별 관광지의 방문객 수나 수용률을 제공하지 않는다. 기본 배포는 `legacy`이며, 과거 평가와 가중치를 고정한 14일 shadow 평가를 모두 통과하기 전에는 앱을 전환할 수 없다.

## 데이터와 저장

`MeanEvidence`는 인구·날씨·행사·달력의 수신 당시 버전을 별도로 보관한다. 기존 원본/날씨 정리와 독립적으로 400일 유지하며, source post_save가 자료를 기록한다. bulk_create/update로 해당 source 모델을 저장하는 새 코드에서는 capture를 명시적으로 호출해야 한다. 기존 수집기는 개별 save/get_or_create 경로다.

인구의 최소/최대 중간값을 사용한다. 데모·대체·음수·비정상 범위는 제외하고 유효한 0은 유지한다. 정시부터 5분 이내 첫 관측이 해당 시점의 값이며, 없으면 결측이다. 관측/수신 시각 모두 발행 시각 이하여야 입력으로 쓸 수 있다. 예보는 발표 시각도 검사한다. 수신 시각 없는 과거 자료를 임의의 과거 시각으로 소급하지 않는다.

`MeanPrediction.payload`에는 발행 당시 예측·비교 모델값·가중치·근거 수·대체 사유·입력 hash/스냅숏 ID를 보관한다. 스냅숏은 원본을 매시간 복제하지 않고 불변 evidence ID 목록을 보존한다. 이후 정답은 별도 필드에 채운다. 정답 도착 기한은 대상 시각 이후 24시간이다. 참조 원본의 400일 보존 기간 내에서는 외부 API 호출 없이 재현 가능하다. 기존 중앙값 집계는 사용하지 않는다.

행사 원본은 자동 버전 보관하지만, **영향 구역 및 반복 행사/개최 회차는 검증한 manifest로 등록**한다. 원본 카탈로그의 가까운 행사만 보고 임의로 구역 영향을 부여하지 않는다. 행사 변경이 확인되면 검증 manifest를 다시 등록한다. 과거 manifest는 남는다. 비어 있는 `events`는 확인된 행사 없음이며, manifest가 없으면 미확인이다.

## 계산

- 발행 시각: 한국 시간 정시. 수집기 tick은 정시 후 1분 이내에만 해당 정시 예측을 생성하며 발행 이후 자료는 제외한다. 늦은 실행은 과거 예측을 생성하지 않는다.
- 과거: 발행 전에 끝난 날짜의 84일. 같은 시각·요일·공휴일 여부 → 같은 시각·평일/주말/공휴일 그룹 → 같은 시각 전체 순서로 넓힌다. 어느 단계에서도 서로 다른 날짜 8개가 없으면 숫자를 반환하지 않는다.
- 기본 평균 B: `2 ** (-경과일 / 반감기)` 가중평균. 초기 반감기 28일.
- 날씨 유사도: `exp(-기온차/5) * (강수 형태 동일 ? 1 : 0.25)`. 강수 형태는 없음/비/눈/혼합. 과거 관측 날씨와 발행 당시 미래 예보를 비교한다.
- 조건 평균 C: 유사도와 최근성으로 가중. 같은 행사 사례가 있으면 그 행사로 제한하고, 없으면 날씨 평균으로 돌아가 `event_unmodeled`를 기록한다. 복수 행사는 행사 조건을 생략한다.
- H: `(1-alpha)*B + alpha*C`, `alpha=n/(n+8)`. n은 날짜별 유사도 합이며, 행사에서는 회차별 최대 유사도 합이다. 조건 근거가 없으면 H=B.
- D: 최근 30분의 5분 구간별 마지막 인구에서 해당 시각의 조건 반영 평소 평균을 뺀 차이의 평균. 3구간 미만 또는 마지막 관측이 15분 초과이면 D=0.
- 예측: `max(0, H + exp(-h/tau)*D)`. 초기 tau=1.5시간. tau=null이면 보정하지 않는다.
- 표시는 발행 당시 과거 분포의 중간순위 백분위. 동률은 같은 점수로 처리한다. 신뢰 확률을 만들어내지 않는다.

## 실행

백엔드 디렉터리에서 기존 가상환경의 Python을 사용한다.

```powershell
& '../.integration-venv/Scripts/python.exe' -B manage.py migrate --noinput
& '../.integration-venv/Scripts/python.exe' -B manage.py mean_crowd archive
& '../.integration-venv/Scripts/python.exe' -B manage.py mean_crowd audit --output '../experiments/mean-crowd/results/data-audit.json'
& '../.integration-venv/Scripts/python.exe' -B manage.py mean_crowd init --manifest '../experiments/mean-crowd/candidates.json'
& '../.integration-venv/Scripts/python.exe' -B manage.py collect_crowd_inputs --once
& '../.integration-venv/Scripts/python.exe' -B manage.py mean_crowd tick
& '../.integration-venv/Scripts/python.exe' -B manage.py mean_crowd backtest --output '../experiments/mean-crowd/results/validation.json'
& '../.integration-venv/Scripts/python.exe' -B manage.py mean_crowd validate-shadow --output '../experiments/mean-crowd/results/shadow.json'
& '../.integration-venv/Scripts/python.exe' -B manage.py mean_crowd promote
& '../.integration-venv/Scripts/python.exe' -B manage.py mean_crowd rollback
```

init은 한 번만 실행한다. 운영 수집 진입점은 기존 `ops/collect-crowd.ps1`이며 매분 호출하는 기존 OS 스케줄러에 연결한다. 수집기 자체가 호출 한도·재시도·due 시간을 관리한다. 이 구현은 새 OS 예약 작업을 자동 등록하지 않는다.

후보 manifest는 `candidates`(구역 ID 배열), `grids`(ID별 `x,y`), `mapping_evidence`(공식 구역 경계와 변환 근거)를 가진다. 최소 3개 후보를 받는다. 첫 7일의 수집 주기별 유효 관측 확보율로 상위 3개를 고정하며 동률은 ID 순이다. 90% 미만 구역은 제외하고, 3개를 확보하지 못하면 정확도 검증은 대기한다. 선정 후 후보를 임의로 교체하지 않는다.

인구는 5분 간격 목표지만 기존 20% 호출 여유를 보존한다. 예를 들어 일 1,000회 한도에서 3구역은 **10분 간격**이다. 10분보다 긴 주기가 필요하면 후보 수를 줄이도록 init이 거절한다. 실제 정시 관측 확보율 90%는 별도로 검증하므로 느린 수집을 정확도 합격으로 취급하지 않는다. 날씨 격자는 후보를 우선 수집하고 기존 기상청 호출 한도를 따른다.

행사 manifest 예시(예시 식별자를 실제 검증 결과로 교체):

```json
{
  "area_id": 1,
  "start_date": "2026-09-01",
  "end_date": "2026-09-30",
  "verification_evidence": "행사 운영자가 확인한 영향 구역·일정의 출처",
  "events": [{
    "family": "verified-recurring-festival",
    "edition": "2026-autumn",
    "start_date": "2026-09-20",
    "end_date": "2026-09-21",
    "starts_at": null,
    "ends_at": null
  }]
}
```

`mean_crowd events --manifest 파일.json`으로 등록한다. 수신 시각은 등록 시각으로 고정하며 과거로 지정할 수 없다.

## 검증과 배포 기준

후보 선정 이후 56일 학습, 14일 선택, 14일 최종 평가를 분리한다. 마지막 정답 기한을 포함해 27시간을 더 기다린다. 학습 시간별 관측 확보율은 구역마다 90% 이상이어야 한다. 학습 평균(최소 1)을 정규화 분모, 학습 90백분위를 최고 혼잡 기준으로 고정한다.

반감기 14/28/56, tau 끔/0.5/1.5/3, 날씨·행사 켬/끔의 48개 조합을 선택 기간에서 비교한다. 구역과 예측 거리별 정규화 MAE를 동일 비중 평균하고 동률이면 보정 항이 적은 모델을 고른다. 행사 모델은 과거 3회차와 별도 평가 회차의 실제 인구 근거가 없으면 선택에서 제외한다.

지난주 같은 시간, 현재 유지, 산술평균, 최근성 평균, 조건 평균과 비교한다. 비교 모델도 같은 정답 쌍에서 비교한다. 마지막 평가 기간에서 가중치를 재선택하지 않는다. 성능 통과 후 가중치를 고정하고 추가 14일 실제 shadow 발행을 확인한다. 누락된 예정 예측도 제공 가능률의 분모에 들어간다.

합격: 3개 구역×3개 거리 각각 정답 쌍 100개와 14일, 평일/주말 포함; 제공/정답 확보율 각각 90%; 산술평균 대비 정규화 MAE 5% 이상 개선; 선택한 최선 비교 모델보다 개선; 구역·거리·최고 혼잡 MAE 5% 초과 악화 없음. 2,000회 날짜 단위 bootstrap의 개선 차이 95% 구간도 음수여야 한다. 자료/최고점 부족과 통계적 불확실성은 NEEDS_MORE_DATA, 악화는 FAIL이다. 합성 테스트의 PASS는 실제 데이터 합격이 아니다.

promote는 backtest와 shadow가 모두 PASS일 때만 동작한다. 앱은 현재 예측 부분을 유지하고 미래 예측 부분만 구역 평균 모델로 전환한다. 미발행·결측은 null과 사유다. 품질 숫자는 미평가로 표시한다. rollback은 기존 모델로 되돌린다. 일별 monitor는 정답 확정 지연을 제외한 최근 구간에서 셀마다 100개가 있을 때 성능을 비교하고, 3일 연속 산술평균보다 10% 이상 나쁘면 산술평균으로 전환한다. 반복 실행해도 하루를 중복 계산하지 않는다.

## 테스트 명령과 운영 한계

```powershell
& '../.integration-venv/Scripts/python.exe' -B manage.py test places.test_mean_forecast places.test_mean_study --noinput
& '../.integration-venv/Scripts/python.exe' -B manage.py test --noinput
```

Flutter 계약 테스트는 `flutter test --no-pub test/crowd_estimate_test.dart`다. 인구 수집 API와 공급자 추정치의 실제 정확도는 단위 테스트로 증명할 수 없다. 실제 비공개 예측 및 데이터 축적을 완료해야 성능 검증을 완료할 수 있다. 독립 실험은 표준 라이브러리와 기존 Django만 사용하며 학습 서버·새 패키지를 요구하지 않는다.
