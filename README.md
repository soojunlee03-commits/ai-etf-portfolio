# AI ETF Portfolio Competition

한국어 교육용 ETF 자산배분 대회 앱입니다. SPY·IEF·GLD·VNQ·SGOV 초기 배분, 제출 잠금, 회차별 리밸런싱, 달러/원화 NAV, 공식 순위, 학기 보관과 감사 기록을 제공합니다. 실제 매매와 자동 AI 추천은 없습니다.

## 공개 운영앱

[공개 운영앱 열기](https://ai-etf-portfolio-class.streamlit.app/) · [배포 기록](docs/Production_Deployment_KO.md)

공개 앱은 Neon PostgreSQL에 저장합니다. 로컬 앱의 SQLite와 자동 동기화되지 않으므로 실제 수업 관리는 공개 앱에서 진행하세요.

## 이 컴퓨터에서 실행

프로젝트 폴더의 PowerShell에서 실행합니다. 가상환경과 최초 관리자 계정이 준비되어 있으므로 재초기화할 필요가 없습니다.

```powershell
.\start.ps1
```

[운영 앱](http://127.0.0.1:8501/)을 엽니다. 최초 임시 로그인 정보는 로컬 `data/admin-access.txt`에 있으며 처음 로그인하면 비밀번호를 변경합니다. 변경 후 임시 파일을 삭제하세요.

별도 가상 자료 체험:

```powershell
.\start_demo.ps1
```

[데모 앱](http://127.0.0.1:8502/)에서 로컬 `data/demo-access.csv`의 계정으로 로그인하세요. 무작위 비밀번호는 소스에 포함하지 않습니다. 데모 DB는 운영 DB와 별도이며 다시 실행해도 연습 기록을 지우지 않습니다.

## 사용설명서

- [학생 빠른 시작](docs/Student_Quick_Start_KO.md) · [학생 상세 설명서](docs/Student_Manual_KO.md) · [학생 PDF](output/pdf/Student_Manual_KO.pdf)
- [관리자 빠른 시작](docs/Admin_Quick_Start_KO.md) · [관리자 상세 설명서](docs/Admin_Manual_KO.md) · [관리자 PDF](output/pdf/Admin_Manual_KO.pdf)
- [설치·배포·복구 안내](docs/Deployment_Operations_KO.md)
- [영문 CSV 열의 한국어 데이터 사전](docs/Data_Dictionary_KO.md)
- [인수 테스트 결과](docs/Acceptance_Test_Results_KO.md)

앱의 학생 **사용가이드**, 관리자 **관리자 사용가이드**에서도 동일한 상세 설명서를 읽습니다. 학생은 앱 URL의 **학생 회원가입**에서 아이디·공개 닉네임·8자 이상 비밀번호를 직접 정하고 수업을 선택해 참여합니다. 등록 가능한 학기가 없으면 가입 후 교수자가 수강 등록할 수 있습니다. 기존 계정도 그대로 사용할 수 있습니다.

## 새 컴퓨터 설치

Python 3.12에서 실행합니다. 관리자 생성은 빈 DB에서 최초 한 번만 합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_admin.py
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address=127.0.0.1
```

## 저장과 공개 배포

기본 SQLite `data/portfolio.db`가 사용자·학기·제출·가격 원장·공식 성과를 영구 보관합니다. `data/demo.db`는 별도 데모입니다. 재시작으로 데이터를 지우지 않으며 DB 트리거와 추가 버전으로 정정 전 기록을 보존합니다.

연결 우선순위는 환경변수 DATABASE_URL → 비공개 `.streamlit/secrets.toml` → 기본 SQLite입니다. `configure_database.py`는 코드 편집 없이 연결을 설정합니다. 공개 수업 운영에는 영구 PostgreSQL과 HTTPS 호스팅을 사용하세요. Dockerfile 및 Streamlit 배포 절차를 제공합니다. 외부 계정이 없어 실제 PostgreSQL 연결, 공개 URL, 동시 접속 부하 검증은 아직 하지 않았습니다. 기존 SQLite에서 PostgreSQL로의 자동 데이터 이전 기능은 없습니다.

## 성과 기준

- 최초 관측 거래일 USD NAV와 ETF 비교 지수를 100으로 시작합니다.
- 보유 평가액에 저장된 일별 수정종가 배율을 곱합니다. 매일 목표 비중으로 자동 재배분하지 않습니다.
- 적용 예정일 이후 첫 미국 거래일 종가에서 기존 보유 수익을 먼저 반영하고 새 비중으로 바꿉니다. 미제출은 기존 보유 유지입니다.
- KRW NAV = USD NAV × 당일 원/달러 환율 ÷ 최초 관측일 환율. 수익률 = NAV/100 - 1입니다.
- Yahoo ETF Adj Close와 KRW=X 같은 날짜 Close를 사용합니다. 같은 수집본의 수정종가 비율을 저장해 배당·분할 후 가격 개정에 따른 수집본 혼합을 피합니다. 같은 날짜 FX는 완전히 같은 거래 시각이라는 의미가 아닙니다.
- XNYS 거래일과 결측을 검사합니다. 오늘 미완성 자료, 음수·무한 가격, 거래일 누락은 저장하지 않습니다. 기존 날짜는 명시적 정정 외에 덮어쓰지 않습니다.
- 공식 확정은 일별 성과·순위·출처 식별값을 추가 저장합니다. 입력 변경이나 자료 오류가 있으면 순위 공개를 차단합니다.
- USD 수익률 소수점 6자리로 비교하며 공동순위는 1, 1, 3입니다. 수수료·세금·슬리피지는 0이고 별도 배당 현금은 중복 적립하지 않습니다.

## 백업·검사

```powershell
.\.venv\Scripts\python.exe backup_db.py backup data/backup-20260919.db
.\.venv\Scripts\python.exe -m pytest -q
```

화면에서도 완전 SQLite DB를 다운로드할 수 있습니다. 복원은 앱 중지 후 `recovery.ps1`, 복원본 재실행은 `start_recovered.ps1`입니다. JSON/CSV는 비밀번호 해시가 없는 분석 자료이며 완전 복구를 대신하지 않습니다. 테스트는 임시 DB를 사용하고 운영 DB를 바꾸지 않습니다.

## 구조

| 위치 | 역할 |
| --- | --- |
| app.py / portfolio/ui_app.py / ui_helpers.py | 한국어 화면과 안내 |
| portfolio/db.py | DB 스키마·추가형 초기화·불변 원장 |
| portfolio/service.py / operations.py | 인증·권한·제출·계산·공식 확정·내보내기 |
| portfolio/market.py / calendar.py | 무료 시세·CSV·미국 거래일 |
| setup_admin.py / configure_database.py | 최초 관리자·비공개 연결 설정 |
| seed_demo.py / start_demo.ps1 | 가상 자료 별도 실행 |
| backup_db.py / recovery.ps1 | 일관된 백업과 원본을 보존하는 복원 |
| tests / docs / output/pdf | 자동 검사·한국어 안내·배포 설명서 |

PBKDF2-SHA256 600,000회 비밀번호 해시, 서버의 학생별 접근 통제, 중복 제출 유일 제약, 5회 실패 시 15분 잠금, 8시간 세션 만료를 적용합니다. 모든 관리자는 한 설치의 모든 수업을 관리합니다. 외부 SSO와 이메일 복구는 제공하지 않습니다.

[yfinance 공식 안내](https://ranaroussi.github.io/yfinance/)의 데이터 이용 조건을 확인하세요. 교육용 모의투자이며 실거래나 투자 조언을 제공하지 않습니다.
