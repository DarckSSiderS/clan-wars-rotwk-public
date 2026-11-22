from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class ResourceLedgerEntry(Base):
    __tablename__ = "resource_ledger"
    __table_args__ = (
        UniqueConstraint(
            "operation_id",
            "clan_id",
            "resource",
            name="uq_resource_ledger_operation_clan_resource",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    operation_id = Column(String(120), nullable=False, index=True)
    clan_id = Column(Integer, ForeignKey("clans.id"), nullable=False, index=True)
    resource = Column(String(32), nullable=False)
    amount = Column(Integer, nullable=False)
    balance_before = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    action = Column(String(80), nullable=False, index=True)
    source_type = Column(String(80), nullable=True)
    source_id = Column(String(120), nullable=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(80), nullable=False, index=True)
    entity_type = Column(String(80), nullable=False, index=True)
    entity_id = Column(String(120), nullable=True, index=True)
    before_data = Column(JSON, nullable=True)
    after_data = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
