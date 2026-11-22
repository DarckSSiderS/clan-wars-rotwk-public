from typing import List, Optional
import re
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.repositories.achievement_repository import AchievementRepository, UserAchievementRepository
from app.repositories.user_repository import UserRepository
from app.core.exceptions import (
    AchievementNotFoundException, UserNotFoundException,
    UserAchievementNotFoundException
)
from app.schemas.achievement import (
    AchievementCreate, AchievementUpdate, UserAchievementCreate,
    UserAchievementUpdate
)
from app.models.match import Match
from app.services.notification_service import notification_service


class AchievementService:
    """Сервис для работы с достижениями"""
    
    def __init__(self):
        self.achievement_repo = AchievementRepository()
    
    def get_achievement(self, db: Session, achievement_id: int):
        """Получить достижение по ID"""
        achievement = self.achievement_repo.get(db, achievement_id)
        if not achievement:
            raise AchievementNotFoundException(achievement_id)
        return achievement
    
    def get_achievements(self, db: Session, skip: int = 0, limit: int = 100) -> List:
        """Получить список достижений"""
        return self.achievement_repo.get_multi(db, skip=skip, limit=limit)
    
    def get_available_achievements(self, db: Session) -> List:
        """Получить доступные достижения"""
        return self.achievement_repo.get_available_achievements(db)
    
    def get_achievements_by_category(self, db: Session, category: str) -> List:
        """Получить достижения по категории"""
        return self.achievement_repo.get_achievements_by_category(db, category)
    
    def get_achievements_by_type(self, db: Session, achievement_type: str) -> List:
        """Получить достижения по типу"""
        return self.achievement_repo.get_achievements_by_type(db, achievement_type)
    
    def create_achievement(self, db: Session, achievement_data: AchievementCreate):
        """Создать новое достижение"""
        return self.achievement_repo.create(db, obj_in=achievement_data)
    
    def update_achievement(self, db: Session, achievement_id: int, achievement_data: AchievementUpdate):
        """Обновить достижение"""
        achievement = self.get_achievement(db, achievement_id)
        return self.achievement_repo.update(db, db_obj=achievement, obj_in=achievement_data)
    
    def delete_achievement(self, db: Session, achievement_id: int):
        """Удалить достижение"""
        achievement = self.get_achievement(db, achievement_id)
        return self.achievement_repo.remove(db, id=achievement_id)


