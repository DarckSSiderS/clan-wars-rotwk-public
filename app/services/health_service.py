from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.campaign import CampaignRuleSet
from app.services.realtime_service import realtime_hub
from app.services.scheduler_service import WorkerStatusService


class HealthService:
    def readiness(self, db: Session) -> dict[str, object]:
        components = {
            "database": "down",
            "campaign_rules": "unknown",
            "worker": "unknown",
        }
        if realtime_hub.redis_enabled:
            components["redis"] = realtime_hub.redis_status
        try:
            db.execute(select(1)).scalar_one()
            components["database"] = "up"
            active_rules = (
                db.query(CampaignRuleSet.id)
                .filter(CampaignRuleSet.is_active.is_(True))
                .limit(1)
                .first()
            )
            components["campaign_rules"] = "up" if active_rules else "down"
            worker = WorkerStatusService().get_status(db)
            components["worker"] = "up" if worker["is_running"] else "down"
        except Exception:
            db.rollback()

        ready = all(status == "up" for status in components.values())
        return {
            "status": "ready" if ready else "not_ready",
            "components": components,
        }
