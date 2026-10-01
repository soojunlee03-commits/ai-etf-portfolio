import json
import pytest
from sqlalchemy import update
from portfolio.db import connect, users, semesters, windows, allocations, snapshots, enrollments
from portfolio.service import Service, RuleError, ETFS

PASSWORD = 'testing-only-password'
W = {k:20 for k in ETFS}

@pytest.fixture
def system(tmp_path):
    svc=Service(connect(f'sqlite:///{tmp_path / "test.db"}'))
    svc.bootstrap('admin',PASSWORD)
    admin=svc.login('admin',PASSWORD)
    svc.create_semester(admin,'Test','2026-01-05','2026-06-30','2026-01-04T10:00:00+00:00')
    sid=svc.rows(semesters)[0]['id']
    for name in ['one','two']:
        svc.add_student(admin,name,name,PASSWORD,sid)
        u=svc.login(name,PASSWORD)
        svc.change_password(u,PASSWORD,PASSWORD+'new')
    students=[r['id'] for r in svc.rows(users) if r['role']=='student']
    return svc,admin,sid,*students

def submit_initial(svc,uid,sid,values=W):
    svc.submit(uid,sid,values,'Initial',at='2026-01-03T10:00:00+00:00')

def test_student_signup(system):
    svc,admin,sid,*_=system
    uid=svc.signup_student(' MyStudent ','학생','abcd1234',sid)
    assert svc.login('MYSTUDENT','abcd1234')==uid
    user=svc.rows(users,users.c.id==uid)[0]
    assert user['role']=='student' and not user['must_change']
    assert user['password']!='abcd1234'
    assert svc.rows(enrollments,enrollments.c.user_id==uid)[0]['semester_id']==sid
    with svc.engine.connect() as c:
        with pytest.raises(RuleError): svc.actor(c,uid,admin=True)
    with pytest.raises(RuleError,match='이미 사용'):
        svc.signup_student('mystudent','다른 학생','abcd1234',sid)
    for username,name,password in [('short','학생','1234567'),(' ','학생','abcd1234'),('blank',' ','abcd1234')]:
        with pytest.raises(RuleError): svc.signup_student(username,name,password,sid)
    with svc.engine.begin() as c:
        c.execute(update(semesters).where(semesters.c.id==sid).values(archived=True))
    with pytest.raises(RuleError): svc.signup_student('archived','학생','abcd1234',sid)
    assert not svc.rows(users,users.c.username=='archived')
    assert svc.signup_student('no_class','학생','abcd1234')
    svc.change_password(uid,'abcd1234','newpass8')
    assert svc.login('mystudent','newpass8')==uid

def test_signup_requires_initialized_app(tmp_path):
    svc=Service(connect(f'sqlite:///{tmp_path / "empty.db"}'))
    with pytest.raises(RuleError,match='관리자 초기 설정'):
        svc.signup_student('student','학생','abcd1234')
    assert not svc.rows(users)

def market(svc,admin):
    data=[]
    for day,prev,factor,fx in [('2026-01-05','2026-01-02',1,1000),('2026-01-06','2026-01-05',1.1,1100),('2026-01-07','2026-01-06',1.2,1050),('2026-01-08','2026-01-07',1.1,1000)]:
        factors={k:1 for k in ETFS}; factors['SPY']=factor
        data.append({'day':day,'previous_day':prev,'prices':{k:100 for k in ETFS},'factors':factors,'fx':fx,'source':'test synthetic'})
    svc.store_market(admin,data)
    return data

@pytest.mark.parametrize('bad',[{'SPY':100}, {**W,'SPY':19}, {**W,'SPY':21}, {**W,'SPY':float('nan')}, {**W,'SPY':float('inf')}, {**W,'SPY':-10,'IEF':50}, {**W,'SPY':'bad'}])
def test_invalid_weights(system,bad):
    svc,admin,sid,one,two=system
    with pytest.raises(RuleError): submit_initial(svc,one,sid,bad)

def test_lock_and_access(system):
    svc,admin,sid,one,two=system
    submit_initial(svc,one,sid)
    with pytest.raises(RuleError): submit_initial(svc,one,sid)
    with pytest.raises(RuleError): svc.history(two,sid,one)
    with pytest.raises(RuleError): svc.add_student(one,'bad','bad',PASSWORD,sid)
    with pytest.raises(RuleError): svc.export(one)
    with pytest.raises(RuleError): svc.leaderboard(one,sid)
    assert len(svc.history(admin,sid,one))==1

