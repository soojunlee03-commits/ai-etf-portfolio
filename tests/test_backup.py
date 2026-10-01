import sqlite3
import pytest
from backup_db import copy_database

def test_backup_restore(tmp_path):
    source=tmp_path/'source.db'
    with sqlite3.connect(source) as c:
        c.execute('CREATE TABLE records(value TEXT)')
        c.execute('INSERT INTO records VALUES (?)',('preserved',))
    backup=copy_database(source,tmp_path/'backup.db')
    restored=copy_database(backup,tmp_path/'restored.db')
    with sqlite3.connect(restored) as c:
        assert c.execute('SELECT value FROM records').fetchone()[0]=='preserved'
    with pytest.raises(ValueError):copy_database(source,backup)
