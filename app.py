import logging
import streamlit as st
from portfolio.ui_app import main
from portfolio.service import RuleError

st.set_page_config(page_title='AI ETF Portfolio Competition', page_icon='📊', layout='wide')
try:
    main()
except RuleError as error:
    st.error(f'{error} 현재 기록을 확인하고 문제가 계속되면 담당 교수자에게 문의하세요.')
except Exception as error:
    logging.error('application_failed type=%s', type(error).__name__)
    st.error('앱 또는 데이터베이스에 연결하지 못했습니다. 저장 여부를 확인할 수 없습니다. 새로고침 후 다시 확인하고, 문제가 계속되면 담당 운영자에게 데이터 연결과 백업 상태 점검을 요청하세요.')
