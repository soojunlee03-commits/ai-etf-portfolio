# 운영앱 공개 배포 기록

- 배포일: 2026-10-01 (한국 시각)
- 운영앱 URL: https://ai-etf-portfolio-class.streamlit.app/
- GitHub: https://github.com/soojunlee03-commits/ai-etf-portfolio
- 브랜치: master
- 실행 파일: app.py
- Python: 3.12
- DB: Neon PostgreSQL, project icy-pine-94665126, production branch, neondb
- DATABASE_URL은 Streamlit Secrets에만 설정하며 GitHub에 포함하지 않습니다.
- 로컬 관리자 1명, 학기 1개 및 기존 감사·로그인 기록을 새 PostgreSQL에 복사했습니다. 이전 트랜잭션에서 모든 테이블의 행 내용이 일치하는 것을 검증했습니다.
- 로컬 SQLite와 공개 PostgreSQL은 별도입니다. 이전 시점 이후의 변경은 서로 자동 동기화되지 않습니다. 공개 수업은 위 운영앱 URL에서 관리하세요.
- 공개 접근·화면 검증: Streamlit의 Make this app public 활성화, 로그인 화면, 학생 회원가입(8자 이상 비밀번호), 이전한 학기 표시를 확인했습니다. 관리자 실제 로그인은 현재 사용 중인 비밀번호로 사용자가 확인해야 합니다.
