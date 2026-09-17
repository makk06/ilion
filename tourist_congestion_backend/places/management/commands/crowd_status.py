import json
from django.core.management.base import BaseCommand
from django.db.models import Max
from django.utils import timezone
from places.models import CollectorState, CrowdArea, CrowdData, CrowdEstimate
from places.services.crowd_collector import daily_limit, seoul_interval, LIMIT_ENV


class Command(BaseCommand):
    help = 'Show sanitized provider progress, budgets and missing/stale Seoul coverage.'

    def handle(self,*args,**options):
        now=timezone.now()
        areas=list(CrowdArea.objects.filter(source='seoul_realtime').annotate(latest=Max('observations__observed_at')))
        stale=[a.external_id for a in areas if not a.latest or (now-a.latest).total_seconds()>=3600]
        report={'areas_registered':len(areas),'missing_or_expired_areas':stale,
                'snapshots':CrowdEstimate.objects.count(),'providers':{}}
        limit = daily_limit('seoul')
        interval = seoul_interval(limit, len(areas)) if limit > 0 and areas else None
        coverage = min(1, 60 / interval) if interval else 0
        report['baseline_readiness'] = {
            'collection_strategy': 'uniform_all_areas', 'interval_minutes': interval,
            'ideal_hourly_coverage_upper_bound': coverage,
            'required_hourly_coverage': .7, 'required_distribution_days': 28,
            'required_conditional_days': 4,
            'status': 'CADENCE_INSUFFICIENT' if coverage < .7 else 'REQUIRES_OBSERVATIONS',
            'accuracy_status': 'UNKNOWN',
        }
        for provider in LIMIT_ENV:
            states=list(CollectorState.objects.filter(provider=provider))
            budget=next((s for s in states if s.key=='_budget'),None)
            report['providers'][provider]={'approved_daily_limit':daily_limit(provider),
                'budget_date':str(budget.budget_date) if budget else None,'attempts':budget.calls if budget else 0,
                'failed_jobs':[{'key':s.key,'error':s.last_error,'failures':s.failures,
                                'next_run_at':s.next_run_at.isoformat() if s.next_run_at else None} for s in states if s.last_error],
                'last_success_at':max((s.last_success_at for s in states if s.last_success_at),default=None)}
        self.stdout.write(json.dumps(report,ensure_ascii=False,default=str))
