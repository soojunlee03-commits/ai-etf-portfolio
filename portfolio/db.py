import os
from pathlib import Path
from sqlalchemy import (create_engine, MetaData, Table, Column, Integer, String,
                        Boolean, Text, ForeignKey, UniqueConstraint, event, text)

metadata = MetaData()
users = Table('users', metadata,
    Column('id', Integer, primary_key=True), Column('username', String(100), unique=True, nullable=False),
    Column('name', String(100), nullable=False), Column('password', Text, nullable=False),
    Column('role', String(20), nullable=False), Column('active', Boolean, nullable=False, default=True),
    Column('must_change', Boolean, nullable=False, default=True),
    Column('failed', Integer, nullable=False, default=0), Column('locked_until', String(40), default=''))
semesters = Table('semesters', metadata,
    Column('id', Integer, primary_key=True), Column('name', String(150), nullable=False),
    Column('start', String(10), nullable=False), Column('end', String(10), nullable=False),
    Column('initial_deadline', String(40), nullable=False),
    Column('leaderboard', Boolean, nullable=False, default=False),
    Column('archived', Boolean, nullable=False, default=False))
semester_trash = Table('semester_trash', metadata,
    Column('semester_id', ForeignKey('semesters.id'), primary_key=True),
    Column('deleted_at', String(40), nullable=False),
    Column('actor_id', ForeignKey('users.id'), nullable=False))
enrollments = Table('enrollments', metadata,
    Column('id', Integer, primary_key=True), Column('semester_id', ForeignKey('semesters.id'), nullable=False),
    Column('user_id', ForeignKey('users.id'), nullable=False), UniqueConstraint('semester_id', 'user_id'))
late_initial_permissions = Table('late_initial_permissions', metadata,
    Column('semester_id', ForeignKey('semesters.id'), primary_key=True),
    Column('user_id', ForeignKey('users.id'), primary_key=True),
    Column('granted_by', ForeignKey('users.id'), nullable=False),
    Column('granted_at', String(40), nullable=False),
    Column('reason', Text, nullable=False))
windows = Table('windows', metadata,
    Column('id', Integer, primary_key=True), Column('semester_id', ForeignKey('semesters.id'), nullable=False),
    Column('name', String(150), nullable=False), Column('opens', String(40), nullable=False),
    Column('closes', String(40), nullable=False), Column('effective', String(10), nullable=False),
    UniqueConstraint('semester_id', 'effective'))
submissions = Table('submissions', metadata,
    Column('id', Integer, primary_key=True), Column('semester_id', ForeignKey('semesters.id'), nullable=False),
    Column('user_id', ForeignKey('users.id'), nullable=False), Column('event_key', String(40), nullable=False),
    Column('effective', String(10), nullable=False), Column('submitted_at', String(40), nullable=False),
    UniqueConstraint('semester_id', 'user_id', 'event_key'))
allocations = Table('allocation_versions', metadata,
    Column('id', Integer, primary_key=True), Column('submission_id', ForeignKey('submissions.id'), nullable=False),
    Column('weights', Text, nullable=False), Column('reason', Text, nullable=False),
    Column('created_at', String(40), nullable=False), Column('actor_id', ForeignKey('users.id'), nullable=False))
snapshots = Table('market_versions', metadata,
    Column('id', Integer, primary_key=True), Column('day', String(10), nullable=False),
    Column('previous_day', String(10), nullable=False),
    Column('factors', Text, nullable=False), Column('fx', String(50), nullable=False),
    Column('prices', Text, nullable=False), Column('source', Text, nullable=False),
    Column('created_at', String(40), nullable=False))
audit = Table('audit_log', metadata,
    Column('id', Integer, primary_key=True), Column('actor_id', ForeignKey('users.id'), nullable=False),
    Column('action', String(80), nullable=False), Column('target', String(150), nullable=False),
    Column('before', Text, nullable=False), Column('after', Text, nullable=False),
    Column('reason', Text, nullable=False), Column('created_at', String(40), nullable=False))
settings = Table('app_settings', metadata,
    Column('key', String(60), primary_key=True), Column('value', Text, nullable=False))
login_events = Table('login_events', metadata,
    Column('id', Integer, primary_key=True), Column('user_id', ForeignKey('users.id'), nullable=False),
    Column('created_at', String(40), nullable=False))
official_runs = Table('official_runs', metadata,
    Column('id', Integer, primary_key=True), Column('semester_id', ForeignKey('semesters.id'), nullable=False),
    Column('measurement_date', String(10), nullable=False), Column('digest', String(64), nullable=False),
    Column('payload', Text, nullable=False), Column('actor_id', ForeignKey('users.id'), nullable=False),
    Column('created_at', String(40), nullable=False), Column('reason', Text, nullable=False))

def configured_url():
    if os.environ.get('DATABASE_URL'): return os.environ['DATABASE_URL']
    secret_path=Path(__file__).resolve().parents[1]/'.streamlit'/'secrets.toml'
    if secret_path.exists():
        import tomllib
        with secret_path.open('rb') as f:
            return tomllib.load(f).get('DATABASE_URL','sqlite:///data/portfolio.db')
    return 'sqlite:///data/portfolio.db'

def connect(url=None):
    url = url or configured_url()
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql+psycopg://', 1)
    if url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
    if url.startswith('sqlite:'):
        Path('data').mkdir(exist_ok=True)
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True,
                           connect_args={'check_same_thread': False, 'timeout': 30} if url.startswith('sqlite:') else {})
    if url.startswith('sqlite:'):
        @event.listens_for(engine, 'connect')
        def configure(dbapi, _):
            dbapi.execute('PRAGMA foreign_keys=ON')
            dbapi.execute('PRAGMA journal_mode=WAL')
    metadata.create_all(engine)
    # Additive migration: existing users, semesters, submissions and passwords remain intact.
    with engine.begin() as c:
        for name in ('allocation_versions', 'market_versions', 'audit_log', 'official_runs'):
            if engine.dialect.name == 'sqlite':
                for action in ('UPDATE', 'DELETE'):
                    c.execute(text(f"CREATE TRIGGER IF NOT EXISTS immutable_{name}_{action} BEFORE {action} ON {name} BEGIN SELECT RAISE(ABORT, 'append-only record'); END"))
            elif engine.dialect.name == 'postgresql':
                c.execute(text("CREATE OR REPLACE FUNCTION prevent_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'append-only record'; END; $$"))
                c.execute(text(f"DROP TRIGGER IF EXISTS immutable_history ON {name}"))
                c.execute(text(f"CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION prevent_history_mutation()"))
    return engine
