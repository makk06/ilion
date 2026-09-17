import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .exceptions import ExternalAPIAuthError, ExternalAPIError, ExternalAPIQuotaError


DEFAULT_TIMEOUT_SECONDS = 10


def build_retrying_session():
    retry = Retry(
        total=0,
        connect=0,
        read=0,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=('GET',),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


def get_json(session, url, *, params=None, timeout=None, provider):
    """Fetch JSON without leaking credential-bearing URLs into exceptions."""
    try:
        response = session.get(
            url,
            params=params,
            timeout=timeout or DEFAULT_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        raise ExternalAPIError(f'{provider} request failed') from None

    try:
        payload = response.json()
    except ValueError:
        payload = None

    try:
        response.raise_for_status()
    except requests.RequestException:
        if response.status_code in (401, 403):
            header = (payload or {}).get('OpenAPI_ServiceResponse', {}).get('cmmMsgHeader', {}) if isinstance(payload, dict) else {}
            code = header.get('returnReasonCode')
            suffix = f', code {code}' if code and str(code).isdigit() else ''
            raise ExternalAPIAuthError(f'{provider} rejected credentials (HTTP {response.status_code}{suffix})') from None
        if response.status_code == 429:
            raise ExternalAPIQuotaError(f'{provider} call quota exceeded') from None
        detail = extract_error_detail(payload)
        suffix = f', {detail}' if detail else ''
        raise ExternalAPIError(
            f'{provider} request failed (HTTP {response.status_code}{suffix})'
        ) from None

    if not isinstance(payload, dict):
        raise ExternalAPIError(f'{provider} returned an invalid JSON payload')
    return payload


def extract_error_detail(payload):
    if not isinstance(payload, dict):
        return ''

    public_data_error = (
        payload.get('OpenAPI_ServiceResponse', {}).get('cmmMsgHeader', {})
    )
    if public_data_error:
        code = public_data_error.get('returnReasonCode')
        message = (
            public_data_error.get('returnAuthMsg')
            or public_data_error.get('errMsg')
        )
        return _format_error(code, message)

    top_level_code = payload.get('resultCode')
    top_level_message = payload.get('resultMsg')
    if top_level_code or top_level_message:
        return _format_error(top_level_code, top_level_message)

    result = payload.get('RESULT') or payload.get('result') or {}
    code = result.get('RESULT.CODE') or result.get('CODE') or result.get('code')
    message = (
        result.get('RESULT.MESSAGE')
        or result.get('MESSAGE')
        or result.get('message')
    )
    return _format_error(code, message)


def _format_error(code, message):
    if code and message:
        return f'code {code}: {str(message)[:200]}'
    if code:
        return f'code {code}'
    if message:
        return str(message)[:200]
    return ''
