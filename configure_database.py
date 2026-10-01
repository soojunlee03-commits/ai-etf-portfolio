"""One-time connection helper; no secret appears in terminal output or history."""
from getpass import getpass
from pathlib import Path
import json

if __name__=='__main__':
    path=Path(__file__).resolve().parent/'.streamlit'/'secrets.toml'
    if path.exists(): raise SystemExit('설정 파일이 이미 있습니다. 기존 파일을 안전하게 보관한 후 운영자에게 설정 변경을 요청하세요.')
    value=getpass('DB 연결 URL을 붙여 넣으세요 (입력 내용은 표시되지 않습니다): ').strip()
    if not value.startswith(('sqlite:///','postgresql://','postgresql+psycopg://','postgres://')):
        raise SystemExit('지원하는 SQLite 또는 PostgreSQL URL이 아닙니다. 저장하지 않았습니다.')
    path.parent.mkdir(exist_ok=True)
    path.write_text('DATABASE_URL = '+json.dumps(value)+'\n',encoding='utf-8')
    print('비공개 연결 설정을 저장했습니다. 앱을 재시작하세요. 이 파일은 Git에 올리지 마세요.')
