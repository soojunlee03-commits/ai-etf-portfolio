"""XNYS session dates; NYSE/NYSE Arca share the regular US equity holiday calendar."""
from functools import lru_cache
from datetime import date, timedelta
import exchange_calendars as xc

@lru_cache(maxsize=16)
def calendar(year):
    return xc.get_calendar('XNYS', start=f'{year-1}-01-01', end=f'{year+2}-12-31')

def sessions(start, end):
    start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    if end < start:
        return []
    result=[]
    for year in range(start.year, end.year+1):
        lo=max(start,date(year,1,1)); hi=min(end,date(year,12,31))
        result.extend(str(d.date()) for d in calendar(year).sessions_in_range(str(lo),str(hi)))
    return result

def previous_session(day):
    day=date.fromisoformat(str(day))
    return str(calendar(day.year).date_to_session(str(day-timedelta(days=1)),direction='previous').date())
