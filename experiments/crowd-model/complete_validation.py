"""Execute offline stage-1 checks and write auditable completion evidence."""
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
from run import ROOT, protected_hashes, encode
from area_validation import read_assessment


def main():
    output = Path(__file__).parent/'completion-results'
    output.mkdir(exist_ok=True)
    before = protected_hashes()
    frontend = ROOT/'tourist_congestion_frontend'
    frontend_before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for folder in ('lib', 'test') for p in (frontend/folder).rglob('*.dart')}
    checks = []
    commands = [
        ('experiment_tests', [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'experiments/crowd-model', '-p', 'test_*.py', '-v'], ROOT),
        ('django_check', [sys.executable, '-B', 'manage.py', 'check'], ROOT/'tourist_congestion_backend'),
        ('django_tests', [sys.executable, '-B', 'manage.py', 'test', '--verbosity', '2'], ROOT/'tourist_congestion_backend'),
        ('flutter_contract', ['cmd.exe', '/d', '/c', r'C:\Users\poplo\development\flutter\bin\flutter.bat', 'test', '--no-pub', 'test/crowd_estimate_test.dart'], frontend),
    ]
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONIOENCODING': 'utf-8'}
    for name, cmd, cwd in commands:
        print('Running '+name, flush=True)
        started = datetime.now(timezone.utc)
        try:
            process = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
            log = process.stdout+'\n'+process.stderr
            code = process.returncode
        except subprocess.TimeoutExpired:
            log, code = 'TIMEOUT after 180 seconds; check not passed.', -1
        (output/(name+'.log')).write_text(log, encoding='utf-8')
        count = re.search(r'Ran (\d+) tests?', log)
        flutter_count = re.findall(r'\+(\d+)', log)
        checks.append({'name': name, 'command': cmd, 'cwd': str(cwd), 'exit_code': code,
                       'status': 'PASS' if code == 0 else 'FAIL', 'started_at': started.isoformat(),
                       'ended_at': datetime.now(timezone.utc).isoformat(),
                       'tests': int(count.group(1)) if count else int(flutter_count[-1]) if name == 'flutter_contract' and flutter_count else None,
                       'log': name+'.log'})
    deterministic = ['metrics.json', 'observations.json', 'splits.json', 'manifest.json', 'synthetic_checks.json', 'deferred.json']
    hashes = []
    for iteration in (1, 2):
        destination = output/f'replay-{iteration}'
        process = subprocess.run([sys.executable, '-B', 'experiments/crowd-model/run.py', '--output', str(destination)],
                                 cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=180)
        (output/f'replay-{iteration}.log').write_text(process.stdout+'\n'+process.stderr, encoding='utf-8')
        if process.returncode:
            hashes.append(None)
        else:
            hashes.append({name: hashlib.sha256((destination/name).read_bytes()).hexdigest() for name in deterministic})
    same = hashes[0] is not None and hashes[0] == hashes[1]
    stage2 = read_assessment(ROOT/'tourist_congestion_backend/db.sqlite3', datetime.now(timezone.utc))
    unchanged = before == protected_hashes() and all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == h for p, h in frontend_before.items())
    stage1 = 'PASS' if all(c['status'] == 'PASS' for c in checks) and same and unchanged else 'FAIL'
    manifest = json.loads((output/'replay-2/manifest.json').read_text(encoding='utf-8')) if hashes[1] else {}
    if manifest.get('forward_pairs') != 0:
        stage1 = 'FAIL'
    evidence = {'checked_at': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(),
                'platform': platform.platform(), 'checks': checks, 'stage_1': stage1, 'stage_2': stage2,
                'stage_3': {'status': 'NOT_STARTED', 'reason': 'No independent venue crowd labels'},
                'protected_files_unchanged': unchanged, 'separate_process_rerun_identical': same,
                'deterministic_hashes': hashes, 'forward_pairs': manifest.get('forward_pairs'),
                'secret_hashes_exported': False}
    (output/'evidence.json').write_text(encode(evidence)+'\n', encoding='utf-8')
    table = '\n'.join(f"| {c['name']} | {c['status']} | {c['tests'] if c['tests'] is not None else '—'} |" for c in checks)
    report = f'''# 혼잡도 검증 단계별 완료 보고서

검증 시각: {evidence['checked_at']}

| 단계 | 상태 | 판정 |
|---|---|---|
| 1. 구현·실험 신뢰성 | {stage1} | 필수 명령·계산·누수·재현성·계약 검증 |
| 2. 영역 예측 성능 | {stage2['status']} | 현재 순방향 평가 표본과 경험적 기준선 부족 |
| 3. 관광지 체감 혼잡 | NOT_STARTED | 독립 현장 정답 없음 |

**{'구현·실험 검증 완료, 실제 정확도 미검증' if stage1 == 'PASS' else '구현 검증 미완료: 아래 실패 명령 확인 필요'}**

## 실행 결과

| 검사 | 결과 | 테스트 수 |
|---|---|---:|
{table}

수작업 사례는 원 인구 평균·median, 로그 목표 1·3에서 Ridge 기울기 2/3,
Hybrid A 변화율 1, 완전히 분리된 두 leaf stump를 검증한다.
평가 target을 바꾸고 재분할·재학습하며, 순서 변경과 행 제거의 불변성도 검사한다.
합성 사례는 테스트에만 사용하며 실제 모델 성능 지표에는 포함하지 않는다.

Django 전체 테스트 로그에는 정상값·대체값·TTL·미래 수신, 날씨 결측,
매핑 충돌, horizon·버전·영역 분리, API 호환·외부 요청 및 N+1 검사가 포함된다.
Flutter 계약 테스트는 예상 5단계·낮은 신뢰도·추천 제외 동작을 확인한다.
이는 전체 기기 UI·현장 정확도 검증을 의미하지 않는다.

## 재현성과 보존

- 별도 두 프로세스 결과 동일: **{same}**. 실행 시간은 해시 비교에서 제외했다.
- 운영 Python·DB·환경설정 및 Flutter 소스·테스트 보존: **{unchanged}**.
- 실제 수신 시점을 지킨 미래 평가 쌍: **{manifest.get('forward_pairs')}개**.
- 비밀키와 비밀키 파일 해시는 결과에 내보내지 않았다.
- 명령·환경·입력 해시·실행 로그: `experiments/crowd-model/completion-results/evidence.json` 및 같은 폴더.

## 영역 예측 평가 준비와 제한

읽기 전용 평가기를 추가했다. 모델 버전·기준선 정책·horizon별로 분리하고,
같은 정답 행에서 영역 균등 MAE를 비교한다. 목표 시각 이후 5분 이내 관측,
24시간 이내 수신만 인정한다. 표본 100개·7일·2영역·평일과 주말을 요구한다.
KST 발행 날짜를 2,000회 재표집(seed 20260913)하고, 각 표본에서 영역 균등 MAE를
다시 계산한다. 두 비교 모델보다 MAE가 낮고 오차 차이 95% 구간 상한이 모두 0 미만일 때만 통과한다.
평가 완료 여부와 성능 통과 여부는 별도 필드로 기록한다.

현재 결과는 BLOCKED다. 합성 PASS/FAIL 테스트는 실제 정확도 증거가 아니다.
121개 균등 수집·약 220분 주기·기준선 조건·정답 창을 변경하지 않았으며,
자동 운영 중단이나 새 API 호출을 추가하지 않았다. 완료 날짜는 보장하지 않는다.

## 운영 결정

[모델 선정 보고서](MODEL_SELECTION_REPORT.md)의 결론을 유지한다.
운영 후보는 heuristic-v1.2, fallback은 낮은 신뢰도의 유형·시간 prior다.
Hybrid A의 보조 회고적 인구 재현 결과를 제품 정확도나 POI 방문객 수로 해석하지 않는다.
독립 현장 조사와 사용자 데이터 수집은 시작하지 않았다.
'''
    (ROOT/'VALIDATION_COMPLETION_REPORT.md').write_text(report, encoding='utf-8')
    print(encode({'stage_1': stage1, 'stage_2': stage2['status'], 'stage_3': 'NOT_STARTED', 'checks': checks}))
    return 0 if stage1 == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
