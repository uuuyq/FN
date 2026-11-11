import argparse
from getpass import getpass
from argon2 import PasswordHasher
from sqlalchemy import select
from app.core.database import make_engine, write_transaction
from app.models import User


def main():
    parser = argparse.ArgumentParser(description='Create an account without exposing the password in arguments')
    parser.add_argument('username')
    args = parser.parse_args()
    password = getpass('Password (12+ characters): ')
    if not args.username.strip() or len(args.username.strip()) > 100:
        raise SystemExit('Username must contain 1-100 characters')
    args.username = args.username.strip()
    if not 12 <= len(password) <= 1024 or password != getpass('Repeat password: '):
        raise SystemExit('Passwords must match and contain 12-1024 characters')
    with write_transaction(make_engine()) as db:
        if db.scalar(select(User).where(User.username == args.username)):
            raise SystemExit('Account already exists; no changes made')
        db.add(User(username=args.username, password_hash=PasswordHasher().hash(password)))
    print('Account created')


if __name__ == '__main__':
    main()
