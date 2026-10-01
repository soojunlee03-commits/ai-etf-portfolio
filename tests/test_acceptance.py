"""End-to-end class operations using isolated fictional data, real hashing and SQLite."""
import csv
import io
import json
import zipfile
from datetime import date, timedelta
from pathlib import Path
import pytest
from sqlalchemy import insert, update, delete
from sqlalchemy.exc import DatabaseError
from streamlit.testing.v1 import AppTest
from seed_demo import seed
from backup_db import copy_database
from portfolio.db import connect, users, semesters, snapshots, allocations, official_runs, windows
from portfolio.service import Service, RuleError, ETFS
from portfolio.ui_helpers import ADMIN_PAGES

@pytest.fixture(scope='module')
def template(tmp_path_factory):
    root=tmp_path_factory.mktemp('acceptance')
    path=seed(root/'demo.db')
    creds=list(csv.DictReader((root/'demo-access.csv').open(encoding='utf-8-sig')))
    return path,creds

@pytest.fixture
def demo(template,tmp_path):
    source,creds=template; path=copy_database(source,tmp_path/'class.db')
    svc=Service(connect('sqlite:///'+path.as_posix()))
    admin=svc.login(creds[0]['username'],creds[0]['password'])
    student=svc.login(creds[1]['username'],creds[1]['password'])
    yield svc,admin,student,creds,path
    svc.engine.dispose()

def test_official_snapshot_privacy_and_correction(demo):
    svc,admin,student,creds,path=demo
    assert svc.health(admin,1)['ok']
    assert len(svc.leaderboard(student,1))==4
    assert 'payload' not in svc.official_status(student,1)['run']
    old=svc.rows(official_runs)[0]['payload']
    h=svc.history(student,1)[0]
    svc.correct_allocation(admin,h['id'],{k:20 for k in ETFS},'입력 내용 검토에 따른 공식 정정')
    assert svc.official_status(admin,1)['state']=='재확정 필요'
    with pytest.raises(RuleError):svc.leaderboard(student,1)
    svc.publish_official(admin,1)
    assert len(svc.leaderboard(student,1))==4
    assert svc.rows(official_runs)[0]['payload']==old
    with pytest.raises(DatabaseError):
        with svc.engine.begin() as c:c.execute(update(allocations).values(reason='overwrite'))
    with pytest.raises(DatabaseError):
        with svc.engine.begin() as c:c.execute(delete(official_runs))

@pytest.mark.parametrize('problem',['missing_fx','missing_etf','invalid_total','stale','invalid_factor'])
def test_bad_data_blocks_official_rankings(demo,problem):
    svc,admin,student,_,_=demo
    if problem=='invalid_total':
        h=svc.history(student,1)[0]
        with svc.engine.begin() as c:
            c.execute(insert(allocations).values(submission_id=h['id'],weights=json.dumps({k:1 for k in ETFS}),reason='test corruption',created_at='2026-01-01T00:00:00+00:00',actor_id=admin))
    elif problem=='stale':
        future=date.today()+timedelta(days=10)
        health=svc.health(admin,1,as_of=future)
        assert not health['ok'] and any(i['code']=='stale' for i in health['issues'])
        with pytest.raises(RuleError):svc.publish_official(admin,1,as_of=future)
        return
    else:
        r=svc.rows(snapshots)[-1].copy();r.pop('id')
        if problem=='missing_fx':r['fx']='nan'
        if problem=='missing_etf':r['prices']=json.dumps({'SPY':100})
        if problem=='invalid_factor':r['factors']=json.dumps({k:999 for k in ETFS})
        with svc.engine.begin() as c:c.execute(insert(snapshots).values(**r))
    assert not svc.health(admin,1)['ok']
    with pytest.raises(RuleError):svc.leaderboard(student,1)
    with pytest.raises(RuleError):svc.publish_official(admin,1)

def test_export_backup_restart_archive(demo,tmp_path):
    svc,admin,student,creds,path=demo
    archive=zipfile.ZipFile(io.BytesIO(svc.export_zip(admin,1)))
    assert {'semester.json','performance_records.csv','leaderboard_records.csv','audit_log.csv','official_runs.csv'}<=set(archive.namelist())
    content=json.loads(archive.read('semester.json'))
    assert 'password' not in content['tables']['users'][0]
    before=svc.performance(student,1)
    full=tmp_path/'full.db';full.write_bytes(svc.database_backup(admin))
    svc.semester_settings(admin,1,False,True)
    svc.activate_semester(admin,2)
    assert svc.history(student,1)
    with pytest.raises(RuleError):svc.leaderboard(student,1)
    svc.engine.dispose(); reopened=Service(connect('sqlite:///'+path.as_posix()))
    assert reopened.performance(student,1)==before
    restored=Service(connect('sqlite:///'+full.as_posix()))
    assert restored.login(creds[1]['username'],creds[1]['password'])==student
    assert restored.performance(student,1)==before
    assert len(restored.leaderboard(student,1))==4
    reopened.engine.dispose();restored.engine.dispose()

