# 시간당 모델 성능 검증 실행

서울시 구역 인구와 TMAP 장소 밀도는 독립적으로 평가한다. 기존 앱 모델은 자동으로 교체하지 않는다.

## 운영 순서

1. `hourly_crowd status`로 공급자 설정과 후보를 확인한다. TMAP은 실제 키·무료 호출 한도·검증된 POI가 준비되어야 한다. 키를 명령줄이나 보고서에 넣지 않는다.
2. 기존 `collect_crowd_inputs --once --max-seconds 45`를 매분 실행한다. 실제 외부 인구·밀도 호출은 58~59분, 정시 발행은 0~1분에 수행한다. 서버 한 곳의 수집기를 사용한다.
3. 7일 점검 후 정시 표본 확보율 90% 이상인 대상을 고정한다. 이후 초기 56일·선택 14일을 확보한다.
4. `hourly_crowd select --provider seoul`로 16개 조합 중 하나를 고정한다. TMAP에도 별도로 실행한다. `evaluate`는 선택을 대신 실행하지 않는다.
5. 선택 계산이 완료된 다음 정시부터 새로운 14일 holdout을 시작한다. 늦은 선택 여부와 원래 예정 시각을 남긴다. 지나간 기간을 이미 고정했던 기간으로 소급하지 않는다.
6. `hourly_crowd evaluate --provider seoul --artifacts ../output/hourly-validation/seoul/holdout`로 평가한다. PASS면 다음 정시부터 추가 14일 실제 발행 검증을 시작한다.
7. `hourly_crowd shadow --provider seoul --artifacts ../output/hourly-validation/seoul/shadow`로 비공개 운영 성능을 검사한다. 두 단계 모두 PASS인 구성만 기존 `promote` 명령의 대상이 된다.

명령은 backend 디렉터리에서 `.integration-venv`의 Python으로 `manage.py` 뒤에 실행한다. `--output`은 요약 JSON 파일, `--artifacts`는 보고서 디렉터리다. `advance`는 준비된 단계만 자동 진행하고 공급자별 오류를 분리하며 자동 승격하지 않는다.

Windows: 프로젝트 루트에서 `pwsh -NoProfile -File ops/install-hourly-validation.ps1`를 실행한다. 수집 작업은 매분, 평가 작업은 매시간 실행한다. 예약 작업은 pythonw.exe가 ops/hourly-job.py를 직접 실행하므로 Windows PowerShell 실행 정책을 변경하지 않는다. 로그는 output/hourly-validation에 비밀값을 제거한 뒤 크기를 제한해 저장한다. 동일 이름의 다른 작업은 덮어쓰지 않는다. 비밀번호를 저장하지 않는 현재 사용자 작업이므로 **컴퓨터가 켜져 있고 사용자가 로그인한 동안** 동작한다. 실제 90% 확보율을 달성하려면 이 조건을 계속 유지하거나 상시 서버의 기존 수집 타이머에 연결해야 한다. 중복 서버 수집은 금지한다.

일시 중지: `Disable-ScheduledTask -TaskName IlionCrowdCollection` 및 `Disable-ScheduledTask -TaskName IlionHourlyValidation`. 다시 켤 때는 대응하는 `Enable-ScheduledTask`를 사용한다. 실행 결과는 `Get-ScheduledTaskInfo`와 `hourly_crowd status`로 확인한다.

## 평가 계약

- 선택한 파라미터, 비교 모델, 최근성 비교 파라미터, 학습 평균, 최고 혼잡 기준, 대상 목록, 고정·평가 시작 시각을 해시로 고정한다. 변경되면 평가·승격·앱 어댑터에서 거부한다. 새로운 구성은 새로운 실험이 필요하다.
- 비교 정답 쌍은 최종 모델·단순 평균·지난주 같은 시각·현재값 유지·선택한 비교 모델이 모두 있는 경우다. 장소·거리마다 제공률, 정답 확보율, 공통 쌍 비율이 각각 90% 이상이어야 한다.
- 정답은 예측 저장 여부와 무관하게 원본 관측에서 정시 이전 15분 규칙으로 읽는다. 보간하지 않는다. 실제 발행 평가에서 대상 시각이 지난 뒤 계산한 예측은 제공으로 인정하지 않는다.
- 재현 입력은 각 발행 시각의 84일 범위로 별도 조회한다. 평가 마지막 시점의 84일 자료를 첫 평가 시점에 그대로 적용하지 않는다.
- 장소·거리마다 100쌍, 14개 한국 날짜, 평일·주말을 요구한다. 밀도 NMAE 분모에 1 하한을 적용하지 않는다. 0 학습 평균 대상은 승격 보류한다.
- 단순 평균 대비 NMAE 5% 이상 개선 및 선택 기간 최선 비교 모델보다 개선해야 한다. 어떤 장소·거리의 MAE 및 최고 혼잡 MAE도 단순 평균보다 5% 초과 악화되면 안 된다.
- 정답의 한국 날짜 단위로 전체 장소·거리를 함께 2,000회 재표집한다(시드 20260913). 두 비교 모델에 대한 NMAE 차이 95% 신뢰구간 상한이 0 미만이어야 한다. 14일 실험은 다른 계절까지 검증하지 않는다.
- `rain_forecast`는 강수 예보, `rain_observed`는 실제 관측 강수다. 미확인 자료를 실제 강수·행사 없음으로 해석하지 않는다. 이번 모델에는 날씨·행사 보정이 없다.
- 자료 부족과 성능 미달은 별도 상태다. 부족한 고정 기간을 동일 자료로 반복 평가해도 새로운 근거가 생기지 않는다. 이미 본 결과로 재선택한 모델에는 새로운 미관측 평가 기간이 필요하다.

## 보조 자료 재현

프로젝트 루트에서 다음을 실행한다. 기존 자료 파일은 읽기만 하며 운영 DB에는 연결하지 않는다.

```powershell
& ./.integration-venv/Scripts/python.exe scripts/validate_hourly_proxy.py --input 'PATH/TO/population.csv' --output output/hourly-validation/proxy
```

대상은 사직동·삼청동·가회동, 기간은 2026-03-01~05-31이다. 56일 학습·14일 선택·22일 평가를 유지한다. 이미 확인한 평가 기간이므로 결과는 항상 `AUXILIARY_ONLY`다. 즉시 수신 가정은 메모리에서만 사용하고 수신 이력을 만들지 않는다. 현재값 누락과 1시간 가용성 지연은 별도 민감도 분석이다.

각 보고서에는 `report.json`, `REPORT.md`, `predictions.csv`, `predictions.jsonl`, `series.html`을 생성한다. 전체 기간 그래프의 빈 값에서는 선을 끊는다. 원본·모델 SHA256과 선택 점수도 보조 보고서에 남긴다. 행정동 내국인 인구를 관광지 실제 방문객이나 TMAP 밀도로 해석하지 않는다.

## 검증 명령

```powershell
& ../.integration-venv/Scripts/python.exe manage.py test --noinput
& ../.integration-venv/Scripts/python.exe manage.py check
& ../.integration-venv/Scripts/python.exe manage.py makemigrations --check --dry-run
```

계산·누수·독립 정답·표본·신뢰구간 날짜·선택 고정·수정 거부·저장 재현·날씨 구분·보고서 행 보존을 검사한다. 기존 합성 DB 부하 결과는 이번 실제 예측 성능 지표와 합치지 않는다. 최소 수집 일정은 약 105일에 단계 계산 및 실행 지연을 더한 기간이다.
