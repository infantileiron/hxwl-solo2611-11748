from datetime import datetime
from sqlalchemy import Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
from src.utils.time import now


class CalibrationState(Base):
    """单行状态表：保存当前校准版本，同时作为导入切换的串行化锁。"""

    __tablename__ = 'calibration_state'

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(default=0)


class CalibrationBatch(Base):
    """一次校准单导入。整批校验通过后才写入口径。"""

    __tablename__ = 'calibration_batches'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    filename: Mapped[str] = mapped_column(String(160))
    checksum: Mapped[str] = mapped_column(String(64), unique=True)
    row_count: Mapped[int]
    applied_count: Mapped[int] = mapped_column(default=0)
    ignored_count: Mapped[int] = mapped_column(default=0)
    version: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20), default='applied')
    author: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=now)


class CalibrationEntry(Base):
    """追加式校准明细。version 表示该偏差在哪个版本起生效。"""

    __tablename__ = 'calibration_entries'
    __table_args__ = (
        Index('ix_calibration_entries_lookup', 'probe', 'handoff_date', 'version'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('calibration_batches.id'))
    version: Mapped[int] = mapped_column(default=0)
    probe: Mapped[str] = mapped_column(String(300))
    handoff_date: Mapped[str] = mapped_column(String(10))
    revision: Mapped[int]
    offset: Mapped[float] = mapped_column(Float)
    calibration_id: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(default=now)
