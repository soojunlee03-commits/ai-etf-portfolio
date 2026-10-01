"""Explicit cloud demo connection; never fall back to the production database."""
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from .db import settings
from .service import RuleError

MARKER='cloud_demo_only'

def demo_url(value):
    if not value:
        raise RuleError('웹 데모 DB 연결 설정이 필요합니다. 배포 설정에 DEMO_DATABASE_URL을 등록하세요.')
    url=make_url(value)
    if url.drivername not in ('postgres','postgresql','postgresql+psycopg'):
        raise RuleError('웹 데모에는 별도의 영구 PostgreSQL DB가 필요합니다.')
    return url.set(drivername='postgresql+psycopg')

def check_demo_marker(engine):
    # Read before the app schema initializer can touch the selected database.
    with engine.connect() as c:
        marker=c.execute(select(settings.c.value).where(settings.c.key==MARKER)).scalar()
    if marker!='1':
        raise RuleError('웹 데모로 준비된 DB가 아닙니다. 운영 DB와 다른 연결인지 확인하세요.')

def verified_url(value):
    url=demo_url(value)
    engine=create_engine(url,pool_pre_ping=True,hide_parameters=True)
    try: check_demo_marker(engine)
    finally: engine.dispose()
    return url.render_as_string(hide_password=False)
