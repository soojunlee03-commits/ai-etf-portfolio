# 설치·배포·복구 안내

2026-09-19 기준. 로컬 실행은 검증했습니다. 외부 호스팅 계정과 실제 PostgreSQL 접속 정보가 제공되지 않아 공개 URL 생성 및 PostgreSQL 통합 검증은 수행하지 않았습니다. 무료 서비스의 한도·휴면·백업 조건은 가입 시 확인하세요.

## 1. 이 컴퓨터에서 실행

프로젝트 폴더에서 PowerShell을 열어 실행합니다. 서버가 이미 켜져 있으면 http://127.0.0.1:8501/ 을 열면 됩니다.

```powershell
.\start.ps1
```

최초 관리자 계정은 준비되어 있습니다. 최초 임시 로그인 정보는 로컬 `data/admin-access.txt`에서 확인하세요. 첫 로그인 후 비밀번호를 바꾸고 임시 파일을 삭제합니다. 이미 변경했다면 변경한 비밀번호를 사용하며 계정을 재초기화하지 않습니다.

## 2. 별도 데모 체험

```powershell
.\start_demo.ps1
```

http://127.0.0.1:8502/ 에 접속하고 `data/demo-access.csv`를 로컬에서 열어 계정을 확인합니다. 관리자 1명과 가상 학생 4명의 비밀번호는 무작위로 생성되어 소스에 포함되지 않습니다. 학생 계정으로 성과 학기의 성과·이력·현재 회차를 확인하고 초기 제출 연습 학기로 바꾸어 첫 제출을 연습하세요.

데모는 `data/demo.db`, 운영은 기본 `data/portfolio.db`를 사용합니다. 다시 실행해도 기존 연습 기록을 지우지 않습니다. 날짜가 지난 데모에는 자료 지연 경고가 표시될 수 있습니다. 데모 자료를 실제 수업 DB에 복사하지 마세요.

## 3. 새 Windows 컴퓨터에 설치

Python 3.12를 설치하고 프로젝트를 복사합니다. `.venv`는 컴퓨터마다 새로 만듭니다. 관리자 생성은 빈 DB에서 최초 한 번만 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_admin.py
.\start.ps1
```

setup_admin.py에서 관리자 아이디와 8자 이상 비밀번호를 입력합니다. 비밀번호 입력은 화면에 표시되지 않습니다. 기존 사용자가 있으면 초기화가 거부됩니다. PowerShell이 스크립트를 막으면 아래 직접 실행 명령을 사용하세요.

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address=127.0.0.1
```

종료는 실행 터미널에서 Ctrl+C입니다. DB는 유지됩니다. 실행 중인 SQLite를 파일 복사하는 대신 앱의 DB 백업 기능을 사용하세요. 동기화 폴더의 라이브 DB를 여러 컴퓨터에서 동시에 열지 마세요.

## 4. 영구 DB 설정

연결 우선순위는 환경변수 DATABASE_URL → `.streamlit/secrets.toml` → `sqlite:///data/portfolio.db`입니다. 로컬 단일 서버에는 SQLite를 사용할 수 있습니다. 외부 공유 운영이나 임시 디스크 호스팅에는 별도 영구 PostgreSQL을 연결하세요.

DB 제공자의 연결 URL을 얻은 뒤 아래 도우미에 붙여 넣습니다. URL에는 비밀번호가 있으므로 채팅이나 Git에 공개하지 마세요.

```powershell
.\.venv\Scripts\python.exe configure_database.py
```

입력은 화면에 표시되지 않으며 비공개 설정 파일을 새로 만듭니다. 기존 설정 파일은 덮어쓰지 않습니다. 형식 예시는 `postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require`입니다. 실제 값은 제공자로부터 받아야 합니다. 앱과 setup_admin.py는 같은 설정을 읽습니다. 변경 후 앱을 재시작하세요.

빈 PostgreSQL에 처음 접속할 때 테이블과 변경 방지 트리거를 생성하므로 스키마 생성 권한이 필요합니다. DB 계정은 서버에서만 사용합니다. 학생 권한은 서버 서비스 계층에서 검사하며 브라우저에 DB를 직접 공개하지 않습니다.

SQLite에서 PostgreSQL로 기존 기록을 자동 이전하는 기능은 없습니다. 실제 수업 기록이 있다면 먼저 전체 백업·학기 ZIP을 보존하고 별도의 이전 검증을 수행하세요. 연결만 바꾸면 기존 SQLite 기록이 자동으로 나타나지 않습니다.

## 5. Streamlit Community Cloud 배포

계정 소유자가 GitHub 저장소, Streamlit 계정, 영구 PostgreSQL을 준비해야 합니다.

