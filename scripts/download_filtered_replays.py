#!/usr/bin/env python3
"""
Скрипт для загрузки полных данных с API /api/replays и дополнения существующих матчей
новой информацией, не заменяя уже существующие поля.
"""

import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional
import logging

# Добавляем путь к корневой директории проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.match import Match

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ReplayDataUpdater:
    def __init__(self):
        self.api_url = "https://bfmeladder.com/api/replays"
        self.proxy = os.getenv("PROXY_URL")
        self.output_file = "ennorath_replays_with_full_data.json"
        
        # Целевой патч Ennorath
        self.target_patch = "1.9.6.7c"

    def filter_replay_by_patch(self, replay_data: Dict) -> bool:
        """
        Фильтрует реплеи по патчу Ennorath.
        """
        patch_name = replay_data.get('PatchName', '')
        patch_id = replay_data.get('PatchId', '')
        
        # Проверяем различные варианты названия патча Ennorath
        ennorath_indicators = [
            '1.9.6.7c',
            'Ennorath',
            'ennorath',
            '1.9.6'
        ]
        
        for indicator in ennorath_indicators:
            if indicator in patch_name or indicator in patch_id:
                return True
        
        return False

    def process_replay_data(self, replay_data: Dict) -> Optional[Dict]:
        """
        Обрабатывает данные реплея и создает структурированный объект.
        """
        try:
            # Если это строка, пытаемся распарсить как JSON
            if isinstance(replay_data, str):
                try:
                    replay_data = json.loads(replay_data)
                except json.JSONDecodeError:
                    logger.warning(f"Не удалось распарсить реплей как JSON: {replay_data[:100]}")
                    return None
            
            # Проверяем наличие необходимых полей
            if not replay_data.get('Players') or len(replay_data['Players']) < 2:
                return None
            
            # Фильтруем по патчу Ennorath
            if not self.filter_replay_by_patch(replay_data):
                return None
            
            # Находим победителя и проигравшего
            winner = None
            loser = None
            
            for player in replay_data['Players']:
                if player.get('IsWinner'):
                    winner = player
                else:
                    loser = player
            
            if not winner or not loser:
                return None
            
            # Создаем ссылку на скачивание реплея
            replay_id = replay_data.get('ReplayId', '')
            if replay_id:
                replay_download_url = f"https://bfmeladder.com/api/replays/download?replayId={replay_id}"
            else:
                replay_download_url = None
            
            # Создаем обработанный объект
            processed_replay = {
                'replay_id': replay_id,
                'arena_id': replay_data.get('ArenaId'),
                'patch_id': replay_data.get('PatchId'),
                'patch_name': replay_data.get('PatchName'),
                'game_name': replay_data.get('GameName'),
                'map_id': replay_data.get('MapId'),
                'map_name': replay_data.get('MapName'),
                'map_preview_source': replay_data.get('MapPreviewSource'),
                'gamemode_name': replay_data.get('GamemodeName'),
                'duration': replay_data.get('Duration'),
                'date': replay_data.get('Date'),
                'elo_delta': replay_data.get('EloDelta'),
                'downloads': replay_data.get('Downloads'),
                'likes': replay_data.get('Likes', []),
                'comments': replay_data.get('Comments', []),
                'replay_download_url': replay_download_url,
                'is_valid': replay_data.get('IsValid'),
                'is_qualification_round': replay_data.get('IsQualificationRound'),
                
                # Данные победителя
                'winner': {
                    'player_uuid': winner.get('PlayerAccountUuid'),
                    'faction_index': winner.get('FactionIndex'),
                    'faction_name': winner.get('FactionName'),
                    'faction_icon_source': winner.get('FactionIconSource'),
                    'team': winner.get('Team'),
                    'old_rank': winner.get('OldRank'),
                    'new_rank': winner.get('NewRank'),
                    'is_live': winner.get('IsLive', False)
                },
                
                # Данные проигравшего
                'loser': {
                    'player_uuid': loser.get('PlayerAccountUuid'),
                    'faction_index': loser.get('FactionIndex'),
                    'faction_name': loser.get('FactionName'),
                    'faction_icon_source': loser.get('FactionIconSource'),
                    'team': loser.get('Team'),
                    'old_rank': loser.get('OldRank'),
                    'new_rank': loser.get('NewRank'),
                    'is_live': loser.get('IsLive', False)
                }
            }
            
            return processed_replay
            
        except Exception as e:
            logger.error(f"Ошибка при обработке реплея: {e}")
            return None

    async def download_replays(self) -> List[Dict]:
        """
        Загружает данные с API через прокси.
        """
        connector = ProxyConnector.from_url(self.proxy) if self.proxy else aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            try:
                logger.info("Загружаем данные с %s", self.api_url)
                async with session.get(self.api_url) as response:
                    if response.status == 200:
                        text_data = await response.text()
                        logger.info(f"Получен ответ длиной {len(text_data)} символов")
                        
                        if not text_data.strip():
                            logger.error("Получен пустой ответ от API")
                            return []
                        
                        try:
                            data = json.loads(text_data)
                            logger.info(f"Загружено {len(data)} реплеев")
                            return data
                        except json.JSONDecodeError as e:
                            logger.error(f"Ошибка парсинга JSON: {e}")
                            return []
                    else:
                        logger.error(f"Ошибка при загрузке: {response.status}")
                        return []
            except Exception as e:
                logger.error(f"Ошибка при загрузке данных: {e}")
                return []

    def update_existing_matches(self, processed_replays: List[Dict]):
        """
        Дополняет существующие матчи в базе данных новой информацией из API.
        НЕ заменяет уже существующие поля.
        """
        db = SessionLocal()
        try:
            updated_count = 0
            not_found_count = 0
            
            for replay in processed_replays:
                replay_id = replay['replay_id']
                
                # Ищем существующий матч
                existing_match = db.query(Match).filter(Match.match_id == replay_id).first()
                
                if existing_match:
                    # Дополняем существующий матч новой информацией, НЕ заменяя существующие поля
                    
                    # Обновляем только пустые или отсутствующие поля
                    if not existing_match.arena_id:
                        existing_match.arena_id = replay['arena_id']
                    if not existing_match.patch_id:
                        existing_match.patch_id = replay['patch_id']
                    if not existing_match.patch_name:
                        existing_match.patch_name = replay['patch_name']
                    if not existing_match.game_name:
                        existing_match.game_name = replay['game_name']
                    if not existing_match.map_id:
                        existing_match.map_id = replay['map_id']
                    if not existing_match.map_preview_source:
                        existing_match.map_preview_source = replay['map_preview_source']
                    if not existing_match.gamemode_name:
                        existing_match.gamemode_name = replay['gamemode_name']
                    if not existing_match.elo_delta:
                        existing_match.elo_delta = replay['elo_delta']
                    if not existing_match.downloads:
                        existing_match.downloads = replay['downloads']
                    if not existing_match.likes:
                        existing_match.likes = json.dumps(replay['likes'])
                    if not existing_match.comments:
                        existing_match.comments = json.dumps(replay['comments'])
                    if not existing_match.replay_download_url:
                        existing_match.replay_download_url = replay['replay_download_url']
                    if existing_match.is_valid is None:
                        existing_match.is_valid = replay['is_valid']
                    if existing_match.is_qualification_round is None:
                        existing_match.is_qualification_round = replay['is_qualification_round']
                    
                    # Дополняем UUID и ранги игроков только если они пустые
                    if not existing_match.winner_player_uuid:
                        existing_match.winner_player_uuid = replay['winner']['player_uuid']
                    if not existing_match.loser_player_uuid:
                        existing_match.loser_player_uuid = replay['loser']['player_uuid']
                    if not existing_match.winner_faction_index:
                        existing_match.winner_faction_index = replay['winner']['faction_index']
                    if not existing_match.loser_faction_index:
                        existing_match.loser_faction_index = replay['loser']['faction_index']
                    if not existing_match.winner_old_rank:
                        existing_match.winner_old_rank = replay['winner']['old_rank']
                    if not existing_match.winner_new_rank:
                        existing_match.winner_new_rank = replay['winner']['new_rank']
                    if not existing_match.loser_old_rank:
                        existing_match.loser_old_rank = replay['loser']['old_rank']
                    if not existing_match.loser_new_rank:
                        existing_match.loser_new_rank = replay['loser']['new_rank']
                    
                    updated_count += 1
                else:
                    not_found_count += 1
                    logger.warning(f"Матч с ID {replay_id} не найден в базе данных")
            
            db.commit()
            logger.info(f"Дополнено {updated_count} существующих матчей")
            logger.info(f"Не найдено в базе: {not_found_count} матчей")
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении базы данных: {e}")
            db.rollback()
        finally:
            db.close()

    def save_filtered_data(self, replays: List[Dict]):
        """
        Сохраняет отфильтрованные данные в JSON файл.
        """
        try:
            # Статистика
            total_replays = len(replays)
            
            # Создаем метаданные
            metadata = {
                'generated_at': datetime.now().isoformat(),
                'total_replays': total_replays,
                'target_patch': self.target_patch,
                'description': f'Полные данные реплеев патча {self.target_patch}'
            }
            
            # Создаем итоговый объект
            output_data = {
                'metadata': metadata,
                'replays': replays
            }
            
            # Сохраняем в файл
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Данные сохранены в {self.output_file}")
            logger.info(f"Всего реплеев: {total_replays}")
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении данных: {e}")

    async def process_replays(self):
        """
        Основной метод обработки реплеев.
        """
        logger.info("Начинаем загрузку и обработку реплеев...")
        
        # Загружаем данные
        replays = await self.download_replays()
        if not replays:
            logger.error("Не удалось загрузить данные")
            return
        
        # Обрабатываем данные
        logger.info(f"Обрабатываем данные для патча {self.target_patch}...")
        processed_replays = []
        
        for replay in replays:
            processed_replay = self.process_replay_data(replay)
            if processed_replay:
                processed_replays.append(processed_replay)
        
        logger.info(f"Обработано {len(processed_replays)} реплеев патча {self.target_patch} из {len(replays)} общих")
        
        # Дополняем базу данных
        self.update_existing_matches(processed_replays)
        
        # Сохраняем результат в JSON
        self.save_filtered_data(processed_replays)
        
        logger.info("Обработка завершена!")

async def main():
    """
    Главная функция.
    """
    updater = ReplayDataUpdater()
    await updater.process_replays()

if __name__ == "__main__":
    asyncio.run(main())
