# 웹 데모 배포

배포 실행 파일은 **demo_app.py**입니다. 운영용 app.py와 별개이며 DEMO_DATABASE_URL만 사용합니다. 설정 누락 시 운영 SQLite로 자동 연결하지 않습니다.

1. GitHub의 비공개 저장소에 소스를 올립니다. data, secrets.toml, .env, .venv는 제외합니다.
2. 비어 있는 데모 전용 PostgreSQL DB를 준비합니다. 운영 DB와 공유하지 않습니다.
3. 로컬에서 `.\.venv\Scripts\python.exe prepare_cloud_demo.py`를 실행하고 해당 연결 URL을 숨김 입력합니다. 새 가상 학생·합성 가격을 현재 날짜 기준으로 준비합니다. 기존 대상 기록이나 기존 계정 파일은 덮어쓰지 않습니다.
4. 생성된 로컬 data/cloud-demo-access.csv에서 웹 데모 계정을 확인합니다. 로컬 데모 계정과는 별도입니다. 준비에 실패하면 이 계정 파일이 남을 수 있으므로 완료 메시지를 반드시 확인하세요.
5. Streamlit에서 GitHub 저장소와 브랜치를 선택하고 실행 파일에 demo_app.py를 지정합니다. Python 3.12를 선택하고 Secrets에 DEMO_DATABASE_URL을 설정합니다. 연결 값은 GitHub에 올리지 않습니다.
6. 배포 URL에서 학생·관리자 로그인을 확인하고, 제출 후 앱 재시작 및 다른 기기 접속 시 기록이 유지되는지 확인합니다. 이 검증 전에는 배포 완료로 간주하지 않습니다.

비공개 설정 형식(실제 접속 정보를 채팅이나 코드에 넣지 마세요):

```toml
DEMO_DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require"
```

외부 DB를 사용하므로 앱 서버 재시작으로 연습 기록을 초기화하지 않습니다. 로컬 운영·데모 DB는 변경하지 않고 웹용 수업을 새로 만듭니다. 웹 데모에도 실제 학생 개인정보 대신 가상 자료만 넣으세요. 사용한 날짜가 지나면 자료 지연이나 기간 종료 안내가 표시될 수 있습니다.

공식 배포 화면 설명: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
