"""Provider-separated selection, untouched holdout, and real issued shadow gates."""
from datetime import timedelta
from statistics import mean
from django.utils import timezone
from places.hourly_models import HourlyStudy, HourlyForecast, HourlyDaily, HourlyObservation
from .hourly_forecast import PARAMETERS, METRICS, predict, samples, dt
from .hourly_store import dataset, calendar, digest, analysis_context
from .mean_validation import assess, metrics
from .hourly_decisions import CONTRACT, distribution, annotate, assess_decisions


def key(params):
    return f"half={params['half_life']};tau={params['tau']}"


def eligible(study):
    return study.targets.filter(selected=True).exclude(pk__in=study.state.get('zero_mean_targets', []))


def row(target, forecast, actual, calendar_values):
    at = dt(forecast['valid_at'])
    analysis = forecast.get('analysis', {})
    tags = [('holiday' if calendar_values.get(at.date().isoformat()) else 'weekend' if at.weekday() >= 5 else 'weekday')]
    if analysis.get('rain_forecast') is True:
        tags.append('rain_forecast')
    if analysis.get('rain_observed') is True:
        tags.append('rain_observed')
    if analysis.get('verified_event') is True:
        tags.append('event')
    return {'area_id': target.pk, 'issued_at': forecast['issued_at'], 'valid_at': forecast['valid_at'],
            **{k: forecast.get(k) for k in ('provider', 'external_id', 'metric', 'unit', 'scope')},
            'hours_ahead': forecast['hours_ahead'], 'population': forecast['value'], 'actual': actual,
            **forecast['comparisons'], 'parameters': forecast['parameters'],
            'tags': tags, 'analysis': analysis, 'reasons': forecast.get('reasons', [])}


def gate(rows, study):
    state = study.state
    report = assess(rows, list(eligible(study).values_list('pk', flat=True)),
                    state['scales'], state['peaks'], reference='reference', required_areas=None, date_field='valid_at', strict_coverage=True,
                    relative_peak_threshold=CONTRACT['very_busy_above'])
    report['provider'] = study.provider
    report['metric'], report['unit'], report['scope'] = METRICS[study.provider]
    report['metrics']['value'] = report['metrics'].pop('population')
    report['zero_mean_targets'] = study.state.get('zero_mean_targets', [])
    report['parameters'] = state.get('parameters')
    report['selected_reference'] = state.get('reference')
    report['scales'], report['peaks'] = state['scales'], state['peaks']
    report['targets'] = list(eligible(study).values('id', 'external_id', 'name'))
    report['numeric_status'] = report['status']
    report['usability'] = assess_decisions(rows, state['peaks'], list(eligible(study).values_list('pk', flat=True)))
    guidance = report['usability']['guidance']
    if report['status'] != 'FAIL' and guidance['status'] != 'PASS':
        report['status'] = guidance['status']
        report['reasons'] += guidance['reasons']
    if not state.get('selection_guidance_pass', False) and report['status'] == 'PASS':
        report.update(status='NEEDS_MORE_DATA', reasons=['selection_decision_gate_not_passed'])
    report['decision_contract_version'] = CONTRACT['version']
    report['decision'] = ('eligible_for_next_stage' if report['status'] == 'PASS' else
                          'keep_arithmetic_no_promotion' if report['status'] == 'FAIL' else 'collect_more_data')
    return report


def missing(reason):
    return {'status': 'NEEDS_MORE_DATA', 'reasons': [reason]}


LOCK_FIELDS = ('parameters', 'reference', 'recent_parameters', 'scales', 'peaks', 'frozen_at', 'holdout_start', 'frozen_targets', 'decision_contract', 'selection_guidance_pass', 'selection_ranking_pass')


def selection_hash(study):
    return digest({k: study.state.get(k) for k in LOCK_FIELDS})


def require_frozen(study):
    state = study.state
    if state.get('decision_contract') != CONTRACT:
        raise ValueError('Decision contract changed; a new untouched evaluation is required')
    if not state.get('selection_hash') or state['selection_hash'] != selection_hash(study):
        raise ValueError('Missing or changed selection contract; a new experiment is required')
    if sorted(eligible(study).values_list('pk', flat=True)) != state['frozen_targets']:
        raise ValueError('Evaluation cohort changed; a new experiment is required')
    if dt(state['frozen_at']) >= dt(state['holdout_start']):
        raise ValueError('Selection must finish before the untouched holdout')


