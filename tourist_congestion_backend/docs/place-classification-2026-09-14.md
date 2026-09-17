# 장소 실내외 설명 근거 · 2026-09-14

> 아래는 최초 `description_v1`/`luna_description_v2` 구현 당시의 보존 기록이다.
> 현재 운영 계약·20+20 평가·호출 예산은
> [문맥 기반 분류와 검증 결과](./place-classification-context-evaluation-2026-09-14.md)를
> 우선한다. 아래의 문자 앵커·512 출력 토큰·실호출 5회 수치는 과거 시점 값이다.

이 구현은 공개 TourAPI 장소명·카테고리·상세 설명만 다룬다. 사용자 위치·프로필·행동은 분류 서비스나 OpenAI 호출에 보내지 않는다. 일반 추천 API와 DEBUG 테스트베드는 AI를 호출하지 않는다.

## 증거·순위 계약

- 수동 `manual` 분류는 자동 처리로 덮어쓰지 않는다. 수동도 별도 현장검증 정확도 보증은 아니다.
- `description_rule`은 설명의 짧고 명시적인 실내·실외 방문 표현만 채택한다. 부정, 주변/과거 시설, 상충 표현, 단지 다른 시설을 언급한 문장은 유보한다. 혼합 장소는 `mixed`이고 실내 필수에는 통과하지 않는다.
- `reviewed_name_rule_*`은 기존 좁은 장소명 추정이다. 출처가 있으나 `required_indoor_outdoor` 필수 조건은 통과하지 않는다.
- `luna_validated`는 별도 승인된 오프라인 AI의 추정이다. 원문 내 인용문·주활동 범위·부정/상충 여부를 로컬에서 재검증해도 사실 검증이 아니므로 실내 필수 조건에는 통과하지 않는다.
- 날씨와 실내외 선호 점수의 근거 강도는 수동 1.0, 설명 규칙 0.75, 이름 규칙 0.5, AI 추정 0.5다. 이는 경험적으로 측정한 정확도가 아닌 개발 초기의 순위 영향량이다. `weather_evidence_required`는 사용 가능한 예보+유효 분류가 있으면 통과하지만, `required_indoor_outdoor`는 수동/명시 설명 규칙만 통과한다.
- 자동 설명 분류 레코드는 방법·규칙 버전·SHA-256 입력 해시·정규화된 원문 속 정확한 인용문과 span·모델명(해당 시)·분류 시각을 저장한다. 장소명·카테고리·설명이 바뀌면 기존 자동 근거는 추천 시 즉시 비활성화하고 다음 상세 동기화/배치에서 재분류한다. 실패·애매한 AI 응답은 기존 유효한 이름 추정도 지우지 않는다.

## 이번 로컬 dry-run과 적용

설명 보유 407건을 비용 0으로 검사했다. 설명 규칙이 결정한 것은 7건이고 나머지 400건은 이 규칙에서 유보했다. 첫 dry-run의 변경 후보 11건 중 4건은 기존 개발 시드 이름 규칙 `v1`→`v2` 출처 표기 차이로, 이번 DB 적용 대상에서 제외했다. 승인된 아래 7건만 SQLite 백업 뒤 규칙 적용했다. 별도 승인된 Luna 호출 5회 결과는 아래와 같다.

| 장소 ID | 장소 | 전 → 후 | 근거 |
|---|---|---|---|
| 2565 | 놀이마루 | unknown → mixed | `실내와 실외 모두` |
| 3184 | 더베이101요트투어 | unknown → mixed | `실내 휴식공간과 야외 데크` |
| 8489 | 서울광장 스케이트장 | unknown → outdoor | `야외 스케이트장` |
| 25349 | 제주교육박물관 | name indoor → mixed | `상설 전시장과 기획 및 체험전시실, 야외전시장` |
| 31488 | 남포동 지하도상가 | unknown → indoor | `지하상가` |
| 34931 | 슈터스클럽 | unknown → indoor | `실내 사격장` |
| 38914 | 싱싱뽈락회 해운대본점 | unknown → indoor | `실내 공간` |

