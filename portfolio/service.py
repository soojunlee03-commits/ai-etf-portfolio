"""All authorization, submission and calculation rules live here, not in widgets."""
import hashlib
import hmac
import json
import math
import secrets
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal, InvalidOperation
from sqlalchemy import select, insert, update, delete, and_
from sqlalchemy.exc import IntegrityError
from .db import users, semesters, enrollments, windows, submissions, allocations, snapshots, audit, metadata, login_events, official_runs, semester_trash, settings
from .operations import Operations
from .calendar import previous_session, sessions

ETFS = {'SPY': '미국 주식 (S&P 500)', 'IEF': '미국 중기 국채', 'GLD': '금',
        'VNQ': '미국 부동산 투자신탁', 'SGOV': '미국 초단기 국채 · 현금성 자산'}

class RuleError(Exception):
    pass

def now():
    return datetime.now(timezone.utc).isoformat()

def password_hash(value):
    if len(value) < 8:
        raise RuleError('비밀번호는 8자 이상이어야 합니다.')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', value.encode(), salt.encode(), 600000).hex()
    return f'{salt}${digest}'

def verify(value, stored):
    salt, digest = stored.split('$')
    return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256', value.encode(), salt.encode(), 600000).hex(), digest)

def weights(values):
    if set(values) != set(ETFS):
        raise RuleError('SPY, IEF, GLD, VNQ, SGOV 다섯 ETF만 입력하세요.')
    try:
        numbers = {k: Decimal(str(v)) for k, v in values.items()}
        if any(not v.is_finite() or v < 0 or v > 100 for v in numbers.values()):
            raise ValueError()
        if sum(numbers.values()) != Decimal('100'):
            raise RuleError('배분 합계가 정확히 100%여야 합니다.')
    except (InvalidOperation, ValueError, TypeError):
        raise RuleError('비중은 0~100 사이의 유효한 숫자로 입력하세요.') from None
    return {k: float(v) for k, v in numbers.items()}

