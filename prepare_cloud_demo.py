"""Initialize a dedicated EMPTY cloud DB with fresh fictional classroom data.

Connection input is private. Passwords are saved locally, never in Git or logs.
Existing destinations are refused; the local production/demo databases are untouched.
"""
import tempfile
from getpass import getpass
from pathlib import Path
from sqlalchemy import select, insert, text
from portfolio.db import connect, metadata, settings
from portfolio.cloud_demo import demo_url, MARKER
from seed_demo import seed

def copy_into_empty(source,target):
    tables=list(metadata.sorted_tables)
    with source.connect() as src:
        rows={t.name:[dict(r) for r in src.execute(select(t)).mappings()] for t in tables}
    with target.begin() as dst:
        if target.dialect.name=='postgresql':
            dst.execute(text('LOCK TABLE '+', '.join(t.name for t in tables)+' IN ACCESS EXCLUSIVE MODE'))
        for table in tables:
            if dst.execute(select(table).limit(1)).first():
                raise ValueError('대상 DB에 기존 기록이 있어 중단했습니다. 비어 있는 데모 전용 DB를 사용하세요.')
        for table in tables:
            if rows[table.name]: dst.execute(insert(table),rows[table.name])
            if target.dialect.name=='postgresql' and 'id' in table.c and rows[table.name]:
                dst.execute(text("SELECT setval(pg_get_serial_sequence(:name, 'id'), :highest, true)"),
                            {'name':table.name,'highest':max(r['id'] for r in rows[table.name])})
        dst.execute(insert(settings).values(key=MARKER,value='1'))

def prepare(value,credential_path):
    url=demo_url(value)
    path=Path(credential_path)
    if path.exists(): raise ValueError('계정 파일이 이미 있습니다. 기존 파일은 덮어쓰지 않습니다.')
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        source_path=seed(Path(folder)/'demo.db')
        source=connect('sqlite:///'+source_path.as_posix())
        target=None
        # Reserve local credential storage first so successful upload cannot lose passwords.
        try:
            target=connect(url.render_as_string(hide_password=False))
            with path.open('x',encoding='utf-8-sig') as out:
                out.write((Path(folder)/'demo-access.csv').read_text(encoding='utf-8-sig'))
            copy_into_empty(source,target)
        finally:
            source.dispose()
            if target is not None:target.dispose()
    return path

if __name__=='__main__':
    try:
        value=getpass('비어 있는 데모 전용 PostgreSQL 연결 URL (입력은 숨김): ').strip()
        path=prepare(value,Path('data')/'cloud-demo-access.csv')
        print('웹 데모 DB 준비 완료. 계정 파일: '+str(path))
        print('Streamlit 실행 파일은 demo_app.py, 비공개 설정 이름은 DEMO_DATABASE_URL입니다.')
    except Exception as error:
        print('준비하지 못했습니다. 빈 DB 여부와 연결 설정을 확인하세요. 오류 유형: '+type(error).__name__)
        raise SystemExit(1)
