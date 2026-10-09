import time
from pathlib import Path
from streamlit.testing.v1 import AppTest
from portfolio.db import connect, users, semesters
from portfolio.service import Service

def test_self_signup_and_login(tmp_path,monkeypatch):
    url=f'sqlite:///{tmp_path / "signup-ui.db"}'
    monkeypatch.setenv('DATABASE_URL',url)
    svc=Service(connect(url))
    svc.bootstrap('instructor','admin123')
    admin=svc.login('instructor','admin123')
    svc.create_semester(admin,'My class','2027-01-05','2027-06-30','2027-01-04T01:00:00+00:00')
    at=AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py').run(timeout=30)
    for label,value in [('사용할 아이디','chosen'),('공개 닉네임','나의 닉네임'),('비밀번호 (8자 이상)','pass1234'),('비밀번호 확인','mismatch')]:
        next(t for t in at.text_input if t.label==label).set_value(value)
    next(b for b in at.button if b.label=='회원가입').click().run(timeout=30)
    assert any('일치하지' in e.value for e in at.error)
    assert len(svc.rows(users))==1
    next(t for t in at.text_input if t.label=='비밀번호 확인').set_value('pass1234')
    next(b for b in at.button if b.label=='회원가입').click().run(timeout=30)
    assert not at.exception and not at.error
    assert any('회원가입이 완료' in s.value for s in at.success)
    next(t for t in at.text_input if t.label=='아이디').set_value('chosen')
    next(t for t in at.text_input if t.label=='비밀번호').set_value('pass1234')
    next(b for b in at.button if b.label=='로그인').click().run(timeout=30)
    assert not at.exception and not at.error
    assert not any(h.value=='처음 로그인 · 비밀번호 변경' for h in at.header)
    assert '학생 관리' not in at.sidebar.radio[0].options

def test_login_and_admin_pages(tmp_path,monkeypatch):
    url=f'sqlite:///{tmp_path / "ui.db"}'
    monkeypatch.setenv('DATABASE_URL',url)
    svc=Service(connect(url))
    svc.bootstrap('instructor','temporary-test-secret')
    admin=svc.login('instructor','temporary-test-secret')
    svc.create_semester(admin,'Semester','2027-01-05','2027-06-30','2027-01-04T01:00:00+00:00')
    at=AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py').run(timeout=30)
    at.text_input[0].set_value('instructor');at.text_input[1].set_value('temporary-test-secret')
    next(b for b in at.button if b.label=='로그인').click().run(timeout=30)
    assert not at.exception
    assert not at.error
    for page in ['학생 관리','학기 / 일정','시장 데이터','데이터 상태','정정 / 감사','내보내기 / 백업','관리자 사용가이드','운영 현황']:
        at.sidebar.radio[0].set_value(page).run(timeout=30)
        assert not at.exception, page
        assert not at.error, page

def test_student_submission_and_navigation(tmp_path,monkeypatch):
    url=f'sqlite:///{tmp_path / "student-ui.db"}'
    monkeypatch.setenv('DATABASE_URL',url)
    svc=Service(connect(url))
    svc.bootstrap('instructor','temporary-test-secret')
    admin=svc.login('instructor','temporary-test-secret')
    svc.create_semester(admin,'Student semester','2027-01-05','2027-06-30','2027-01-04T01:00:00+00:00')
    sid=svc.rows(semesters)[0]['id']
    svc.add_student(admin,'student','Student','temporary-student-secret',sid)
    at=AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py').run(timeout=30)
    at.text_input[0].set_value('student');at.text_input[1].set_value('temporary-student-secret')
    next(b for b in at.button if b.label=='로그인').click().run(timeout=30)
    assert any(h.value=='처음 로그인 · 비밀번호 변경' for h in at.header)
    at.text_input[0].set_value('temporary-student-secret')
    at.text_input[1].set_value('new-student-secret');at.text_input[2].set_value('new-student-secret')
    next(b for b in at.button if b.label=='비밀번호 변경').click().run(timeout=30)
    assert not at.exception and not at.error
    next(c for c in at.checkbox if c.label=='제출 후 직접 수정할 수 없음을 확인했습니다.').check().run()
    next(b for b in at.button if b.label=='초기 자산배분 최종 제출').click().run(timeout=30)
    assert not at.exception and not at.error
    assert any('제출 완료' in s.value for s in at.success)
    assert len(svc.history(svc.login('student','new-student-secret'),sid))==1
    for page in ['성과','리밸런싱','포트폴리오 이력','사용가이드']:
        at.sidebar.radio[0].set_value(page).run(timeout=30)
        assert not at.exception and not at.error, page
    assert '순위표' not in at.sidebar.radio[0].options
    assert '학생 관리' not in at.sidebar.radio[0].options

