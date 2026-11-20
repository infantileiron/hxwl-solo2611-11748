import os
import tempfile

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')
os.environ.setdefault('JWT_SECRET', 'test-secret')

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.config.database import Base
from src.models import calibration as calibration_models  # noqa: F401
from src.models import identity, jobs, source  # noqa: F401


@pytest.fixture()
def db():
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
