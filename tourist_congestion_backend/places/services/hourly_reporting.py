"""Portable evaluation artifacts; no API calls or writes to operational evidence."""
import csv
import html
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from .hourly_forecast import dt


def export_report(directory, report, rows):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    fields = ['provider', 'external_id', 'area_id', 'metric', 'unit', 'scope', 'issued_at', 'valid_at', 'hours_ahead', 'value', 'actual',
              'arithmetic', 'weekly', 'persistence', 'recent', 'reference', 'reasons', 'tags', 'decision_scores', 'decision_contract_version']
    with (root/'predictions.csv').open('w', newline='', encoding='utf-8-sig') as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            value = {k: row.get(k) for k in fields}
            value['value'] = row.get('population')
            for k in ('reasons', 'tags', 'decision_scores'):
                value[k] = json.dumps(value[k] or [], ensure_ascii=False)
            writer.writerow(value)
    with (root/'predictions.jsonl').open('w', encoding='utf-8') as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, default=str, allow_nan=False)+'\n')
    errors = defaultdict(list)
    for row in rows:
        if row.get('population') is not None and row.get('actual') is not None:
            errors[dt(row['valid_at']).date().isoformat()].append(abs(row['population']-row['actual']))
    report['worst_dates'] = sorted([{'date': day, 'mae': mean(v), 'pairs': len(v)}
                                  for day, v in errors.items()], key=lambda v: (-v['mae'], v['date']))[:10]
    (root/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str, allow_nan=False), encoding='utf-8')
    lines = ['# 시간당 예측 검증 보고서', '', f"판정: **{report['status']}**", '',
             f"자료 구분: {report.get('evaluation_kind', 'operational')}", '',
             '실제값은 공급자 추정치다. 보조 자료·합성 실험은 운영 성능 합격 근거가 아니다.', '',
             '## 비교 성능', '', '| 방법 | NMAE | MAE | RMSE | 편향 |', '|---|---:|---:|---:|---:|']
    for name, result in report.get('metrics', {}).items():
        score = result.get('nmae')
        if score is not None:
            numbers = ' | '.join(f'{result[k]:.6g}' if result.get(k) is not None else '-' for k in ('mae', 'rmse', 'bias'))
            lines.append(f'| {name} | {score:.4%} | {numbers} |')
    lines += ['', '## 장소·거리별 오차', '', '| 장소:거리 | 쌍 수 | MAE | RMSE | 편향 |', '|---|---:|---:|---:|---:|']
    model = report.get('metrics', {}).get('value', report.get('metrics', {}).get('population', {}))
    for key, cell in model.get('cells', {}).items():
        lines.append(f"| {key} | {cell['count']} | {cell['mae']:.6g} | {cell['rmse']:.6g} | {cell['bias']:.6g} |")
    if report.get('usability'):
        u = report['usability']
        peak_label = ('평소보다 매우 붐빔 놓침' if u.get('contract', {}).get('peak_basis') == 'issuance_time_within_target_percentile' else '최고 혼잡 놓침')
        lines += ['', '## 방문 판단 검증', '', f"단계 안내: **{u['guidance']['status']}** · 장소 순위: **{u['ranking']['status']}**", '',
                  f'| 대상:거리 | 한산 오안내 | 분모 | {peak_label} | 분모 |', '|---|---:|---:|---:|---:|']
        for key, c in u['guidance']['cells'].items():
            a, b = c['false_relaxed']['model'], c['peak_miss']['model']
            ar = f"{a['rate']:.2%}" if a['rate'] is not None else '자료 부족'
            br = f"{b['rate']:.2%}" if b['rate'] is not None else '자료 부족'
            lines.append(f"| {key} | {ar} | {a['count']} | {br} | {b['count']} |")
        lines += ['', '오류율 차이 신뢰구간·순서 역전율·동률·미달 사유는 report.json에 포함한다. 보조 자료는 운영 승격 근거가 아니다.']
    lines += ['', '## 해석과 재현', '', *[f'- {r}' for r in report.get('reasons', [])],
              '- 신뢰구간·자료 확보율·조건별 분석·오차가 큰 날짜는 report.json에 기록한다.',
              '- 전체 평가 기간 그래프: [series.html](series.html). 원자료: predictions.csv / predictions.jsonl.',
              '- 그래프는 모든 발행을 포함하며 결측 지점에서 선을 끊는다. 날짜 선택으로 결과를 선별하지 않는다.']
    (root/'REPORT.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    plots = ['<!doctype html><html lang="ko"><meta charset="utf-8"><title>예측과 실제값</title>',
             '<style>body{font:16px system-ui;margin:28px}svg{width:100%;max-width:1200px}section{margin:32px 0}</style>',
             f'<h1>{html.escape(report.get("evaluation_kind", "운영 평가"))}</h1>',
             '<p>검정: 실제값 · 파랑: 예측 · 주황: 단순 평균. 가로축: 한국 시간, 세로축: 공급자 값.</p>']
    groups = defaultdict(list)
    for row in rows:
        groups[(str(row['area_id']), row['hours_ahead'])].append(row)
    for (area, horizon), group in sorted(groups.items()):
        group.sort(key=lambda r: dt(r['valid_at']))
        nums = [r[k] for r in group for k in ('actual', 'population', 'arithmetic') if r.get(k) is not None]
        if not nums:
            continue
        lo, hi = min(nums), max(nums)
        span = hi-lo or 1
        chart = [f'<section><h2>{html.escape(area)} / {horizon}시간</h2><svg viewBox="0 0 1200 270" role="img" aria-label="전체 기간 예측 비교">',
                 '<path d="M70 20V225H1160" fill="none" stroke="#aaa"/>',
                 f'<text x="0" y="25">{hi:.5g}</text><text x="0" y="225">{lo:.5g}</text>']
        for field, color in (('arithmetic', '#d97706'), ('actual', '#222'), ('population', '#2563eb')):
            command = []
            previous = False
            for i, r in enumerate(group):
                v = r.get(field)
                if v is None:
                    previous = False
                    continue
                x, y = 70+1090*i/max(1, len(group)-1), 225-205*(v-lo)/span
                command.append(f'{"L" if previous else "M"}{x:.2f},{y:.2f}')
                previous = True
            chart.append(f'<path d="{" ".join(command)}" stroke="{color}" fill="none" stroke-width="1.2"/>')
        for x, r in ((70, group[0]), (850, group[-1])):
            chart.append(f'<text x="{x}" y="255">{html.escape(r["valid_at"][:16])}</text>')
        plots += chart+['</svg></section>']
    (root/'series.html').write_text('\n'.join(plots)+'</html>', encoding='utf-8')
