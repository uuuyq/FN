from app.core.database import make_engine, write_transaction
from app.models import Equipment, Exercise
from scripts.catalog_data import EQUIPMENT, EXERCISES


def seed(engine):
    with write_transaction(engine) as db:
        for key, name in EQUIPMENT.items():
            if not db.get(Equipment, key):
                db.add(Equipment(id=key, name=name))
        for item in EXERCISES:
            if not db.get(Exercise, item['id']):
                db.add(Exercise(**item))


if __name__ == '__main__':
    seed(make_engine())
