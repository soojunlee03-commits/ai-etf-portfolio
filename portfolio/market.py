"""Download completed Yahoo daily bars; never revise stored history implicitly."""
from datetime import date, timedelta
import pandas as pd
import yfinance as yf
from .calendar import sessions, previous_session
from .service import ETFS, RuleError

def fetch(start, end):
    start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    if end >= date.today():
        raise RuleError('미완성 가격을 피하기 위해 오늘 이전 날짜까지만 가져올 수 있습니다.')
    if end < start:
        raise RuleError('시작일과 종료일을 확인하세요.')
    symbols = [*ETFS, 'KRW=X']
    frames = {}
    for symbol in symbols:
        frame = yf.download(symbol, start=str(start-timedelta(days=14)), end=str(end+timedelta(days=1)),
            auto_adjust=False, actions=False, progress=False, threads=False, multi_level_index=False)
        field = 'Close' if symbol == 'KRW=X' else 'Adj Close'
        if frame is None or frame.empty or field not in frame:
            raise RuleError(f'{symbol} 데이터를 가져오지 못했습니다. 잠시 후 다시 시도하거나 CSV를 가져오세요.')
        series = frame[field].copy()
        series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
        frames[symbol] = series
    # Keep every observed ETF session; do not silently drop incomplete sessions.
    prices = pd.concat({k: frames[k] for k in ETFS}, axis=1).dropna(how='all').sort_index()
    fx = frames['KRW=X'].reindex(prices.index)
    expected=sessions(str(start),str(end))
    observed={str(d.date()) for d in prices.index}
    missing=[d for d in expected if d not in observed]
    if missing:
        raise RuleError(f'{missing[0]} 거래일 데이터가 누락되어 저장하지 않았습니다. 잠시 후 재시도하거나 교수자에게 문의하세요.')
    rows = []
    for i, (day, row) in enumerate(prices.iterrows()):
        if day.date() < start or day.date() > end:
            continue
        if i == 0 or row.isna().any() or prices.iloc[i-1].isna().any() or pd.isna(fx.loc[day]):
            raise RuleError(f'{day.date()} 가격 또는 동일 날짜 환율이 누락되었습니다. 저장을 중단했습니다.')
        previous = prices.iloc[i-1]
        if str(prices.index[i-1].date())!=previous_session(str(day.date())):
            raise RuleError('직전 거래일 가격이 누락되어 저장하지 않았습니다. 누락 기간을 확인하세요.')
        rows.append({'day': str(day.date()), 'previous_day': str(prices.index[i-1].date()),
            'prices': {k: float(row[k]) for k in ETFS},
            'factors': {k: float(row[k]/previous[k]) for k in ETFS}, 'fx': float(fx.loc[day]),
            'source': 'Yahoo Finance via yfinance; ETF Adj Close daily ratio; KRW=X same-date Close'})
    if not rows:
        raise RuleError('선택한 기간에 저장할 거래일 데이터가 없습니다.')
    return rows

def from_csv(file):
    df = pd.read_csv(file, dtype={'day': str, 'previous_day': str})
    required = {'day', 'previous_day', 'fx', *ETFS, *[f'{k}_factor' for k in ETFS]}
    if not required <= set(df.columns) or df.empty or df['day'].duplicated().any():
        raise RuleError('CSV 열 또는 날짜 중복을 확인하세요. 관리자 설명서의 양식을 사용하세요.')
    rows = []
    for r in df.to_dict('records'):
        if date.fromisoformat(r['day']) >= date.today():
            raise RuleError('오늘 이전의 완료된 데이터만 가져올 수 있습니다.')
        rows.append({'day': r['day'], 'previous_day': r['previous_day'], 'fx': float(r['fx']),
            'prices': {k: float(r[k]) for k in ETFS}, 'factors': {k: float(r[f'{k}_factor']) for k in ETFS},
            'source': 'Instructor verified CSV; adjusted daily factors and same-date USD/KRW'})
    return rows
