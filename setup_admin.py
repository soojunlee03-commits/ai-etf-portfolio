"""One-time local bootstrap. No default password or embedded secret."""
from getpass import getpass
import argparse
import secrets
from pathlib import Path
from sqlalchemy import update
from portfolio.db import users
from portfolio.db import connect
from portfolio.service import Service

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--generate-local', action='store_true', help='Create a random initial instructor password in ignored data/admin-access.txt')
    args = parser.parse_args()
    username = 'instructor' if args.generate_local else input('Admin username: ').strip()
    if not username:
        raise SystemExit('Username required.')
    password = secrets.token_urlsafe(18) if args.generate_local else getpass('Password (8+ characters): ')
    if not args.generate_local and password != getpass('Confirm password: '):
        raise SystemExit('Passwords do not match.')
    svc = Service(connect())
    svc.bootstrap(username, password)
    if args.generate_local:
        with svc.engine.begin() as c:
            c.execute(update(users).where(users.c.username==username).values(must_change=True))
        Path('data').mkdir(exist_ok=True)
        Path('data/admin-access.txt').write_text(f'Local app: http://localhost:8501\nUsername: {username}\nTemporary password: {password}\n\nChange this password at first login, then delete this file.\n',encoding='utf-8')
        print('Temporary login details saved to data/admin-access.txt (excluded from Git).')
    print('Admin created. Start the app with: python -m streamlit run app.py')
