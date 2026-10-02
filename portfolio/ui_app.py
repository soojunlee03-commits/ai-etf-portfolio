import os
from datetime import date, datetime, time, timedelta, timezone
import pandas as pd
import streamlit as st
from .db import connect, users, semesters, enrollments, windows, submissions, audit
from .service import Service, RuleError, now
from .market import fetch, from_csv
from .ui_helpers import (STUDENT_PAGES,ADMIN_PAGES,display_time,localstamp,perform,finish,
    screen_help,allocation_form,review,draw_performance,show_history,guide)

@st.cache_resource
def service(url): return Service(connect(url))

@st.cache_data(ttl=900,show_spinner=False)
def fetch_cached(start,end): return fetch(start,end)

def password_ui(svc,uid):
    st.info('임시 비밀번호를 본인만 아는 비밀번호로 바꾸세요. 변경 후 권한에 맞는 메뉴가 나타납니다.')
    with st.form('password'):
        old=st.text_input('현재 비밀번호',type='password',help='교수자에게 받은 임시 비밀번호 또는 현재 비밀번호')
        new=st.text_input('새 비밀번호 (8자 이상)',type='password')
        repeat=st.text_input('새 비밀번호 확인',type='password')
        if st.form_submit_button('비밀번호 변경'):
            if new!=repeat: st.error('저장하지 않았습니다. 새 비밀번호 두 칸을 동일하게 입력하세요.')
            elif perform(lambda:svc.change_password(uid,old,new))[0]: finish('비밀번호를 변경했습니다. 학기를 선택하고 다음 단계를 진행하세요.')

def choose_semester(choices,key,active):
    choices=sorted(choices,key=lambda r:(r['id']!=active,-r['id']))
    previous=st.session_state.get(key)
    if previous and previous not in choices: st.session_state.pop(key,None)
    return st.sidebar.selectbox('학기 / 수업',choices,format_func=lambda r:r['name']+(' · 보관' if r['archived'] else ''),key=key)

