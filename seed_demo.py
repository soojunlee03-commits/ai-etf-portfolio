"""Create a separate, never-overwritten fictional classroom with random local credentials."""
import csv
import json
import math
import secrets
from pathlib import Path
from datetime import date, timedelta
from portfolio.db import connect, users, semesters, windows
from portfolio.service import Service, ETFS
from portfolio.calendar import sessions, previous_session

def seed(path='data/demo.db',today=None):
    path=Path(path).resolve(); today=today or date.today()
    if path.exists():
        return path
    path.parent.mkdir(parents=True,exist_ok=True)
    svc=Service(connect('sqlite:///'+path.as_posix())); credentials=[]
    password=secrets.token_urlsafe(18); svc.bootstrap('demo_admin',password)
    admin=svc.login('demo_admin',password); credentials.append({'role':'관리자','username':'demo_admin','password':password})
    start=sessions(str(today-timedelta(days=45)),str(today))[0]
    end=str(today+timedelta(days=45))
    deadline=str(date.fromisoformat(start)-timedelta(days=1))+'T00:00:00+00:00'
    svc.create_semester(admin,'데모 · 성과와 리밸런싱 체험',start,end,deadline)
    sid=svc.rows(semesters)[0]['id']
    svc.create_semester(admin,'데모 · 초기 자산배분 연습',str(today+timedelta(days=7)),str(today+timedelta(days=90)),str(today+timedelta(days=5))+'T00:00:00+00:00')
    practice=max(svc.rows(semesters),key=lambda r:r['id'])['id']
    past_eff=date.fromisoformat(start)+timedelta(days=14)
    svc.add_window(admin,sid,'지난 회차 · 예시',str(past_eff-timedelta(days=3))+'T00:00:00+00:00',str(past_eff-timedelta(days=1))+'T00:00:00+00:00',str(past_eff))
    past=svc.rows(windows)[0]
    svc.add_window(admin,sid,'현재 회차 · 제출 체험',str(today-timedelta(days=1))+'T00:00:00+00:00',str(today+timedelta(days=2))+'T00:00:00+00:00',str(today+timedelta(days=3)))
    for i,name in enumerate(['푸른고래','초록나무','노란별','보라구름'],1):
        pw=secrets.token_urlsafe(18); username=f'demo_student{i}'
        svc.add_student(admin,username,name,pw,sid); uid=svc.login(username,pw); svc.change_password(uid,pw,pw)
        svc.enroll(admin,uid,practice); credentials.append({'role':'학생','username':username,'password':pw})
        weights={'SPY':20+i*5,'IEF':30-i*5,'GLD':20,'VNQ':15,'SGOV':15}
        svc.submit(uid,sid,weights,'가상 수업의 초기 분산투자 전략',at=str(date.fromisoformat(start)-timedelta(days=2))+'T00:00:00+00:00')
        if i<4:
            svc.submit(uid,sid,{'SPY':25,'IEF':30,'GLD':20,'VNQ':10,'SGOV':15},'금리 변동과 주식 위험을 함께 고려하여 국채 비중을 높였습니다.',past['id'],at=past['opens'])
    records=[]; prices={k:100.0 for k in ETFS}
    for j,day in enumerate(sessions(start,str(today-timedelta(days=1)))):
        factors={k:1+0.001*math.sin(j/3+i)+0.0003*(i-1) for i,k in enumerate(ETFS)}
        prices={k:prices[k]*factors[k] for k in ETFS}
        records.append({'day':day,'previous_day':previous_session(day),'prices':prices.copy(),'factors':factors,'fx':1350+8*math.sin(j/5),'source':'DEMO_SYNTHETIC_NOT_OFFICIAL_MARKET_DATA'})
    svc.store_market(admin,records); svc.semester_settings(admin,sid,True,False); svc.activate_semester(admin,sid)
    svc.publish_official(admin,sid,'데모 합성 데이터의 확정 절차 예시',as_of=today-timedelta(days=1))
    access=path.parent/'demo-access.csv'
    with access.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['role','username','password']); writer.writeheader(); writer.writerows(credentials)
    svc.engine.dispose()
    return path

if __name__=='__main__':
    p=seed(); print(f'Demo database ready: {p}\nLogin details: {p.parent / "demo-access.csv"}\nDemo uses fictional data only. Existing files are not reset.')