홀드아웃 4건은 규칙상 모두 유보했다. 확정 오분류를 관찰하지 않았다는 사실을 정확도로 해석할 수 없다. 설명 커버리지는 전체 장소의 일부이며, 이름/설명만으로 시설 개방 상태나 방문 동선은 판정하지 못한다.

실제 OpenAI Responses 호출은 총 **5회**, 반환 사용량 합계 입력 **2,045토큰**·출력 **249토큰**, DB 예산 예약 5/20회다. 1건(39603)만 AI 추정으로 적용했고 4건은 유보했다. 모의 응답 단위 테스트와 아래 실제 응답을 구분한다. 실호출은 이 다섯 건에서 중단했으며 전국 전수 AI 호출은 하지 않았다.

| 장소 ID | 모델 제안·원문 대조 | 최종 처리 |
|---|---|---|
| 27051 달개비 | 첫 버전 제안은 로컬 검증 불일치. `store:false`이고 당시 검수용 출력도 없어 문구 재구성 불가 | review, 적용 없음 |
| 39603 오반장 | `mixed`, 야외 테이블과 내부 공간을 모두 설명한 원문 연속 인용. 최초 응답 `scope=principal_place`를 혼합 장소에서 잘못 거절한 검증 버그를 수정하고 같은 입력 해시·인용문으로 **재호출 없이 사후 재검증** | `luna_validated/mixed` 적용, 필수 실내 불통과 |
| 26220 부산종합운동장 | `mixed`, 인용문에 실내체육관·야구장은 있으나 실외를 명시한 표현이 없음 | review, 적용 없음 |
| 42070 잠원수영장(실외) | `outdoor`, 인용문이 해당 장소의 노출이 아니라 “일반 야외수영장 이용요금”과의 비교 | review, 적용 없음 |
| 11357 서귀포홍리실내수영장 | `indoor`, 인용문이 장소명 자체뿐이어서 설명의 독립 근거가 아님. 최초 적용 직후 검증 규칙 강화에 따라 자동 라벨·근거를 회수 | review, 적용 없음 |

## 로컬 CLI · 예산

```bash
cd tourist_congestion_backend
.venv/bin/python manage.py classify_place_descriptions --limit 100
# 적용 전 출력된 ID·인용문을 사람이 검수한 뒤, 승인된 ID만 지정
.venv/bin/python manage.py classify_place_descriptions --apply --limit 7 --place-id 2565 --place-id 3184 --place-id 8489 --place-id 25349 --place-id 31488 --place-id 34931 --place-id 38914
```

기본은 읽기 전용 dry-run이다. `--limit` 최대 500. AI 배치는 애매하며 설명이 2,400자를 넘지 않는 장소만 대상이다. 실제 호출은 `OPENAI_API_KEY` 설정과 `--apply --ai --allow-live-ai --max-calls N` 네 조건이 모두 있어야 한다. 개발 환경에 키가 설정된 사실만 확인했으며 값은 콘솔/문서에 출력하지 않았다. 이번 7건 규칙 적용 재현 명령은 AI를 사용하지 않는다. 추가 실제 호출은 승인된 이번 5회 범위를 넘어 별도 판단이 필요하다.

AI 경로는 정확한 `gpt-5.6-luna`의 Responses API, `store:false`, `reasoning.effort:none`, strict JSON schema, 출력 최대 512토큰, 요청 15초, 설명 2,400자 제한을 사용한다. 로컬 일일 상한 20회와 명령당 `--max-calls`를 모두 적용하고 장소/입력/프롬프트 버전별 1회만 시도한다. 시도 예약과 예산 차감은 짧은 DB 트랜잭션에서 처리하고 네트워크 중 DB 잠금을 유지하지 않는다. 거부·불완전·타임아웃·잘못된 인용문은 적용하지 않고 오류 코드/사용 토큰 수만 저장한다. 실패 시 같은 입력은 자동 재시도하지 않는다. 원문 응답·오류 본문·키는 DB에 저장하지 않는다. `ProviderCallBudget`의 `openai_luna/classification` 사용량은 호출 예약 시 증가하므로 실제 과금량과 다를 수 있다.

참조: [Luna 모델 지원 범위](https://developers.openai.com/api/docs/models/gpt-5.6-luna), [Responses API](https://developers.openai.com/api/reference/cli/resources/responses/methods/create), [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
