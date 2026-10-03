"""Fail-closed configuration check before public deployment (does not prove external integration)."""
import os
import sys
from urllib.parse import urlsplit


def check(env):
    errors = []
    if env.get('DEMO_MODE', 'false').lower() != 'false':
        errors.append('DEMO_MODE must be false')
    for key in ['SUPABASE_URL', 'SUPABASE_ANON_KEY', 'ADMIN_USER_IDS', 'POSTGRES_PASSWORD', 'APP_ORIGIN', 'CAMPUSMATE_DOMAIN']:
        if not env.get(key, '').strip():
            errors.append(f'{key} is required')
    for key in ['SINGLE_ADMIN_OVERRIDES', 'COLLECTOR_SKIP_ROBOTS']:
        if env.get(key, 'false').lower() != 'false':
            errors.append(f'{key} must be false for deployment')
    if env.get('DATABASE_URL') and not env['DATABASE_URL'].startswith(('postgresql://', 'postgresql+psycopg://')):
        errors.append('DATABASE_URL must use PostgreSQL for deployment')
    if len(env.get('POSTGRES_PASSWORD', '')) < 24:
        errors.append('POSTGRES_PASSWORD must contain at least 24 URL-safe random characters')
    origin = urlsplit(env.get('APP_ORIGIN', ''))
    if origin.scheme != 'https' or not origin.hostname or origin.path or origin.query or origin.fragment or origin.username:
        errors.append('APP_ORIGIN must be an HTTPS origin without path/query/credentials')
    if origin.netloc != env.get('CAMPUSMATE_DOMAIN'):
        errors.append('APP_ORIGIN host must match CAMPUSMATE_DOMAIN')
    if not env.get('SUPABASE_URL', '').startswith('https://'):
        errors.append('SUPABASE_URL must use HTTPS')
    if bool(env.get('DEVELOPMENT_DIFY_API_BASE')) != bool(env.get('DEVELOPMENT_DIFY_APP_KEY')):
        errors.append('Development Dify base and key must be configured together; leave both empty for rule mode')
    if env.get('COLLECTOR_ENABLED', 'false').lower() != 'false':
        errors.append('COLLECTOR_ENABLED must be false for the platform closure release')
    if env.get('PUBLIC_NOTICE_WATCH_ENABLED','false').lower() == 'true' and not env.get('COLLECTOR_ALLOWED_HOSTS','').strip():
        errors.append('Continuous notice monitoring requires official COLLECTOR_ALLOWED_HOSTS')
    return errors


if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()
    issues = check(os.environ)
    for issue in issues:
        print(issue)
    if not issues:
        print('Configuration present. Still requires real identity/data/PostgreSQL/browser/restore/TLS acceptance.')
    sys.exit(bool(issues))
