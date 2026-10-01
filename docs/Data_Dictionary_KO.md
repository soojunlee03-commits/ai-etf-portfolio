# 내보내기 데이터 사전

스키마 버전 2. CSV는 UTF-8 BOM이며 영문 열 이름을 사용합니다. JSON의 schema_version은 형식 버전, exported_at은 UTC 내보내기 시각, tables는 테이블 묶음입니다. 빈 테이블은 ZIP에 CSV가 없을 수 있으며 JSON에서 확인할 수 있습니다.

## 공통 규칙

id는 내부 식별자, user_id는 users.id, semester_id는 semesters.id, actor_id는 작업한 users.id입니다. 날짜는 YYYY-MM-DD, 시각은 UTC 오프셋을 포함한 ISO 8601입니다. 앱은 한국 시간으로 표시합니다. 비중은 0~100 백분율, 수익률 5는 5%입니다.

## 사용자와 학기

| 테이블 | 열과 한국어 의미 |
| --- | --- |
| users | id 번호, username 로그인 아이디, name 공개 닉네임, role(admin/student) 권한, active 접속 허용, must_change 비밀번호 변경 필요 |
| semesters | id 번호, name 이름, start 시작일, end 종료일, initial_deadline 초기 제출 마감, leaderboard 순위 공개, archived 보관 여부 |
| enrollments | id 등록 번호, semester_id 학기, user_id 학생; 학기·학생 조합은 유일 |
| windows | id 회차 번호, semester_id 학기, name 회차명, opens 시작 시각, closes 마감 시각, effective 적용 예정 미국 날짜 |
| app_settings | key 설정 이름, value 설정값; active_semester는 기본 운영 학기 번호 |
| login_events | id 기록 번호, user_id 사용자, created_at 성공 로그인 UTC 시각 |

users의 password(해시), failed(실패 횟수), locked_until(잠금 만료)은 JSON/CSV에서 제외하며 완전 DB 백업에만 포함합니다. 실패한 로그인 비밀번호는 저장하지 않습니다.

## 제출과 배분 버전

submissions: id 제출 번호, semester_id 학기, user_id 학생, event_key 회차(initial이면 최초 배분, 그 외 windows.id 문자열), effective 적용 예정일, submitted_at 최초 제출 시각입니다. 학기·학생·회차 조합은 유일합니다.

allocation_versions: id 버전 번호, submission_id 제출 번호, weights ETF별 백분율 JSON(합계 100), reason 전략·정정 사유, created_at 생성 시각, actor_id 학생·관리자 번호입니다. 같은 제출의 가장 큰 id가 현재 버전이며 과거 행은 보존됩니다.

## market_versions: 가격 원장

| 열 | 의미 |
| --- | --- |
| id / day / previous_day | 자료 버전 / 미국 거래일 / 직전 거래일 |
| prices | 수집 시점의 ETF별 수정종가 JSON |
| factors | 같은 수집본의 당일/직전 수정종가 배율 JSON |
| fx | 같은 날짜 1달러당 원화 환율 |
| source / created_at | 출처 및 관례 / 저장 UTC 시각 |

같은 날짜의 가장 큰 id를 사용하며 과거 버전을 보존합니다. 서로 다른 수집 시점의 가격 수준을 나누지 않고 factors를 연결합니다. FX의 같은 날짜는 주식 종가와 정확히 같은 시각이라는 뜻은 아닙니다. 여러 수업이 공통 원장을 공유하므로 학기 내보내기에도 공통 가격 원장이 포함됩니다.

## audit_log: 감사 기록

id 기록 번호, actor_id 작업자, action 작업 종류, target 대상, before/after 변경 전후 JSON, reason 사유, created_at UTC 시각입니다. 계정 비밀번호 자체는 기록하지 않습니다. 행은 추가 전용입니다.

## official_runs: 공식 확정본

id 확정 번호, semester_id 학기, measurement_date 측정 마지막 거래일, digest 계산 입력의 SHA-256 식별값, payload 상세 JSON, actor_id 관리자, created_at 확정 시각, reason 사유입니다.

payload.performance는 학생 번호별 일별 배열입니다. date, USD NAV, KRW NAV, USD return %, KRW return %, USD/KRW, SPY/IEF/GLD/VNQ/SGOV 지수값을 포함합니다. payload.board는 확정 순위입니다. market_version_ids는 사용 자료 버전, conventions는 가격·환율·적용 관례, source_digest는 입력 식별값입니다. 시작일·적용 거래일·측정일을 포함한 전체 일별 기록을 보존하고 과거 확정본을 덮어쓰지 않습니다.

## performance_records: 현재 계산값

학기 내보내기의 현재 재계산 자료입니다. user_id, semester_id, status=provisional, price_date, usd_nav, krw_nav, usd_return_pct, krw_return_pct, usd_krw와 spy_index, ief_index, gld_index, vnq_index, sgov_index입니다. 공식 이력은 official_runs.payload에서 확인하세요.

## leaderboard_records: 확정 순위 이력

run_id 확정 번호, user_id 학생, usd_return_pct/krw_return_pct 누적수익률, recent_14d_return_pct 최근 14일 달러 성과, measurement_date 측정일, rank 순위입니다. 비교 기간이 부족하면 최근 성과는 null입니다. 여러 확정본이 함께 있으므로 run_id로 구분하세요.

## 계산과 파일 취급

최초 관측일 NAV는 100입니다. 기존 ETF별 평가액에 factors를 곱한 합계가 USD NAV입니다. 적용 거래일 종가에서 새 비중으로 재배분하며 KRW NAV = USD NAV × 당일 환율 / 최초 관측일 환율입니다. ETF 지수도 100에서 시작합니다.

CSV에서 수식으로 오인할 수 있는 =, +, -, @ 시작 문자열에는 작은따옴표를 붙입니다. 원문은 JSON을 참고하세요. 파일에는 학생 식별 정보와 전략이 있어 공개하지 않습니다. 분석 파일을 바꾸어도 앱 DB는 바뀌지 않으며 완전 복구 입력으로 사용할 수 없습니다.
