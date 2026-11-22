from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from app.models.quest import Quest, UserQuest, QuestType, QuestCategory
from app.models.user import User
from app.models.match import Match

class QuestService:
    
    def __init__(self):
        self.level_experience_requirements = {
            1: 0,
            2: 1000,
            3: 2500,
            4: 4500,
            5: 7000,
            6: 10000,
            7: 13500,
            8: 17500,
            9: 22000,
            10: 27000
        }
    
    def get_level_experience_requirement(self, level: int) -> int:
        """Получить требуемый опыт для уровня"""
        if level in self.level_experience_requirements:
            return self.level_experience_requirements[level]
        # Для уровней выше 10 используем формулу
        return 27000 + (level - 10) * 6000
    
    def calculate_level_from_experience(self, experience: int) -> int:
        """Вычислить уровень на основе опыта"""
        for level in range(1, 100):  # Максимум 100 уровень
            required_exp = self.get_level_experience_requirement(level)
            if experience < required_exp:
                return level - 1
        return 100
    
    def add_experience_to_user(self, db: Session, user_id: int, experience: int) -> Dict:
        """Добавить опыт пользователю и обновить уровень"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        
        old_level = user.level
        user.experience += experience
        new_level = self.calculate_level_from_experience(user.experience)
        user.level = new_level
        
        db.commit()
        db.refresh(user)
        
        return {
            "old_level": old_level,
            "new_level": new_level,
            "experience_gained": experience,
            "total_experience": user.experience,
            "level_up": new_level > old_level
        }
    
    def add_coins_to_user(self, db: Session, user_id: int, coins: int) -> int:
        """Добавить монеты пользователю"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        
        user.balance += coins
        db.commit()
        db.refresh(user)
        
        return user.balance
    
    def get_quests(self, db: Session, quest_type: Optional[QuestType] = None) -> List[Quest]:
        """Получить список заданий"""
        query = db.query(Quest).filter(Quest.is_active == True)
        if quest_type:
            query = query.filter(Quest.quest_type == quest_type)
        return query.all()

    def _get_rotation_quests(self, db: Session, quest_type: QuestType, slots: int = 6) -> List[Quest]:
        """Expose a small rotating selection while keeping a larger quest catalog."""
        quests = self.get_quests(db, quest_type)
        if len(quests) <= slots:
            return quests
        now = datetime.utcnow()
        if quest_type == QuestType.DAILY:
            rotation = now.date().toordinal()
        else:
            rotation = now.date().toordinal() // 7
        start = rotation % len(quests)
        return [quests[(start + offset) % len(quests)] for offset in range(slots)]
    
    def get_user_quests(self, db: Session, user_id: int, quest_type: Optional[QuestType] = None) -> List[UserQuest]:
        """Получить задания пользователя"""
        query = db.query(UserQuest).filter(
            and_(
                UserQuest.user_id == user_id,
                UserQuest.expires_at > datetime.utcnow()
            )
        )
        if quest_type:
            query = query.join(Quest).filter(Quest.quest_type == quest_type)
        return query.all()
    
    def create_user_quest(self, db: Session, user_id: int, quest_id: int) -> UserQuest:
        """Создать задание для пользователя"""
        quest = db.query(Quest).filter(Quest.id == quest_id).first()
        if not quest:
            return None
        
        # Определяем время истечения
        now_utc = datetime.utcnow()
        now_moscow = now_utc + timedelta(hours=3)  # Московское время (UTC+3)
        
        if quest.quest_type == QuestType.DAILY:
            # Ежедневные задания истекают в 00:00:00 по московскому времени следующего дня
            tomorrow_moscow = now_moscow + timedelta(days=1)
            expires_at_moscow = tomorrow_moscow.replace(hour=0, minute=0, second=0, microsecond=0)
            # Конвертируем обратно в UTC
            expires_at = expires_at_moscow - timedelta(hours=3)
        else:  # WEEKLY
            # Еженедельные задания истекают в следующее воскресенье в 00:00:00 по московскому времени
            days_until_sunday = (6 - now_moscow.weekday()) % 7
            if days_until_sunday == 0:  # Если сегодня воскресенье
                days_until_sunday = 7  # Истекает в следующее воскресенье
            next_sunday_moscow = now_moscow + timedelta(days=days_until_sunday)
            expires_at_moscow = next_sunday_moscow.replace(hour=0, minute=0, second=0, microsecond=0)
            # Конвертируем обратно в UTC
            expires_at = expires_at_moscow - timedelta(hours=3)
        
        user_quest = UserQuest(
            user_id=user_id,
            quest_id=quest_id,
            expires_at=expires_at
        )
        
        db.add(user_quest)
        db.commit()
        db.refresh(user_quest)
        
        return user_quest
    
    def assign_daily_quests(self, db: Session, user_id: int) -> List[UserQuest]:
        """Назначить ежедневные задания пользователю"""
        # Получаем активные ежедневные задания
        daily_quests = self._get_rotation_quests(db, QuestType.DAILY)
        
        assigned_quests = []
        for quest in daily_quests:
            # Проверяем, есть ли уже такое задание у пользователя
            existing = db.query(UserQuest).filter(
                and_(
                    UserQuest.user_id == user_id,
                    UserQuest.quest_id == quest.id,
                    UserQuest.expires_at > datetime.utcnow()
                )
            ).first()
            
            if not existing:
                user_quest = self.create_user_quest(db, user_id, quest.id)
                if user_quest:
                    assigned_quests.append(user_quest)
        
        return assigned_quests
    
    def assign_weekly_quests(self, db: Session, user_id: int) -> List[UserQuest]:
        """Назначить еженедельные задания пользователю"""
        # Получаем активные еженедельные задания
        weekly_quests = self._get_rotation_quests(db, QuestType.WEEKLY)
        
        assigned_quests = []
        for quest in weekly_quests:
            # Проверяем, есть ли уже такое задание у пользователя
            existing = db.query(UserQuest).filter(
                and_(
                    UserQuest.user_id == user_id,
                    UserQuest.quest_id == quest.id,
                    UserQuest.expires_at > datetime.utcnow()
                )
            ).first()
            
            if not existing:
                user_quest = self.create_user_quest(db, user_id, quest.id)
                if user_quest:
                    assigned_quests.append(user_quest)
        
        return assigned_quests
    
    def claim_quest_reward(self, db: Session, user_id: int, quest_id: int) -> Optional[Dict]:
        """Получить награду за задание"""
        user_quest = (
            db.query(UserQuest)
            .filter(
                and_(
                    UserQuest.user_id == user_id,
                    UserQuest.quest_id == quest_id,
                    UserQuest.is_completed.is_(True),
                    UserQuest.is_claimed.is_(False),
                    UserQuest.expires_at > datetime.utcnow(),
                )
            )
            .with_for_update()
            .first()
        )
        
        if not user_quest:
            return None
        
        quest = user_quest.quest
        user = db.query(User).filter(User.id == user_id).with_for_update().first()
        if not user:
            return None

        old_level = user.level
        user.balance += quest.reward_coins
        user.experience += quest.reward_experience
        user.level = self.calculate_level_from_experience(user.experience)
        user_quest.is_claimed = True
        db.commit()
        db.refresh(user)
        
        return {
            "quest_id": quest.id,
            "quest_title": quest.title_key,
            "coins_earned": quest.reward_coins,
            "experience_earned": quest.reward_experience,
            "new_balance": user.balance,
            "level_info": {
                "old_level": old_level,
                "new_level": user.level,
                "experience_gained": quest.reward_experience,
                "total_experience": user.experience,
                "level_up": user.level > old_level,
            },
        }

    def update_user_quest_progress(self, db: Session, user_id: int, username: str) -> List[Dict]:
        """Обновить прогресс заданий пользователя на основе матчей"""
        # Получаем активные задания пользователя (не завершенные)
        user_quests = db.query(UserQuest).filter(
            and_(
                UserQuest.user_id == user_id,
                UserQuest.expires_at > datetime.utcnow(),
                UserQuest.is_completed.is_(False)
            )
        ).all()
        
        if not user_quests:
            return []
        
        # Получаем статистику за сегодня
        today = datetime.utcnow().date()
        today_matches = db.query(Match).filter(
            and_(
                (Match.winner_player == username) | (Match.loser_player == username),
                func.date(Match.match_date) == today
            )
        ).order_by(Match.match_date).all()
        
        if not today_matches:
            return []
        
        # Подсчитываем статистику
        total_matches = len(today_matches)
        wins = sum(1 for match in today_matches if match.winner_player == username)
        
        # Для серии побед
        current_streak = 0
        max_streak = 0
        for match in today_matches:
            if match.winner_player == username:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        
        completed_quests = []
        dirty = False
        
        # Обновляем прогресс для каждого задания
        for user_quest in user_quests:
            quest = user_quest.quest
            updated = False
            
            if quest.category == QuestCategory.WINS:
                if user_quest.current_progress != wins:
                    user_quest.current_progress = wins
                    updated = True
            
            elif quest.category == QuestCategory.MATCHES_PLAYED:
                if user_quest.current_progress != total_matches:
                    user_quest.current_progress = total_matches
                    updated = True
            
            elif quest.category == QuestCategory.STREAK:
                if user_quest.current_progress != max_streak:
                    user_quest.current_progress = max_streak
                    updated = True
            
            if updated:
                dirty = True

            # Проверяем, завершено ли задание
            if updated and user_quest.current_progress >= quest.target_value:
                user_quest.is_completed = True
                user_quest.completed_at = datetime.utcnow()
                
                completed_quests.append({
                    "quest_id": quest.id,
                    "quest_title": quest.title_key,
                    "category": quest.category.value,
                    "target_value": quest.target_value,
                    "current_progress": user_quest.current_progress
                })
        
        if dirty:
            db.commit()
        
        return completed_quests

    def update_quest_progress(self, db: Session, user_id: int) -> List[Dict]:
        """Обновить прогресс всех активных заданий пользователя"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return []
        
        # Получаем активные задания пользователя
        user_quests = db.query(UserQuest).filter(
            and_(
                UserQuest.user_id == user_id,
                UserQuest.expires_at > datetime.utcnow(),
                UserQuest.is_claimed.is_(False),
            )
        ).all()
        
        if not user_quests:
            return []
        
        # Границы московских суток храним и сравниваем в UTC.
        now_utc = datetime.utcnow()
        now_moscow = now_utc + timedelta(hours=3)
        today_start = (
            now_moscow.replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(hours=3)
        )
        today_end = today_start + timedelta(days=1)
        
        # Начало недели для еженедельных заданий
        week_start = today_start - timedelta(days=today_start.weekday())
        
        completed_quests = []
        dirty = False
        
        for user_quest in user_quests:
            quest = user_quest.quest
            updated = False
            
            if quest.quest_type == QuestType.DAILY:
                # Статистика за сегодня
                today_wins = db.query(Match).filter(
                    and_(
                        Match.winner_player == user.username,
                        Match.match_date >= today_start,
                        Match.match_date < today_end
                    )
                ).count()
                
                today_losses = db.query(Match).filter(
                    and_(
                        Match.loser_player == user.username,
                        Match.match_date >= today_start,
                        Match.match_date < today_end
                    )
                ).count()
                
                today_total = today_wins + today_losses
                
                if quest.category == QuestCategory.WINS:
                    if user_quest.current_progress != today_wins:
                        user_quest.current_progress = today_wins
                        updated = True
                elif quest.category == QuestCategory.MATCHES_PLAYED:
                    if user_quest.current_progress != today_total:
                        user_quest.current_progress = today_total
                        updated = True
                elif quest.category == QuestCategory.STREAK:
                    # Для серии побед считаем максимальную серию за сегодня
                    today_matches = db.query(Match).filter(
                        and_(
                            (Match.winner_player == user.username) | (Match.loser_player == user.username),
                            Match.match_date >= today_start,
                            Match.match_date < today_end
                        )
                    ).order_by(Match.match_date).all()
                    
                    current_streak = 0
                    max_streak = 0
                    for match in today_matches:
                        if match.winner_player == user.username:
                            current_streak += 1
                            max_streak = max(max_streak, current_streak)
                        else:
                            current_streak = 0
                    
                    if user_quest.current_progress != max_streak:
                        user_quest.current_progress = max_streak
                        updated = True
            
            elif quest.quest_type == QuestType.WEEKLY:
                # Статистика за неделю
                week_wins = db.query(Match).filter(
                    and_(
                        Match.winner_player == user.username,
                        Match.match_date >= week_start,
                        Match.match_date < today_end
                    )
                ).count()
                
                week_losses = db.query(Match).filter(
                    and_(
                        Match.loser_player == user.username,
                        Match.match_date >= week_start,
                        Match.match_date < today_end
                    )
                ).count()
                
                week_total = week_wins + week_losses
                
                if quest.category == QuestCategory.WINS:
                    if user_quest.current_progress != week_wins:
                        user_quest.current_progress = week_wins
                        updated = True
                elif quest.category == QuestCategory.MATCHES_PLAYED:
                    if user_quest.current_progress != week_total:
                        user_quest.current_progress = week_total
                        updated = True
                elif quest.category == QuestCategory.STREAK:
                    # Для серии побед считаем максимальную серию за неделю
                    week_matches = db.query(Match).filter(
                        and_(
                            (Match.winner_player == user.username) | (Match.loser_player == user.username),
                            Match.match_date >= week_start,
                            Match.match_date < today_end
                        )
                    ).order_by(Match.match_date).all()
                    
                    current_streak = 0
                    max_streak = 0
                    for match in week_matches:
                        if match.winner_player == user.username:
                            current_streak += 1
                            max_streak = max(max_streak, current_streak)
                        else:
                            current_streak = 0
                    
                    if user_quest.current_progress != max_streak:
                        user_quest.current_progress = max_streak
                        updated = True
            
            if updated:
                dirty = True

            # Проверяем, завершено ли задание
            if user_quest.current_progress >= quest.target_value and not user_quest.is_completed:
                user_quest.is_completed = True
                user_quest.completed_at = datetime.utcnow()
                dirty = True
                completed_quests.append({
                    "quest_id": quest.id,
                    "quest_title": quest.title_key,
                    "category": quest.category.value,
                    "target_value": quest.target_value,
                    "current_progress": user_quest.current_progress
                })
        
        if dirty:
            db.commit()
        
        return completed_quests

    def update_quest_progress_summary(self, db: Session, user_id: int) -> Dict:
        """Update quest progress and return the API-facing change summary.

        Keeping this orchestration in the service prevents API routes from
        implementing their own day boundaries and quest completion rules.
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {
                "active_count": 0,
                "updated_count": 0,
                "completed_count": 0,
                "completed_quests": [],
                "stats": {"total_matches": 0, "wins": 0},
            }

        active_quests = db.query(UserQuest).filter(
            and_(
                UserQuest.user_id == user_id,
                UserQuest.expires_at > datetime.utcnow(),
                UserQuest.is_claimed.is_(False),
            )
        ).all()
        previous_state = {
            user_quest.id: (user_quest.current_progress, user_quest.is_completed)
            for user_quest in active_quests
        }

        completed_quests = self.update_quest_progress(db, user_id)

        now_utc = datetime.utcnow()
        now_moscow = now_utc + timedelta(hours=3)
        today_start = (
            now_moscow.replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(hours=3)
        )
        today_end = today_start + timedelta(days=1)
        today_matches = db.query(Match).filter(
            and_(
                (Match.winner_player == user.username)
                | (Match.loser_player == user.username),
                Match.match_date >= today_start,
                Match.match_date < today_end,
            )
        ).all()

        updated_count = sum(
            previous_state[user_quest.id]
            != (user_quest.current_progress, user_quest.is_completed)
            for user_quest in active_quests
        )
        return {
            "active_count": len(active_quests),
            "updated_count": updated_count,
            "completed_count": len(completed_quests),
            "completed_quests": completed_quests,
            "stats": {
                "total_matches": len(today_matches),
                "wins": sum(
                    match.winner_player == user.username
                    for match in today_matches
                ),
            },
        }

    def reset_expired_quests(self, db: Session, user_id: int) -> List[UserQuest]:
        """Сбросить истекшие задания и создать новые"""
        now = datetime.utcnow()
        
        # Удаляем истекшие задания
        expired_quests = db.query(UserQuest).filter(
            and_(
                UserQuest.user_id == user_id,
                UserQuest.expires_at <= now
            )
        ).all()
        
        for expired_quest in expired_quests:
            db.delete(expired_quest)
        
        # Проверяем, есть ли активные задания
        active_daily_quests = db.query(UserQuest).join(Quest).filter(
            and_(
                UserQuest.user_id == user_id,
                Quest.quest_type == QuestType.DAILY,
                UserQuest.expires_at > now
            )
        ).count()
        
        active_weekly_quests = db.query(UserQuest).join(Quest).filter(
            and_(
                UserQuest.user_id == user_id,
                Quest.quest_type == QuestType.WEEKLY,
                UserQuest.expires_at > now
            )
        ).count()
        
        # Держим полный ротационный набор, включая пользователей старого формата.
        new_daily_quests = []
        new_weekly_quests = []

        if active_daily_quests < 6:
            new_daily_quests = self.assign_daily_quests(db, user_id)

        if active_weekly_quests < 6:
            new_weekly_quests = self.assign_weekly_quests(db, user_id)
        
        db.commit()
        
        return new_daily_quests + new_weekly_quests 
