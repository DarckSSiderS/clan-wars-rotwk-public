from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models.clan import Clan
from app.models.operation import AdminAuditLog, ResourceLedgerEntry


RESOURCE_MODEL_FIELDS = {
    "gold": "gold",
    "iron": "iron",
    "wood": "wood",
    "food": "food",
    "mithril": "mithril",
    "influence": "territory_points",
}


class ResourceLedgerService:
    @staticmethod
    def lock_clans(db: Session, clan_ids) -> dict[int, Clan]:
        """Read current balances under transaction-scoped locks in a stable order.

        SQLAlchemy's identity map can contain a clan read before another request
        committed. Refresh clean attributes once per transaction, while preserving
        intentional pending changes made by the current transaction.
        """
        transaction = db.get_nested_transaction() or db.get_transaction() or db.begin()
        state = db.info.get("resource_clan_locks")
        if state is None or state[0] is not transaction:
            state = (transaction, set())
            db.info["resource_clan_locks"] = state
        locked = state[1]
        result = {}
        for clan_id in sorted(set(filter(None, clan_ids))):
            with db.no_autoflush:
                clan = db.get(Clan, clan_id)
                if clan is None:
                    continue
                if clan_id not in locked:
                    clean_columns = [
                        attr.key for attr in inspect(Clan).column_attrs
                        if not inspect(clan).attrs[attr.key].history.has_changes()
                    ]
                    db.refresh(clan, attribute_names=clean_columns, with_for_update=True)
                    locked.add(clan_id)
                result[clan_id] = clan
        return result

    def apply_change(
        self,
        db: Session,
        clan: Clan,
        *,
        resource: str,
        amount: int,
        operation_id: str,
        action: str,
        source_type: str | None = None,
        source_id: str | int | None = None,
        actor_user_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> tuple[ResourceLedgerEntry, bool]:
        resource_key = resource.strip().lower()
        model_field = RESOURCE_MODEL_FIELDS.get(resource_key)
        if not model_field:
            raise ValueError(f"Неизвестный ресурс: {resource}")

        self.lock_clans(db, [clan.id])
        # Flush only pending ledger entries, including when autoflush is disabled.
        # The clan lock serializes competing uses of the same operation key.
        pending = [row for row in db.new if isinstance(row, ResourceLedgerEntry)]
        if pending:
            db.flush(pending)
        existing = db.query(ResourceLedgerEntry).filter(
            ResourceLedgerEntry.operation_id == operation_id,
            ResourceLedgerEntry.clan_id == clan.id,
            ResourceLedgerEntry.resource == resource_key,
        ).first()
        if existing:
            return existing, False

        before = int(getattr(clan, model_field) or 0)
        after = before + int(amount)
        if after < 0:
            raise ValueError(f"Недостаточно ресурса: {resource_key}")

        setattr(clan, model_field, after)
        if model_field == "territory_points":
            base_before = int(clan.base_influence or 0)
            base_after = base_before + int(amount)
            if base_after < 0:
                raise ValueError("Недостаточно базового влияния")
            clan.base_influence = base_after
        if model_field == "gold":
            clan.resources = after

        entry = ResourceLedgerEntry(
            operation_id=operation_id,
            clan_id=clan.id,
            resource=resource_key,
            amount=int(amount),
            balance_before=before,
            balance_after=after,
            action=action,
            source_type=source_type,
            source_id=str(source_id) if source_id is not None else None,
            actor_user_id=actor_user_id,
            details=details,
        )
        db.add(entry)
        return entry, True


class AdminAuditService:
    def record(
        self,
        db: Session,
        *,
        actor_user_id: int,
        action: str,
        entity_type: str,
        entity_id: str | int | None = None,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> AdminAuditLog:
        entry = AdminAuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            before_data=before_data,
            after_data=after_data,
            reason=reason,
        )
        db.add(entry)
        return entry
