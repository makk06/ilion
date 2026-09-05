import hashlib
import secrets

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
