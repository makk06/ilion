# 서울시 인구 / TMAP 밀도 시간당 예측

`hourly-mean-v2`는 기존 `area-mean-v1` 기록을 보존하는 별도 실험이다. 기존 앱 모델은 실제 holdout 및 14일 shadow가 모두 PASS일 때만 대상별로 전환한다. 생활인구 후향 실험의 37.2% 개선이나 합성 부하 테스트는 운영 성능 합격 근거가 아니다.

## 운영 설정과 시작

기존 backend `.env`에 승인된 계정 설정만 입력한다. 키를 버전 관리하거나 로그에 출력하지 않는다.

| 공급자 | 키 설정 | 일일 전체 호출 한도 | 같은 한도를 사용하는 다른 작업의 일일 예약량 |
|---|---|---|---|
| 서울시 | SEOUL_OPEN_API_KEY | SEOUL_DAILY_LIMIT | SEOUL_OTHER_DAILY_CALLS (기본 0) |
| TMAP | TMAP_APP_KEY | TMAP_DAILY_LIMIT | TMAP_OTHER_DAILY_CALLS (기본 0) |

활성 장소 수는 `min(10, floor(max(0, 0.8 × 한도 − 다른 작업 예약량) / 24))`다. 기존 서버 예산 장부에서 모든 요청과 재시도를 실제로 차감하므로 한도를 넘지 않는다. TMAP 대상 확인은 별도로 일일 20% 이내에서 실행한다. 공급자 콘솔의 여러 상품이 한도를 공유하면 예약량을 설정해야 한다. 다른 프로그램이 소비한 호출은 이 서버가 자동으로 알 수 없다.

백엔드 디렉터리에서 실행한다.

```powershell
python manage.py migrate --noinput
python manage.py hourly_crowd init --provider seoul
python manage.py hourly_crowd init --provider tmap
python manage.py hourly_crowd discover --provider tmap
python manage.py hourly_crowd status
```

init은 공급자별 한 번만 실행한다. 서울시는 검증된 관광지-구역 연결 수 내림차순·공급자 ID 순서로 최대 10곳을 등록한다. TMAP은 기존 관광지 순회에서 POI 이름과 주소가 공백 제거 후 정확히 일치하고 `type=1` 밀도가 실제 반환된 경우만 등록한다. 불일치/미지원 장소를 근접 장소로 바꾸지 않는다. 확인 명령은 예산 부족 시 커서를 저장하고 다음 날 재실행할 수 있다. 수집이 시작된 후에는 후보를 자동 교체하지 않는다. 등록된 후보만 한도 내 활성화되며 키·한도가 없으면 대기한다.

기존 `ops/collect-crowd.ps1` 또는 systemd timer에서 **매분** 호출하는 `collect_crowd_inputs --once`에 v2 작업을 연결했다. 새로운 외부 큐·DB·스케줄러 패키지는 없다. init만으로 OS 예약 작업이 설치되지는 않는다. 기존 OS 스케줄러가 실제 동작하는지 운영자가 확인해야 한다.

```powershell
python manage.py collect_crowd_inputs --once --max-seconds 45
# v2만 수동 점검 (동일 전역 lease 적용)
python manage.py hourly_crowd tick
```

서울시 v2가 초기화되면 기존 서울시 고빈도 수집을 v2의 시간당 수집으로 대체한다. 받은 인구는 기존 CrowdData에도 연결해 현재 정보 입력을 유지하지만, 시간당 수집 사이에는 기존 최신성 정책에 따라 오래된 정보로 표시될 수 있다. v1이 아직 앱에 승격되지 않았다면 v1 shadow 발행은 중단하고 기록은 남긴다. 날씨·행사·달력 수집은 유지한다.

## 시간과 예측 계약

- 매시 58~59분에 다음 정시용 자료를 수집한다. 동일 수집 슬롯은 한 번만 처리하며 내부 재시도도 예산을 사용한다.
- 정시 표본은 관측·수신 시각이 모두 정시 이하이고 관측 시각이 정시 전 15분 이내인 최신 유효 값이다. 동일 관측의 수정 버전은 첫 유효 수신을 사용한다. 늦게 도착한 정답을 과거에 있었던 것처럼 소급하지 않는다.
- 정시 후 첫 2분 동안 예측 작업이 실행될 수 있지만 입력 마감은 정시다. 실제 계산 완료 시각도 별도 저장한다. 더 늦게 실행되면 해당 발행은 누락되며 제공률 분모에는 포함된다.
- 최근 84개 완료 날짜에서 같은 시각·요일·공휴일 여부 → 평일/주말/공휴일 그룹 → 같은 시각 전체 순으로 최소 8일을 찾는다.
- 기본은 단순 평균이다. 선택 후보는 반감기 없음/14/28/56일 × τ 없음/0.5/1.5/3시간, 총 16개다.
- 현재 표본과 현재 시각 과거 평균의 차이를 `exp(-h/τ)`로 감쇠해 더한다. 현재가 없으면 보정 생략, 대상 과거가 없으면 null, 음수는 0으로 제한한다.
- 날씨·행사 가중치는 끈다. 발행 당시에 알려진 예보 강수 및 검증된 행사 맥락만 오류 분석 태그에 기록한다. 미래 예보 강수 태그는 실제 관측 강수 검증과 구분해야 한다. 확인되지 않은 행사·날씨는 null로 남긴다.