def select_parameters(study, now=None):
    now = dt(now or timezone.now())
    targets = list(eligible(study).select_related('study'))
    if not targets or not study.state.get('training_start'):
        return missing('collection_or_selection_incomplete')
    start = dt(study.state['training_start'])
    tune, test, end = (start+timedelta(days=d) for d in (56, 70, 84))
    if now < test:
        return missing('training_and_selection_period_incomplete')
    if 'parameters' in study.state:
        require_frozen(study)
        return {'status': 'FROZEN', 'holdout_start': study.state['holdout_start']}
    data = {t.pk: dataset(t, test)[0] for t in targets}
    truths = {t.pk: samples(data[t.pk], test) for t in targets}
    if 'parameters' not in study.state:
        scales, peaks, blocked = {}, {}, []
        for t in targets:
            values = sorted(r['value'] for at, r in truths[t.pk].items() if start <= at < tune)
            if len(values) < .9*56*24:
                return missing('training_coverage_below_90_percent')
            scale = mean(values)
            if scale <= 0:
                blocked.append(t.pk)
                continue
            scales[str(t.pk)] = scale
            peaks[str(t.pk)] = values[int(.9*(len(values)-1))]
        study.state['zero_mean_targets'] = sorted(set(study.state.get('zero_mean_targets', [])+blocked))
        study.save(update_fields=['state'])
        targets = [t for t in targets if t.pk not in blocked]
        if not targets:
            return missing('zero_training_mean')
        choices = {key(p): [] for p in PARAMETERS}
        reference_rows = []
        at = tune
        while at+timedelta(hours=3) < test:
            cal = calendar(at, at-timedelta(days=84))
            for target in targets:
                source = {**data[target.pk], 'calendar': cal}
                dist = distribution(source, at)
                for params in PARAMETERS:
                    for forecast in predict(source, at, params):
                        actual = truths[target.pk].get(dt(forecast['valid_at']), {}).get('value')
                        choices[key(params)].append(annotate(row(target, forecast, actual, cal), dist))
            at += timedelta(hours=1)
        # Same issue/target rows for every candidate and comparator during selection.
        good_indices = [i for i in range(len(next(iter(choices.values()))))
                        if all(rs[i]['population'] is not None and rs[i]['actual'] is not None for rs in choices.values())
                        and all(next(iter(choices.values()))[i].get(k) is not None for k in ('weekly', 'persistence', 'arithmetic'))]
        reference_rows = next(iter(choices.values()))
        good_set = set(good_indices)
        coverage = {}
        for target in targets:
            for h in (1, 2, 3):
                indices = [i for i, r in enumerate(reference_rows) if r['area_id'] == target.pk and r['hours_ahead'] == h]
                coverage[f'{target.pk}:{h}'] = sum(i in good_set for i in indices)/len(indices) if indices else 0
        if any(v < .9 for v in coverage.values()):
            return missing('selection_pair_coverage_below_90_percent')
        scores = {k: metrics([rs[i] for i in good_indices], 'population', scales, peaks)['nmae'] for k, rs in choices.items()}
        decision_scores = {k: assess_decisions([rs[i] for i in good_indices], peaks, [t.pk for t in targets]) for k, rs in choices.items()}
        safe = [p for p in PARAMETERS if decision_scores[key(p)]['guidance']['status'] == 'PASS']
        rank_safe = [p for p in safe if decision_scores[key(p)]['ranking']['status'] == 'PASS']
        winner = min(rank_safe or safe or PARAMETERS, key=lambda p: (scores[key(p)], (p['tau'] is not None)+(p['half_life'] is not None), key(p)))
        reference_rows = [next(iter(choices.values()))[i] for i in good_indices]
        refs = {k: metrics(reference_rows, k, scales, peaks)['nmae'] for k in ('arithmetic', 'weekly', 'persistence')}
        for params in PARAMETERS:
            if params['tau'] is None:
                refs[key(params)] = scores[key(params)]
        reference = min(refs, key=lambda k: (refs[k], k))
        recent = min((p for p in PARAMETERS if p['tau'] is None and p['half_life'] is not None),
                     key=lambda p: (scores[key(p)], key(p)))
        study.state.update(parameters=winner, reference=reference, scales=scales, peaks=peaks,
                           decision_contract=CONTRACT, selection_guidance_pass=bool(safe), selection_ranking_pass=bool(rank_safe),
                           selection_decisions=decision_scores, recent_parameters=recent, tuning_scores=scores, reference_scores=refs, selection_coverage=coverage)
        # Start a fresh, untouched period AFTER calculation and durable selection.
        completed = max(now, dt(timezone.now()))
        study.state.update(frozen_at=completed.isoformat(),
            nominal_holdout_start=test.isoformat(),
            late_selection=completed > test,
            holdout_start=(completed.replace(minute=0, second=0, microsecond=0)+timedelta(hours=1)).isoformat(),
            frozen_targets=sorted(t.pk for t in targets))
        study.state['selection_hash'] = selection_hash(study)
        selected_fields = (*LOCK_FIELDS, 'selection_hash', 'nominal_holdout_start', 'late_selection',
                           'zero_mean_targets', 'selection_decisions', 'tuning_scores', 'reference_scores', 'selection_coverage')
        frozen = {k: study.state[k] for k in selected_fields}
        # Optimistic update keeps concurrent collector metadata and rejects a second selection.
        for _ in range(3):
            latest = HourlyStudy.objects.get(pk=study.pk)
            if 'parameters' in latest.state:
                raise ValueError('Selection already frozen by another process')
            updated = {**latest.state, **frozen}
            if HourlyStudy.objects.filter(pk=study.pk, state=latest.state).update(state=updated):
                study.state = updated
                break
        else:
            raise ValueError('Concurrent study change; retry selection')
    return {'status': 'FROZEN', 'parameters': study.state['parameters'], 'holdout_start': study.state['holdout_start']}


