def test_level_system():
    """Тестирование системы уровней"""
    
    # Система уровней из QuestService
    level_experience_requirements = {
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
    
    def get_level_experience_requirement(level):
        if level in level_experience_requirements:
            return level_experience_requirements[level]
        # Для уровней выше 10 используем формулу
        return 27000 + (level - 10) * 6000
    
    def calculate_level_from_experience(experience):
        for level in range(1, 100):  # Максимум 100 уровень
            required_exp = get_level_experience_requirement(level)
            if experience < required_exp:
                return level - 1
        return 100
    
    def calculate_experience_progress(level, experience):
        # Опыт для текущего уровня
        current_level_exp = get_level_experience_requirement(level)
        # Опыт для следующего уровня
        next_level_exp = get_level_experience_requirement(level + 1)
        # Опыт, накопленный на текущем уровне
        current_level_progress = experience - current_level_exp
        # Максимальный опыт для текущего уровня
        max_level_progress = next_level_exp - current_level_exp
        
        percentage = min((current_level_progress / max_level_progress) * 100, 100)
        
        return {
            'current': current_level_progress,
            'max': max_level_progress,
            'percentage': round(percentage)
        }
    
    # Тестируем игрока Zira_aa
    print("🔍 Тестирование системы уровней для Zira_aa")
    print(f"Уровень: 2")
    print(f"Опыт: 1001")
    
    # Проверяем правильность уровня
    calculated_level = calculate_level_from_experience(1001)
    print(f"Рассчитанный уровень: {calculated_level}")
    
    # Проверяем прогресс
    progress = calculate_experience_progress(2, 1001)
    print(f"Прогресс: {progress['current']} / {progress['max']} опыта ({progress['percentage']}%)")
    
    # Проверяем несколько уровней
    print("\n📊 Таблица уровней:")
    for level in range(1, 11):
        required_exp = get_level_experience_requirement(level)
        print(f"Уровень {level}: {required_exp} опыта")
    
    # Тестируем разные значения опыта
    print("\n🧪 Тестирование разных значений опыта:")
    test_experiences = [0, 500, 1000, 1500, 2500, 5000, 10000, 15000]
    
    for exp in test_experiences:
        level = calculate_level_from_experience(exp)
        progress = calculate_experience_progress(level, exp)
        print(f"Опыт {exp} -> Уровень {level} -> Прогресс: {progress['current']}/{progress['max']} ({progress['percentage']}%)")

if __name__ == "__main__":
    test_level_system() 