def test_ui_end_to_end_rebalance_and_admin(demo,monkeypatch):
    svc,admin,student,creds,path=demo
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+path.as_posix())
    at=AppTest.from_file(Path('app.py').resolve()).run(timeout=45)
    at.text_input[0].set_value(creds[1]['username']);at.text_input[1].set_value(creds[1]['password'])
    next(b for b in at.button if b.label=='로그인').click().run(timeout=45)
    assert not at.exception and not at.error
    assert any(m.label=='포트폴리오 NAV (Portfolio NAV)' for m in at.metric)
    at.sidebar.radio[0].set_value('리밸런싱').run(timeout=45)
    next(n for n in at.number_input if n.label=='SPY 비중 (%)').set_value(10).run()
    assert next(b for b in at.button if b.label=='리밸런싱 최종 제출').disabled
    next(n for n in at.number_input if n.label=='SPY 비중 (%)').set_value(25)
    at.text_area[0].set_value('금리 하락을 예상하여 국채 중심의 기존 방어적 비중을 유지합니다.')
    next(c for c in at.checkbox if c.label=='변경 사유와 비중을 확인했으며 최종 제출에 동의합니다.').check().run()
    next(b for b in at.button if b.label=='리밸런싱 최종 제출').click().run(timeout=45)
    assert not at.exception and not at.error
    assert any('수정 불가' in s.value for s in at.success)
    assert len(svc.history(student,1))==3
    at.sidebar.radio[0].set_value('포트폴리오 이력').run(timeout=45)
    assert len(at.expander)==3
    next(b for b in at.button if b.label=='로그아웃').click().run()
    at.text_input[0].set_value(creds[0]['username']);at.text_input[1].set_value(creds[0]['password'])
    next(b for b in at.button if b.label=='로그인').click().run(timeout=45)
    for page in ADMIN_PAGES:
        at.sidebar.radio[0].set_value(page).run(timeout=45)
        assert not at.exception and not at.error,page
    at.sidebar.radio[0].set_value('데이터 상태').run(timeout=45)
    next(b for b in at.button if b.label=='공식 성과 확정').click().run(timeout=45)
    assert not at.error
    assert len(svc.leaderboard(admin,1))==4

def test_database_failure_is_korean(tmp_path,monkeypatch):
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+(tmp_path/'does-not-exist'/'db.sqlite').as_posix())
    at=AppTest.from_file(Path('app.py').resolve()).run(timeout=30)
    assert not at.exception
    assert at.error and '데이터베이스' in at.error[0].value
    assert 'OperationalError' not in at.error[0].value

def test_backend_access_controls(demo):
    svc,admin,student,_,_=demo
    for fn in [lambda:svc.activate_semester(student,2),lambda:svc.publish_official(student,1),lambda:svc.export_zip(student,1),lambda:svc.database_backup(student),lambda:svc.history(student,1,student+1)]:
        with pytest.raises(RuleError):fn()
    sid=2
    svc.submit(student,sid,{k:20 for k in ETFS},'초기 전략')
    with pytest.raises(RuleError):svc.submit(student,sid,{k:20 for k in ETFS},'중복')
    past=min(svc.rows(windows),key=lambda r:r['id'])
    with pytest.raises(RuleError):svc.submit(student,1,{k:20 for k in ETFS},'마감 이후의 배분을 다시 제출할 수 없는지 확인합니다.',past['id'])

def test_admin_creates_class_and_student_through_forms(demo,monkeypatch):
    svc,admin,_,creds,path=demo
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+path.as_posix())
    at=AppTest.from_file(Path('app.py').resolve()).run(timeout=45)
    at.text_input[0].set_value(creds[0]['username']);at.text_input[1].set_value(creds[0]['password'])
    next(b for b in at.button if b.label=='로그인').click().run(timeout=45)
    at.sidebar.radio[0].set_value('학기 / 일정').run(timeout=45)
    next(t for t in at.text_input if t.label=='학기 / 수업 이름 (필수)').set_value('화면 검증 새 학기')
    next(c for c in at.checkbox if c.label=='새 학기의 날짜를 확인했으며 기존 학기가 보존됨을 이해했습니다.').check()
    button=next(b for b in at.button if b.label=='새 학기 생성')
    assert not button.disabled
    button.click().run(timeout=45)
    assert not at.error and not at.exception
    new=next(s for s in svc.rows(semesters) if s['name']=='화면 검증 새 학기')
    at.sidebar.selectbox[0].select(new).run(timeout=45)
    next(c for c in at.checkbox if c.label=='기본 표시 학기를 변경하며 이전 기록은 보존됨을 확인했습니다.').check().run()
    next(b for b in at.button if b.label=='운영 학기로 설정').click().run(timeout=45)
    assert svc.selected_semester()==new['id']
    next(c for c in at.checkbox if c.label=='순위표 공개 (OPEN)').check()
    next(c for c in at.checkbox if c.label=='학생에게 미치는 영향과 보관 전 백업을 확인했습니다.').check()
    next(b for b in at.button if b.label=='운영 설정 저장').click().run(timeout=45)
    assert next(s for s in svc.rows(semesters) if s['id']==new['id'])['leaderboard']
    next(b for b in at.button if b.label=='일정 추가').click().run(timeout=45)
    assert not at.error and not at.exception
    assert svc.rows(windows,windows.c.semester_id==new['id'])
    at.sidebar.radio[0].set_value('학생 관리').run(timeout=45)
    next(t for t in at.text_input if t.label=='학생 아이디 (필수)').set_value('new_ui_student')
    next(t for t in at.text_input if t.label=='공개 닉네임 (필수)').set_value('화면 검증 학생')
    next(t for t in at.text_input if t.label=='임시 비밀번호 (8자 이상)').set_value('ui-only-testing-secret')
    next(b for b in at.button if b.label=='학생 등록').click().run(timeout=45)
    assert not at.error and not at.exception
    assert len(svc.submission_dashboard(admin,new['id'])['students'])==1
    at.sidebar.radio[0].set_value('학기 / 일정').run(timeout=45)
    next(c for c in at.checkbox if c.label=='학기 보관 · 학생 제출 중단').check()
    next(c for c in at.checkbox if c.label=='학생에게 미치는 영향과 보관 전 백업을 확인했습니다.').check()
    next(b for b in at.button if b.label=='운영 설정 저장').click().run(timeout=45)
    assert next(s for s in svc.rows(semesters) if s['id']==new['id'])['archived']
    assert svc.rows(semesters,semesters.c.id==1)
