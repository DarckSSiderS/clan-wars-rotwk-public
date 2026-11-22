import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta

def test_moscow_time():
    """Тестирование московского времени"""
    
    print("🕐 Тестирование московского времени (UTC+3)")
    print("=" * 50)
    
    # Текущее время в UTC
    now_utc = datetime.utcnow()
    print(f"Текущее время UTC: {now_utc}")
    
    # Московское время (UTC+3)
    now_moscow = now_utc + timedelta(hours=3)
    print(f"Текущее время МСК: {now_moscow}")
    
    print("\n📅 Тестирование ежедневных заданий:")
    print("-" * 30)
    
    # Ежедневные задания истекают в 23:59:59 по московскому времени
    expires_at_moscow = now_moscow.replace(hour=23, minute=59, second=59, microsecond=999999)
    expires_at_utc = expires_at_moscow - timedelta(hours=3)
    
    print(f"Время истечения МСК: {expires_at_moscow}")
    print(f"Время истечения UTC: {expires_at_utc}")
    
    # Вычисляем время до истечения
    time_diff = expires_at_moscow - now_moscow
    total_seconds = int(time_diff.total_seconds())
    
    if total_seconds > 0:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        print(f"Осталось времени: {hours}ч {minutes}м")
    else:
        print("Задание истекло")
    
    print("\n📅 Тестирование еженедельных заданий:")
    print("-" * 30)
    
    # Еженедельные задания истекают в воскресенье в 23:59:59 по московскому времени
    days_until_sunday = (6 - now_moscow.weekday()) % 7
    expires_at_moscow_weekly = now_moscow + timedelta(days=days_until_sunday)
    expires_at_moscow_weekly = expires_at_moscow_weekly.replace(hour=23, minute=59, second=59, microsecond=999999)
    expires_at_utc_weekly = expires_at_moscow_weekly - timedelta(hours=3)
    
    print(f"Дней до воскресенья: {days_until_sunday}")
    print(f"Время истечения МСК: {expires_at_moscow_weekly}")
    print(f"Время истечения UTC: {expires_at_utc_weekly}")
    
    # Вычисляем время до истечения
    time_diff_weekly = expires_at_moscow_weekly - now_moscow
    total_seconds_weekly = int(time_diff_weekly.total_seconds())
    
    if total_seconds_weekly > 0:
        days = total_seconds_weekly // 86400
        remaining_seconds = total_seconds_weekly % 86400
        hours = remaining_seconds // 3600
        print(f"Осталось времени: {days}д {hours}ч")
    else:
        print("Задание истекло")
    
    print("\n✅ Тест завершен!")

if __name__ == "__main__":
    test_moscow_time() 