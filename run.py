#!/usr/bin/env python3
"""
Запуск приложения ClanWar
"""

import uvicorn
from app.config import settings

if __name__ == "__main__":
    print("🚀 Запуск ClanWar на 0.0.0.0:8000")
    print(f"📝 Режим отладки: {'Включен' if settings.DEBUG else 'Выключен'}")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info",
        access_log=False,
    )
