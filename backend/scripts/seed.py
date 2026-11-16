from app.core.database import make_engine, write_transaction
from app.models import Equipment, PublicExercise
from app.equipment_categories import PRESET_CATEGORIES
from scripts.catalog_data import EQUIPMENT, EXERCISES


def seed(engine):
    with write_transaction(engine) as db:
        for key, name in EQUIPMENT.items():
            if not db.get(Equipment, key):
                db.add(Equipment(id=key, name=name, category=PRESET_CATEGORIES.get(key, "其他")))
        for item in EXERCISES:
            if not db.get(PublicExercise, item['id']):
                db.add(PublicExercise(**item))


if __name__ == '__main__':
    seed(make_engine())
