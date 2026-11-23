"""Seed the e2e database: shared catalog data and the e2e user."""


def main():
    import os

    from argon2 import PasswordHasher
    from app.core.database import make_engine, write_transaction
    from app.models import User
    from scripts.seed import seed

    engine = make_engine(os.environ["DATABASE_URL"])
    seed(engine)
    password = PasswordHasher().hash("e2e-test-password")
    with write_transaction(engine) as db:
        db.add(User(username="e2e-user", password_hash=password))
        db.add(User(username="e2e-other", password_hash=password))
    engine.dispose()
    print("e2e database ready")


if __name__ == "__main__":
    main()
