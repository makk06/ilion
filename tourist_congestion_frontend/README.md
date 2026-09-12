# 이리ON 프런트엔드

Flutter 앱은 Django `/api`를 직접 사용하는 공통 HTTP 서비스와 인증 세션을 사용합니다. 서버가 꺼져 있으면 오류와 재시도 UI를 표시하며, 임시 관광지나 혼잡도 값으로 바꾸지 않습니다.

## 실행

백엔드 README에 따라 Python 환경을 준비하고 마이그레이션과 개발 시드를 적용한 뒤 서버를 실행합니다. 공공데이터 API 키는 백엔드 환경에만 설정합니다.

```powershell
flutter pub get
flutter run -d chrome --web-port 7357 --dart-define=API_BASE_URL=http://127.0.0.1:8000/api
```

Android 에뮬레이터는 호스트 PC를 `10.0.2.2`로 접근합니다.

```powershell
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api
flutter build apk --debug --dart-define=API_BASE_URL=http://10.0.2.2:8000/api
```

실제 Android 기기는 접근 가능한 서버 주소를 지정하고, 백엔드 `DJANGO_ALLOWED_HOSTS`도 해당 호스트를 허용해야 합니다. 운영 빌드는 HTTPS API 주소를 지정합니다. HTTP 허용은 Android debug manifest에만 적용합니다. iOS 실행·서명은 macOS/Xcode 환경이 필요합니다.

## 기능과 데이터

- 장소 검색·지역/혼잡도 필터·페이지 추가 조회: 기존 장소 API 사용
- 지도: OpenFreeMap 벡터 타일과 실제 관광지 좌표. `assets/maps/simple.json`에서 물·녹지·주요 도로·지역명과 옅은 건물 윤곽을 표시하며, 상점/시설 아이콘·도로번호는 제외합니다. 위치 권한 거부 시 지역 검색을 사용합니다.
- 길찾기: 선택한 장소 좌표를 카카오맵으로 전달. 직선 거리를 도보/차량 이동 시간으로 표시하지 않음
- 장소 상세: 실제 이미지, 소개, 운영시간, 연락처, 혼잡도 출처·관측 시각 표시
- 혼잡도: 데이터가 없으면 정보 없음, 오래된 관측값은 명시. 자체 예측값은 생성하지 않음
- 회원가입·로그인·토큰 갱신·로그아웃: 기존 인증 API와 기기 보안 저장소 사용
- 즐겨찾기·최근 본 장소·후기·사진·좋아요·동행·일정·문의·취향: 서버 저장
- 포인트: 서버 원장 조회. 후기 작성 보상은 장소별 최초 1회 기준
- 사진 첨부는 방문 인증을 의미하지 않음
- 제휴 리워드가 없는 경우 교환 불가 안내. 실제 상품 발급·푸시 알림 전송은 별도 운영 연동 필요

브라우저 보안 저장소는 HTTPS 또는 localhost 환경에서 사용합니다. 웹을 다른 도메인에 배포할 때는 백엔드 `CORS_ALLOWED_ORIGINS`에 정확한 프런트엔드 origin을 지정합니다. 로컬 DEBUG 모드에서는 localhost와 127.0.0.1 개발 포트를 허용합니다.

## 검증

```powershell
flutter analyze
flutter test
flutter build web --dart-define=API_BASE_URL=http://127.0.0.1:8000/api
```

위젯 테스트는 응답 형식, 오류 복구, 화면 이동과 상태를 확인합니다. 실제 서버 검증은 Django 테스트와 실행 중인 로컬 API를 별도로 사용합니다. 공공데이터 공급자의 실시간 수집 성공과 실제 기기의 위치/카메라 권한은 유효한 키와 해당 기기에서 추가 확인해야 합니다.
