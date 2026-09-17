# 행사 안내와 30일 행사 보정 실험

TourAPI 목록·변경 조회는 시간당 한 번 실행한다. 기존 공유 예산, 재시도와 수집기 잠금을 사용한다. `event_details`는 변경된 행사 최대 5건씩 처리하며 활성 대상 연결을 우선한다. 목록에서 사라진 것은 취소가 아니다. TourAPI의 업데이트 속도나 집회 포괄성을 보장하지 않는다.

## 운영 순서

백엔드 디렉터리에서 프로젝트 가상환경 Python을 사용한다.

```powershell
python manage.py migrate
python manage.py event_crowd init
python manage.py collect_crowd_inputs --once --max-seconds 45
python manage.py event_crowd tick
python manage.py event_crowd reproduce
python manage.py event_crowd report --output ../output/event-validation/provider-reports.json
```

`init`는 기존 행사의 새 이력 최초 확인 시각을 실행 시각으로 기록한다. 기존 과거 수신 이력을 만들어내지 않는다. 반복 실행은 이미 이관한 행사를 변경하지 않는다. 기존 Windows 정시 평가 작업에서 `tick`도 실행한다. 새 예약 작업을 추가할 필요는 없다.

Django 관리자 `/admin/`에서 TourEvent를 등록한다. 집회는 `source=manual`, `external_id=manual:...`, 공식 출처 URL을 입력한다. 반복 행사일 때만 확인된 family/edition을 함께 지정한다. 행사 변경·취소는 삭제 대신 상태 변경으로 기록한다. EventTargetLink에서 HourlyTarget을 선택하고 영향 구역 근거를 입력한 뒤 verified를 체크한다. 행진은 대상 구역별 시작·종료 시각을 입력한다. 거리로 자동 연결하지 않는다. 연결 해제도 삭제가 아니라 verified 해제로 처리한다.

TourAPI 날짜만 있는 자료는 그대로 date_only로 취급한다. 자유 텍스트 운영시간을 자동으로 확정된 시각으로 변환하지 않는다. 상세 원문을 확인한 관리자가 정확한 시각을 지정한다.

## API / 화면

혼잡도 응답에 현재 시각 `event_context`, 정시 1·2·3시간 `event_contexts`, 각 예측의 `event_context`를 추가한다. 각 컨텍스트에는 `valid_at`, `checked_at`, `collection_status`, `coverage=registered_events_only`, `events`가 있다. 행사에는 이름·출처·기간·확인 시각·메시지가 있다. 날짜만 있으면 시간 미확인, 수집 성공 후 3시간이 지나면 확인 지연으로 표시한다. 빈 목록을 행사 없음으로 해석하지 않는다.

카드·상세는 방문 시각이 정확하게 일치하는 컨텍스트를 선택한다. 안내는 숫자 예측 유무와 독립적이며 추천 점수를 바꾸지 않는다. 수동 행사는 기존 거리 기반 보정에 입력하지 않는다. 기존 TourAPI 거리 보정을 사용하는 레거시 경로는 유지되며 새 30일 실험에서는 사용하지 않는다.

## 비공개 계산·검증

`hourly-event-30day-v1`: 30일 평균, 반감기 없음, tau=3. 기존 84일 운영 모델과 승인 기록은 수정하지 않는다. 동일 조건의 30일 무보정 모델 및 산술평균을 비교한다. 숫자 보정은 같은 대상·공급자·반복 행사에서 서로 다른 완료 회차가 3개 이상일 때만 계산한다. 회차별 잔차 평균에 n/(n+8)을 적용한다. 현재 잔차에서 현재 행사 효과도 차감한다. 복수 행사·불명확한 시간·검증되지 않은 연결·표본 부족은 숫자 보정하지 않는다.

과거 400일에서 행사 효과를 계산하고, 발행 당시의 행사 버전 및 0·1·2·3시간별 파생 효과·참고 회차를 실행 입력에 고정한다. 일반 인구 입력은 30일과 현재값의 버전 상한·해시로 재현한다. 이 방식은 400일 원본 보관으로 300일 예측 기록을 재현할 수 있게 한다. 파생 효과는 관측 ID 전체 목록을 반복 저장하지 않는다.

```powershell
python manage.py event_crowd replay --target 1 --start 2026-09-01T00:00:00+09:00 --end 2026-09-02T00:00:00+09:00
python manage.py event_crowd freeze --study 1 --start 2026-11-01T00:00:00+09:00
python manage.py event_crowd validate --study 1
python manage.py event_crowd validate-shadow --study 1
python manage.py event_crowd promote --study 1
python manage.py event_crowd monitor --study 1
python manage.py event_crowd rollback --study 1
python manage.py event_crowd prune
```

날짜는 예시다. 선택 시작 이전 56일의 평균으로 정규화하고, 선택 14일의 공통 쌍에서 비교 모델을 고정한다. 실제 동결 이후 시작하는 최종 14일, 그 다음 실제 발행 14일을 따로 검사한다. 경계를 가로지르는 행사·정답은 제외한다. 대상마다 평가 회차가 있어야 하며 인구/밀도를 합산하지 않는다. 필요한 정답·회차·날짜가 부족하면 승격이 거절된다. 기존 PASS만으로는 승격되지 않는다. 순위는 행사 실험의 순위 검증도 통과해야 한다.

`promote`는 명시적인 운영 명령이다. 앱 연결은 기존 승인된 대상 경로 안에서만 행사 모델로 바뀐다. 최근 7일 정답이 충분하며 품질 악화가 3일 연속이면 tick에서 승격을 해제한다. 행사 안내는 독립적으로 유지한다.

## 완료 상태 (2026-09-16)

- 행사 안내·이력·수동 등록·보정 실험 코드 및 마이그레이션 구현.
- 기존 행사 904건을 현재 확인 시각으로 이관. 검증된 영향 구역 연결은 자동으로 만들지 않음.
- 실제 시간당 관측 4건: 30일 평균 및 행사 회차 검증에 부족. 보고 상태는 NEEDS_MORE_DATA.
- 실제 예측 정확도나 행사 효과의 인과성은 검증 완료가 아님. 새 모델 승격 안 함.
- 사후 확인한 월드컵·집회 일정은 운영 과거 입력으로 소급 주입하지 않음.
