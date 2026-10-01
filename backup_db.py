"""Consistent SQLite backup and non-destructive restore."""
import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

def copy_database(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file() or destination.exists():
        raise ValueError('Source must exist and destination must not already exist.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro', uri=True)) as src:
        if src.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Database integrity check failed.')
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
    return destination

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action', choices=['backup','restore'])
    parser.add_argument('path')
    parser.add_argument('destination', nargs='?')
    args=parser.parse_args()
    if args.action=='backup':
        from sqlalchemy.engine import make_url
        from portfolio.db import configured_url
        configured = make_url(configured_url())
        if configured.get_backend_name() != 'sqlite' or not configured.database:
            parser.error('PostgreSQL은 공급자의 백업 기능 또는 pg_dump를 사용하세요.')
        result=copy_database(configured.database,args.path)
    else:
        if not args.destination:
            parser.error('Restore requires a new destination file.')
        result=copy_database(args.path,args.destination)
    print(f'Created {result}')