class UserAchievementService:
    """Сервис для работы с достижениями пользователей"""

    DIRECT_REQUIREMENTS = {
        "matches", "wins", "losses", "unique_maps", "unique_factions",
        "best_streak", "long_games", "fast_wins", "night_matches",
        "unique_opponents", "active_days", "team_games", "team_wins",
    }
    PREFIX_REQUIREMENTS = {
        "faction_games", "faction_wins", "faction_winrate",
        "map_games", "map_wins", "map_winrate", "mode_games", "mode_wins",
    }
    
    def __init__(self):
        self.user_achievement_repo = UserAchievementRepository()
        self.achievement_repo = AchievementRepository()
        self.user_repo = UserRepository()

    def ensure_user_achievements(self, db: Session, user_id: int):
        available_achievements = self.achievement_repo.get_available_achievements(db)
        existing_ids = {
            item.achievement_id
            for item in self.user_achievement_repo.get_user_achievements(db, user_id)
        }
        created = False
        for achievement in available_achievements:
            if achievement.id not in existing_ids:
                self.user_achievement_repo.create(
                    db,
                    obj_in={
                        "user_id": user_id,
                        "achievement_id": achievement.id,
                        "progress": 0,
                        "is_completed": False,
                    },
                )
                created = True
        if created:
            db.commit()
    
    def get_user_achievements(self, db: Session, user_id: int) -> List:
        """Получить все достижения пользователя"""
        self.ensure_user_achievements(db, user_id)
        self.sync_user_achievements(db, user_id)
        return self.user_achievement_repo.get_user_achievements(db, user_id)

    @staticmethod
    def _duration_seconds(value: Optional[str]) -> int:
        try:
            parts = [int(part) for part in str(value or "").split(":")]
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            if len(parts) == 2:
                return parts[0] * 60 + parts[1]
        except (TypeError, ValueError):
            pass
        return 0

    @staticmethod
    def _normalize_game_mode(value: Optional[str]) -> str:
        text = " ".join(str(value or "").strip().lower().split())
        match = re.search(r"([1-4])\s*(?:v|vs|versus)\s*([1-4])", text)
        if match and match.group(1) == match.group(2):
            size = match.group(1)
            return f"{size} versus {size}"
        return text or "1 versus 1"

    @classmethod
    def supports_requirement(cls, requirement: Optional[str]) -> bool:
        value = str(requirement or "").strip()
        if value in cls.DIRECT_REQUIREMENTS:
            return True
        prefix = value.split(":", 1)[0]
        return prefix in cls.PREFIX_REQUIREMENTS

    def sync_user_achievements(self, db: Session, user_id: int) -> None:
        """Пересчитать прогресс только по полям сохранённых матчей."""
        user = self.user_repo.get(db, user_id)
        if not user:
            return
        self.ensure_user_achievements(db, user_id)
        from app.services.player_match_scope import PlayerMatchScope
        scope = PlayerMatchScope(db, user)
        matches = scope.query(db).order_by(Match.match_date.asc(), Match.id.asc()).all()
        player_entry = scope.participant
        wins = [match for match in matches if scope.is_winner(match)]
        losses = [match for match in matches if match not in wins]
        faction_games, faction_wins = {}, {}
        map_games, map_wins = {}, {}
        mode_games, mode_wins = {}, {}
        factions, maps, active_days, won_opponents = set(), set(), set(), set()
        long_games = fast_wins = night_matches = 0
        team_games = team_wins = 0
        current_streak = best_streak = 0

        for match in matches:
            entry = player_entry(match)
            is_win = scope.is_winner(match)
            faction = entry.faction if entry is not None else (
                match.winner_faction if is_win else match.loser_faction
            )
            opponents = [
                participant.nickname
                for participant in (match.participants or [])
                if bool(participant.is_winner) != is_win and not participant.is_observer
            ]
            if not opponents:
                opponents = [match.loser_player if is_win else match.winner_player]
            mode = self._normalize_game_mode(match.gamemode_name or match.game_mode)
            mode_games[mode] = mode_games.get(mode, 0) + 1
            if is_win:
                mode_wins[mode] = mode_wins.get(mode, 0) + 1
            if mode != "1 versus 1":
                team_games += 1
                team_wins += int(is_win)
            if faction:
                factions.add(faction)
                faction_games[faction] = faction_games.get(faction, 0) + 1
                if is_win:
                    faction_wins[faction] = faction_wins.get(faction, 0) + 1
            if match.map_name:
                maps.add(match.map_name)
                map_games[match.map_name] = map_games.get(match.map_name, 0) + 1
                if is_win:
                    map_wins[match.map_name] = map_wins.get(match.map_name, 0) + 1
            if match.match_date:
                active_days.add(match.match_date.date())
                if match.match_date.hour >= 22 or match.match_date.hour < 6:
                    night_matches += 1
            duration = self._duration_seconds(match.duration)
            long_games += int(duration >= 30 * 60)
            fast_wins += int(is_win and duration and duration <= 10 * 60)
            if is_win:
                current_streak += 1
                best_streak = max(best_streak, current_streak)
                won_opponents.update(opponent for opponent in opponents if opponent)
            else:
                current_streak = 0

        stats = {
            "matches": len(matches), "wins": len(wins), "losses": len(losses),
            "unique_maps": len(maps), "unique_factions": len(factions),
            "best_streak": best_streak, "long_games": long_games,
            "fast_wins": fast_wins, "night_matches": night_matches,
            "unique_opponents": len(won_opponents), "active_days": len(active_days),
            "team_games": team_games, "team_wins": team_wins,
        }
        changed = False
        for user_achievement in self.user_achievement_repo.get_user_achievements(db, user_id):
            achievement = user_achievement.achievement
            # Earned awards survive renames and history preferences; never pay twice.
            if user_achievement.is_completed:
                continue
            requirement = achievement.requirement_type or ""
            value = 0
            if requirement.startswith("faction_games:"):
                value = faction_games.get(requirement.split(":", 1)[1], 0)
            elif requirement.startswith("faction_wins:"):
                value = faction_wins.get(requirement.split(":", 1)[1], 0)
            elif requirement.startswith("map_games:"):
                value = map_games.get(requirement.split(":", 1)[1], 0)
            elif requirement.startswith("map_wins:"):
                value = map_wins.get(requirement.split(":", 1)[1], 0)
            elif requirement.startswith("mode_games:"):
                subject = self._normalize_game_mode(requirement.split(":", 1)[1])
                value = mode_games.get(subject, 0)
            elif requirement.startswith("mode_wins:"):
                subject = self._normalize_game_mode(requirement.split(":", 1)[1])
                value = mode_wins.get(subject, 0)
            elif requirement.startswith("faction_winrate:") or requirement.startswith("map_winrate:"):
                parts = requirement.split(":")
                subject = parts[1]
                minimum_games = int(parts[3]) if len(parts) > 3 else 1
                games = faction_games.get(subject, 0) if parts[0] == "faction_winrate" else map_games.get(subject, 0)
                wins_for_subject = faction_wins.get(subject, 0) if parts[0] == "faction_winrate" else map_wins.get(subject, 0)
                value = round(wins_for_subject * 100 / games) if games >= minimum_games else 0
            else:
                value = stats.get(requirement, 0)
            progress = min(value, achievement.target_value)
            if user_achievement.progress != progress:
                user_achievement.progress = progress
                changed = True
            completed = progress >= achievement.target_value
            if completed != user_achievement.is_completed:
                was_completed = user_achievement.is_completed
                user_achievement.is_completed = completed
                user_achievement.completed_at = datetime.now(timezone.utc) if completed else None
                user_achievement.updated_at = datetime.now(timezone.utc)
                if completed and not was_completed and achievement.reward_amount:
                    user.balance += achievement.reward_amount
                if completed and not was_completed:
                    notification_service.create(
                        db,
                        user_id=user_id,
                        notification_type="achievement_completed",
                        title="Получено достижение",
                        message=f"«{achievement.name}» теперь в вашей летописи наград.",
                        link_url="/achievements",
                        entity_type="achievement",
                        entity_id=achievement.id,
                        commit=False,
                    )
                changed = True
        if changed:
            db.commit()
    
    def get_completed_achievements(self, db: Session, user_id: int) -> List:
        """Получить завершенные достижения пользователя"""
        return self.user_achievement_repo.get_completed_achievements(db, user_id)
    
    def get_in_progress_achievements(self, db: Session, user_id: int) -> List:
        """Получить достижения в процессе выполнения"""
        return self.user_achievement_repo.get_in_progress_achievements(db, user_id)
    
    def get_user_achievement(self, db: Session, user_id: int, achievement_id: int):
        """Получить достижение пользователя"""
        user_achievement = self.user_achievement_repo.get_user_achievement_by_achievement(
            db, user_id, achievement_id
        )
        if not user_achievement:
            raise UserAchievementNotFoundException(user_id, achievement_id)
        return user_achievement
    
    def create_user_achievement(self, db: Session, user_id: int, achievement_id: int):
        """Создать достижение пользователя"""
        # Проверяем существование пользователя
        user = self.user_repo.get(db, user_id)
        if not user:
            raise UserNotFoundException(user_id=user_id)
        
        # Проверяем существование достижения
        achievement = self.achievement_repo.get(db, achievement_id)
        if not achievement:
            raise AchievementNotFoundException(achievement_id)
        
        # Проверяем, не создано ли уже достижение
        existing_achievement = self.user_achievement_repo.get_user_achievement_by_achievement(
            db, user_id, achievement_id
        )
        if existing_achievement:
            return existing_achievement
        
        # Создаем достижение пользователя
        user_achievement_data = {
            "user_id": user_id,
            "achievement_id": achievement_id,
            "progress": 0,
            "is_completed": False
        }
        return self.user_achievement_repo.create(db, obj_in=user_achievement_data)
    
    def update_achievement_progress(self, db: Session, user_id: int, achievement_id: int, progress: int):
        """Обновить прогресс достижения"""
        user_achievement = self.get_user_achievement(db, user_id, achievement_id)
        achievement = self.achievement_repo.get(db, achievement_id)
        
        # Обновляем прогресс
        user_achievement.progress = min(progress, achievement.target_value)
        
        # Проверяем, завершено ли достижение
        if user_achievement.progress >= achievement.target_value and not user_achievement.is_completed:
            user_achievement.is_completed = True
            user_achievement.completed_at = datetime.utcnow()
            
            # Начисляем награду пользователю
            user = self.user_repo.get(db, user_id)
            if user and achievement.reward_amount:
                user.balance += achievement.reward_amount
            notification_service.create(
                db,
                user_id=user_id,
                notification_type="achievement_completed",
                title="Получено достижение",
                message=f"«{achievement.name}» теперь в вашей летописи наград.",
                link_url="/achievements",
                entity_type="achievement",
                entity_id=achievement.id,
                commit=False,
            )
        
        user_achievement.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user_achievement)
        
        return user_achievement
    
    def complete_achievement(self, db: Session, user_id: int, achievement_id: int):
        """Завершить достижение"""
        user_achievement = self.get_user_achievement(db, user_id, achievement_id)
        achievement = self.achievement_repo.get(db, achievement_id)
        
        if user_achievement.is_completed:
            return user_achievement
        
        # Устанавливаем максимальный прогресс и завершаем
        user_achievement.progress = achievement.target_value
        user_achievement.is_completed = True
        user_achievement.completed_at = datetime.utcnow()
        user_achievement.updated_at = datetime.utcnow()
        
        # Начисляем награду пользователю
        user = self.user_repo.get(db, user_id)
        if user and achievement.reward_amount:
            user.balance += achievement.reward_amount
        notification_service.create(
            db,
            user_id=user_id,
            notification_type="achievement_completed",
            title="Получено достижение",
            message=f"«{achievement.name}» теперь в вашей летописи наград.",
            link_url="/achievements",
            entity_type="achievement",
            entity_id=achievement.id,
            commit=False,
        )
        
        db.commit()
        db.refresh(user_achievement)
        
        return user_achievement
    
    def get_achievement_progress_summary(self, db: Session, user_id: int):
        """Получить сводку по прогрессу достижений"""
        all_achievements = self.achievement_repo.get_available_achievements(db)
        user_achievements = self.get_user_achievements(db, user_id)
        
        completed_count = len([ua for ua in user_achievements if ua.is_completed])
        total_count = len(all_achievements)
        total_points = sum(
            (ua.achievement.points or 0)
            for ua in user_achievements
            if ua.is_completed and ua.achievement
        )
        
        return {
            "total_achievements": total_count,
            "completed_achievements": completed_count,
            "total_points": total_points,
            "completion_percentage": (completed_count / total_count * 100) if total_count > 0 else 0
        } 
