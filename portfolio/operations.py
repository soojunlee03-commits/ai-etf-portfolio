"""Instructor operations, health gates, immutable official results and portable exports."""
import hashlib
import io
import json
import math
import zipfile
import csv
from collections import Counter
from datetime import date, timedelta
from sqlalchemy import select, insert, update, and_, text
from .db import users, semesters, enrollments, submissions, allocations, windows, snapshots, audit, settings, official_runs, login_events
from .calendar import sessions, previous_session

class Operations:
    def selected_semester(self):
        found=self.rows(settings,settings.c.key=='active_semester')
        return int(found[0]['value']) if found else None

    def activate_semester(self, uid, sid):
        from .service import RuleError
        with self.engine.begin() as c:
            self.actor(c,uid,True)
            self.semester(c,sid,True)
            old=c.execute(select(settings).where(settings.c.key=='active_semester')).mappings().first()
            if old:
                c.execute(update(settings).where(settings.c.key=='active_semester').values(value=str(sid)))
            else:
                c.execute(insert(settings).values(key='active_semester',value=str(sid)))
            self.log(c,uid,'activate_semester',f'semester:{sid}',dict(old) if old else {},{'semester_id':sid},'기본 표시 학기 변경; 이전 학기 보존')

    def health(self, uid, sid, as_of=None):
        """Fail closed. Only aggregate notices leave this function for a student."""
        from .service import ETFS, weights
        issues=[]
        def issue(code, message):
            issues.append({'code':code,'message':message})
        try:
            with self.engine.connect() as c:
                u=self.actor(c,uid)
                if u['role']!='admin': self.access(c,uid,sid)
                s=dict(self.semester(c,sid))
        except Exception:
            # Do not convert an authorization failure into a readable health report.
            raise
        reference=min(as_of or date.today()-timedelta(days=1),date.fromisoformat(s['end']))
        try:
            expected=sessions(s['start'],str(reference))
            market=[r for r in self.market() if s['start']<=r['day']<=str(reference)]
            by_day={r['day']:r for r in market}
            if not expected:
                issue('not_started','아직 평가할 완료 거래일이 없습니다. 시작일 이후 시장 데이터를 저장하세요.')
            missing=[d for d in expected if d not in by_day]
            if missing:
                issue('missing_prices',f'ETF 가격·환율 스냅샷이 {len(missing)}거래일 누락되었습니다. 첫 누락일: {missing[0]}. 시장 데이터에서 누락 기간을 가져오세요.')
            for r in market:
                if r['day'] not in expected or r['previous_day']!=previous_session(r['day']):
                    issue('calendar','거래일 연결이 잘못되었습니다. 관리자에게 가격 날짜 점검을 요청하세요.'); break
                if set(r['prices'])!=set(ETFS) or set(r['factors'])!=set(ETFS) or any(not math.isfinite(float(v)) or float(v)<=0 for v in [*r['prices'].values(),*r['factors'].values()]):
                    issue('invalid_prices','ETF 가격 또는 일별 배율이 유효하지 않습니다. 정정 후 다시 점검하세요.'); break
                if not math.isfinite(r['fx']) or r['fx']<=0:
                    issue('invalid_fx','환율이 누락되었거나 유효하지 않습니다. 같은 날짜의 원/달러 환율을 정정하세요.'); break
                if any(not 0.5<=float(v)<=1.5 for v in r['factors'].values()):
                    issue('outlier','하루 변동률이 ±50% 범위를 벗어났습니다. 입력 배율과 수정종가를 확인하고 정정하세요.'); break
            if market and (reference-date.fromisoformat(market[-1]['day'])).days>4:
                issue('stale','가격·환율 기준일이 4일을 초과해 오래되었습니다. 최신 데이터를 가져오세요.')
            enrolled=self.rows(enrollments,enrollments.c.semester_id==sid)
            accounts={r['id'] for r in self.rows(users)}
            all_semesters={r['id'] for r in self.rows(semesters)}
            if any(r['user_id'] not in accounts or r['semester_id'] not in all_semesters for r in self.rows(enrollments)):
                issue('orphan','학생 또는 학기 연결이 손상되었습니다. 담당 운영자에게 복구를 요청하세요.')
            subs=self.rows(submissions,submissions.c.semester_id==sid)
            if any(n>1 for n in Counter((r['user_id'],r['event_key']) for r in subs).values()):
                issue('duplicates','중복 제출 기록이 있습니다. 공식 순위를 차단했습니다. 관리자에게 문의하세요.')
            if any(r['user_id'] not in {e['user_id'] for e in enrolled} for r in subs):
                issue('orphan_submission','수강 등록과 연결되지 않은 제출이 있습니다. 담당 운영자에게 문의하세요.')
            for sub in subs:
                versions=self.rows(allocations,allocations.c.submission_id==sub['id'])
                if not versions:
                    issue('allocation','배분 버전이 없는 제출이 있습니다. 담당 운영자에게 문의하세요.'); break
                try:
                    weights(json.loads(max(versions,key=lambda r:r['id'])['weights']))
                except Exception:
                    issue('allocation','유효하지 않은 자산배분이 있습니다. 관리자가 합계 100%와 ETF 비중을 정정해야 합니다.'); break
            if not issues:
                admin=next((r['id'] for r in self.rows(users) if r['role']=='admin' and r['active']),None)
                for e in enrolled:
                    if any(r['user_id']==e['user_id'] and r['event_key']=='initial' for r in subs):
                        p=self.performance(admin,sid,e['user_id'])
                        if not p or any(not math.isfinite(r['USD NAV']) or not math.isfinite(r['KRW NAV']) for r in p):
                            issue('performance','성과 계산을 완료하지 못했습니다. 배분과 가격 데이터를 점검하세요.'); break
            latest=market[-1]['day'] if market else None
        except Exception:
            issue('unreadable','저장된 데이터 형식 또는 DB 연결을 점검할 수 없습니다. 순위는 공개되지 않습니다. 운영자에게 문의하세요.')
            latest=None
        return {'ok':not issues,'issues':issues,'measurement_date':latest,'reference_date':str(reference),
                'status':'공식 계산 가능' if not issues else '공식 순위 차단'}

    def source_digest(self, uid, sid):
        with self.engine.connect() as c:
            u=self.actor(c,uid)
            if u['role']!='admin': self.access(c,uid,sid)
            s=dict(self.semester(c,sid))
        subs=self.rows(submissions,submissions.c.semester_id==sid)
        ids={r['id'] for r in subs}
        data={'semester':{k:s[k] for k in ('id','start','end','initial_deadline')},
              'submissions':subs,'allocations':[r for r in self.rows(allocations) if r['submission_id'] in ids],
              'market':[r for r in self.rows(snapshots) if s['start']<=r['day']<=s['end']],
              'enrollments':self.rows(enrollments,enrollments.c.semester_id==sid)}
        for key in ('submissions','allocations','market','enrollments'):
            data[key]=sorted(data[key],key=lambda r:r['id'])
        return hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest()

    def official_status(self, uid, sid):
        with self.engine.connect() as c:
            u=self.actor(c,uid)
            if u['role']!='admin': self.access(c,uid,sid)
        runs=self.rows(official_runs,official_runs.c.semester_id==sid)
        if not runs: return {'state':'미확정','run':None}
        latest=max(runs,key=lambda r:r['id'])
        state='공식 확정' if latest['digest']==self.source_digest(uid,sid) else '재확정 필요'
        if u['role']!='admin':
            latest={k:latest[k] for k in ('id','measurement_date','created_at')}
        return {'state':state,'run':latest}

    def publish_official(self, uid, sid, reason='정기 공식 성과 확정', as_of=None):
        from .service import RuleError, now
        with self.engine.connect() as c: self.actor(c,uid,True)
        health=self.health(uid,sid,as_of)
        if not health['ok']:
            raise RuleError('공식 성과를 저장하지 않았습니다. 데이터 상태의 경고를 해결한 뒤 다시 확정하세요.')
        before=self.source_digest(uid,sid)
        history={}
        try:
            for e in self.rows(enrollments,enrollments.c.semester_id==sid):
                if self.history(uid,sid,e['user_id']):
                    p=self.performance(uid,sid,e['user_id'])
                    if not p or any(not math.isfinite(float(r[k])) for r in p for k in ('USD NAV','KRW NAV')):
                        raise ValueError('performance')
                    history[str(e['user_id'])]=p
        except Exception:
            raise RuleError('성과 계산을 완료하지 못해 저장하지 않았습니다. 데이터 상태와 학생 배분을 확인하세요.') from None
        if not history:
            raise RuleError('저장하지 않았습니다. 초기 자산배분이 제출된 학생이 있어야 공식 성과를 확정할 수 있습니다.')
        if before!=self.source_digest(uid,sid):
            raise RuleError('계산 도중 데이터가 바뀌어 저장하지 않았습니다. 다시 확정하세요.')
        payload={'performance':history,'board':self.rank_records(history),
                 'conventions':{'price':'same-vintage adjusted-close daily ratios','fx':'KRW=X same-date daily Close, KRW per USD','effective':'close on first XNYS session on/after effective date'},
                 'market_version_ids':[r['id'] for r in self.market() if any(p['date']==r['day'] for p in next(iter(history.values())))],
                 'source_digest':before}
        with self.engine.begin() as c:
            rid=c.execute(insert(official_runs).values(semester_id=sid,measurement_date=health['measurement_date'],digest=before,
                payload=json.dumps(payload,ensure_ascii=False),actor_id=uid,created_at=now(),reason=reason)).inserted_primary_key[0]
            self.log(c,uid,'publish_official',f'semester:{sid}',{}, {'run_id':rid,'date':health['measurement_date']},reason)
        return rid

    def database_backup(self, uid):
        from contextlib import closing
        import tempfile
        import sqlite3
        from pathlib import Path
        from .service import RuleError
        with self.engine.begin() as c:
            self.actor(c,uid,True)
            self.log(c,uid,'database_backup','all',{}, {},'관리자가 완전 복구용 SQLite 백업 생성')
        if self.engine.dialect.name!='sqlite':
            raise RuleError('PostgreSQL은 공급자의 전체 백업 기능을 사용하세요.')
        with tempfile.TemporaryDirectory() as folder:
            destination=Path(folder)/'backup.db'
            raw=self.engine.raw_connection()
            try:
                with closing(sqlite3.connect(destination)) as dest: raw.driver_connection.backup(dest)
            finally: raw.close()
            return destination.read_bytes()

    def rank_records(self, histories):
        result=[]
        for uid, p in histories.items():
            last=p[-1]
            boundary=date.fromisoformat(last['date'])-timedelta(days=14)
            earlier=[r for r in p if r['date']<=str(boundary)]
            recent=(last['USD NAV']/earlier[-1]['USD NAV']-1)*100 if earlier else None
            result.append({'user_id':int(uid),'usd_return_pct':round(last['USD return %'],6),'krw_return_pct':round(last['KRW return %'],6),
                           'recent_14d_return_pct':recent,'measurement_date':last['date']})
        result.sort(key=lambda r:(-r['usd_return_pct'],r['user_id']))
        previous,rank=None,0
        for i,r in enumerate(result,1):
            if r['usd_return_pct']!=previous: rank=i
            r['rank']=rank; previous=r['usd_return_pct']
        return result

    def submission_dashboard(self, uid, sid):
        with self.engine.connect() as c:
            self.actor(c,uid,True); s=dict(self.semester(c,sid))
        from .service import now
        ws=sorted(self.rows(windows,windows.c.semester_id==sid),key=lambda r:r['opens'])
        opened=[w for w in ws if w['opens']<=now()]
        current=opened[-1] if opened else (ws[0] if ws else None)
        next_deadline=next((w['closes'] for w in ws if w['closes']>=now()),None)
        if s['initial_deadline']>=now(): next_deadline=s['initial_deadline']
        subs=self.rows(submissions,submissions.c.semester_id==sid)
        students={u['id']:u for u in self.rows(users)}
        logins=self.rows(login_events)
        rows=[]
        for e in self.rows(enrollments,enrollments.c.semester_id==sid):
            u=students[e['user_id']]
            ls=[r['created_at'] for r in logins if r['user_id']==u['id']]
            rows.append({'user_id':u['id'],'username':u['username'],'display_name':u['name'],'active':u['active'],
                'must_change_password':u['must_change'],'last_login_at':max(ls) if ls else '',
                'initial_submitted':any(r['user_id']==u['id'] and r['event_key']=='initial' for r in subs),
                'latest_rebalance_submitted':any(r['user_id']==u['id'] and current and r['event_key']==str(current['id']) for r in subs)})
        return {'students':rows,'window':current,'next_deadline':next_deadline}

    def export_zip(self, uid, sid):
        """English columns; CSV formula injection is neutralized at the export boundary."""
        data=json.loads(self.export(uid,sid))
        buffer=io.BytesIO()
        def safe(v):
            if isinstance(v,(dict,list)): v=json.dumps(v,ensure_ascii=False)
            if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@','\t','\r')): return "'"+v
            return v
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('semester.json',json.dumps(data,ensure_ascii=False,indent=2))
            for name,rows in data['tables'].items():
                if not isinstance(rows,list) or not rows: continue
                out=io.StringIO(); writer=csv.DictWriter(out,fieldnames=list(rows[0])); writer.writeheader()
                writer.writerows({k:safe(v) for k,v in r.items()} for r in rows)
                z.writestr(name+'.csv',out.getvalue().encode('utf-8-sig'))
            from pathlib import Path
            dictionary=Path(__file__).resolve().parents[1]/'docs'/'Data_Dictionary_KO.md'
            if dictionary.exists(): z.writestr('Data_Dictionary_KO.md',dictionary.read_bytes())
        return buffer.getvalue()
