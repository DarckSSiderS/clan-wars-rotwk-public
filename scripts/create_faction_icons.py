#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Создание уникальных иконок для фракций
"""

import shutil
from pathlib import Path

# Создаем папку для иконок фракций
icons_dir = Path('frontend/public/icons/factions')
icons_dir.mkdir(parents=True, exist_ok=True)

# Копируем существующие иконки и создаем уникальные для каждой фракции
faction_icons = {
    'gondor': 'sauronwb.png',        # Белая башня Гондора
    'rohan': 'axeswb.png',           # Топоры Рохана
    'isengard': 'towerwb.png',       # Башня Изенгарда
    'mordor': 'sauroneyewb.png',     # Глаз Саурона
    'angmar': 'orcwb.png',           # Орки Ангмара
    'misty_mountains': 'ennorathtvwb.png', # Гномы Мглистых Гор
    'lothlorien': 'ennorathtvwb.png', # Эльфы Лотлориэна
    'imladris': 'ennorathtvwb.png',  # Эльфы Имладриса
    'arnor': 'sauronwb.png',         # Королевство Арнор
    'harad': 'sauroneyewb.png'       # Воины Харада
}

source_dir = Path('frontend/public/icons')

print("Создание иконок фракций...")

for faction, source_icon in faction_icons.items():
    source_path = source_dir / source_icon
    target_path = icons_dir / f"{faction}.png"
    
    if source_path.exists():
        shutil.copy2(source_path, target_path)
        print(f"✅ Создана иконка для {faction}: {source_icon}")
    else:
        print(f"❌ Исходная иконка не найдена: {source_icon}")

print("Создание иконок завершено!") 