def evaluate(study, now=None, output=None):
    now = dt(now or timezone.now())
    if 'parameters' not in study.state:
        return missing('selection_not_frozen')
    require_frozen(study)
    test = dt(study.state['holdout_start'])
    end = test+timedelta(days=14)
    targets = list(eligible(study).select_related('study'))
    data = {t.pk: dataset(t, min(now, end))[0] for t in targets}
    truths = {t.pk: samples(data[t.pk], min(now, end)) for t in targets}
    if now < end:
        return missing('final_evaluation_period_incomplete')
    result = []
    at = test
    while at+timedelta(hours=3) < end:
        cal = calendar(at, at-timedelta(days=84))
        for target in targets:
            source = {**dataset(target, at)[0], 'calendar': cal}
            dist = distribution(source, at)
            forecasts = predict(source, at, study.state['parameters'])
            context = analysis_context(target, at)
            ref_params = next((p for p in PARAMETERS if key(p) == study.state['reference']), None)
            references = predict(source, at, ref_params) if ref_params else None
            recent = predict(source, at, study.state['recent_parameters'])
            for i, forecast in enumerate(forecasts):
                forecast['analysis'] = context[forecast['hours_ahead']]
                actual = truths[target.pk].get(dt(forecast['valid_at']), {}).get('value')
                r = row(target, forecast, actual, cal)
                r['reference'] = references[i]['value'] if references else r[study.state['reference']]
                r['recent'] = recent[i]['value']
                result.append(annotate(r, dist))
        at += timedelta(hours=1)
    report = gate(result, study)
    report.update(period=[test.isoformat(), end.isoformat()], parameter_hash=digest(study.state['parameters']))
    report.update(evaluation_kind='operational_asof_replay', selection_hash=study.state['selection_hash'])
    if output:
        from .hourly_reporting import export_report
        export_report(output, report, result)
    study.state['validation'] = report
    if report['status'] == 'PASS' and not study.state.get('shadow_start'):
        completed = max(now, dt(timezone.now()))
        study.state['shadow_start'] = completed.replace(minute=0, second=0, microsecond=0)+timedelta(hours=1)
        study.state['shadow_start'] = study.state['shadow_start'].isoformat()
    study.save(update_fields=['state'])
    return report


