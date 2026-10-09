from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import logging
import pandas as pd
import streamlit as st
import altair as alt
from .service import RuleError, ETFS, weights

KST=timezone(timedelta(hours=9))
ROOT=Path(__file__).resolve().parents[1]
STUDENT_PAGES=['내 포트폴리오','성과','리밸런싱','포트폴리오 이력','사용가이드']
ADMIN_PAGES=['운영 현황','학생 성과 / 제출 내역','학생 관리','학기 / 일정','시장 데이터','데이터 상태','정정 / 감사','내보내기 / 백업','관리자 사용가이드']

def display_time(value):
    return datetime.fromisoformat(value).astimezone(KST).strftime('%Y-%m-%d %H:%M KST') if value else '없음'

def localstamp(d,t):
    return datetime.combine(d,t,KST).astimezone(timezone.utc).isoformat()

def perform(fn,message='정상적으로 저장했습니다. 화면에서 변경 결과를 확인하세요.'):
    try:
        result=fn(); st.success(message); return True,result
    except RuleError as e: st.error(f'{e} 문제가 계속되면 담당 교수자에게 문의하세요.')
    except Exception as e:
        logging.error('operation_failed type=%s',type(e).__name__)
        st.error('처리를 완료하지 못했습니다. 저장 여부는 현재 기록을 확인하세요. 다시 시도하고, 문제가 계속되면 담당 교수자에게 문의하세요.')
    return False,None

def finish(message):
    st.session_state['notice']=message; st.rerun()

def screen_help(purpose,entry,next_step):
    st.write(purpose); st.caption(f'입력할 내용: {entry} · 다음 단계: {next_step}')

def allocation_form(key,defaults=None):
    defaults=defaults or {k:20.0 for k in ETFS}; values={}
    for col,(ticker,description) in zip(st.columns(5),ETFS.items()):
        with col:
            values[ticker]=st.number_input(f'{ticker} 비중 (%)',min_value=0.0,max_value=100.0,value=float(defaults[ticker]),step=1.0,format='%.2f',key=f'{key}_{ticker}',help='0~100 사이의 숫자입니다. 예: 30은 전체의 30%입니다.')
            st.caption(description)
    total=sum(values.values()); a,b,c=st.columns(3)
    a.metric('현재 합계',f'{total:.2f}%'); b.metric('남은 비중',f'{100-total:.2f}%')
    try: weights(values); valid=True
    except RuleError: valid=False
    c.metric('제출 가능 여부','제출 가능' if valid else '제출 불가')
    if not valid: st.warning('자산배분 비중의 합계가 100%가 되도록 입력해 주세요. 아직 저장되지 않았습니다.')
    return values,valid

def review(values,effective,reason='',previous=None):
    st.subheader('제출 전 확인')
    st.dataframe(pd.DataFrame([{'ETF':k,**({'이전 목표 비중 (%)':previous[k]} if previous else {}),'제출할 비중 (%)':values[k]} for k in ETFS]),hide_index=True,width='stretch')
    st.caption(f'제출일: {datetime.now(KST):%Y-%m-%d} · 적용일: {effective} 이후 첫 미국 거래일 종가')
    if reason: st.write('사유: '+reason)
    st.warning('최종 제출 후 학생은 수정할 수 없습니다. 오류가 있으면 담당 교수자에게 정정을 요청하세요.')

def performance_health(svc,uid,sid,admin_preview=False):
    health=svc.health(uid,sid)
    if admin_preview and not health['ok'] and health['measurement_date']:
        # Validate the entire saved interval; never bridge an internal price gap.
        if {i['code'] for i in health['issues']} <= {'missing_prices','stale'}:
            saved=svc.health(uid,sid,as_of=date.fromisoformat(health['measurement_date']))
            if saved['ok']:
                return saved,health['issues']
    return health,[]