def student_ui(svc,user):
    uid=user['id']; enrolled={r['semester_id'] for r in svc.rows(enrollments,enrollments.c.user_id==uid)}
    choices=[r for r in svc.available_semesters() if r['id'] in enrolled]
    if not choices: st.info('등록된 학기가 없습니다. 담당 교수자에게 수강 등록을 요청한 뒤 다시 로그인하세요.'); return
    s=choose_semester(choices,'student_semester',svc.selected_semester()); sid=s['id']
    pages=STUDENT_PAGES[:4]+(['순위표'] if s['leaderboard'] else [])+STUDENT_PAGES[4:]
    page=st.sidebar.radio('학생 메뉴',pages)
    st.caption(f'{user["name"]} · {s["name"]} · {s["start"]} ~ {s["end"]}')
    st.info('로그인 → 초기 자산배분 → NAV 확인 → 리밸런싱 → 성과·이력 확인')
    if s['archived']: st.warning('보관된 학기입니다. 기록은 열람할 수 있지만 새 제출은 할 수 없습니다.')
    history=svc.history(uid,sid)
    scheduled=sorted(svc.rows(windows,windows.c.semester_id==sid),key=lambda r:r['opens'])
    available=[w for w in scheduled if w['opens']<=now()<=w['closes'] and not s['archived']]
    pending=next((w for w in available if not any(h['event_key']==str(w['id']) for h in history)),None)
    upcoming=next((w for w in scheduled if w['closes']>=now()),None)
    if page=='내 포트폴리오':
        st.header('내 포트폴리오')
        screen_help('현재 제출 상태를 확인하고 초기 자산배분을 입력합니다.','다섯 ETF 비중, 최초 전략은 선택','제출 후 성과 → 리밸런싱 → 포트폴리오 이력')
        a,b,c=st.columns(3); a.metric('초기 자산배분','제출 완료' if history else '진행 전')
        b.metric('리밸런싱 기간','현재 이용 가능' if available else '기간 종료 / 예정')
        next_deadline=display_time(s['initial_deadline']) if not history else display_time(upcoming['closes']) if upcoming else '예정 없음'
        c.metric('다음 마감일',next_deadline[:10])
        st.caption('마감 시각: '+next_deadline)
        if not s['leaderboard']: st.caption('현재 순위표는 교수자가 비공개로 설정했습니다.')
        if not history:
            if s['archived'] or now()>s['initial_deadline']: st.warning('초기 자산배분 기간이 종료되었습니다. 새 제출은 저장되지 않습니다. 담당 교수자에게 문의하세요.')
            else:
                st.success('지금 해야 할 일: 초기 자산배분을 입력하고 제출해 주세요.')
                values,valid=allocation_form(f'initial_{sid}')
                reason=st.text_area('최초 투자 전략 (선택)',placeholder='예: 주식의 성장성과 국채의 안정성을 함께 고려했습니다.',key=f'initial_reason_{sid}')
                review(values,s['start'],reason)
                confirmed=st.checkbox('제출 후 직접 수정할 수 없음을 확인했습니다.',key=f'initial_confirm_{sid}')
                if st.button('초기 자산배분 최종 제출',type='primary',disabled=not(confirmed and valid)):
                    if perform(lambda:svc.submit(uid,sid,values,reason))[0]: finish('초기 자산배분이 정상적으로 제출되었습니다. 학생은 다시 수정할 수 없습니다. 이제 성과 화면에서 NAV와 수익률을 확인하세요.')
        else:
            st.success('초기 자산배분 제출 완료 · 수정 불가')
            st.write('지금 해야 할 일: '+('리밸런싱에서 새 비중과 변경 사유를 제출하세요.' if pending else '현재 제출할 항목이 없습니다. 성과를 확인하세요.'))
            st.subheader('최근 제출한 목표 비중'); st.dataframe(pd.DataFrame([history[-1]['weights']]),hide_index=True,width='stretch')
            st.caption(f'적용일 {history[-1]["effective"]}. 실제 보유 비중은 가격에 따라 달라집니다.'); draw_performance(svc,uid,sid)
    elif page=='성과':
        st.header('성과'); screen_help('포트폴리오와 ETF의 누적수익률을 비교합니다.','입력 없음; 가격·환율 기준일 확인','리밸런싱 기간이면 새 전략을 제출하세요.'); draw_performance(svc,uid,sid)
    elif page=='리밸런싱':
        st.header('리밸런싱'); screen_help('다음 기간의 목표 비중을 제출합니다.','ETF 비중 합계 100%, 변경 사유 20자 이상','제출 전 검토 → 확인 → 리밸런싱 최종 제출')
        st.info('미제출 시 기존 보유 자산을 유지합니다. 최종 제출 후 또는 마감 후에는 수정할 수 없습니다.')
        st.metric('리밸런싱 기간 상태','열림 (OPEN)' if available else '닫힘 (CLOSED)')
        if scheduled: st.dataframe(pd.DataFrame([{'회차':w['name'],'시작일':display_time(w['opens']),'마감일':display_time(w['closes']),'적용일':w['effective']} for w in scheduled]),hide_index=True,width='stretch')
        else: st.info('일정이 없습니다. 교수자가 일정을 등록하면 여기에서 확인할 수 있습니다.')
        if not available: st.info('지금은 입력할 수 없습니다. 다음 기간을 확인하고 성과를 검토하세요.')
        elif not history: st.warning('초기 자산배분 제출 기록이 필요합니다. 담당 교수자에게 문의하세요.')
        else:
            w=available[0]; submitted=next((h for h in history if h['event_key']==str(w['id'])),None)
            if submitted:
                st.success('리밸런싱 제출 완료 · 수정 불가'); st.dataframe(pd.DataFrame([submitted['weights']]),hide_index=True)
                st.write('변경 사유: '+submitted['reason']); st.caption(f'제출일 {display_time(submitted["submitted_at"])} · 적용일 {submitted["effective"]}')
            else:
                st.caption(f'현재 회차 {w["name"]} · 마감일 {display_time(w["closes"])} · 수정 가능 (최종 제출 전)')
                values,valid=allocation_form(f'rebalance_{w["id"]}',history[-1]['weights'])
                reason=st.text_area('리밸런싱 사유 (필수, 20자 이상)',placeholder='예: 향후 금리 하락을 예상하여 미국 국채 비중을 높였습니다.')
                st.caption(f'입력한 사유: {len(reason.strip())}자 / 최소 20자'); review(values,w['effective'],reason,history[-1]['weights'])
                confirm=st.checkbox('변경 사유와 비중을 확인했으며 최종 제출에 동의합니다.')
                if st.button('리밸런싱 최종 제출',type='primary',disabled=not(confirm and valid and len(reason.strip())>=20)):
                    if perform(lambda:svc.submit(uid,sid,values,reason,w['id']))[0]: finish('리밸런싱 제출 완료 · 수정 불가. 포트폴리오 이력에서 제출일과 적용일을 확인하세요.')
    elif page=='포트폴리오 이력':
        st.header('포트폴리오 이력'); screen_help('각 배분의 비중·사유·적용일을 확인합니다.','입력 없음','정정이 필요하면 회차와 사유를 교수자에게 전달하세요.')
        st.caption('버전은 최초 저장과 관리자 정정의 횟수입니다. 최신 버전이 표시되며 이전 버전도 보존됩니다.'); show_history(svc,uid,sid)
    elif page=='순위표':
        st.header('순위표'); screen_help('교수자가 확정한 공통 기준의 순위를 확인합니다.','입력 없음','개인 상세 성과는 성과 메뉴에서 확인하세요.')
        st.caption('달러 누적수익률 기준 · 소수점 6자리 동률은 공동순위 (1, 1, 3) · 최근 2주는 14일 전 또는 직전 거래일 대비')
        try: st.dataframe(pd.DataFrame(svc.leaderboard(uid,sid)),hide_index=True,width='stretch')
        except RuleError as e: st.info(str(e))
    else: guide()