def test_delete_last_semester_and_restore_ui(tmp_path,monkeypatch):
    url=f'sqlite:///{tmp_path / "trash-ui.db"}'
    monkeypatch.setenv('DATABASE_URL',url)
    svc=Service(connect(url)); svc.bootstrap('admin','test-password')
    admin=svc.login('admin','test-password')
    svc.create_semester(admin,'Delete me','2027-01-05','2027-06-30','2027-01-04T01:00:00+00:00')
    at=AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py').run(timeout=30)
    at.session_state['uid']=admin; at.session_state['login_time']=time.time()
    at.run(timeout=30)
    at.sidebar.radio[0].set_value('학기 / 일정').run(timeout=30)
    next(t for t in at.text_input if t.label=='삭제할 학기 이름을 정확히 입력').set_value('Delete me')
    next(c for c in at.checkbox if c.label=='위 학기 전체를 휴지통으로 이동합니다.').check()
    next(b for b in at.button if b.label=='학기 삭제').click().run(timeout=30)
    assert not at.exception and not at.error
    assert svc.available_semesters()==[]
    next(b for b in at.button if b.label=='학기 복원').click().run(timeout=30)
    assert not at.exception and not at.error
    assert svc.available_semesters()[0]['name']=='Delete me'


def test_admin_submissions_survive_missing_and_stale_prices(tmp_path,monkeypatch):
    from portfolio.service import ETFS, RuleError
    import pytest
    url=f'sqlite:///{tmp_path / "admin-detail.db"}'
    monkeypatch.setenv('DATABASE_URL',url)
    svc=Service(connect(url)); svc.bootstrap('admin','admin-test-password')
    admin=svc.login('admin','admin-test-password')
    svc.create_semester(admin,'Review class','2026-01-05','2026-12-31','2026-01-04T01:00:00+00:00')
    sid=svc.rows(semesters)[0]['id']
    student=svc.signup_student('one','Submitted student','student-password',sid)
    svc.signup_student('two','Unsubmitted student','student-password',sid)
    svc.submit(student,sid,{k:20 for k in ETFS},'분산 투자를 위한 최초 전략',at='2026-01-03T01:00:00+00:00')
    at=AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py').run(timeout=30)
    at.session_state['uid']=admin; at.session_state['login_time']=time.time()
    at.run(timeout=30)
    at.sidebar.radio[0].set_value('학생 성과 / 제출 내역').run(timeout=30)
    assert not at.exception and not at.error
    table=at.dataframe[0].value
    assert table.iloc[0]['SPY']=='20.0%'
    assert table.iloc[0]['최근 제출 사유']=='분산 투자를 위한 최초 전략'
    assert table.iloc[0]['성과 데이터']=='가격·환율 확인 필요'
    assert table.iloc[1]['성과 데이터']=='초기 미제출'
    assert any('분산 투자를 위한 최초 전략' in m.value for m in at.markdown)
    svc.store_market(admin,[dict(day=day,previous_day=prev,fx=1300,
        factors={k:factor for k in ETFS},prices={k:100 for k in ETFS},source='test')
        for day,prev,factor in [('2026-01-05','2026-01-02',1),('2026-01-06','2026-01-05',1.01)]])
    at.run(timeout=30)
    assert not at.exception and not at.error
    table=at.dataframe[0].value
    assert table.iloc[0]['성과 기준일']=='2026-01-06'
    assert table.iloc[0]['USD 수익률']=='+1.00%'
    assert table.iloc[0]['성과 데이터']=='저장 기준일 참고 성과'
    assert any('검증된 저장 자료' in w.value for w in at.warning)
    assert any(m.label=='포트폴리오 NAV (Portfolio NAV)' and m.value=='101.00' for m in at.metric)
    with pytest.raises(RuleError): svc.leaderboard(admin,sid)
    svc.engine.dispose()


def test_admin_preview_rejects_internal_market_gap(tmp_path):
    from portfolio.service import ETFS
    from portfolio.ui_helpers import performance_health
    svc=Service(connect(f'sqlite:///{tmp_path / "gap.db"}'))
    svc.bootstrap('admin','admin-test-password'); admin=svc.login('admin','admin-test-password')
    svc.create_semester(admin,'Gap class','2026-01-05','2026-12-31','2026-01-04T01:00:00+00:00')
    sid=svc.rows(semesters)[0]['id']
    # Simulate a damaged saved interval, which the import path normally rejects.
    svc.market=lambda:[dict(day=day,previous_day=prev,fx=1300,
        factors={k:1 for k in ETFS},prices={k:100 for k in ETFS})
        for day,prev in [('2026-01-05','2026-01-02'),('2026-01-07','2026-01-06')]]
    health,delayed=performance_health(svc,admin,sid,admin_preview=True)
    assert not health['ok'] and not delayed
    svc.engine.dispose()


def test_login_failure_is_explained_after_service_refresh(tmp_path,monkeypatch):
    import portfolio.ui_app as ui
    from portfolio.ui_helpers import perform
    from portfolio.service import RuleError
    url=f'sqlite:///{tmp_path / "login-refresh.db"}'
    first=ui.service(url)
    first.bootstrap('admin','correct-test-password')
    class RefreshedService(Service):
        pass
    monkeypatch.setattr(ui,'Service',RefreshedService)
    fresh=ui.service(url)
    assert isinstance(fresh,RefreshedService)
    assert fresh.engine is first.engine
    messages=[]
    monkeypatch.setattr('portfolio.ui_helpers.st.error',messages.append)
    assert perform(lambda:fresh.login('admin','wrong-password'))==(False,None)
    assert '로그인 정보가 올바르지 않거나 계정이 잠겼습니다' in messages[0]
    assert fresh.login('admin','correct-test-password')
    fresh.engine.dispose()
