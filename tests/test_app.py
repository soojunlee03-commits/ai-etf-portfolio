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