예측 공통 필드는 `provider`, `external_id`, `metric`, `unit`, `scope`, `issued_at`, `valid_at`, `hours_ahead`, `value`, `correction`, `sample_days`, `latest_observed_at`, `model_version`, `parameters`, `reasons`다.

| 공급자 | metric | unit | scope |
|---|---|---|---|
| 서울시 | population_count | persons | area_population |
| TMAP | population_density | persons_per_m2 | place_density |

밀도 예측의 `population`과 기존 응답의 `area_population`은 null이다. 상대 혼잡도는 해당 공급자/대상의 과거 분포 백분위다. 서로 다른 장소의 동일 점수가 같은 밀도라는 뜻이 아니며 점유율·정확도도 아니다. 화면은 TMAP 밀도에 명/㎡ 단위를 표시한다.

## 저장과 재현

HourlyObservation에는 인덱스가 있는 대상·관측 시각·수신 시각·수치 값과 수정 이력을 저장한다. 반복 수신은 값과 관측 시각으로 중복 제거한다. 원본은 `HOURLY_RAW_DIR`(기본 backend/hourly_raw)의 gzip 파일로 보관하고 DB에는 경로·해시만 저장한다.

한 정시의 세 예측은 HourlyRun의 입력 정보를 공유한다. 84일 조회 범위·입력 마감·관측 ID 상한·작은 달력 투영·입력 해시·모델 버전만 저장하고 전체 입력 ID 목록은 저장하지 않는다. 당시 관측이 없거나 해시가 달라졌으면 재현을 거부한다.

```powershell
python manage.py hourly_crowd reproduce --run 1 --output reproduced.json
python manage.py hourly_crowd prune
```

관측·원본은 400일, 상세 예측은 300일, 일별 집계는 400일 보관한다. 따라서 보존된 예측에 필요한 84일 입력이 먼저 삭제되지 않는다. 원본 정리는 지정된 원본 루트 안의 날짜별 gzip만 대상으로 하며 심볼릭 링크를 따라가지 않는다.

## 공급자별 평가와 승격

첫 7일의 168개 정시 슬롯 중 90% 이상 확보한 대상을 고정한다. 이후 56일 초기 학습·14일 선택·14일 최종 평가를 구분한다. 한 공급자의 준비 지연은 다른 공급자를 막지 않는다.

```powershell
# 선택 기간 종료 때 실행해 가중치 고정; 최종 평가 종료 후 같은 명령으로 holdout 평가
python manage.py hourly_crowd evaluate --provider seoul --output seoul-evaluation.json
python manage.py hourly_crowd evaluate --provider tmap --output tmap-evaluation.json
# holdout PASS 이후 실제 발행을 추가 14일 확보
python manage.py hourly_crowd shadow --provider seoul --output seoul-shadow.json
python manage.py hourly_crowd promote --provider seoul --target 1
python manage.py hourly_crowd rollback --provider seoul --target 1
python manage.py hourly_crowd monitor
```

TMAP도 동일 명령을 사용한다. `--target`을 생략하면 해당 공급자의 선택된 대상을 모두 적용한다. 이미 다른 공급자가 승격된 관광지와 충돌하면 기존 대상의 명시적 rollback 후 전환해야 한다. 결측을 다른 공급자로 대체하지 않는다.

정규화 분모는 해당 대상의 초기 학습 평균이며 밀도에도 실제 평균을 사용한다. 평균 0이면 선택·승격을 보류한다. 지표는 공급자별 MAE/RMSE/편향/NMAE와 장소·거리·날짜 유형·최고 혼잡 시간 오차, 제공률·정답 확보율이다. 혼잡 최고점 기준은 학습 90백분위로 고정한다.

대상/거리마다 100쌍·14일·평일/주말 포함, 제공/정답 확보율 90% 이상, 단순 평균 대비 NMAE 5% 개선, 선택 기간 최선 비교 모델보다 개선, 장소/거리/최고 혼잡 MAE 5% 초과 악화 없음, 2,000회 날짜 재표집 95% 신뢰구간의 개선 방향 확정을 모두 요구한다. 파라미터 해시가 바뀌면 기존 PASS로 승격할 수 없다. 부족하면 NEEDS_MORE_DATA, 악화면 FAIL이다.

매일 최근 7일에 거리별 정답 100쌍 이상이 있고, 어느 거리라도 단순 평균보다 MAE가 10% 초과 악화된 상태가 3일 연속이면 해당 대상 승격을 해제한다. 같은 날짜를 여러 번 실행해도 연속 일수는 늘지 않는다. 원래 앱의 동작으로 돌아가며 검증되지 않은 다른 공급자를 자동 선택하지 않는다.

## 검증 실행과 상태

```powershell
python manage.py test --noinput
flutter test --no-pub
python scripts/benchmark_hourly.py --output path-to-new-benchmark-directory
```

합성 부하 보고서는 `hourly-v2-verification.md`를 참고한다. 기능 테스트 통과는 공급자 API의 실제 제공 품질이나 예측 성능을 보증하지 않는다. TMAP 키·승인 한도 및 실제 장기 수신 이력이 없는 상태에서는 기능 구현과 설정 대기까지만 보고한다.
