from datetime import datetime, timedelta

def test_moscow_time_logic():
    """Тестирование логики московского времени"""
    
    print("🕐 Тестирование логики московского времени")
    print("=" * 50)
    
    # Симулируем разные времена дня
    test_times = [
        datetime(2025, 8, 28, 10, 0, 0),  # 10:00 UTC (13:00 МСК)
        datetime(2025, 8, 28, 20, 0, 0),  # 20:00 UTC (23:00 МСК)
        datetime(2025, 8, 28, 23, 0, 0),  # 23:00 UTC (02:00 МСК следующего дня)
    ]
    
    for i, test_time in enumerate(test_times, 1):
        print(f"\n📅 Тест {i}: {test_time} UTC")
        print("-" * 30)
        
        # Московское время
        moscow_time = test_time + timedelta(hours=3)
        print(f"Московское время: {moscow_time}")
        
        # Ежедневные задания истекают в 23:59:59 по московскому времени
        expires_at_moscow = moscow_time.replace(hour=23, minute=59, second=59, microsecond=999999)
        expires_at_utc = expires_at_moscow - timedelta(hours=3)
        
        print(f"Истекает МСК: {expires_at_moscow}")
        print(f"Истекает UTC: {expires_at_utc}")
        
        # Вычисляем время до истечения
        time_diff = expires_at_moscow - moscow_time
        total_seconds = int(time_diff.total_seconds())
        
        if total_seconds > 0:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            print(f"Осталось: {hours}ч {minutes}м")
        else:
            print("Истекло")
    
    print("\n✅ Тест завершен!")

if __name__ == "__main__":
    test_moscow_time_logic() 