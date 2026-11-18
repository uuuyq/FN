from sqlalchemy import select

from app.core.database import make_engine, write_transaction
from app.models import (Equipment, PublicExercise, UserEquipment,
                        UserExercisePreference, WorkoutSet)
from app.equipment_categories import PRESET_CATEGORIES
from scripts.catalog_data import EQUIPMENT, EXERCISES


def seed(engine):
    with write_transaction(engine) as db:
        # 器械：补齐目录中缺失的
        for key, name in EQUIPMENT.items():
            if not db.get(Equipment, key):
                db.add(Equipment(id=key, name=name,
                                 category=PRESET_CATEGORIES.get(key, '其他')))

        # 动作：更新已有、插入缺失
        for item in EXERCISES:
            row = db.get(PublicExercise, item['id'])
            if row:
                for field, value in item.items():
                    setattr(row, field, value)
                row.version = (row.version or 1) + 1
            else:
                db.add(PublicExercise(**item))

        # 删除不在目录中、且未被用户数据引用的动作
        keep_ids = {item['id'] for item in EXERCISES}
        referenced = set(db.scalars(select(WorkoutSet.public_exercise_id)
                                    .where(WorkoutSet.public_exercise_id.is_not(None))))
        referenced |= set(db.scalars(select(UserExercisePreference.public_exercise_id)
                                     .where(UserExercisePreference.public_exercise_id.is_not(None))))
        for row in db.scalars(select(PublicExercise)):
            if row.id not in keep_ids and row.id not in referenced:
                db.delete(row)

        # 删除目录中已不存在、且未被用户器械库引用的器械
        used_equipment = set(db.scalars(select(UserEquipment.equipment_id)
                                        .where(UserEquipment.equipment_id.is_not(None))))
        for row in db.scalars(select(Equipment)):
            if row.id not in EQUIPMENT and row.id not in used_equipment:
                db.delete(row)


if __name__ == '__main__':
    seed(make_engine())
