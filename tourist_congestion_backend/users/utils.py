import hashlib
import hmac
import secrets

from django.conf import settings

ADJECTIVES = [
    '즐거운', '행복한', '용감한', '차분한', '똑똑한',
    '든든한', '신나는', '느긋한', '재빠른', '포근한',
]
NOUNS = [
    '고양이', '강아지', '여행자', '탐험가', '판다',
    '호랑이', '부엉이', '다람쥐', '수달', '펭귄', '독수리',
]


def generate_random_nickname():
    adjective = secrets.choice(ADJECTIVES)
    noun = secrets.choice(NOUNS)
    number = secrets.randbelow(9000) + 1000
    return f'{adjective}{noun}{number}'


def hash_token(raw_token):
    return hashlib.sha256(raw_token.encode()).hexdigest()


def hash_email_for_withdrawal(email):
    """재가입 차단용 이메일 지문.

    단순 sha256을 쓰면 안 된다. 이메일은 후보 공간이 좁아 전수 대입으로 복원된다.
    서버만 아는 키로 HMAC을 걸어야 실질적 익명성이 생긴다.
    """
    return hmac.new(
        settings.WITHDRAWAL_HASH_KEY.encode(),
        email.strip().lower().encode(),
        hashlib.sha256,
    ).hexdigest()