def stored_rows(study, start, end):
    targets = list(eligible(study).select_related('study'))
    found = {(f.run.target_id, dt(f.run.issued_at), f.payload['hours_ahead']): f for f in
             HourlyForecast.objects.filter(run__target__study=study, run__issued_at__gte=start,
                 run__issued_at__lt=end).select_related('run__target')}
    truths = {}
    for target in targets:
        query = HourlyObservation.objects.filter(target=target, observed_at__gte=dt(start)-timedelta(minutes=15),
            observed_at__lt=end, received_at__lte=end).values('id', 'observed_at', 'received_at', 'value')
        truths[target.pk] = samples({'observations': list(query)}, dt(end))
    rows = []
    at = dt(start)
    while at+timedelta(hours=3) < dt(end):
        for target in targets:
            recent_values = reference_values = None
            for h in (1, 2, 3):
                f = found.get((target.pk, at, h))
                valid_at = at+timedelta(hours=h)
                actual = truths[target.pk].get(valid_at, {}).get('value')
                if f and f.run.parameters == study.state['parameters'] and dt(f.run.computed_at) <= valid_at:
                    r = row(target, f.payload, actual, f.run.inputs['calendar'])
                    if recent_values is None:
                        source, _ = dataset(target, at, f.run.inputs)
                        recent_values = predict(source, at, study.state['recent_parameters'])
                        dist = distribution(source, at)
                    r['recent'] = recent_values[h-1]['value']
                    # Compute only the comparison on the exact saved input version.
                    ref_params = next((p for p in PARAMETERS if key(p) == study.state['reference']), None)
                    if ref_params:
                        if reference_values is None:
                            reference_values = predict(source, at, ref_params)
                        r['reference'] = reference_values[h-1]['value']
                    else:
                        r['reference'] = r[study.state['reference']]
                else:
                    r = {'area_id': target.pk, 'issued_at': at.isoformat(), 'hours_ahead': h,
                         'valid_at': valid_at.isoformat(), 'population': None, 'actual': actual,
                         'arithmetic': None, 'reference': None, 'weekly': None, 'persistence': None,
                         'reasons': ['forecast_missing_or_not_issued_before_target']}
                if r.get('population') is not None:
                    annotate(r, dist)
                rows.append(r)
        at += timedelta(hours=1)
    return rows


def validate_shadow(study, now=None, output=None):
    now = dt(now or timezone.now())
    if study.state.get('validation', {}).get('status') != 'PASS' or not study.state.get('shadow_start'):
        return missing('holdout_not_passed')
    require_frozen(study)
    if study.state['validation'].get('selection_hash') != study.state['selection_hash']:
        raise ValueError('Holdout selection contract mismatch')
    start = dt(study.state['shadow_start'])
    end = start+timedelta(days=14)
    if now < end:
        return missing('14_day_shadow_incomplete')
    rows = stored_rows(study, start, end)
    report = gate(rows, study)
    report.update(period=[start.isoformat(), end.isoformat()], parameter_hash=digest(study.state['parameters']))
    report.update(evaluation_kind='actually_issued_shadow', selection_hash=study.state['selection_hash'])
    if output:
        from .hourly_reporting import export_report
        export_report(output, report, rows)
    study.state['shadow_validation'] = report
    study.save(update_fields=['state'])
    return report


def promote(study, now=None, target_ids=None):
    report = validate_shadow(study, now)
    if report['status'] != 'PASS' or study.state.get('validation', {}).get('parameter_hash') != digest(study.state['parameters']):
        raise ValueError('Real holdout and shadow PASS required for these parameters')
    # Explicit target route: a place already served by a promoted target is a conflict.
    used = {p for target in HourlyStudy.objects.exclude(pk=study.pk) for t in target.targets.filter(promoted=True)
            for p in t.mapping.get('place_ids', [])}
    targets = eligible(study)
    if target_ids is not None:
        targets = targets.filter(pk__in=target_ids)
        if targets.count() != len(set(target_ids)):
            raise ValueError('Only selected targets from this study may be promoted')
    if any(used.intersection(t.mapping.get('place_ids', [])) for t in targets):
        raise ValueError('Place already has another promoted provider; rollback it before switching')
    targets.update(promoted=True)
    return report


