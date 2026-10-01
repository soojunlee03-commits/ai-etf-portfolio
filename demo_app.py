"""Streamlit Community Cloud entrypoint for the private testing demo."""
import logging
import os
import streamlit as st
from portfolio.cloud_demo import verified_url
from portfolio.service import RuleError
from portfolio.ui_app import main

st.set_page_config(page_title='ETF 포트폴리오 · 웹 데모',page_icon='📊',layout='wide')

@st.cache_resource
def connection(value):
    return verified_url(value)

try:
    value=os.environ.get('DEMO_DATABASE_URL')
    if not value:
        try: value=st.secrets.get('DEMO_DATABASE_URL')
        except FileNotFoundError: value=None
    main(database_url=connection(value),demo=True)
except RuleError as error:
    st.error(str(error))
except Exception as error:
    logging.error('cloud_demo_failed type=%s',type(error).__name__)
    st.error('웹 데모에 연결하지 못했습니다. 운영자에게 데모 DB 준비 여부와 비공개 연결 설정을 확인해 달라고 요청하세요.')
