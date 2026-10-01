import pytest
from pathlib import Path
from sqlalchemy import insert, select
from streamlit.testing.v1 import AppTest
from portfolio.db import connect, users, settings
from portfolio.cloud_demo import demo_url, check_demo_marker, MARKER
from portfolio.service import RuleError, Service
from prepare_cloud_demo import copy_into_empty

def test_demo_requires_explicit_postgres():
    for value in (None,'','sqlite:///data/portfolio.db'):
        with pytest.raises(RuleError):demo_url(value)
    assert demo_url('postgresql://example:example@localhost/demo').drivername=='postgresql+psycopg'

def test_transfer_refuses_existing_and_checks_marker(tmp_path):
    source=connect('sqlite:///'+(tmp_path/'source.db').as_posix())
    target=connect('sqlite:///'+(tmp_path/'target.db').as_posix())
    try:
        svc=Service(source);svc.bootstrap('demo_admin','test-only-cloud-password')
        with pytest.raises(RuleError):check_demo_marker(target)
        copy_into_empty(source,target)
        check_demo_marker(target)
        assert Service(target).login('demo_admin','test-only-cloud-password')
        with pytest.raises(ValueError):copy_into_empty(source,target)
        assert len(Service(target).rows(users))==1
    finally:source.dispose();target.dispose()

def test_cloud_entrypoint_never_falls_back_to_production(monkeypatch,tmp_path):
    monkeypatch.delenv('DEMO_DATABASE_URL',raising=False)
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+(tmp_path/'should-not-exist.db').as_posix())
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'demo_app.py').run(timeout=30)
    assert not at.exception and at.error
    assert not (tmp_path/'should-not-exist.db').exists()
