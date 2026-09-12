"""Bounded provider reads. Each retry consumes the same server-side budget."""
import os
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests

from .exceptions import ExternalAPIConfigurationError, ExternalAPIError

MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class ProviderDeferredRetry(ExternalAPIError):
    def __init__(self, seconds):
        super().__init__('Provider requested deferred retry')
        self.retry_after = seconds


def required_key(name):
    value = os.environ.get(name, '')
    if not value:
        raise ExternalAPIConfigurationError(f'{name} is not configured')
    return value


class BudgetSession(requests.Session):
    def __init__(self, charge):
        super().__init__()
        self.charge = charge
        self.use_reserve = False

    def request(self, method, url, **kwargs):
        if method.upper() != 'GET':
            raise ExternalAPIError('Only provider GET requests are allowed')
        kwargs['timeout'] = (3, 10)
        kwargs['allow_redirects'] = False  # credentials must stay on the selected host
        kwargs['stream'] = True
        for attempt in range(3):
            self.charge(retry=attempt > 0 or self.use_reserve)
            response = None
            delay = .5 * 2**attempt + random.uniform(0, .25)
            try:
                response = super().request(method, url, **kwargs)
                if response.status_code not in (429, 500, 502, 503, 504):
                    if 300 <= response.status_code < 400:
                        response.close()
                        raise ExternalAPIError('Provider redirect rejected')
                    data = bytearray()
                    for chunk in response.iter_content(65536):
                        data.extend(chunk)
                        if len(data) > MAX_RESPONSE_BYTES:
                            response.close()
                            raise ExternalAPIError('Provider response exceeds size limit')
                    response._content = bytes(data)
                    response._content_consumed = True
                    return response
                retry_after = response.headers.get('Retry-After')
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        try:
                            delay = max(delay, (parsedate_to_datetime(retry_after)-datetime.now(timezone.utc)).total_seconds())
                        except (ValueError, TypeError):
                            pass
                    if delay > 30:
                        response.close()
                        raise ProviderDeferredRetry(delay)
                response.close()
            except requests.RequestException:
                if response is not None:
                    response.close()
            if attempt < 2:
                time.sleep(max(0, delay))
        raise ExternalAPIError('Provider temporarily unavailable')


def xml_root(content):
    if len(content) > MAX_RESPONSE_BYTES or b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
        raise ExternalAPIError('Unsafe or oversized XML response')
    try:
        return ElementTree.fromstring(content)
    except ElementTree.ParseError:
        raise ExternalAPIError('Invalid provider XML') from None


def get_xml(session, url, params=None):
    try:
        response = session.get(url, params=params, timeout=(3, 10))
        response.raise_for_status()
    except requests.RequestException:
        raise ExternalAPIError('Provider XML request failed') from None
    root = xml_root(response.content)
    code = root.findtext('.//resultCode')
    if code is not None and code.strip() not in ('0', '00', '0000'):
        raise ExternalAPIError('Provider returned an application error')
    if root.find('.//cmmMsgHeader') is not None:
        raise ExternalAPIError('Provider rejected request')
    return root