def test_deadline(system):
    svc,admin,sid,one,two=system
    with pytest.raises(RuleError): svc.submit(one,sid,W,'late',at='2026-01-04T11:00:00+00:00')
    with pytest.raises(RuleError): svc.submit(one,sid,W,'wrong window',window_id=100)

def test_buy_hold_rebalance_fx(system):
    svc,admin,sid,one,two=system
    initial={k:0 for k in ETFS}; initial['SPY']=100
    submit_initial(svc,one,sid,initial)
    market(svc,admin)
    svc.add_window(admin,sid,'rebalance','2026-01-05T01:00:00+00:00','2026-01-06T01:00:00+00:00','2026-01-07')
    wid=svc.rows(windows)[0]['id']
    new={k:0 for k in ETFS}; new['SGOV']=100
    with pytest.raises(RuleError): svc.submit(one,sid,new,'',wid,at='2026-01-05T02:00:00+00:00')
    svc.submit(one,sid,new,'Defensive allocation to protect against equity risk',wid,at='2026-01-05T02:00:00+00:00')
    with pytest.raises(RuleError): svc.submit(one,sid,new,'Again',wid,at='2026-01-05T03:00:00+00:00')
    p=svc.performance(one,sid)
    assert [r['USD NAV'] for r in p]==pytest.approx([100,110,132,132])
    assert p[1]['KRW return %']==pytest.approx(21)
    assert p[-1]['SPY']==pytest.approx(145.2)

def test_no_submission_means_hold_and_drift(system):
    svc,admin,sid,one,two=system
    submit_initial(svc,one,sid)
    market(svc,admin)
    p=svc.performance(one,sid)
    assert p[-1]['USD NAV']==pytest.approx(109.04)

def test_revision_retains_history(system):
    svc,admin,sid,one,two=system
    submit_initial(svc,one,sid)
    sid2=svc.history(one,sid)[0]['id']
    new={k:0 for k in ETFS}; new['SPY']=100
    svc.correct_allocation(admin,sid2,new,'Input correction')
    assert len(svc.rows(allocations))==2
    assert svc.history(one,sid)[0]['versions']==2
    assert len(json.loads(svc.export(admin))['tables']['audit_log'])>0
    assert 'password' not in json.loads(svc.export(admin))['tables']['users'][0]

def test_snapshot_freeze_and_correct(system):
    svc,admin,sid,one,two=system
    data=market(svc,admin)
    data[1]['fx']=1200
    svc.store_market(admin,data)
    assert svc.market()[1]['fx']==1100
    svc.store_market(admin,[data[1]],True,'FX correction')
    assert svc.market()[1]['fx']==1200
    assert len(svc.rows(snapshots))==5
    bad={**data[-1],'day':'2026-01-12','previous_day':'2026-01-09'}
    with pytest.raises(RuleError):svc.store_market(admin,[bad])

def test_archive_inactive_leaderboard(system):
    svc,admin,sid,one,two=system
    submit_initial(svc,one,sid);submit_initial(svc,two,sid)
    market(svc,admin)
    with svc.engine.begin() as c:
        c.execute(update(semesters).where(semesters.c.id==sid).values(end='2026-01-08'))
    svc.publish_official(admin,sid)
    svc.semester_settings(admin,sid,True,True)
    assert [r['순위'] for r in svc.leaderboard(one,sid)]==[1,1]
    with pytest.raises(RuleError):svc.add_window(admin,sid,'x','2026-01-05T01:00:00+00:00','2026-01-06T01:00:00+00:00','2026-01-07')
    svc.edit_student(admin,one,'one',False)
    with pytest.raises(RuleError):svc.history(one,sid)
    with pytest.raises(RuleError):svc.login('one',PASSWORD+'new')

def test_login_throttle(system):
    svc,admin,sid,one,two=system
    for _ in range(5):
        with pytest.raises(RuleError):svc.login('one','wrong')
    with pytest.raises(RuleError):svc.login('one',PASSWORD+'new')

def test_market_prepend_and_holidays(system):
    from portfolio.calendar import sessions, previous_session
    svc,admin,*_=system
    data=market(svc,admin)
    earlier={**data[0],'day':'2026-01-02','previous_day':'2025-12-31'}
    svc.store_market(admin,[earlier])
    assert svc.market()[0]['day']=='2026-01-02'
    assert previous_session('2026-01-02')=='2025-12-31'
    assert sessions('2026-01-01','2026-01-04')==['2026-01-02']
    with pytest.raises(RuleError):svc.store_market(admin,[{**earlier,'day':'2026-01-01'}])
