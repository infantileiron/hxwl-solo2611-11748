import json
from sqlalchemy import func, select
from src.config.database import Session
from src.constants.enums import Role
from src.domain.calibration import validate_rows as validate_calibrations
from src.domain.demo import demo_calibration_rows, demo_rows
from src.domain.spec import SPEC
from src.models.identity import User
from src.models.source import Dataset
from src.services.calibrations import apply_batch
from src.services.datasets import save
from src.utils.security import hash_password


def seed():
    with Session.begin() as db:
        for role in Role:
            if not db.get(User, role.value):
                db.add(User(username=role.value, role=role, password_hash=hash_password(f'{role.value}-demo-2611')))
        item, created = save(db, SPEC['default_dataset'], SPEC['sample_name'], demo_rows(), 'seed')
        calibration_rows = validate_calibrations(demo_calibration_rows())
        calibration, calibration_created = apply_batch(
            db, '麦屿探针 11 月校准单', SPEC['calibration_sample_name'], calibration_rows, 'seed')
        return {'users': db.scalar(select(func.count()).select_from(User)),
                'datasets': db.scalar(select(func.count()).select_from(Dataset)),
                'seed_dataset_id': item.id, 'row_count': item.row_count, 'checksum': item.checksum,
                'created_dataset': created, 'calibration_version': calibration.version,
                'calibration_created': calibration_created}


if __name__ == '__main__':
    print(json.dumps(seed(), ensure_ascii=False))
