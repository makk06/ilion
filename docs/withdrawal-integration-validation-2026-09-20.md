# 회원 탈퇴 PR #15 / #16 통합 검증

> **후속 변경(2026-09-21):** 아래 검증 결과는 당시 상태의 이력입니다. 현재 작업 브랜치는 기기 위치를 비활성화하고 최종 파기 시 현재 첨부 사진을 삭제합니다. [후속 작업/검증 기록](release-readiness-2026-09-21.md)을 함께 확인하세요.

검증일: 2026-09-20. 원본 PR head: #15 a3acad565e, #16 edba96729f.
기준 main: f2596da. 운영 배포 및 실제 사용자 데이터 변경은 수행하지 않았다.

## 통합 계약

- 신청: `POST /api/me/withdraw`, bearer + 비밀번호(이메일 계정) 또는 Google id_token.
- 신청 직후 모든 refresh 폐기, inactive 계정 access 거부, 7일 후 파기 예약.
- 기한 내 로그인: 403 + `withdrawal_pending` + `purge_at`.
- 철회: `POST /api/me/withdraw/cancel`, 본인 확인 및 명시적 동의 후 세션 재발급.
- 동일 이름 WithdrawView 중복과 PR #16의 별도 DELETE 경로를 제거했다.
- 비활성 Google 계정 토큰 발급과 Google 경유 재가입 제한 우회를 차단했다.
- 파기/철회는 트랜잭션 안에서 계정을 잠그고 현재 상태를 다시 검사한다.
  한 계정 파기 실패는 다음 계정 처리를 막지 않으며 다음 실행에서 재시도한다.
- 보호된 탈퇴/비밀번호 변경 요청은 만료 access를 갱신하고 한 번 재시도한다.
  로그인 실패·철회 실패를 토큰 갱신으로 처리하지 않는다.

## 검증 결과

- #15 보완 상태 Django 전체: 293 tests PASS.
- #15 + #16 통합 Django 전체: 305 tests PASS.
- Flutter 3.47.5 / Dart 3.13.4: analyze PASS, tests 93 PASS, web build PASS.
  SDK가 고정하는 패키지 5개의 lockfile 변경도 함께 검증했다.
- Django `makemigrations --check --dry-run`: 변경 없음.
- Django production `check --deploy --fail-level WARNING`: PASS.
- 임시 DB에서 최신 스키마 신규 생성 PASS.
- 마이그레이션 테스트: config.0001 적용 DB → users.0007 업그레이드,
  SQLite 백업/무결성, 미승인 대상 거부 PASS.
- 격리 서버 실제 HTTP: 가입 → 탈퇴 → 기존 access/refresh 거부 → pending 로그인
  → 이전 헤더를 포함한 본인 확인 철회 → 새 access로 프로필 접근 PASS.
- 프런트 회귀: 돌아가기 무요청, 성공 시 세션 삭제, 실패 시 세션 유지,
  중복 제출 방지, 철회 동의/거절, 철회 기한 오류, 만료 토큰 갱신 PASS.
  390×844 및 1440×1000 위젯 크기에서 검증했다.

## 제한 및 배포 전 확인

- 브라우저/네이티브 UI 제어 연결이 없어 실제 브라우저 클릭 및 스크린샷 검수는
  수행하지 못했다. 웹 빌드, 위젯 테스트, 실제 HTTP 검증으로 보완했다.
- 현재 Flutter 로그인은 이메일 계정만 지원한다. Google 탈퇴·철회는 API 모의
  Google 검증을 사용한 테스트이며 실제 Google OAuth 및 Flutter UI는 별도 검증 대상이다.
- 법률 문서는 #14의 **검토용 초안**이며 공개 약관으로 승인하지 않았다.
- 후기 텍스트/사진에는 개인정보가 남을 수 있다. 계정 연결 제거를 완전한 익명화
  또는 법적 적합성 검증으로 해석하지 않는다. 앱은 사전 직접 삭제를 안내한다.
- 운영 배포 전 독립된 50자 이상 WITHDRAWAL_HASH_KEY가 필요하다.
  deploy.json에는 이름만 추가했다. 운영 값 등록/조회는 하지 않았다.
- 운영 DB는 config.0001_merge_main_recommendation까지 먼저 적용되어야 한다.
  이전 DB의 정확한 이력 확인 없이 마이그레이션 대상을 우회하지 않는다.
- main 병합은 배포나 운영 데이터 파기 승인이 아니다.
- 비밀번호 변경 시 기존 access도 무효화하도록 JWT 비밀번호 지문 검사를 활성화했다.
  구 릴리스 토큰에는 지문이 없어 배포 후 한 번 재로그인이 필요하다.
