#!/usr/bin/env python3
"""
Скрипт для замены всех упоминаний фракции "Goblins" на "Мглистые Горы" в базе данных.
Это необходимо, так как фракции "Гоблины" не существует в игре.
"""

import sys
import os
from sqlalchemy.orm import Session
from sqlalchemy import text

# Добавляем путь к корневой директории проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.match import Match

def fix_goblins_to_misty_mountains():
    """
    Заменяет все упоминания фракции "Goblins" на "Мглистые Горы" в таблице matches.
    """
    db = SessionLocal()
    try:
        # Подсчитываем количество записей для замены
        goblins_count = db.query(Match).filter(
            (Match.winner_faction == "Goblins") | (Match.loser_faction == "Goblins")
        ).count()
        
        print(f"Найдено {goblins_count} записей с фракцией 'Goblins'")
        
        if goblins_count == 0:
            print("Записи с фракцией 'Goblins' не найдены.")
            return
        
        # Обновляем записи с winner_faction = "Goblins"
        winner_updates = db.query(Match).filter(Match.winner_faction == "Goblins").update(
            {"winner_faction": "Мглистые Горы"}
        )
        
        # Обновляем записи с loser_faction = "Goblins"
        loser_updates = db.query(Match).filter(Match.loser_faction == "Goblins").update(
            {"loser_faction": "Мглистые Горы"}
        )
        
        # Подтверждаем изменения
        db.commit()
        
        print(f"Успешно обновлено:")
        print(f"  - winner_faction: {winner_updates} записей")
        print(f"  - loser_faction: {loser_updates} записей")
        print(f"  - Всего обновлено: {winner_updates + loser_updates} записей")
        
        # Проверяем результат
        remaining_goblins = db.query(Match).filter(
            (Match.winner_faction == "Goblins") | (Match.loser_faction == "Goblins")
        ).count()
        
        if remaining_goblins == 0:
            print("✅ Все упоминания 'Goblins' успешно заменены на 'Мглистые Горы'")
        else:
            print(f"⚠️  Осталось {remaining_goblins} записей с 'Goblins'")
            
    except Exception as e:
        print(f"Ошибка при обновлении данных: {e}")
        db.rollback()
    finally:
        db.close()

def show_statistics():
    """
    Показывает статистику по фракциям в базе данных.
    """
    db = SessionLocal()
    try:
        print("\n=== Статистика по фракциям ===")
        
        # Статистика по победителям
        winner_stats = db.query(Match.winner_faction, db.func.count(Match.id)).group_by(Match.winner_faction).all()
        print("\nПобедители по фракциям:")
        for faction, count in sorted(winner_stats, key=lambda x: x[1], reverse=True):
            print(f"  {faction}: {count}")
        
        # Статистика по проигравшим
        loser_stats = db.query(Match.loser_faction, db.func.count(Match.id)).group_by(Match.loser_faction).all()
        print("\nПроигравшие по фракциям:")
        for faction, count in sorted(loser_stats, key=lambda x: x[1], reverse=True):
            print(f"  {faction}: {count}")
            
    except Exception as e:
        print(f"Ошибка при получении статистики: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    print("=== Скрипт замены фракции 'Goblins' на 'Мглистые Горы' ===\n")
    
    # Показываем текущую статистику
    show_statistics()
    
    # Выполняем замену
    print("\n" + "="*50)
    fix_goblins_to_misty_mountains()
    
    # Показываем статистику после изменений
    print("\n" + "="*50)
    show_statistics() 