def monitor(now=None):
    now = dt(now or timezone.now())
    day = now.date()-timedelta(days=1)
    for study in HourlyStudy.objects.all():
        if 'parameters' not in study.state:
            continue
        targets = list(study.targets.filter(selected=True))
        recorded = set(HourlyDaily.objects.filter(target__in=targets, date=day).values_list('target_id', flat=True))
        if not targets or all(t.pk in recorded for t in targets):
            continue
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        rows = stored_rows(study, end-timedelta(days=7), end)
        ranking = assess_decisions(rows, study.state.get('peaks', {}), [t.pk for t in targets], min_days=7)['ranking']
        for target in targets:
            if HourlyDaily.objects.filter(target=target, date=day).exists():
                continue
            values = [r for r in rows if r['area_id'] == target.pk]
            matched = [r for r in values if all(r.get(k) is not None for k in ('population', 'arithmetic', 'actual'))]
            enough = all(sum(r['hours_ahead'] == h for r in matched) >= 100 for h in (1, 2, 3))
            errors = {h: {'mae': mean(abs(r['population']-r['actual']) for r in matched if r['hours_ahead'] == h),
                          'arithmetic_mae': mean(abs(r['arithmetic']-r['actual']) for r in matched if r['hours_ahead'] == h)}
                      for h in (1, 2, 3) if any(r['hours_ahead'] == h for r in matched)}
            bad = enough and any(v['mae'] > 1.1*v['arithmetic_mae'] for v in errors.values())
            usability = assess_decisions(values, study.state.get('peaks', {}), [target.pk], min_days=7)
            decision_bad = enough and usability['guidance']['status'] == 'FAIL'
            bad = bad or decision_bad
            summary = {'ranking_bad': ranking['status'] == 'FAIL', 'usability': usability, 'window': 'last_7_days', 'errors': errors, 'pairs': len(matched), 'bad': bad,
                       'provided_rate': mean(r.get('population') is not None for r in values) if values else 0,
                       'truth_rate': mean(r.get('actual') is not None for r in values) if values else 0}
            HourlyDaily.objects.create(target=target, date=day, payload=summary)
            previous = list(HourlyDaily.objects.filter(target=target, date__gte=day-timedelta(days=2), date__lte=day))
            if len(previous) == 3 and all(r.payload.get('bad') for r in previous):
                target.promoted = False
                target.save(update_fields=['promoted'])
            if len(previous) == 3 and all(r.payload.get('ranking_bad') for r in previous):
                study.state['ranking_suspended'] = True
                study.save(update_fields=['state'])


def advance(provider=None, output=None):
    """Hourly maintenance: advance independent studies, never promote automatically."""
    from pathlib import Path
    from .hourly_reporting import export_report
    reports = {}
    studies = HourlyStudy.objects.all()
    if provider:
        studies = studies.filter(provider=provider)
    for study in studies:
        directory = Path(output)/study.provider if output else None
        try:
            if 'parameters' not in study.state:
                report = select_parameters(study)
            elif 'validation' not in study.state:
                report = evaluate(study, output=directory/'holdout' if directory else None)
            elif study.state['validation']['status'] == 'PASS' and 'shadow_validation' not in study.state:
                report = validate_shadow(study, output=directory/'shadow' if directory else None)
            else:
                require_frozen(study)
                report = study.state.get('shadow_validation', study.state['validation'])
        except ValueError as exc:
            report = {'status': 'BLOCKED', 'reasons': [str(exc)]}
        from .hourly_collector import configured
        report = {**report, 'provider': study.provider, 'collection_configured': configured(study.provider),
                  'observation_count': HourlyObservation.objects.filter(target__study=study).count(),
                  'selected_targets': eligible(study).count()}
        reports[study.provider] = report
        if directory:
            export_report(directory/'status', {**report, 'provider': study.provider}, [])
    monitor()
    return reports