1. 소스와 requirements.txt를 저장소에 올립니다. `data/`, `.venv/`, `.env`, `.streamlit/secrets.toml`은 제외되었는지 확인합니다.
2. 비공개 연결 도우미로 외부 DB를 지정하고 setup_admin.py를 실행해 그 DB에 관리자 계정을 만듭니다. 기존 DB라면 기존 계정을 사용합니다.
3. Streamlit에서 Create app을 선택하고 저장소, 실제 브랜치, 실행 파일 `app.py`를 지정합니다.
4. Advanced settings에서 Python 3.12와 Secrets의 DATABASE_URL을 설정합니다. 비밀번호를 코드에 넣지 않습니다.
5. 배포된 HTTPS 주소에서 관리자 로그인, 학기 생성, 학생의 첫 로그인·제출을 시험합니다. 재시작 뒤에도 기록이 남는지 확인합니다.
6. 작은 시험 수업으로 가격 수집, 공식 확정, 순위 비공개, 백업·복원을 확인한 후 학생에게 URL을 전달합니다.

배포 항목은 [Streamlit 배포 문서](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), 비공개 설정은 [Secrets 안내](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)에 따릅니다. 호스팅의 임시 SQLite 파일을 수업 영구 저장소로 사용하지 마세요. localhost 주소는 같은 컴퓨터에서만 열립니다.

## 6. Docker와 업데이트

Dockerfile을 제공합니다. 운영 담당자는 DATABASE_URL을 비공개 환경변수로 주고 HTTPS를 설정합니다. SQLite라면 `/app/data`에 쓰기 가능한 영구 볼륨이 필요하며 여러 컨테이너가 같은 SQLite를 동시에 쓰지 않도록 합니다. 이미지에는 data와 secrets를 복사하지 않습니다. 상태 점검 주소는 `/_stcore/health`입니다. 이 환경에서는 Docker 빌드와 실서비스 배포를 검증하지 않았습니다.

업데이트 순서는 앱 중지 → 전체 DB 백업 → 소스 반영 → 의존성 설치 → 실행 → 로그인·이력·성과 확인입니다. 이번 버전은 기존 테이블을 지우지 않고 새 테이블을 추가합니다. 배분 버전·가격 원장·감사·공식 확정본에는 UPDATE/DELETE 방지 트리거를 둡니다. 모든 미래 변경을 자동 처리하는 일반 마이그레이션 도구는 아니므로 다음 업데이트도 사본에서 먼저 시험하세요.

## 7. 백업과 복원

화면에서는 **내보내기 / 백업 → 완전 복구용 DB 백업 준비 → 완전 복구용 DB 다운로드**를 사용합니다. 명령 백업은 설정된 SQLite를 새 파일로 복사하며 기존 목적지는 덮어쓰지 않습니다.

```powershell
.\.venv\Scripts\python.exe backup_db.py backup data/backup-20260919.db
```

복원은 앱을 중지하고 아래를 실행합니다. 백업 전체 경로와 새로운 복원 경로를 입력한 뒤 `복원`으로 확인합니다. 무결성을 검사하고 새 파일에 복원합니다.

```powershell
.\recovery.ps1
```

이후 같은 복원본으로 시작할 때는 다음을 사용합니다. 일반 start.ps1과 혼용하지 마세요.

```powershell
.\start_recovered.ps1
```

관리자·학생 로그인, 초기·리밸런싱 이력, 공식 기준일, 학생 수를 비교합니다. 확인 전 원본·백업을 지우지 않습니다. JSON/CSV는 비밀번호 해시가 없는 분석 자료이며 완전 복구를 대신하지 않습니다. DB 경로를 잘못 바꾸어 빈 파일이 열리면 먼저 원래 경로를 확인하고 새 계정을 만들지 마세요.

PostgreSQL은 제공자 전체 백업 또는 운영자의 pg_dump/pg_restore로 새 DB에 복원합니다. 접속 비밀번호를 명령 인수나 공개 로그에 남기지 마세요. [PostgreSQL 백업 문서](https://www.postgresql.org/docs/current/backup-dump.html)를 참고하고 복원 후 같은 화면 검증을 수행합니다.

## 8. 장애와 남은 운영 검증

앱이 열리지 않으면 서버 실행과 포트 8501을 확인합니다. DB 오류는 접속·권한·용량을, 가격 오류는 기간·공급원 응답을 점검합니다. 데이터 상태 경고가 있을 때 공식 순위가 차단되는 것은 정상입니다. 오류 메시지와 발생 시각을 운영자에게 전달하되 비밀번호·접속 문자열·DB 파일은 공개하지 않습니다.

외부 공개 전 실제 PostgreSQL 생성/복원 권한, HTTPS, 동시 접속 부하, 무료 데이터 접근과 백업 보관 정책을 검증해야 합니다. 외부 SSO, 이메일 비밀번호 복구, 자동 시장자료 예약 수집, AI 추천, 실거래는 제공하지 않습니다.