def draw_performance(svc,uid,sid,student=None,admin_preview=False):
    health,delayed=performance_health(svc,uid,sid,admin_preview)
    state=svc.official_status(uid,sid)
    if delayed:
        st.warning(f"최신 가격이 아직 반영되지 않았습니다. {health['measurement_date']}까지 검증된 저장 자료의 참고 성과입니다. 현재 수익률이나 공식 순위로 사용하지 마세요.")
    display_status='저장 기준일 참고 성과 · 최신 데이터 갱신 필요' if delayed else health['status']
    st.caption(f'데이터 상태: {display_status} · 성과 상태: {state["state"]} · 가격·환율 기준일: {health["measurement_date"] or "준비 전"}')
    if not health['ok']:
        for issue in health['issues']: st.warning(issue['message'])
        st.info('불완전한 데이터로 오해하지 않도록 성과 표시를 보류합니다. 자산배분은 보존됩니다. 교수자에게 데이터 갱신을 요청하세요.'); return
    perf=svc.performance(uid,sid,student)
    if not perf:
        st.info('초기 자산배분 제출과 시작일의 가격·환율이 있어야 성과를 계산할 수 있습니다. 제출 내역과 시장 데이터를 확인하세요.'); return
    last=perf[-1]; a,b,c=st.columns(3)
    a.metric('포트폴리오 NAV (Portfolio NAV)',f'{last["USD NAV"]:.2f}')
    b.metric('달러 기준 수익률 (USD Return)',f'{last["USD return %"]:+.2f}%')
    c.metric('원화 기준 수익률 (KRW Return)',f'{last["KRW return %"]:+.2f}%')
    st.write('포트폴리오 NAV는 시작값 100인 모의투자 가치 지수입니다. 105는 누적수익률 5%를 뜻하며 ETF 운용사가 공시하는 NAV와 다릅니다.')
    if state['state']!='공식 확정': st.info('현재 성과는 잠정 계산입니다. 공식 순위는 교수자의 성과 확정 후 공개됩니다.')
    df=pd.DataFrame(perf).set_index('date')
    st.subheader('포트폴리오 가치의 변화')
    line_chart(df[['USD NAV','KRW NAV']].rename(columns={'USD NAV':'달러 기준 NAV','KRW NAV':'원화 기준 NAV'}),'가치 지수 (시작 = 100)')
    st.caption(f'기준일 {last["date"]}. 달러 자산의 수익과 환율 효과가 원화 가치에 함께 반영됩니다.')
    st.subheader('ETF별 누적 성과')
    line_chart(df[list(ETFS)],'ETF 성과 지수 (시작 = 100)')
    st.caption(f'기준일 {last["date"]}. 배당·분할을 반영한 수정종가 비율입니다. 학생 비중과 무관한 ETF 자체 성과입니다.')
    st.dataframe(pd.DataFrame([{'ETF':k,'자산군':v,'성과 지수':round(last[k],2),'누적수익률 (%)':round(last[k]-100,2),'가격 기준일':last['date'],'데이터 상태':'정상'} for k,v in ETFS.items()]),hide_index=True,width='stretch')
    st.info(f'USD/KRW는 1달러당 원화입니다 ({last["USD/KRW"]:,.2f}원). 환율이 오르면 다른 조건이 같을 때 원화 가치가 증가합니다. 원화 수익률 = (1 + 달러 수익률) × (현재 환율 ÷ 시작 환율) − 1.')

def line_chart(frame,label):
    frame=frame.copy(); frame.index=pd.to_datetime(frame.index); frame.index.name='거래일'
    data=frame.reset_index().melt('거래일',var_name='기준',value_name='지수')
    chart=alt.Chart(data).mark_line().encode(x=alt.X('거래일:T',title='미국 거래일'),
        y=alt.Y('지수:Q',title=label,scale=alt.Scale(zero=False)),color=alt.Color('기준:N',title='기준'),
        tooltip=[alt.Tooltip('거래일:T',format='%Y-%m-%d'),alt.Tooltip('기준:N'),alt.Tooltip('지수:Q',format='.2f')]).properties(height=280)
    st.altair_chart(chart,width='stretch')

def show_history(svc,uid,sid,target=None):
    history=svc.history(uid,sid,target); valid=svc.health(uid,sid)['ok']
    perf=svc.performance(uid,sid,target) if valid else []
    if not history: st.info('아직 제출된 초기 자산배분이 없습니다. 내 포트폴리오에서 비중을 입력하고 최종 제출하세요.')
    for h in history:
        point=next((p for p in perf if p['date']>=h['effective']),None)
        state='적용됨' if point else '적용 대기 / 데이터 확인 필요'
        with st.expander(f'{"초기 자산배분" if h["event_key"]=="initial" else "리밸런싱"} · 적용일 {h["effective"]} · 버전 {h["versions"]}',expanded=True):
            st.caption(f'수정 불가 · {state} · 제출일 {display_time(h["submitted_at"])} · 최신 버전 {display_time(h["created_at"])}')
            st.dataframe(pd.DataFrame([h['weights']]),hide_index=True,width='stretch'); st.write('사유: '+h['reason'])
            if point: st.caption(f'실제 적용일 {point["date"]} · NAV {point["USD NAV"]:.2f} · 달러 수익률 {point["USD return %"]:.2f}% · 원화 수익률 {point["KRW return %"]:.2f}%')
    return history

def guide(admin=False):
    path=ROOT/'docs'/('Admin_Manual_KO.md' if admin else 'Student_Manual_KO.md')
    if path.exists():
        import re
        for part in re.split(r'(!\[[^\]]*\]\([^\)]+\))',path.read_text(encoding='utf-8')):
            match=re.fullmatch(r'!\[([^\]]*)\]\(([^\)]+)\)',part)
            if match: st.image(str(path.parent/match.group(2)),caption=match.group(1))
            else: st.markdown(part)
    else: st.info('사용가이드를 준비 중입니다. 각 화면의 입력 안내를 따라 주세요.')