def semester_admin(svc,uid):
    st.header('학기 / 일정'); screen_help('학기 또는 수업 분반을 만들고 일정을 설정합니다.','학기명, 날짜 (YYYY-MM-DD), 한국 시각','생성 → 운영 학기 설정 → 학생 등록')
    st.caption('새 학기를 만들어도 이전 기록은 삭제되지 않습니다. 잘못 만든 빈 학기는 보관하고 새로 생성하세요. 모든 운영 변경은 감사 기록에 남습니다.')
    with st.form('semester_create'):
        name=st.text_input('학기 / 수업 이름 (필수)',placeholder='예: 2026 가을 · 투자론 A반')
        start=st.date_input('포트폴리오 시작일',date.today()+timedelta(days=7),format='YYYY-MM-DD')
        end=st.date_input('학기 종료일',date.today()+timedelta(days=120),format='YYYY-MM-DD')
        deadline=st.date_input('초기 자산배분 마감일 (한국 시간)',date.today()+timedelta(days=5),format='YYYY-MM-DD'); dt=st.time_input('초기 자산배분 마감 시각',time(23,59))
        st.caption('마감은 시작일 전이어야 합니다. 생성 후 날짜는 고정됩니다.')
        confirm=st.checkbox('새 학기의 날짜를 확인했으며 기존 학기가 보존됨을 이해했습니다.')
        if st.form_submit_button('새 학기 생성'):
            if not confirm: st.warning('날짜와 기존 학기 보존 안내를 확인하고 확인란을 선택하세요.')
            elif perform(lambda:svc.create_semester(uid,name,start,end,localstamp(deadline,dt)))[0]: finish('새 학기를 생성했습니다. 사이드바에서 선택한 후 운영 학기로 설정하고 학생을 등록하세요.')

def dashboard_table(svc,uid,sid):
    rows=svc.submission_dashboard(uid,sid)['students']
    if rows: st.dataframe(pd.DataFrame([{'닉네임':r['display_name'],'아이디':r['username'],'계정':'활성' if r['active'] else '비활성','초기 제출':'완료' if r['initial_submitted'] else '미제출','최근 리밸런싱':'완료' if r['latest_rebalance_submitted'] else '미제출 / 일정 없음','비밀번호 변경 필요':'예' if r['must_change_password'] else '아니요','최근 로그인':display_time(r['last_login_at'])} for r in rows]),hide_index=True,width='stretch')
    else: st.info('등록된 학생이 없습니다. 학생 관리에서 학생을 등록하거나 기존 학생을 수강 등록하세요.')

