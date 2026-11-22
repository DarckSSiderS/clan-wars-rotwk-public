#!/usr/bin/env python3
"""
Скрипт для инициализации тестовых данных
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.database import SessionLocal, Base, engine
from app.models import User, Clan, ClanMember, ClanInvite, ClanApplication
from app.core.security import get_password_hash
from app.config import settings

def init_test_data():
    """Инициализация тестовых данных"""
    db = SessionLocal()
    
    try:
        # Очищаем существующие данные
        print("Очистка существующих данных...")
        db.query(ClanApplication).delete()
        db.query(ClanInvite).delete()
        db.query(ClanMember).delete()
        db.query(Clan).delete()
        db.query(User).delete()
        db.commit()
        
        print("Создание пользователей...")
        
        # Создаем пользователей
        users_data = [
            {
                "username": "admin",
                "email": "admin@example.com",
                "hashed_password": get_password_hash("admin"),
                "is_active": True,
                "balance": 1000,
                "level": 10,
                "experience": 5000
            },
            {
                "username": "warrior",
                "email": "warrior@example.com",
                "hashed_password": get_password_hash("warrior123"),
                "is_active": True,
                "balance": 500,
                "level": 8,
                "experience": 3200
            },
            {
                "username": "mage",
                "email": "mage@example.com",
                "hashed_password": get_password_hash("mage123"),
                "is_active": True,
                "balance": 750,
                "level": 9,
                "experience": 4100
            },
            {
                "username": "archer",
                "email": "archer@example.com",
                "hashed_password": get_password_hash("archer123"),
                "is_active": True,
                "balance": 300,
                "level": 7,
                "experience": 2800
            },
            {
                "username": "tank",
                "email": "tank@example.com",
                "hashed_password": get_password_hash("tank123"),
                "is_active": True,
                "balance": 200,
                "level": 6,
                "experience": 2200
            },
            {
                "username": "healer",
                "email": "healer@example.com",
                "hashed_password": get_password_hash("healer123"),
                "is_active": True,
                "balance": 400,
                "level": 8,
                "experience": 3500
            },
            {
                "username": "rogue",
                "email": "rogue@example.com",
                "hashed_password": get_password_hash("rogue123"),
                "is_active": True,
                "balance": 600,
                "level": 9,
                "experience": 3800
            },
            {
                "username": "paladin",
                "email": "paladin@example.com",
                "hashed_password": get_password_hash("paladin123"),
                "is_active": True,
                "balance": 800,
                "level": 10,
                "experience": 4800
            }
        ]
        
        users = []
        for user_data in users_data:
            user = User(**user_data)
            db.add(user)
            users.append(user)
        
        db.commit()
        
        # Получаем ID пользователей
        admin = db.query(User).filter(User.username == "admin").first()
        warrior = db.query(User).filter(User.username == "warrior").first()
        mage = db.query(User).filter(User.username == "mage").first()
        archer = db.query(User).filter(User.username == "archer").first()
        tank = db.query(User).filter(User.username == "tank").first()
        healer = db.query(User).filter(User.username == "healer").first()
        rogue = db.query(User).filter(User.username == "rogue").first()
        paladin = db.query(User).filter(User.username == "paladin").first()
        
        print("Создание кланов...")
        
        # Создаем кланы
        clans_data = [
            {
                "name": "Легион Тьмы",
                "description": "Элитный клан темных воинов, специализирующихся на ближнем бою и тактике",
                "leader_id": warrior.id,
                "avatar_url": None,
                "level": 15,
                "experience": 25000,
                "max_members": 20
            },
            {
                "name": "Орден Света",
                "description": "Благородный орден паладинов, защитников справедливости и добра",
                "leader_id": paladin.id,
                "avatar_url": None,
                "level": 12,
                "experience": 18000,
                "max_members": 15
            },
            {
                "name": "Гильдия Магов",
                "description": "Сообщество могущественных магов, изучающих древние искусства",
                "leader_id": mage.id,
                "avatar_url": None,
                "level": 18,
                "experience": 32000,
                "max_members": 12
            },
            {
                "name": "Братство Лучников",
                "description": "Клан опытных лучников и разведчиков, мастеров дальнего боя",
                "leader_id": archer.id,
                "avatar_url": None,
                "level": 10,
                "experience": 15000,
                "max_members": 18
            }
        ]
        
        clans = []
        for clan_data in clans_data:
            clan = Clan(**clan_data)
            db.add(clan)
            clans.append(clan)
        
        db.commit()
        
        # Получаем кланы
        legion = db.query(Clan).filter(Clan.name == "Легион Тьмы").first()
        order = db.query(Clan).filter(Clan.name == "Орден Света").first()
        guild = db.query(Clan).filter(Clan.name == "Гильдия Магов").first()
        brotherhood = db.query(Clan).filter(Clan.name == "Братство Лучников").first()
        
        print("Добавление участников в кланы...")
        
        # Добавляем участников в кланы
        members_data = [
            # Легион Тьмы
            {"user_id": warrior.id, "clan_id": legion.id, "rank": "Лидер", "joined_at": func.now()},
            {"user_id": tank.id, "clan_id": legion.id, "rank": "Участник", "joined_at": func.now()},
            {"user_id": rogue.id, "clan_id": legion.id, "rank": "Участник", "joined_at": func.now()},
            
            # Орден Света
            {"user_id": paladin.id, "clan_id": order.id, "rank": "Лидер", "joined_at": func.now()},
            {"user_id": healer.id, "clan_id": order.id, "rank": "Участник", "joined_at": func.now()},
            
            # Гильдия Магов
            {"user_id": mage.id, "clan_id": guild.id, "rank": "Лидер", "joined_at": func.now()},
            
            # Братство Лучников
            {"user_id": archer.id, "clan_id": brotherhood.id, "rank": "Лидер", "joined_at": func.now()}
        ]
        
        for member_data in members_data:
            member = ClanMember(**member_data)
            db.add(member)
        
        db.commit()
        
        print("Создание приглашений...")
        
        # Создаем приглашения
        invites_data = [
            {
                "clan_id": legion.id,
                "inviter_id": warrior.id,
                "invitee_id": admin.id,
                "message": "Присоединяйся к Легиону Тьмы! Нам нужен сильный лидер."
            },
            {
                "clan_id": order.id,
                "inviter_id": paladin.id,
                "invitee_id": admin.id,
                "message": "Орден Света приглашает тебя стать частью нашего братства."
            }
        ]
        
        for invite_data in invites_data:
            invite = ClanInvite(**invite_data)
            db.add(invite)
        
        db.commit()
        
        print("Создание заявок...")
        
        # Создаем заявки
        applications_data = [
            {
                "clan_id": guild.id,
                "user_id": admin.id,
                "message": "Хочу присоединиться к Гильдии Магов и изучать древние искусства."
            },
            {
                "clan_id": brotherhood.id,
                "user_id": admin.id,
                "message": "Прошу принять меня в Братство Лучников. Имею опыт в стрельбе из лука."
            }
        ]
        
        for application_data in applications_data:
            application = ClanApplication(**application_data)
            db.add(application)
        
        db.commit()
        
        print("✅ Тестовые данные успешно созданы!")
        print("\n📋 Созданные пользователи:")
        for user in users:
            print(f"  - {user.username} (уровень {user.level}, баланс {user.balance})")
        
        print("\n🏰 Созданные кланы:")
        for clan in clans:
            print(f"  - {clan.name} (лидер: {clan.leader.username}, уровень {clan.level})")
        
        print("\n🔑 Учетные данные для входа:")
        print("  admin/admin")
        print("  warrior/warrior123")
        print("  mage/mage123")
        print("  archer/archer123")
        print("  tank/tank123")
        print("  healer/healer123")
        print("  rogue/rogue123")
        print("  paladin/paladin123")
        
    except Exception as e:
        print(f"❌ Ошибка при создании тестовых данных: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    init_test_data() 
