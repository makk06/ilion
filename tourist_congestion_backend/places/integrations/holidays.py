from datetime import datetime
from urllib.parse import unquote

from .crowd_http import get_xml, required_key
from .exceptions import ExternalAPIError


class HolidayClient:
    def __init__(self, session, service_key=None):
        self.session = session
        self.key = unquote(service_key or required_key('HOLIDAY_SERVICE_KEY'))

    def fetch(self, year, month):
        root = get_xml(self.session, 'https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo',
            {'serviceKey': self.key, 'solYear': year, 'solMonth': f'{month:02}', 'numOfRows': 100, 'pageNo': 1})
        result = {}
        nodes = root.findall('.//item')
        if int(root.findtext('.//totalCount') or 0) != len(nodes):
            raise ExternalAPIError('Incomplete holiday response')
        for item in nodes:
            try:
                day = datetime.strptime(item.findtext('locdate'), '%Y%m%d').date()
            except (ValueError, TypeError):
                raise ExternalAPIError('Invalid holiday date') from None
            if day.year != year or day.month != month:
                raise ExternalAPIError('Holiday period mismatch')
            if item.findtext('isHoliday') == 'Y':
                result[day] = item.findtext('dateName') or ''
        return result
