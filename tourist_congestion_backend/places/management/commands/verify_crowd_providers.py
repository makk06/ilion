"""Explicit, budgeted account smoke checks; never dumps credentials or payloads."""
import json
import os
from django.core.management.base import BaseCommand
from django.utils import timezone
from places.catalog import load_seoul_crowd_catalog
from places.integrations.crowd_http import BudgetSession
from places.integrations.seoul_citydata import SeoulCityClient
from places.integrations.tour_api import TourAPIClient
from places.integrations.weather import WeatherClient, latest_issue
from places.integrations.holidays import HolidayClient
from places.integrations.exceptions import ExternalAPIError
from places.services.crowd_collector import KEY_ENV, daily_limit, charge
from places.services.crowd_estimator import KST


class Command(BaseCommand):
    help = 'Run small authenticated provider checks only when keys and approved quotas are configured.'

    def add_arguments(self, parser):
        parser.add_argument('--provider', choices=list(KEY_ENV))

    def handle(self, *args, **options):
        report = {}
        now = timezone.now()
        for provider in KEY_ENV:
            if options['provider'] and options['provider'] != provider:
                continue
            if not os.environ.get(KEY_ENV[provider]) or daily_limit(provider) <= 0:
                report[provider] = {'status':'blocked','reason':'key_or_approved_quota_missing'}
                continue
            try:
                with BudgetSession(lambda retry=False,p=provider:charge(p,retry)) as session:
                    if provider == 'seoul':
                        client = SeoulCityClient(session)
                        for area in load_seoul_crowd_catalog().areas[:2]:
                            client.fetch(area.external_id,now)
                    elif provider == 'tour_api':
                        client=TourAPIClient(session=session)
                        page=client.fetch_places_page(page_size=20)
                        client.fetch_events_page()
                        record=next((r for r in page.records if str(r.raw_data.get('showflag')) == '1'), None)
                        if record is None:
                            raise ExternalAPIError('No public POI available in detail check sample')
                        client.fetch_place_detail(record.external_id,str(record.raw_data['contenttypeid']))
                    elif provider == 'kma':
                        for product in ('getUltraSrtNcst','getUltraSrtFcst','getVilageFcst'):
                            WeatherClient(session).fetch(product,(60,127),latest_issue(product,now))
                    else:
                        local=now.astimezone(KST)
                        HolidayClient(session).fetch(local.year,local.month)
                report[provider]={'status':'passed'}
            except (ExternalAPIError,ValueError,KeyError,TypeError) as error:
                report[provider]={'status':'failed','reason':type(error).__name__}
        self.stdout.write(json.dumps(report,ensure_ascii=False))