def admin_ui(svc,user):
    uid=user['id']; page=st.sidebar.radio('관리자 메뉴',ADMIN_PAGES); choices=svc.available_semesters()
    s=choose_semester(choices,'admin_semester',svc.selected_semester()) if choices else None
    if page=='관리자 사용가이드': guide(True); return
    if page=='학기 / 일정' or not s:
        semester_admin(svc,uid)
        deleted=svc.deleted_semesters(uid)
        with st.expander('삭제한 학기 · 휴지통'):
            st.caption('삭제한 학기의 제출·성과·감사 기록은 보존됩니다. 복원하면 다시 조회할 수 있습니다.')
            if deleted:
                target=st.selectbox('복원할 학기',deleted,format_func=lambda r:f"{r['name']} (#{r['id']})")
                if st.button('학기 복원'):
                    if perform(lambda:svc.restore_semester(uid,target['id']))[0]: finish('학기를 복원했습니다. 운영 학기는 별도로 설정하세요.')
            else: st.info('삭제한 학기가 없습니다.')
        if not s: return
    sid=s['id']
    if page=='학기 / 일정':
        st.subheader('선택한 학기 운영 설정'); st.write(f'선택 학기: {s["name"]} · '+('운영 학기' if svc.selected_semester()==sid else '조회 중인 학기'))
        st.caption('운영 학기는 로그인 후 기본 표시됩니다. 이전 학기는 계속 선택할 수 있습니다. 변경·보관은 감사 기록에 남고 보관 체크 해제로 재개할 수 있습니다.')
        confirm_active=st.checkbox('기본 표시 학기를 변경하며 이전 기록은 보존됨을 확인했습니다.')
        if st.button('운영 학기로 설정',disabled=not confirm_active or s['archived']):
            if perform(lambda:svc.activate_semester(uid,sid))[0]: finish('운영 학기를 설정했습니다. 학생 관리에서 수강 등록을 확인하세요.')
        with st.form('semester_settings'):
            leaderboard=st.checkbox('순위표 공개 (OPEN)',value=s['leaderboard']); archive=st.checkbox('학기 보관 · 학생 제출 중단',value=s['archived'])
            st.caption('보관 전 백업하세요. 보관하면 학생 제출만 중단됩니다. 공개해도 데이터 오류·미확정 상태에서는 순위가 차단됩니다.')
            confirm=st.checkbox('학생에게 미치는 영향과 보관 전 백업을 확인했습니다.')
            if st.form_submit_button('운영 설정 저장'):
                if not confirm: st.warning('학생에게 미치는 영향과 보관 전 백업 안내를 확인하고 확인란을 선택하세요.')
                elif perform(lambda:svc.semester_settings(uid,sid,leaderboard,archive))[0]: finish('운영 설정을 저장했습니다. 운영 현황에서 공개 상태를 확인하세요.')
        with st.expander('학기 전체 삭제'):
            count_students=len(svc.rows(enrollments,enrollments.c.semester_id==sid))
            count_submissions=len(svc.rows(submissions,submissions.c.semester_id==sid))
            st.warning(f"삭제 대상: {s['name']} · 등록 학생 {count_students}명 · 제출 {count_submissions}건")
            st.write('삭제하면 학기 선택·회원가입 목록에서 사라지고 학생 조회·제출이 중단됩니다. 학생 계정과 기록은 보존되며 휴지통에서 복원할 수 있습니다.')
            with st.form(f'delete_semester_{sid}'):
                name=st.text_input('삭제할 학기 이름을 정확히 입력',key=f'delete_name_{sid}')
                confirmed=st.checkbox('위 학기 전체를 휴지통으로 이동합니다.',key=f'delete_confirm_{sid}')
                if st.form_submit_button('학기 삭제'):
                    if not confirmed: st.warning('삭제 대상을 확인하고 확인란을 선택하세요.')
                    elif perform(lambda:svc.delete_semester(uid,sid,name))[0]: finish('학기를 삭제했습니다. 삭제한 학기 · 휴지통에서 복원할 수 있습니다.')
        st.subheader('리밸런싱 일정 추가'); st.caption('기본 간격 14일. 시작 < 마감 < 적용일이며 마감의 UTC 날짜는 적용일보다 앞서야 합니다. 한국 시간 전날 저녁 마감을 권장합니다. 등록 일정은 고정됩니다.')
        ws=sorted(svc.rows(windows,windows.c.semester_id==sid),key=lambda w:w['effective']); nextday=date.fromisoformat(ws[-1]['effective'] if ws else s['start'])+timedelta(days=14)
        with st.form('window'):
            label=st.text_input('회차 이름 (필수)',value=f'리밸런싱 {len(ws)+1}')
            op=st.date_input('리밸런싱 시작일',nextday-timedelta(days=3),format='YYYY-MM-DD'); ot=st.time_input('리밸런싱 시작 시각',time(9))
            cl=st.date_input('리밸런싱 마감일',nextday-timedelta(days=1),format='YYYY-MM-DD'); ct=st.time_input('리밸런싱 마감 시각',time(18))
            eff=st.date_input('적용일 · 미국 거래일 날짜',nextday,format='YYYY-MM-DD')
            if st.form_submit_button('일정 추가'):
                if perform(lambda:svc.add_window(uid,sid,label,localstamp(op,ot),localstamp(cl,ct),eff))[0]: finish('일정을 추가했습니다. 아래 표에서 날짜를 확인하세요.')
        if ws: st.dataframe(pd.DataFrame([{'회차':w['name'],'시작일':display_time(w['opens']),'마감일':display_time(w['closes']),'적용일':w['effective']} for w in ws]),hide_index=True,width='stretch')
    elif page=='학생 관리':
        st.header('학생 관리'); screen_help('계정 생성·수강 등록·학생 정보 변경을 합니다.','아이디, 공개 닉네임, 8자 이상 임시 비밀번호','학생에게 URL과 개인 계정을 전달하세요.')
        with st.form('register'):
            username=st.text_input('학생 아이디 (필수)',placeholder='예: student01',help='개인 이메일 대신 수업 전용 아이디를 권장합니다.')
            name=st.text_input('공개 닉네임 (필수)',placeholder='예: 푸른고래',help='공개 순위표에 표시됩니다.')
            password=st.text_input('임시 비밀번호 (8자 이상)',type='password',help='개별 전달합니다. 처음 로그인하면 변경해야 합니다.')
            if st.form_submit_button('학생 등록'):
                if perform(lambda:svc.add_student(uid,username,name,password,sid))[0]: finish('학생을 등록했습니다. 아래 목록과 운영 현황에서 확인하세요.')
        students=svc.rows(users,users.c.role=='student')
        if students:
            target=st.selectbox('기존 학생',students,format_func=lambda u:f'{u["name"]} ({u["username"]})')
            if st.button('선택 학기에 수강 등록'): perform(lambda:svc.enroll(uid,target['id'],sid))
            with st.form(f'edit_student_{target["id"]}'):
                name=st.text_input('닉네임 수정',value=target['name']); active=st.checkbox('계정 활성화',value=target['active'])
                reset=st.text_input('비밀번호 재설정 (필요할 때만)',type='password',help='8자 이상; 비우면 유지합니다.')
                st.caption('비활성화하면 모든 학기 접근이 차단됩니다. 기록은 보존되고 재활성화로 복구할 수 있습니다. 변경은 감사 기록에 남습니다.')
                confirm=st.checkbox('학생 접근에 미치는 영향을 확인했습니다.')
                if st.form_submit_button('학생 정보 저장'):
                    if not confirm: st.warning('학생 접근에 미치는 영향을 확인하고 확인란을 선택하세요.')
                    elif perform(lambda:svc.edit_student(uid,target['id'],name,active,reset))[0]: finish('학생 정보를 저장했습니다. 활성 상태를 확인하세요.')
        dashboard_table(svc,uid,sid)
    elif page=='운영 현황':
        st.header('운영 현황'); screen_help('제출 누락과 마감·데이터 경고를 확인합니다.','조회할 학생 선택','미제출 학생 안내 또는 데이터 상태 점검')
        dash=svc.submission_dashboard(uid,sid); rows=dash['students']; n=len(rows); initial=sum(r['initial_submitted'] for r in rows); rebal=sum(r['latest_rebalance_submitted'] for r in rows)
        for col,label,value in zip(st.columns(5),['등록 학생','초기 제출','초기 미제출','최근 리밸런싱 제출','최근 리밸런싱 미제출'],[n,initial,n-initial,rebal,n-rebal if dash['window'] else 0]): col.metric(label,value)
        st.caption(f'다음 마감일: {display_time(dash["next_deadline"])} · 최근 회차: {dash["window"]["name"] if dash["window"] else "일정 없음"} · 순위표: {"공개" if s["leaderboard"] else "비공개"}')
        for issue in svc.health(uid,sid)['issues']: st.warning(issue['message'])
        dashboard_table(svc,uid,sid)
        try:
            board=svc.leaderboard(uid,sid)
            if board:
                st.metric('클래스 평균 달러 수익률',f'{sum(r["USD 수익률 %"] for r in board)/len(board):.2f}%'); st.dataframe(pd.DataFrame(board),hide_index=True,width='stretch')
        except RuleError as e: st.info(str(e))
        if rows:
            target=st.selectbox('학생 포트폴리오 조회',rows,format_func=lambda r:f'{r["display_name"]} ({r["username"]})')
            draw_performance(svc,uid,sid,target['user_id']); show_history(svc,uid,sid,target['user_id'])
    elif page=='시장 데이터':
        st.header('시장 데이터'); screen_help('무료 ETF 수정종가와 원/달러 환율을 저장합니다.','시작·종료일 또는 검증된 CSV','데이터 상태 → 공식 성과 확정')
        st.info('기존 데이터는 자동 덮어쓰지 않습니다. 오늘 이전 완료 거래일만 가져옵니다. 연결 실패 시 제출 기록은 유지됩니다.')
        market=svc.market(); start=st.date_input('가져오기 시작일',date.fromisoformat(market[-1]['day'] if market else s['start']),format='YYYY-MM-DD')
        end=st.date_input('가져오기 종료일',date.today()-timedelta(days=1),format='YYYY-MM-DD')
        if st.button('무료 시장 데이터 가져오기',type='primary'):
            with st.spinner('거래일·가격·환율을 검사하고 있습니다…'):
                if perform(lambda:svc.store_market(uid,fetch_cached(start,end)))[0]: finish('시장 데이터를 저장했습니다. 데이터 상태를 점검하고 공식 성과를 확정하세요.')
        with st.expander('검증된 CSV 가져오기 / 데이터 정정'):
            st.caption('열은 관리자 사용가이드와 데이터 사전을 확인하세요. 일별 배율 1.01은 +1%입니다.')
            st.download_button('시장 CSV 양식 다운로드','day,previous_day,fx,SPY,IEF,GLD,VNQ,SGOV,SPY_factor,IEF_factor,GLD_factor,VNQ_factor,SGOV_factor\n',file_name='market-template.csv',mime='text/csv')
            upload=st.file_uploader('시장 데이터 CSV',type='csv'); correction=st.checkbox('기존 날짜를 정정 버전으로 추가 (성과 재계산)')
            reason=st.text_input('시장 데이터 정정 사유',placeholder='예: 환율의 잘못된 소수점 수정')
            confirm=st.checkbox('가격 정정의 영향과 공식 성과 재확정 필요성을 확인했습니다.')
            if st.button('CSV 검증 및 저장',disabled=upload is None or (correction and not confirm)):
                if perform(lambda:svc.store_market(uid,from_csv(upload),correction,reason))[0]: finish('CSV를 저장했습니다. 데이터 상태에서 공식 성과를 다시 확정하세요.')
        if market: st.dataframe(pd.DataFrame([{'가격·환율 날짜':r['day'],'원/달러 환율':r['fx'],'수집 시각':display_time(r['created_at']),'출처':'Yahoo 무료 데이터' if r['source'].startswith('Yahoo') else '관리자 CSV / 데모'} for r in market[-30:]]),hide_index=True,width='stretch')
    elif page=='데이터 상태':
        st.header('데이터 상태'); screen_help('데이터 무결성과 공식 성과 상태를 검사합니다.','공식 확정 시 사유 입력','경고 해결 → 공식 성과 확정 → 순위표 공개')
        health=svc.health(uid,sid); status=svc.official_status(uid,sid)
        st.metric('데이터 점검 결과',health['status']); st.metric('공식 스냅샷 상태',status['state'])
        st.caption(f'점검 기준일 {health["reference_date"]} · 가격·환율 기준일 {health["measurement_date"] or "없음"}')
        if health['ok']: st.success('DB 연결, 거래일, 가격·환율, 배분 합계와 학생 연결이 정상입니다.')
        for issue in health['issues']: st.warning(issue['message'])
        st.info('확정하면 시작일·리밸런싱 적용일·측정일까지 일별 성과와 순위를 영구 보존합니다. 정정해도 이전 확정본은 유지됩니다.')
        reason=st.text_input('공식 성과 확정 사유',value='정기 수업 성과 확정')
        if st.button('공식 성과 확정',type='primary',disabled=not health['ok']):
            if perform(lambda:svc.publish_official(uid,sid,reason))[0]: finish('공식 성과를 확정했습니다. 운영 현황에서 순위와 기준일을 확인하세요.')
        if status['run']: st.caption(f'확정일 {display_time(status["run"]["created_at"])} · 측정일 {status["run"]["measurement_date"]} · 확정 번호 {status["run"]["id"]}')
    elif page=='정정 / 감사':
        st.header('정정 / 감사'); screen_help('잘못 제출된 비중을 새 버전으로 정정합니다.','제출 선택, 비중, 사유','정정 저장 → 감사 로그 → 공식 성과 재확정')
        subs=svc.rows(submissions,submissions.c.semester_id==sid)
        if not subs: st.info('제출 기록이 없습니다. 학생이 초기 자산배분을 제출하면 선택할 수 있습니다.')
        else:
            sub=st.selectbox('정정할 제출',subs,format_func=lambda r:f'학생 #{r["user_id"]} · 적용일 {r["effective"]} · '+('초기 자산배분' if r['event_key']=='initial' else '리밸런싱'))
            old=next(h for h in svc.history(uid,sid,sub['user_id']) if h['id']==sub['id'])
            values,valid=allocation_form(f'correction_{sub["id"]}_{old["version_id"]}',old['weights'])
            reason=st.text_area('배분 정정 사유 (필수)',placeholder='학생 요청과 정정 근거를 입력하세요.'); review(values,sub['effective'],reason,old['weights'])
            st.caption('기존 버전은 보존됩니다. 정정 후 순위는 재확정 전까지 차단됩니다. 잘못 정정했다면 새 정정으로 복구하세요.')
            confirm=st.checkbox('정정 내용과 성과 재계산을 확인했습니다.')
            if st.button('정정 버전 저장',disabled=not(confirm and valid and reason.strip())):
                if perform(lambda:svc.correct_allocation(uid,sub['id'],values,reason))[0]: finish('정정 버전을 저장했습니다. 감사 로그를 확인한 뒤 데이터 상태에서 재확정하세요.')
        st.subheader('감사 로그 · 이 설치의 전체 수업')
        st.dataframe(pd.DataFrame([{'시각':display_time(r['created_at']),'관리자 번호':r['actor_id'],'작업':r['action'],'대상':r['target'],'이전 값':r['before'],'변경 값':r['after'],'사유':r['reason']} for r in svc.rows(audit)]),hide_index=True,width='stretch')
    elif page=='내보내기 / 백업':
        st.header('내보내기 / 백업'); screen_help('학기 자료와 복구용 데이터를 보관합니다.','다운로드 항목 선택','파일 확인 → 학기 보관 → 새 학기 생성')
        st.caption('학기 ZIP은 영문 열 이름의 CSV, JSON, 공식 성과·순위·감사 기록, 한국어 데이터 사전을 포함합니다. 안전한 폴더에 보관하세요.')
        st.download_button('학기 CSV 묶음 다운로드',svc.export_zip(uid,sid),file_name=f'semester-{sid}.zip',mime='application/zip')
        st.download_button('학기 데이터 다운로드',svc.export(uid,sid),file_name=f'semester-{sid}.json',mime='application/json')
        st.download_button('전체 논리 백업 다운로드',svc.export(uid),file_name=f'portfolio-backup-{date.today()}.json',mime='application/json')
        if svc.engine.dialect.name=='sqlite':
            st.caption('완전 복구 DB는 비밀번호 해시도 포함합니다. 관리자만 보관하세요. 복원은 앱을 중지한 뒤 새 파일에 수행합니다.')
            if st.button('완전 복구용 DB 백업 준비'):
                ok,data=perform(lambda:svc.database_backup(uid),'백업을 준비했습니다. 아래 다운로드 버튼을 누르세요.')
                if ok: st.session_state['db_backup']=data
            if st.session_state.get('db_backup'): st.download_button('완전 복구용 DB 다운로드',st.session_state['db_backup'],file_name=f'portfolio-full-{date.today()}.db',mime='application/octet-stream')
        st.info('복구: 앱 중지 → recovery.ps1 실행 → 백업 파일과 새 복원 파일 지정 → 확인 → 재실행. 기존 DB는 덮어쓰지 않습니다. 관리자 사용가이드에서 자세히 확인하세요.')

