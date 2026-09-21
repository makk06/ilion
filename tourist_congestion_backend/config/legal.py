"""공개 약관·처리방침에 들어가는 운영 정보.

문서 내용이 바뀌면 TERMS_VERSION 을 올린다. 가입 시 동의한 버전이 회원에 저장되므로,
버전을 보면 그 회원이 어느 문서에 동의했는지 알 수 있다.
"""

OPERATOR_NAME = '고사연일'
REPRESENTATIVE_NAME = '한도경'
PRIVACY_OFFICER_NAME = '한도경'
PRIVACY_OFFICER_TITLE = '팀장'
CONTACT_EMAIL = 'ehrud8657@gmail.com'
SUPPORT_PATH = '앱 > 마이 > 도움말 및 문의'

TERMS_VERSION = '2026-09-21'
EFFECTIVE_DATE = '2026년 9월 21일'

# 서버(nginx)의 접속 로그 보관 기간. 운영 서버 logrotate 설정(daily, rotate 14) 기준.
# 설정이 바뀌면 이 값도 고친다. 비우면 /privacy 는 공개하지 않고 503 을 돌려준다.
ACCESS_LOG_RETENTION = '최대 15일 (매일 새 파일로 바꾸고 14일치만 보관한 뒤 삭제)'

# 배포 시 생기는 DB 백업의 보관 기간. runtime.prune_database_backups 와 문구가 같이 쓴다.
DATABASE_BACKUP_RETENTION_DAYS = 30


def context():
    return {
        'operator_name': OPERATOR_NAME,
        'representative_name': REPRESENTATIVE_NAME,
        'privacy_officer_name': PRIVACY_OFFICER_NAME,
        'privacy_officer_title': PRIVACY_OFFICER_TITLE,
        'contact_email': CONTACT_EMAIL,
        'support_path': SUPPORT_PATH,
        'terms_version': TERMS_VERSION,
        'effective_date': EFFECTIVE_DATE,
        'access_log_retention': ACCESS_LOG_RETENTION,
        'backup_retention_days': DATABASE_BACKUP_RETENTION_DAYS,
    }