class Service(Operations):
    def __init__(self, engine):
        self.engine = engine

    def rows(self, table, condition=None):
        with self.engine.connect() as c:
            q = select(table)
            return [dict(r) for r in c.execute(q.where(condition) if condition is not None else q).mappings()]

    def actor(self, c, uid, admin=False):
        u = c.execute(select(users).where(users.c.id == uid)).mappings().first()
        if not u or not u['active'] or (admin and u['role'] != 'admin'):
            raise RuleError('이 작업에 대한 접근 권한이 없습니다.')
        return u

    def log(self, c, uid, action, target, before, after, reason):
        c.execute(insert(audit).values(actor_id=uid, action=action, target=str(target),
            before=json.dumps(before, ensure_ascii=False, default=str), after=json.dumps(after, ensure_ascii=False, default=str),
            reason=reason, created_at=now()))

    def bootstrap(self, username, password):
        if not username.strip():
            raise RuleError('관리자 아이디가 필요합니다.')
        with self.engine.begin() as c:
            if c.execute(select(users.c.id)).first():
                raise RuleError('이미 초기화된 시스템입니다.')
            c.execute(insert(users).values(username=username.strip().lower(), name='Instructor',
                password=password_hash(password), role='admin', active=True, must_change=False))

    def login(self, username, password):
        result = None
        with self.engine.begin() as c:
            u = c.execute(select(users).where(users.c.username == username.strip().lower()).with_for_update()).mappings().first()
            if u and u['active'] and (not u['locked_until'] or u['locked_until'] <= now()):
                if verify(password, u['password']):
                    c.execute(update(users).where(users.c.id == u['id']).values(failed=0, locked_until=''))
                    result = u['id']
                    c.execute(insert(login_events).values(user_id=u['id'],created_at=now()))
                else:
                    failed = u['failed'] + 1
                    c.execute(update(users).where(users.c.id == u['id']).values(failed=failed,
                        locked_until=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat() if failed >= 5 else ''))
        if result is None:
            raise RuleError('로그인 정보가 올바르지 않거나 계정이 잠겼습니다. 반복 실패 시 15분 후 다시 시도하세요.')
        return result

    def change_password(self, uid, old, new):
        with self.engine.begin() as c:
            u = self.actor(c, uid)
            if not verify(old, u['password']):
                raise RuleError('현재 비밀번호가 일치하지 않습니다.')
            c.execute(update(users).where(users.c.id == uid).values(password=password_hash(new), must_change=False))

    def signup_student(self, username, name, password, sid=None):
        username, name = username.strip().lower(), name.strip()
        if not username or not name or len(username) > 100 or len(name) > 100:
            raise RuleError('아이디와 닉네임을 각각 1~100자로 입력하세요.')
        hashed = password_hash(password)
        try:
            with self.engine.begin() as c:
                if not c.execute(select(users.c.id).where(users.c.role == 'admin')).first():
                    raise RuleError('관리자 초기 설정이 필요합니다.')
                if sid is not None:
                    self.semester(c, sid, writable=True)
                student = c.execute(insert(users).values(username=username, name=name,
                    password=hashed, role='student', active=True, must_change=False)).inserted_primary_key[0]
                if sid is not None:
                    c.execute(insert(enrollments).values(user_id=student, semester_id=sid))
                self.log(c, student, 'register', student, {},
                         {'username': username, 'semester': sid}, '학생 직접 회원가입')
                return student
        except IntegrityError:
            raise RuleError('이미 사용 중인 아이디입니다. 다른 아이디를 입력하세요.') from None

    def add_student(self, uid, username, name, password, sid):
        if not username.strip() or not name.strip():
            raise RuleError('아이디와 닉네임을 입력하세요.')
        try:
            with self.engine.begin() as c:
                self.actor(c, uid, True)
                self.semester(c, sid, writable=True)
                student = c.execute(insert(users).values(username=username.strip().lower(), name=name.strip(),
                    password=password_hash(password), role='student', active=True, must_change=True)).inserted_primary_key[0]
                c.execute(insert(enrollments).values(user_id=student, semester_id=sid))
                self.log(c, uid, 'register', student, {}, {'username': username, 'semester': sid}, '학생 등록')
        except IntegrityError:
            raise RuleError('이미 사용 중인 아이디입니다. 기존 학생은 수강 등록을 이용하세요.') from None

    def edit_student(self, uid, student, name, active, reset=''):
        with self.engine.begin() as c:
            self.actor(c, uid, True)
            old = c.execute(select(users).where(and_(users.c.id==student, users.c.role=='student'))).mappings().first()
            if not old or not name.strip():
                raise RuleError('유효한 학생과 닉네임을 지정하세요.')
            changes = {'name': name.strip(), 'active': active}
            if reset:
                changes.update(password=password_hash(reset), must_change=True, failed=0, locked_until='')
            c.execute(update(users).where(users.c.id == student).values(**changes))
            self.log(c, uid, 'edit_student', student, {'name': old['name'], 'active': old['active']},
                     {'name': name, 'active': active, 'password_reset': bool(reset)}, '학생 정보 관리')

    def enroll(self, uid, student, sid):
        try:
            with self.engine.begin() as c:
                self.actor(c, uid, True)
                self.semester(c, sid, True)
                u = c.execute(select(users).where(users.c.id==student)).mappings().first()
                if not u or u['role'] != 'student':
                    raise RuleError('학생을 선택하세요.')
                c.execute(insert(enrollments).values(user_id=student, semester_id=sid))
                self.log(c, uid, 'enroll', student, {}, {'semester': sid}, '수강 등록')
        except IntegrityError:
            raise RuleError('이미 등록된 학생입니다.') from None

    def semester(self, c, sid, writable=False):
        s = c.execute(select(semesters).where(semesters.c.id == sid).with_for_update()).mappings().first()
        if not s or c.execute(select(semester_trash.c.semester_id).where(semester_trash.c.semester_id==sid)).first() or (writable and s['archived']):
            raise RuleError('존재하지 않거나 삭제·보관된 학기입니다.')
        return s

    def access(self, c, uid, sid, student=None):
        self.semester(c, sid)
        u = self.actor(c, uid)
        target = student if student is not None else uid
        if u['role'] != 'admin' and target != uid:
            raise RuleError('다른 학생의 포트폴리오는 볼 수 없습니다.')
        if not c.execute(select(enrollments.c.id).where(and_(enrollments.c.user_id==target, enrollments.c.semester_id==sid))).first():
            raise RuleError('해당 학기에 등록되지 않았습니다.')
        return target

    def available_semesters(self):
        with self.engine.connect() as c:
            return [dict(r) for r in c.execute(select(semesters).where(
                ~semesters.c.id.in_(select(semester_trash.c.semester_id)))).mappings()]

    def deleted_semesters(self, uid):
        with self.engine.connect() as c:
            self.actor(c, uid, True)
            return [dict(r) for r in c.execute(select(semesters).join(
                semester_trash, semesters.c.id==semester_trash.c.semester_id)).mappings()]

    def delete_semester(self, uid, sid, confirmation):
        with self.engine.begin() as c:
            self.actor(c, uid, True)
            old = dict(self.semester(c, sid))
            if confirmation != old['name']:
                raise RuleError('삭제할 학기 이름을 정확히 입력하세요.')
            c.execute(insert(semester_trash).values(semester_id=sid, deleted_at=now(), actor_id=uid))
            c.execute(delete(settings).where(and_(settings.c.key=='active_semester', settings.c.value==str(sid))))
            self.log(c, uid, 'delete_semester', f'semester:{sid}', old,
                     {'deleted': True}, '학기 삭제 · 휴지통 이동; 연결 기록 보존')

    def restore_semester(self, uid, sid):
        with self.engine.begin() as c:
            self.actor(c, uid, True)
            c.execute(select(semesters).where(semesters.c.id==sid).with_for_update()).first()
            removed = c.execute(delete(semester_trash).where(semester_trash.c.semester_id==sid))
            if not removed.rowcount:
                raise RuleError('휴지통에 없는 학기입니다.')
            self.log(c, uid, 'restore_semester', f'semester:{sid}', {'deleted': True},
                     {'deleted': False}, '삭제한 학기 복원; 기본 운영 학기는 별도 선택')

    def create_semester(self, uid, name, start, end, deadline):
        start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
        deadline = datetime.fromisoformat(deadline).astimezone(timezone.utc)
        if not name.strip() or end < start or deadline.date() >= start:
            raise RuleError('학기명과 날짜를 확인하세요. 최초 마감은 시작일보다 앞서야 합니다 (UTC 기준).')
        with self.engine.begin() as c:
            self.actor(c, uid, True)
            sid = c.execute(insert(semesters).values(name=name.strip(), start=str(start), end=str(end),
                initial_deadline=deadline.isoformat(), leaderboard=False, archived=False)).inserted_primary_key[0]
            self.log(c, uid, 'create_semester', sid, {}, {'name': name, 'start': start, 'end': end}, '새 학기')

    def semester_settings(self, uid, sid, leaderboard, archived):
        with self.engine.begin() as c:
            self.actor(c, uid, True)
            old = self.semester(c, sid)
            c.execute(update(semesters).where(semesters.c.id==sid).values(leaderboard=leaderboard, archived=archived))
            self.log(c, uid, 'semester_settings', sid, dict(old), {'leaderboard': leaderboard, 'archived': archived}, '학기 운영 설정')

    def add_window(self, uid, sid, name, opens, closes, effective):
        op, cl = [datetime.fromisoformat(x).astimezone(timezone.utc) for x in (opens, closes)]
        effective = date.fromisoformat(str(effective))
        with self.engine.begin() as c:
            self.actor(c, uid, True)
            s = self.semester(c, sid, True)
            if not name.strip() or not op < cl or cl.date() >= effective or not s['start'] < str(effective) <= s['end']:
                raise RuleError('시작 < 마감 < 적용일 순서로 설정하세요. 적용일은 학기 시작 이후, 종료일 이내여야 합니다.')
            existing = c.execute(select(windows).where(windows.c.semester_id==sid)).mappings().all()
            if any(not (cl.isoformat() < w['opens'] or op.isoformat() > w['closes']) or w['effective']==str(effective) for w in existing):
                raise RuleError('기존 기간 또는 적용일과 겹칩니다.')
            c.execute(insert(windows).values(semester_id=sid, name=name, opens=op.isoformat(), closes=cl.isoformat(), effective=str(effective)))
            self.log(c, uid, 'add_window', sid, {}, {'name': name, 'opens': op, 'closes': cl, 'effective': effective}, '리밸런싱 일정 추가')

    def submit(self, uid, sid, values, reason, window_id=None, at=None):
        values = weights(values)
        stamp = at or now()
        try:
            with self.engine.begin() as c:
                u = self.actor(c, uid)
                if u['role'] != 'student' or u['must_change']:
                    raise RuleError('학생 계정에서 비밀번호 변경 후 제출하세요.')
                self.access(c, uid, sid)
                s = self.semester(c, sid, True)
                if window_id is None:
                    if stamp > s['initial_deadline']:
                        raise RuleError('최초 배분 제출 기한이 지났습니다.')
                    effective, key = s['start'], 'initial'
                else:
                    w = c.execute(select(windows).where(and_(windows.c.id==window_id, windows.c.semester_id==sid))).mappings().first()
                    if not w or not w['opens'] <= stamp <= w['closes']:
                        raise RuleError('현재 리밸런싱 제출 기간이 아닙니다.')
                    if len(reason.strip()) < 20:
                        raise RuleError('저장하지 않았습니다. 리밸런싱 사유를 20자 이상 입력한 후 다시 제출하세요.')
                    if not c.execute(select(submissions.c.id).where(and_(submissions.c.user_id==uid, submissions.c.semester_id==sid, submissions.c.event_key=='initial'))).first():
                        raise RuleError('최초 배분을 먼저 제출해야 합니다.')
                    effective, key = w['effective'], str(window_id)
                subid = c.execute(insert(submissions).values(user_id=uid, semester_id=sid,
                    event_key=key, effective=effective, submitted_at=stamp)).inserted_primary_key[0]
                c.execute(insert(allocations).values(submission_id=subid, weights=json.dumps(values), reason=reason.strip() or '최초 배분', created_at=stamp, actor_id=uid))
        except IntegrityError:
            raise RuleError('이미 최종 제출되었습니다. 제출 후에는 변경할 수 없습니다.') from None

    def history(self, uid, sid, student=None):
        with self.engine.connect() as c:
            target = self.access(c, uid, sid, student)
            result = []
            for sub in c.execute(select(submissions).where(and_(submissions.c.user_id==target, submissions.c.semester_id==sid)).order_by(submissions.c.effective)).mappings():
                versions = c.execute(select(allocations).where(allocations.c.submission_id==sub['id']).order_by(allocations.c.id)).mappings().all()
                latest = dict(versions[-1])
                latest['weights'] = json.loads(latest['weights'])
                result.append({**dict(sub), **{'version_id': latest.pop('id')}, **latest, 'versions': len(versions)})
            return result

    def correct_allocation(self, uid, submission_id, values, reason):
        values = weights(values)
        if not reason.strip():
            raise RuleError('정정 사유를 입력하세요.')
        with self.engine.begin() as c:
            self.actor(c, uid, True)
            sub = c.execute(select(submissions).where(submissions.c.id==submission_id)).mappings().first()
            if not sub:
                raise RuleError('제출 기록을 찾을 수 없습니다.')
            old = c.execute(select(allocations).where(allocations.c.submission_id==submission_id).order_by(allocations.c.id.desc())).mappings().first()
            c.execute(insert(allocations).values(submission_id=submission_id, weights=json.dumps(values), reason=reason,
                created_at=now(), actor_id=uid))
            self.log(c, uid, 'correct_allocation', f'semester:{sub["semester_id"]}/student:{sub["user_id"]}/submission:{submission_id}', dict(old), values, reason)

    def market(self):
        latest = {}
        for r in self.rows(snapshots):
            if r['day'] not in latest or r['id'] > latest[r['day']]['id']:
                latest[r['day']] = r
        return [{**latest[d], 'factors': json.loads(latest[d]['factors']), 'prices': json.loads(latest[d]['prices']), 'fx': float(latest[d]['fx'])} for d in sorted(latest)]

    def store_market(self, uid, records, correction=False, reason=''):
        if correction and not reason.strip():
            raise RuleError('시장 데이터 정정 사유가 필요합니다.')
        with self.engine.begin() as c:
            self.actor(c, uid, True)
            # A shared row lock serializes all official snapshot imports on PostgreSQL.
            c.execute(select(users.c.id).where(users.c.role=='admin').order_by(users.c.id).with_for_update()).all()
            records = list(records)
            stored_days = set(c.execute(select(snapshots.c.day)).scalars())
            combined_days = stored_days | {r['day'] for r in records}
            if combined_days and set(sessions(min(combined_days), max(combined_days))) != combined_days:
                raise RuleError('스냅샷 날짜가 연속되지 않습니다. 누락된 미국 거래일을 포함해 다시 가져오세요.')
            for r in sorted(records, key=lambda x: x['day']):
                day = date.fromisoformat(r['day'])
                previous_day = date.fromisoformat(r['previous_day'])
                if previous_day >= day or day >= date.today():
                    raise RuleError('직전 거래일과 완료된 가격 날짜를 확인하세요.')
                if not sessions(str(day),str(day)) or str(previous_day)!=previous_session(str(day)):
                    raise RuleError('저장하지 않았습니다. 미국 거래일과 직전 거래일 연결을 확인하세요.')
                if set(r['factors']) != set(ETFS) or set(r['prices']) != set(ETFS):
                    raise RuleError('다섯 ETF가 모두 포함된 데이터가 필요합니다.')
                if any(not math.isfinite(float(v)) or float(v)<=0 for v in [*r['factors'].values(), *r['prices'].values(), r['fx']]):
                    raise RuleError('가격·수익률 배율·환율은 양의 유한수여야 합니다.')
                old = c.execute(select(snapshots).where(snapshots.c.day==r['day']).order_by(snapshots.c.id.desc())).mappings().first()
                if old and not correction:
                    continue
                if old and old['previous_day'] != r['previous_day']:
                    raise RuleError('정정 시 기존 거래일 연결을 변경할 수 없습니다.')
                c.execute(insert(snapshots).values(day=r['day'], previous_day=r['previous_day'], factors=json.dumps(r['factors']), prices=json.dumps(r['prices']),
                    fx=str(r['fx']), source=r['source'], created_at=now()))
                self.log(c, uid, 'correct_market' if old else 'import_market', r['day'], dict(old) if old else {}, r, reason or '공식 일별 스냅샷 저장')

    def performance(self, uid, sid, student=None):
        history = self.history(uid, sid, student)
        with self.engine.connect() as c:
            s = self.semester(c, sid)
        market = [r for r in self.market() if s['start'] <= r['day'] <= s['end']]
        if not history or not market:
            return []
        if market[0]['previous_day'] >= s['start']:
            # Never silently change the class start because earlier prices are missing.
            return []
        holdings, result, applied = None, [], set()
        base_fx = market[0]['fx']
        etf_index = {k: 100.0 for k in ETFS}
        for i, row in enumerate(market):
            if holdings is not None and i:
                holdings = {k: holdings[k]*row['factors'][k] for k in ETFS}
                etf_index = {k: etf_index[k]*row['factors'][k] for k in ETFS}
            nav = sum(holdings.values()) if holdings else 100.0
            for allocation in history:
                if allocation['id'] not in applied and allocation['effective'] <= row['day']:
                    holdings = {k: nav*allocation['weights'][k]/100 for k in ETFS}
                    applied.add(allocation['id'])
            if holdings is not None:
                result.append({'date': row['day'], 'USD NAV': nav, 'KRW NAV': nav*row['fx']/base_fx,
                    'USD return %': nav-100, 'KRW return %': nav*row['fx']/base_fx-100,
                    'USD/KRW': row['fx'], **{k: etf_index[k] for k in ETFS}})
        return result

    def leaderboard(self, uid, sid):
        with self.engine.connect() as c:
            u = self.actor(c, uid)
            s = self.semester(c, sid)
            if u['role'] != 'admin':
                self.access(c, uid, sid)
                if not s['leaderboard']:
                    raise RuleError('리더보드가 비공개입니다.')
        if not self.health(uid,sid)['ok']:
            raise RuleError('데이터 점검이 필요하여 공식 순위를 표시하지 않습니다. 교수자가 데이터 상태를 확인한 후 다시 공개합니다.')
        status=self.official_status(uid,sid)
        if status['state']!='공식 확정':
            raise RuleError('공식 성과가 미확정이거나 변경되어 순위를 표시하지 않습니다. 교수자가 데이터 상태에서 공식 성과를 확정해야 합니다.')
        names={r['id']:r['name'] for r in self.rows(users)}
        runs=self.rows(official_runs,official_runs.c.semester_id==sid)
        payload=json.loads(max(runs,key=lambda r:r['id'])['payload'])
        return [{'닉네임':names.get(r['user_id'],'학생'),'USD 수익률 %':r['usd_return_pct'],'KRW 수익률 %':r['krw_return_pct'],
                 '최근 2주 수익률 %':r['recent_14d_return_pct'],'기준일':r['measurement_date'],'순위':r['rank'],'상태':'공식 확정'}
                for r in payload['board']]

    def export(self, uid, sid=None):
        with self.engine.connect() as c:
            self.actor(c, uid, True)
            if c.dialect.name == 'postgresql':
                c.rollback()
                c = c.execution_options(isolation_level='REPEATABLE READ')
            data = {t.name: [dict(r) for r in c.execute(select(t)).mappings()] for t in metadata.sorted_tables}
        # Portable logical backup excludes credentials by design; reset passwords after restoring.
        for u in data['users']:
            for key in ('password', 'failed', 'locked_until'):
                u.pop(key, None)
        if sid is not None:
            for key in ('semesters', 'enrollments', 'windows', 'submissions', 'semester_trash'):
                data[key] = [r for r in data[key] if r['id']==sid] if key=='semesters' else [r for r in data[key] if r['semester_id']==sid]
            subids = {r['id'] for r in data['submissions']}
            ids = {r['user_id'] for r in data['enrollments']}
            data['users'] = [r for r in data['users'] if r['id'] in ids]
            data['allocation_versions'] = [r for r in data['allocation_versions'] if r['submission_id'] in subids]
            data['login_events']=[r for r in data['login_events'] if r['user_id'] in ids]
            data['official_runs']=[r for r in data['official_runs'] if r['semester_id']==sid]
            # Market imports are shared class inputs; allocation and semester audits are scoped.
            data['audit_log']=[r for r in data['audit_log'] if r['target'].startswith(f'semester:{sid}/') or r['target']==f'semester:{sid}'
                or r['action'] in ('import_market','correct_market')
                or (r['action'] in ('create_semester','semester_settings','add_window') and r['target']==str(sid))
                or (r['action'] in ('register','enroll','edit_student') and r['target'] in {str(i) for i in ids})
                or (r['action']=='correct_allocation' and any(r['target'].endswith(f'/submission:{i}') for i in subids))]
            data['performance_records']=[]
            columns={'date':'price_date','USD NAV':'usd_nav','KRW NAV':'krw_nav','USD return %':'usd_return_pct','KRW return %':'krw_return_pct','USD/KRW':'usd_krw'}
            for i in ids:
                for p in self.performance(uid,sid,i):
                    data['performance_records'].append({'user_id':i,'semester_id':sid,'status':'provisional',**{columns.get(k,k.lower()+'_index'):v for k,v in p.items()}})
            data['leaderboard_records']=[]
            for run in data['official_runs']:
                data['leaderboard_records'].extend({'run_id':run['id'],**r} for r in json.loads(run['payload'])['board'])
        return json.dumps({'schema_version': 2, 'exported_at': now(), 'tables': data}, ensure_ascii=False, indent=2)