def main(database_url=None, demo=False):
    url=database_url or os.environ.get('DATABASE_URL')
    if not url:
        try: url=st.secrets.get('DATABASE_URL')
        except FileNotFoundError: pass
    svc=service(url); st.title('AI ETF Portfolio Competition'); st.caption('한 학기 동안 배우는 자산배분 · 달러와 원화 성과 · 기록하는 투자 판단')
    if demo or os.environ.get('APP_DEMO')=='1': st.warning('체험용 데모 · 가상 학생과 합성 가격입니다. 실제 수업 DB와 분리되어 있으며 실제 투자 성과가 아닙니다.')
    if st.session_state.get('notice'): st.success(st.session_state.pop('notice'))
    if not svc.rows(users): st.info('관리자 초기 설정이 필요합니다. 서버 운영자가 setup_admin.py를 한 번 실행하면 로그인할 수 있습니다. 학생은 교수자에게 앱 URL을 확인하세요.'); return
    uid=st.session_state.get('uid')
    if uid:
        with svc.engine.connect() as c:
            try: user=dict(svc.actor(c,uid))
            except RuleError: st.session_state.clear(); st.rerun()
        if datetime.now(timezone.utc).timestamp()-st.session_state.get('login_time',0)>8*3600: st.session_state.clear(); st.rerun()
        st.sidebar.write(f'{user["name"]} · {"관리자" if user["role"]=="admin" else "학생"}')
        if st.sidebar.button('로그아웃'): st.session_state.clear(); st.rerun()
        if user['must_change']: st.header('처음 로그인 · 비밀번호 변경'); password_ui(svc,uid); return
        if st.sidebar.checkbox('비밀번호 변경'): password_ui(svc,uid)
        elif user['role']=='admin': admin_ui(svc,user)
        else: student_ui(svc,user)
    else:
        left,right=st.columns([1.2,1])
        with left:
            st.header('나의 투자 판단을 기록하고, 결과를 배워 보세요.')
            st.write('SPY · 미국 주식 / IEF · 미국 중기 국채 / GLD · 금 / VNQ · 미국 리츠 / SGOV · 미국 초단기 국채')
            st.info('로그인 → 초기 자산배분 → NAV 확인 → 리밸런싱 → 성과·이력 확인')
            st.write('처음 방문한 학생은 아래 학생 회원가입에서 아이디와 비밀번호를 직접 정하세요. 관리자는 관리자 계정을 사용하며 권한에 맞는 메뉴가 자동 표시됩니다.')
        with right:
            with st.form('login'):
                st.subheader('로그인'); username=st.text_input('아이디',placeholder='아이디를 입력하세요.'); password=st.text_input('비밀번호',type='password')
                if st.form_submit_button('로그인',type='primary',width='stretch'):
                    ok,uid=perform(lambda:svc.login(username,password),'로그인했습니다.')
                    if ok: st.session_state['uid']=uid; st.session_state['login_time']=datetime.now(timezone.utc).timestamp(); st.rerun()
            st.caption('실패 시 아이디·비밀번호를 확인하세요. 5회 실패하면 15분간 잠깁니다. 문제가 계속되면 담당 교수자에게 문의하세요. 공용 컴퓨터에서는 사용 후 로그아웃하세요.')
            with st.expander('처음 오셨나요? 학생 회원가입'):
                available={r['id']:r['name'] for r in svc.available_semesters() if not r['archived']}
                with st.form('student_signup'):
                    st.subheader('학생 회원가입')
                    new_username=st.text_input('사용할 아이디',max_chars=100,help='영문 대소문자는 구분하지 않습니다.')
                    new_name=st.text_input('공개 닉네임',max_chars=100)
                    new_password=st.text_input('비밀번호 (8자 이상)',type='password')
                    repeat_password=st.text_input('비밀번호 확인',type='password')
                    signup_sid=st.selectbox('참여할 학기 / 수업',list(available),format_func=lambda x:available[x]) if available else None
                    if not available: st.info('아직 등록 가능한 학기가 없습니다. 가입 후 교수자에게 수강 등록을 요청하세요.')
                    if st.form_submit_button('회원가입'):
                        if new_password != repeat_password: st.error('비밀번호가 일치하지 않습니다.')
                        elif perform(lambda:svc.signup_student(new_username,new_name,new_password,signup_sid))[0]:
                            finish('회원가입이 완료되었습니다. 직접 정한 아이디와 비밀번호로 로그인하세요.')
    st.divider(); st.caption('교육용 모의투자 서비스입니다. 실제 거래를 실행하지 않으며 투자 조언을 제공하지 않습니다. 과거 성과는 미래 수익을 보장하지 않습니다.')
