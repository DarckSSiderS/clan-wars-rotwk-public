import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector
from bs4 import BeautifulSoup
import json
import re
from typing import Dict, List, Optional
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, quote, urlparse
from sqlalchemy.orm import Session
from app.models.match import Match, MatchParticipant
from app.models.war import ClanWar
from app.models.worker import WorkerHeartbeat
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.core.time import as_utc, utc_now
from app.schemas.match import MatchCreate
from app.services.war_service import ClanWarService
from app.services.elo_service import (
    BfmeProfileRatingService,
    get_patch_family,
    rating_capture_timestamp,
)
from app.services.campaign_settings_service import (
    CampaignSettingsService,
    ReplaySyncStateService,
)
from app.services.replay_storage_service import ReplayStorageService
from app.services.map_preview_storage_service import MapPreviewStorageService
from app.services.campaign_rule_service import CampaignRuleService
from app.services.arena_replay_scan import ArenaReplayScan
from app.config import settings

logger = logging.getLogger(__name__)


class ReplaySourceError(RuntimeError):
    """The configured replay source could not provide a valid response."""


class ReplayRateLimited(ReplaySourceError):
    def __init__(self, retry_after=None):
        super().__init__("BFME Arena replay source returned HTTP 429")
        self.retry_after = None
        if retry_after:
            try:
                if re.fullmatch(r"[0-9]{1,10}", retry_after):
                    self.retry_after = int(retry_after)
                else:
                    deadline = parsedate_to_datetime(retry_after)
                    self.retry_after = max(0, (as_utc(deadline) - utc_now()).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass


class BFMELadderService:
    def __init__(self):
        self.ladder_base = settings.LADDER_BASE
        self.game = settings.LADDER_GAME
        self.patch = settings.LADDER_PATCH
        self.gamemode = settings.LADDER_GAMEMODE
        self.gamemodes = {
            " ".join(item.split())
            for item in settings.LADDER_GAMEMODES.split(",")
            if item.strip()
        }
        self.proxy = settings.PROXY_URL
        self.last_source = "not_started"
        self.last_scanned_count = 0
        self.last_completed_scan = None
        self._pending_public_scan = None
        self.profile_rating_service = BfmeProfileRatingService()
        
        self.factions = {
            "Гондор": "Гондор",
            "Рохан": "Рохан",
            "Изенгард": "Изенгард",
            "Мордор": "Мордор",
            "Ангмар": "Ангмар",
            "Гномы": "Гномы",
            "Харад": "Харад",
            "Арнор": "Арнор",
            "Лотлориэн": "Лотлориэн",
            "Имладрис": "Имладрис",
            "Мглистые Горы": "Мглистые Горы"
        }
        
        # EN -> RU маппинг для нормализации
        self.factions_en_to_ru = {
            "gondor": "Гондор",
            "rohan": "Рохан",
            "isengard": "Изенгард",
            "mordor": "Мордор",
            "angmar": "Ангмар",
            "dwarves": "Гномы",
            "elves": "Эльфы",
            "goblins": "Гоблины",
            "men": "Люди",
            "harad": "Харад",
            "arnor": "Арнор",
            "lothlorien": "Лотлориэн",
            "imladris": "Имладрис",
            "misty mountains": "Мглистые Горы",
            "rhun": "Рун",
        }
    
    def _normalize_faction(self, name: Optional[str]) -> Optional[str]:
        if not name or not str(name).strip():
            return None
        normalized_name = str(name).strip()
        # уже русское — оставляем
        if normalized_name in self.factions:
            return normalized_name
        # чистим и маппим EN -> RU
        key = normalized_name.lower()
        return self.factions_en_to_ru.get(key, normalized_name)

    def _save_match_to_db(self, db: Session, match_id: str, winner_players: List[tuple], loser_players: List[tuple],
                          match_date: str, duration: str = None, map_name: str = None, is_live: bool = False,
                          patch_version: str = None, game_mode: str = None,
                          api_metadata: Optional[dict] = None,
                          rating_snapshot: Optional[dict] = None,
                          participant_rows: Optional[List[dict]] = None):
        try:
            if is_live:
                # LIVE не сохраняем, чтобы не портить статистику
                return False
            if winner_players and loser_players:
                winner_entry = winner_players[0]
                loser_entry = loser_players[0]
                winner_player, winner_faction = winner_entry[:2]
                loser_player, loser_faction = loser_entry[:2]
                winner_player_uuid = winner_entry[2] if len(winner_entry) > 2 else None
                loser_player_uuid = loser_entry[2] if len(loser_entry) > 2 else None
                from app.services.external_identity_service import ExternalIdentityService
                identities = ExternalIdentityService()
                winner_player_uuid = winner_player_uuid or identities.uuid_for_known_nickname(db, winner_player)
                loser_player_uuid = loser_player_uuid or identities.uuid_for_known_nickname(db, loser_player)

                # Never turn an internal/source identifier into a visible player.
                # A missing display name is skipped and can be retried on the next sync.
                if any(not name or str(name).strip().lower().startswith("player_")
                       for name in (winner_player, loser_player)):
                    logger.warning("Пропущен матч %s: источник не отдал реальные ники", match_id)
                    return False

                # нормализуем фракции перед записью
                winner_faction = self._normalize_faction(winner_faction) or "Неизвестно"
                loser_faction = self._normalize_faction(loser_faction) or "Неизвестно"

                match_datetime = self._parse_match_date(match_date)
                if not match_datetime:
                    return False

                # Проверяем, не существует ли уже такой матч
                existing_match = db.query(Match).filter(Match.match_id == match_id).first()
                if existing_match:
                    logger.info(f"Матч {match_id} уже существует в базе")
                    return False

                match_data = Match(
                    match_id=match_id,
                    winner_player=winner_player,
                    winner_faction=winner_faction,
                    loser_player=loser_player,
                    loser_faction=loser_faction,
                    match_date=match_datetime,
                    duration=duration,
                    game_mode=game_mode or self.gamemode,
                    map_name=map_name,
                    patch_version=patch_version or self.patch,
                    winner_player_uuid=winner_player_uuid,
                    loser_player_uuid=loser_player_uuid,
                    is_live=False  # сохраняем только завершённые
                )
                if api_metadata:
                    self._apply_api_replay_metadata(match_data, api_metadata)
                if rating_snapshot:
                    match_data.winner_elo = rating_snapshot["winner_elo"]
                    match_data.loser_elo = rating_snapshot["loser_elo"]
                    match_data.rating_patch_family = rating_snapshot["patch_family"]
                    match_data.ratings_captured_at = rating_snapshot["captured_at"]
                    match_data.rating_source = rating_snapshot.get("source", "bfmeladder_profile_current")
                db.add(match_data)
                db.flush()
                for participant in participant_rows or []:
                    if not participant.get('player_uuid'):
                        participant['player_uuid'] = identities.uuid_for_known_nickname(db, participant['nickname'])
                    db.add(MatchParticipant(match_id=match_data.id, **participant))
                db.commit()
                try:
                    from app.services.user_service import UserService
                    profile_service = UserService()
                    profiles = participant_rows or [
                        {"nickname": winner_player, "player_uuid": winner_player_uuid},
                        {"nickname": loser_player, "player_uuid": loser_player_uuid},
                    ]
                    for participant in profiles:
                        profile_service.ensure_ladder_profile(
                            db,
                            participant["nickname"],
                            participant.get("player_uuid"),
                        )
                except Exception as profile_error:
                    logger.warning("Не удалось создать ladder-профили матча %s: %s", match_id, profile_error)
                ClanWarService().record_match_result(
                    db,
                    winner_player,
                    loser_player,
                    match_datetime,
                    match=match_data,
                )
                logger.info(f"Сохранен матч {match_id}: {winner_player} ({winner_faction}) vs {loser_player} ({loser_faction})")
                return True
            return False
        except Exception as e:
            logger.warning(f"Ошибка сохранения матча {match_id}: {e}")
            db.rollback()
            return False
    
    def _parse_match_date(self, match_date: str) -> Optional[datetime]:
        """Парсит дату матча в объект datetime"""
        try:
            if match_date.isdigit() and len(match_date) > 10:
                # Unix timestamp в миллисекундах
                timestamp_ms = int(match_date)
                timestamp_s = timestamp_ms / 1000
                return datetime.fromtimestamp(timestamp_s, tz=timezone.utc)
            elif '/' in match_date:
                # Формат YYYY/MM/DD HH:MM или YYYY/MM/DD
                if ' ' in match_date:
                    return datetime.strptime(match_date, "%Y/%m/%d %H:%M")
                else:
                    return datetime.strptime(match_date, "%Y/%m/%d")
            elif '.' in match_date:
                # Формат DD.MM.YYYY
                return datetime.strptime(match_date, "%d.%m.%Y")
        except Exception as e:
            logger.warning(f"Ошибка парсинга даты '{match_date}': {e}")
        return None

    @staticmethod
    def _known_matches_for_replay_ids(
        db: Session,
        replay_items: List[tuple[str, dict]],
    ) -> Dict[str, Match]:
        """Возвращает только уже сохранённые матчи из текущей порции API."""
        match_ids = list(
            dict.fromkeys(
                str(match_id)
                for match_id, _ in replay_items
                if match_id
            )
        )
        if not match_ids:
            return {}

        known_matches: Dict[str, Match] = {}
        # Ограничиваем размер IN-запроса, чтобы он оставался переносимым между БД.
        for start in range(0, len(match_ids), 500):
            batch_ids = match_ids[start:start + 500]
            for match in db.query(Match).filter(Match.match_id.in_(batch_ids)).all():
                known_matches[match.match_id] = match
        return known_matches
    
    def _extract_duration(self, replay_item) -> Optional[str]:
        """Извлекает длительность матча"""
        try:
            # Ищем элемент с текстом "Duration"
            duration_elements = replay_item.find_all('div', string=lambda text: text and 'Duration' in text)
            for duration_element in duration_elements:
                parent = duration_element.find_parent()
                if parent:
                    # Ищем соседний элемент с длительностью
                    duration_value = parent.find_next_sibling()
                    if duration_value:
                        return duration_value.get_text(strip=True)
        except Exception as e:
            logger.warning(f"Ошибка извлечения длительности: {e}")
        return None
    
    def _extract_map_name(self, replay_item) -> Optional[str]:
        """Извлекает название карты"""
        try:
            # Ищем блок с картой
            map_block = replay_item.find('div', {'class': 'mapImageBlock'})
            if map_block:
                # Название карты обычно находится в div под изображением
                map_name_div = map_block.find('div', style=lambda value: value and 'font-weight: 800' in value and 'text-align: center' in value)
                if map_name_div:
                    return map_name_div.get_text(strip=True)
        except Exception as e:
            logger.warning(f"Ошибка извлечения названия карты: {e}")
        return None
    
    def _extract_players_from_section(self, section) -> List[tuple]:
        """Извлекает игроков и их фракции из секции Winners или Losers"""
        players = []
        
        # Ищем контейнеры с игроками (обычно div с flex align-items: center)
        player_containers = section.find_all('div', style=lambda x: x and 'align-items: center' in x)
        
        for container in player_containers:
            try:
                # Ищем имя игрока (обычно в div с font-weight: 800)
                player_name_div = container.find('div', style=lambda x: x and 'font-weight: 800' in x)
                if not player_name_div:
                    continue
                
                # Ищем иконку армии рядом с именем игрока
                army_icon = player_name_div.find('img', {'class': 'armyIcon'})
                if not army_icon:
                    continue
                
                # Извлекаем имя игрока (убираем иконку из текста)
                player_name = player_name_div.get_text(strip=True)
                
                # Определяем фракцию по иконке
                faction = self._get_faction_from_icon_url(army_icon.get('src', ''))
                if faction:
                    players.append((player_name, faction))
                    
            except Exception as e:
                logger.warning(f"Ошибка извлечения игрока: {e}")
                continue
        
        return players
    
    def _get_faction_from_icon_url(self, icon_url: str) -> Optional[str]:
        """Определяет фракцию по URL иконки армии"""
        # Маппинг URL иконок на фракции (на основе данных с сайта)
        icon_mappings = {
            '014c1ebf-1d53-4b29-9914-1fa3e44dae0c.png': 'Харад',
            '806c09f6-3abf-479b-b97a-b856d80b0e02.png': 'Изенгард',
            '73a97e8e-bd4c-450c-87d9-4596e7b68e59.png': 'Мглистые Горы',
            'e464285a-5cc1-457a-b1f6-012c5b10aa25.png': 'Гондор',
            '0afa17d0-7d6f-4b42-a9f0-ad7dd2ac44bf.png': 'Мордор',
            'fe8eff0d-d1d6-459c-8c0f-2ca1a38ee35f.png': 'Лотлориэн',
            'a983b2bd-64eb-412d-9872-5e35279b3ab0.png': 'Имладрис',
            '08217ec7-0c2d-4c68-9afa-e0c98f2d9c8d.png': 'Арнор',
            'efcd9306-00a2-4dfd-8773-7ed8bce73e1b.png': 'Рохан',
            '69eedfea-67c6-4ada-981b-8764a1045d44.png': 'Ангмар',
            '55329afc-4393-475d-96ba-d3b8f3f7703c.png': 'Гномы',
        }
        
        # Извлекаем имя файла из URL
        if '/' in icon_url:
            filename = icon_url.split('/')[-1]
        else:
            filename = icon_url
        
        faction = icon_mappings.get(filename)
        if not faction:
            logger.debug("Неизвестная иконка фракции: %s", filename)
            
        return faction

    async def _stream_api_replays(self, response, max_items: int):
        """Read only the newest objects from the large replay export."""
        decoder = json.JSONDecoder()
        utf8 = __import__("codecs").getincrementaldecoder("utf-8")()
        buffer = ""
        cursor = 0
        eof = False

        async def fill_buffer():
            nonlocal buffer, eof
            chunk = await response.content.read(64 * 1024)
            if not chunk:
                buffer += utf8.decode(b"", final=True)
                eof = True
                return False
            buffer += utf8.decode(chunk)
            return True

        await fill_buffer()
        while buffer and not buffer.lstrip().startswith("{") and not eof:
            await fill_buffer()
        if not buffer.lstrip().startswith("{"):
            return
        cursor = buffer.find("{") + 1
        yielded = 0

        while yielded < max_items:
            try:
                while cursor < len(buffer) and buffer[cursor] in " \t\r\n,":
                    cursor += 1
                if cursor >= len(buffer):
                    if eof or not await fill_buffer():
                        break
                    continue
                if buffer[cursor] == "}":
                    break
                key, cursor = decoder.raw_decode(buffer, cursor)
                while cursor < len(buffer) and buffer[cursor] in " \t\r\n:":
                    cursor += 1
                value, cursor = decoder.raw_decode(buffer, cursor)
            except json.JSONDecodeError:
                if eof:
                    break
                if cursor > 0:
                    buffer = buffer[cursor:]
                    cursor = 0
                await fill_buffer()
                continue

            yielded += 1
            if isinstance(value, dict):
                yield key, value

    @staticmethod
    def _normalize_public_replay(item: dict) -> tuple[str, dict]:
        replay_id = str(item.get("replayId") or "")
        players = []
        for player in item.get("players", []):
            players.append({
                "PlayerAccountUuid": player.get("uuid"),
                "DisplayName": player.get("displayName") or player.get("nickname"),
                "FactionName": player.get("faction"),
                "Team": player.get("team"),
                "IsWinner": bool(player.get("isWinner")),
                "IsObserver": bool(player.get("isObserver", False)),
                "OldRank": player.get("oldRank"),
                "NewRank": player.get("newRank"),
            })
        return replay_id, {
            "ReplayId": replay_id,
            "Date": item.get("date"),
            "ArenaId": item.get("arenaId"),
            "GamemodeName": item.get("gamemode"),
            "MapId": item.get("mapId"),
            "MapName": item.get("mapName"),
            "MapPreviewSource": item.get("mapPreviewSource"),
            "PatchId": item.get("patchId"),
            "PatchName": item.get("patchName"),
            "GameName": item.get("gameName"),
            "Duration": item.get("duration"),
            "Likes": item.get("likes"),
            "Downloads": item.get("downloads"),
            "Comments": item.get("comments"),
            "EloDelta": item.get("eloDelta"),
            "ReplayDownloadUrl": item.get("replayDownloadUrl") or item.get("downloadUrl"),
            "Players": players,
            "IsValid": True,
            "PublicApiPayload": item,
        }

    @staticmethod
    def _html_rank_pair(value: str) -> tuple[Optional[int], Optional[int]]:
        text = value.strip().lower()
        parts = re.split(r"\s*(?:➔|→|âž)\s*", text, maxsplit=1)

        def rank(part: str) -> Optional[int]:
            match = re.search(r"\d+", part)
            return int(match.group(0)) if match else None

        if len(parts) == 2:
            return rank(parts[0]), rank(parts[1])
        values = [int(item) for item in re.findall(r"\d+", text)]
        if text.startswith("unranked"):
            return None, values[-1] if values else None
        if text.endswith("unranked"):
            return values[0] if values else None, None
        if len(values) >= 2:
            return values[0], values[-1]
        return (values[0], values[0]) if values else (None, None)

    @staticmethod
    def _html_meta(card) -> dict[str, str]:
        metadata = {}
        for row in card.select(".meta-row"):
            label = row.select_one(".meta-label")
            value = row.select_one(".meta-value")
            if label and value:
                metadata[label.get_text(" ", strip=True).casefold()] = value.get_text(
                    " ", strip=True
                )
        return metadata

    @staticmethod
    def _html_rating_evidence(row) -> dict | None:
        tooltips = row.select('.player-rank .rx-pop')
        buttons = row.select('.player-rank .rx-btn')
        if len(tooltips) != 1 or len(buttons) != 1:
            return None
        label = buttons[0].get_text(' ', strip=True)
        scope = re.fullmatch(r'[+-]?\d+(?:\.\d+)?(?:\s+(ELO|CW))?', label, re.IGNORECASE)
        if scope is None:
            return None
        values = {}
        for item in tooltips[0].select('li'):
            text = item.get_text(' ', strip=True)
            if not re.match(r'rating\s+(before|after)\s*:', text, re.IGNORECASE):
                continue
            field = re.fullmatch(r'rating\s+(before|after)\s*:\s*(\d+)', text, re.IGNORECASE)
            if field is None or field[1].lower() in values:
                return None
            values[field[1].lower()] = int(field[2])
        if set(values) != {'before', 'after'}:
            return None
        # Source evidence is retained, not certified as game-start ladder Elo.
        kind = {'ELO': 'ladder', 'CW': 'clan_war'}.get((scope[1] or '').upper(), 'unspecified')
        return {**values, 'kind': kind,
                'source': 'replay_html_tooltip', 'time_semantics_verified': False}

    def _parse_html_replays(
        self,
        html: str,
        *,
        scan_limit: Optional[int],
        gamemodes: Optional[set[str]] = None,
        start_override_ms: Optional[int] = None,
        end_override_ms: Optional[int] = None,
        max_per_mode: Optional[int] = None,
    ) -> List[tuple[str, dict]]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".replay-card")
        if not cards:
            if soup.select_one("#replays") is not None:
                return []
            raise ReplaySourceError("BFME Arena replay page has no replay cards")

        allowed_modes = gamemodes or self.gamemodes
        collected = []
        per_mode = {}
        for card in cards:
            replay_id = str(card.get("id") or "").strip()
            metadata = self._html_meta(card)
            team_columns = card.select(".team-col")
            titles = {
                title.get_text(" ", strip=True).casefold()
                for title in card.select(".team-title")
            }
            download = card.select_one('a.replay-dl[href*="/api/replays/download"]')
            duration = metadata.get("duration")
            if (
                not replay_id
                or titles != {"winners", "losers"}
                or not download
                or not duration
                or duration == "-"
            ):
                continue

            mode = " ".join(metadata.get("gamemode", "").split())
            if mode not in allowed_modes:
                continue
            if max_per_mode is not None and per_mode.get(mode, 0) >= max(0, max_per_mode):
                continue

            try:
                replay_date = int(metadata.get("date", ""))
            except (TypeError, ValueError):
                continue
            if start_override_ms is not None and replay_date < start_override_ms:
                continue
            if end_override_ms is not None and replay_date > end_override_ms:
                continue

            players = []
            for team_column in team_columns:
                title = team_column.select_one(".team-title")
                if not title:
                    continue
                is_winner = title.get_text(" ", strip=True).casefold() == "winners"
                for row in team_column.select(".player-row"):
                    profile = row.select_one('a[href^="/u/"]')
                    if not profile:
                        continue
                    nickname = profile.get_text(" ", strip=True)
                    army_icon = row.select_one("img.armyIcon")
                    faction = None
                    if army_icon and army_icon.get("src"):
                        icon_url = army_icon["src"]
                        filename = urlparse(icon_url).path.rsplit("/", 1)[-1]
                        mapped_faction = (
                            self._get_faction_from_icon_url(icon_url)
                            if re.fullmatch(
                                r"[0-9a-fA-F-]{36}\.png",
                                filename,
                            )
                            else None
                        )
                        faction = mapped_faction or filename.rsplit(".", 1)[0].replace(
                            "-", " "
                        )
                    rank_element = row.select_one(".player-rank")
                    rank_text = ' '.join(
                        text.strip() for text in rank_element.find_all(string=True)
                        if not text.find_parent(class_=['rx', 'rx-pop', 'rx-btn'])
                    ) if rank_element else ''
                    old_rank, new_rank = self._html_rank_pair(
                        rank_text
                    )
                    rating_evidence = self._html_rating_evidence(row)
                    players.append(
                        {
                            "PlayerAccountUuid": None,
                            "DisplayName": nickname,
                            "FactionName": faction,
                            "Team": 1 if is_winner else 2,
                            "IsWinner": is_winner,
                            "IsObserver": False,
                            "OldRank": old_rank,
                            "NewRank": new_rank,
                            **({'ArenaRatingEvidence': rating_evidence} if rating_evidence else {}),
                        }
                    )
            if not any(player["IsWinner"] for player in players) or not any(
                not player["IsWinner"] for player in players
            ):
                continue

            map_image = card.select_one(".map-block img.mapImage")
            map_name = card.select_one(".map-name")
            replay = {
                "ReplayId": replay_id,
                "Date": replay_date,
                "GamemodeName": mode,
                "MapName": map_name.get_text(" ", strip=True) if map_name else None,
                "MapPreviewSource": map_image.get("src") if map_image else None,
                "PatchName": metadata.get("patch"),
                "GameName": metadata.get("game"),
                "Duration": duration,
                "Likes": self._optional_int(metadata.get("likes")),
                "Downloads": self._optional_int(metadata.get("downloads")),
                "Comments": self._optional_int(metadata.get("comments")),
                "EloDelta": self._optional_int(metadata.get("elo +/-")),
                "ReplayDownloadUrl": download.get("href"),
                "Players": players,
                "IsValid": True,
                "Source": "bfme_arena_html",
            }
            collected.append((replay_id, replay))
            per_mode[mode] = per_mode.get(mode, 0) + 1
            if scan_limit is not None and len(collected) >= scan_limit:
                break

        return sorted(
            collected,
            key=lambda row: int(row[1].get("Date") or 0),
            reverse=True,
        )

    async def _load_html_replays(
        self,
        session,
        scan_limit: Optional[int],
        *,
        gamemodes: Optional[set[str]] = None,
        start_override_ms: Optional[int] = None,
        end_override_ms: Optional[int] = None,
        max_per_mode: Optional[int] = None,
        player_query: Optional[str] = None,
        paginate_all: bool = False,
    ) -> List[tuple[str, dict]]:
        page = 1
        collected: dict[str, dict] = {}
        seen_pages = set()
        while True:
            params = {"game": self.game, "q": (player_query or "").strip()}
            if paginate_all:
                params["page"] = page
            async with session.get(
                self.ladder_base,
                params=params,
                headers={"Accept": "text/html"},
            ) as response:
                if response.status == 429:
                    raise ReplayRateLimited(response.headers.get("Retry-After"))
                if response.status != 200:
                    raise ReplaySourceError(
                        f"BFME Arena replay page returned HTTP {response.status}"
                    )
                html = await response.text()
            remaining_limit = (
                None
                if scan_limit is None
                else max(0, scan_limit - len(collected))
            )
            page_result = self._parse_html_replays(
                html,
                scan_limit=remaining_limit,
                gamemodes=gamemodes,
                start_override_ms=start_override_ms,
                end_override_ms=end_override_ms,
                max_per_mode=max_per_mode,
            )
            for replay_id, replay in page_result:
                collected[replay_id] = replay

            reached_limit = (
                scan_limit is not None and len(collected) >= scan_limit
            )
            soup = BeautifulSoup(html, "html.parser")
            page_ids = tuple(sorted(card['id'] for card in soup.select('.replay-card[id]')))
            if paginate_all and page_ids:
                if page_ids in seen_pages:
                    raise ReplaySourceError('BFME Arena returned a repeated replay archive page')
                seen_pages.add(page_ids)
            linked_pages = set()
            for link in soup.select('.replay-pagination-controls a.replay-page-btn'):
                values = parse_qs(urlparse(str(link.get('href') or '')).query).get('page', [])
                if len(values) == 1 and values[0].isdigit():
                    linked_pages.add(int(values[0]))
            has_next_page = page + 1 in linked_pages
            if paginate_all and not has_next_page and any(value > page for value in linked_pages):
                raise ReplaySourceError('BFME Arena replay pagination is incomplete')
            # Arena pages are newest first. A finalization scan needs the entire
            # pending war window, including republished older matches.
            if paginate_all and start_override_ms is not None:
                unfiltered_page = self._parse_html_replays(html, scan_limit=None)
                if unfiltered_page and max(int(row[1]["Date"]) for row in unfiltered_page) < start_override_ms:
                    has_next_page = False
            if not paginate_all or reached_limit or not has_next_page:
                break
            if page >= settings.ARENA_BACKFILL_MAX_PAGES:
                raise ReplaySourceError(
                    "BFME Arena player replay archive exceeds the configured page limit"
                )
            page += 1

        result = sorted(
            collected.items(),
            key=lambda row: int(row[1].get("Date") or 0),
            reverse=True,
        )
        self.last_source = "bfme_arena_html"
        self.last_scanned_count = len(result)
        return result

    async def _load_api_replays(
        self,
        session,
        db: Session,
        scan_limit: Optional[int],
        *,
        gamemodes: Optional[set[str]] = None,
        start_override_ms: Optional[int] = None,
        end_override_ms: Optional[int] = None,
        advance_cursor: bool = True,
        max_per_mode: Optional[int] = None,
        player_query: Optional[str] = None,
        force_html: bool = False,
        paginate_html: bool = False,
    ) -> List[tuple[str, dict]]:
        self.last_completed_scan = None
        self._pending_public_scan = None
        self._pending_public_cursor_ms = None
        token = settings.LADDER_PUBLIC_API_TOKEN.strip()
        if not force_html and settings.LADDER_PUBLIC_API_ENABLED and token:
            campaign = CampaignSettingsService().get_or_create(db)
            request_started_ms = int(utc_now().timestamp() * 1000)
            end_ms = end_override_ms if end_override_ms is not None else request_started_ms
            fallback_start = end_ms - settings.LADDER_SYNC_WINDOW_HOURS * 3600 * 1000
            start_ms = start_override_ms if start_override_ms is not None else max(
                    0,
                    int(campaign.replay_cursor_ms if campaign.replay_cursor_ms is not None else fallback_start)
                    - settings.LADDER_SYNC_OVERLAP_MINUTES * 60 * 1000,
                )
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            }
            collected = {}
            arena_ids = {
                settings.LADDER_PATCH_202_ARENA_ID,
                settings.LADDER_ENNORATH_ARENA_ID,
                settings.LADDER_ARENA_ID,
            }
            for arena_id in sorted(filter(None, arena_ids)):
                for gamemode in sorted(gamemodes or self.gamemodes):
                    params = {
                        "start": start_ms,
                        "end": end_ms,
                        "arena": arena_id,
                        "gamemode": gamemode,
                    }
                    async with session.get(
                        settings.LADDER_PUBLIC_API_BASE,
                        params=params,
                        headers=headers,
                    ) as response:
                        if response.status == 429:
                            raise ReplayRateLimited(response.headers.get("Retry-After"))
                        if response.status != 200:
                            raise ReplaySourceError(
                                f"BFME Arena public replay API returned HTTP {response.status}"
                            )
                        payload = await response.json()
                        if not isinstance(payload, list):
                            raise ReplaySourceError(
                                "BFME Arena public replay API returned an unexpected payload"
                            )
                        for item in payload:
                            if (not isinstance(item, dict)
                                    or not isinstance(item.get('replayId'), str)
                                    or not item['replayId'].strip()
                                    or not isinstance(item.get('gameName'), str)
                                    or not item['gameName'].strip()
                                    or not isinstance(item.get('gamemode'), str)
                                    or not item['gamemode'].strip()):
                                raise ReplaySourceError('BFME Arena public API returned a malformed replay')
                            if (item['gameName'] == self.game and item['gamemode'] in self.gamemodes
                                    and not any(isinstance(item.get(key), str) and item[key].strip()
                                        for key in ('patchName', 'patchId'))):
                                raise ReplaySourceError('В ответе Арены отсутствует патч реплея')
                        supported_payload = [
                            item
                            for item in payload
                            if item.get("gameName") == self.game
                            and item.get("gamemode") in self.gamemodes
                            and get_patch_family(item.get("patchName"), item.get("patchId"))
                        ]
                        sorted_payload = sorted(
                            supported_payload,
                            key=lambda item: int(item.get("date") or 0),
                            reverse=True,
                        )
                        if max_per_mode is not None:
                            sorted_payload = sorted_payload[:max(0, max_per_mode)]
                        for item in sorted_payload:
                            replay_id, replay = self._normalize_public_replay(item)
                            if replay_id:
                                collected[replay_id] = replay
            if advance_cursor:
                self._pending_public_cursor_ms = end_ms
            result = sorted(
                collected.items(),
                key=lambda row: int(row[1].get("Date") or 0),
                reverse=True,
            )
            self.last_source = "bfme_public_api"
            self.last_scanned_count = len(result)
            required_arenas = {settings.LADDER_PATCH_202_ARENA_ID, settings.LADDER_ENNORATH_ARENA_ID}
            required_modes = {f'{size} versus {size}' for size in range(1, 5)}
            if (self.game == 'RotWK' and scan_limit is None and max_per_mode is None and not player_query
                    and not settings.LADDER_API_PATCH_FILTER.strip()
                    and len(required_arenas) == 2 and all(required_arenas)
                    and required_modes <= set(gamemodes or self.gamemodes)
                    and 0 <= start_ms < end_ms <= request_started_ms):
                # Пока не сохранены все реплеи, это только кандидат подтверждения.
                self._pending_public_scan = ArenaReplayScan(
                    datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc),
                    datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc),
                    f'bfmeladder:{start_ms}:{end_ms}', replay_ids=frozenset(collected))
            return result

        return await self._load_html_replays(
            session,
            scan_limit,
            gamemodes=gamemodes,
            start_override_ms=start_override_ms,
            end_override_ms=end_override_ms,
            max_per_mode=max_per_mode,
            player_query=player_query,
            paginate_all=paginate_html,
        )

    def _api_replay_matches_filters(self, replay: dict) -> bool:
        if replay.get("GameName") != self.game:
            return False
        if replay.get("GamemodeName") not in self.gamemodes:
            return False
        # Кампания принимает только два поддерживаемых семейства патчей.
        if not get_patch_family(replay.get("PatchName"), replay.get("PatchId")):
            return False
        patch_filter = getattr(settings, "LADDER_API_PATCH_FILTER", "")
        if patch_filter:
            patch_text = f"{replay.get('PatchId', '')} {replay.get('PatchName', '')}".lower()
            if patch_filter.lower() not in patch_text:
                return False
        return bool(replay.get("IsValid", True))

    @staticmethod
    def _optional_int(value):
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _build_participant_rows(
        self,
        replay: dict,
        winners: List[tuple],
        losers: List[tuple],
        rating_snapshot: Optional[dict],
    ) -> List[dict]:
        api_players = [
            player
            for player in replay.get("Players", [])
            if not player.get("IsObserver")
        ]
        ratings = (rating_snapshot or {}).get("participant_ratings", {})
        rows = []
        used_indexes = set()

        for is_winner, extracted_players in ((True, winners), (False, losers)):
            candidates = [
                (index, player)
                for index, player in enumerate(api_players)
                if bool(player.get("IsWinner")) == is_winner
            ]
            for side_index, extracted in enumerate(extracted_players):
                nickname = extracted[0]
                faction = extracted[1] if len(extracted) > 1 else None
                player_uuid = extracted[2] if len(extracted) > 2 else None
                api_index = None
                api_player = None
                if player_uuid:
                    for index, candidate in candidates:
                        candidate_uuid = (
                            candidate.get("PlayerAccountUuid")
                            or candidate.get("PlayerAccountUUID")
                        )
                        if candidate_uuid == player_uuid and index not in used_indexes:
                            api_index, api_player = index, candidate
                            break
                if api_player is None and side_index < len(candidates):
                    api_index, api_player = candidates[side_index]
                if api_index is not None:
                    used_indexes.add(api_index)
                api_player = api_player or {}
                player_uuid = player_uuid or api_player.get("PlayerAccountUuid") or api_player.get("PlayerAccountUUID")
                rows.append({
                    "nickname": nickname,
                    "player_uuid": player_uuid,
                    "faction": self._normalize_faction(
                        faction or api_player.get("FactionName")
                    ) or "Неизвестно",
                    "faction_index": self._optional_int(api_player.get("FactionIndex")),
                    "team": self._optional_int(api_player.get("Team")) or (1 if is_winner else 2),
                    "is_winner": is_winner,
                    "is_observer": False,
                    "old_rank": self._optional_int(api_player.get("OldRank")),
                    "new_rank": self._optional_int(api_player.get("NewRank")),
                    "elo": ratings.get(str(nickname).casefold()),
                })

        unique_rows = {}
        enrichment_fields = (
            "player_uuid",
            "faction",
            "faction_index",
            "old_rank",
            "new_rank",
            "elo",
        )
        for row in rows:
            nickname_key = str(row["nickname"]).strip().casefold()
            if not nickname_key:
                continue
            existing = unique_rows.get(nickname_key)
            if existing is None:
                unique_rows[nickname_key] = row
                continue
            for field in enrichment_fields:
                current = existing.get(field)
                incoming = row.get(field)
                if current in (None, "", "Неизвестно") and incoming not in (
                    None,
                    "",
                    "Неизвестно",
                ):
                    existing[field] = incoming
        return list(unique_rows.values())

    @staticmethod
    def _apply_api_replay_metadata(match: Match, replay: dict) -> bool:
        """Persist the API fields used for ranked-match and campaign validation."""
        previous = match.source_payload if isinstance(match.source_payload, dict) else {}
        original_api = previous.get('PublicApiPayload')
        retained_api = ({'PublicApiPayload': original_api}
            if 'PublicApiPayload' not in replay and isinstance(original_api, dict)
            and original_api.get('replayId') == match.match_id == replay.get('ReplayId') else {})
        from app.services.arena_replay_rating_service import ArenaReplayRatingService
        source_api = replay.get('PublicApiPayload') or retained_api.get('PublicApiPayload')
        retained_rating = next((value for value in (
            replay.get('ArenaReplayRatings'), previous.get('ArenaReplayRatings'))
            if ArenaReplayRatingService.read(value, source_api)), None)
        rejection = previous.get('ArenaReplayRejection')
        retained_rejection = (rejection if not source_api and replay.get('Source') == 'bfme_arena_html'
            and isinstance(rejection, dict) and rejection.get('replay_id') == match.match_id == replay.get('ReplayId')
            else None)
        values = {
            "duration": replay.get("Duration"),
            "arena_id": replay.get("ArenaId"),
            "patch_id": replay.get("PatchId"),
            "patch_name": replay.get("PatchName"),
            "patch_version": replay.get("PatchName") or replay.get("PatchId"),
            "game_name": replay.get("GameName"),
            "map_id": replay.get("MapId"),
            "map_name": replay.get("MapName"),
            "map_preview_source": replay.get("MapPreviewSource"),
            "gamemode_name": replay.get("GamemodeName"),
            "game_mode": replay.get("GamemodeName"),
            "replay_download_url": (
                replay.get("ReplayDownloadUrl")
                or replay.get("DownloadUrl")
            ),
            "source_payload": {
                **{key: value for key, value in replay.items() if key != 'ArenaReplayRatings'},
                **retained_api,
                **({'ArenaReplayRatings': retained_rating} if retained_rating else {}),
                **({'ArenaReplayRejection': retained_rejection} if retained_rejection else {}),
                **({'rating_unverified_players': previous['rating_unverified_players']}
                   if previous.get('rating_unverified_players') else {}),
            },
        }
        for field in ("arena_id", "patch_id", "map_id"):
            if values[field] is not None:
                values[field] = str(values[field])

        for field, api_key in (
            ("elo_delta", "EloDelta"),
            ("downloads", "Downloads"),
        ):
            raw_value = replay.get(api_key)
            if raw_value is not None:
                try:
                    values[field] = int(float(raw_value))
                except (TypeError, ValueError):
                    pass

        for field, api_key in (
            ("is_valid", "IsValid"),
            ("is_qualification_round", "IsQualificationRound"),
        ):
            if api_key in replay:
                values[field] = bool(replay.get(api_key))

        for field, api_key in (("likes", "Likes"), ("comments", "Comments")):
            if api_key in replay:
                values[field] = json.dumps(
                    replay.get(api_key),
                    ensure_ascii=False,
                )

        players = [
            player
            for player in replay.get("Players", [])
            if not player.get("IsObserver")
        ]
        winners = [player for player in players if player.get("IsWinner")]
        losers = [player for player in players if not player.get("IsWinner")]
        if len(winners) == 1 and len(losers) == 1:
            for prefix, player in (("winner", winners[0]), ("loser", losers[0])):
                for suffix, api_key in (
                    ("faction_index", "FactionIndex"),
                    ("old_rank", "OldRank"),
                    ("new_rank", "NewRank"),
                ):
                    raw_value = player.get(api_key)
                    if raw_value is not None:
                        try:
                            values[f"{prefix}_{suffix}"] = int(raw_value)
                        except (TypeError, ValueError):
                            pass

        changed = False
        for field, value in values.items():
            if value is not None and getattr(match, field) != value:
                setattr(match, field, value)
                changed = True
        return changed

    async def _enrich_replay_ratings(self, session, replay, *, html=None):
        """Извлекает Elo конкретной игры; не обращается к текущему рейтингу профиля."""
        from app.services.arena_replay_rating_service import ArenaReplayRatingService
        raw = replay.get('PublicApiPayload')
        if (not isinstance(raw, dict) or not isinstance(raw.get('replayId'), str)
                or not raw['replayId'].strip() or len(raw['replayId']) > 100
                or raw['replayId'] != replay.get('ReplayId')):
            return False
        if ArenaReplayRatingService.read(replay.get('ArenaReplayRatings'), raw):
            return True
        if html is None:
            url = f"{settings.LADDER_REPLAY_BASE.rstrip('/')}/{quote(raw['replayId'], safe='')}"
            try:
                async with session.get(url, headers={'Accept': 'text/html', 'Accept-Language': 'en'},
                                       timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        return False
                    html = await response.text()
            except Exception as error:
                logger.warning('Не удалось получить исторический Elo реплея %s: %s', raw['replayId'], type(error).__name__)
                return False
        value = ArenaReplayRatingService.parse(html, raw)
        if value is None:
            return False
        replay['ArenaReplayRatings'] = value
        return True

    async def _enrich_cycle_replay_ratings(self, session, db, replay_items, known_matches):
        """Повторяет недостающий рейтинг известных игр незавершённых новых циклов."""
        from app.services.arena_replay_rating_service import ArenaReplayRatingService
        from app.services.campaign_cycle_store import CampaignCycleStore
        from app.services.cycle_arena_ingestion_service import CycleArenaIngestionService
        from app.services.cycle_match_service import ReplayFacts
        cycles = [row for row in db.query(CampaignCycleRecord)
            .join(CampaignSeason).filter(CampaignSeason.status == 'active',
                CampaignCycleRecord.settled_at.is_(None), CampaignCycleRecord.orders_frozen_at.isnot(None))
            if (db.get(CampaignSeason, row.season_id).rules_snapshot or {}).get('mechanics_version') == 'cycle_v1']
        windows = [CampaignCycleStore.timeline(row) for row in cycles]
        candidates = dict(known_matches)
        incoming = dict(replay_items)
        # Повторяем тот же сохранённый набор, который рассматривает зачёт. Игра
        # не обязана снова появиться в выдаче API после временного сбоя страницы.
        for cycle, window in zip(cycles, windows):
            for match in CycleArenaIngestionService._matches(db, cycle=cycle, timeline=window,
                    now=window.battle_ends_at, scan=None):
                candidates.setdefault(match.match_id, match)
        pending = []
        for replay_id, match in candidates.items():
            previous = match.source_payload if isinstance(match.source_payload, dict) else {}
            replay = incoming.get(replay_id)
            if replay is None:
                replay = {'ReplayId': replay_id}
            if 'PublicApiPayload' not in replay:
                retained = previous.get('PublicApiPayload')
                if isinstance(retained, dict) and retained.get('replayId') == replay_id == match.match_id:
                    replay['PublicApiPayload'] = retained
            raw = replay.get('PublicApiPayload')
            existing = previous.get('ArenaReplayRatings')
            if ArenaReplayRatingService.read(existing, raw):
                replay['ArenaReplayRatings'] = existing
                continue
            start = ReplayFacts.arena_start(raw.get('date')) if isinstance(raw, dict) else None
            if start is not None and any(window.battle_at <= start < window.battle_ends_at for window in windows):
                pending.append((match, replay))
        semaphore = asyncio.Semaphore(3)

        async def enrich(match, replay):
            async with semaphore:
                if await self._enrich_replay_ratings(session, replay):
                    previous = match.source_payload if isinstance(match.source_payload, dict) else {}
                    match.source_payload = {**previous, 'PublicApiPayload': replay['PublicApiPayload'],
                        'ArenaReplayRatings': replay['ArenaReplayRatings']}

        await asyncio.gather(*(enrich(match, replay) for match, replay in pending))
        db.flush()

    @staticmethod
    def _is_cancelled_public_replay(replay):
        raw = replay.get('PublicApiPayload')
        if not isinstance(raw, dict) or raw.get('duration') != '00:00:00':
            return False
        players = raw.get('players')
        return bool(isinstance(players, list) and players
                    and all(isinstance(p, dict) and p.get('isWinner') is False for p in players))

    @staticmethod
    def _has_invalid_replay_badge(html, replay_id):
        if len(html) > 4_000_000 or '</html>' not in html.lower():
            return False
        soup = BeautifulSoup(html, 'html.parser')
        links = [a for a in soup.select('main a[href]') if urlparse(a['href']).path == '/api/replays/download']
        if len(links) != 1 or parse_qs(urlparse(links[0]['href']).query).get('replayId') != [replay_id]:
            return False
        actions = links[0].parent
        page = actions.parent
        if not {'container', 'page'} <= set(page.get('class', [])) or not page.select_one('.page-head h1'):
            return False
        details = actions.find_previous_sibling('div')
        if details is None:
            return False
        spans = details.find_all('span', recursive=False)
        return (
            any(re.search(r'\b\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC\b', span.get_text()) for span in spans)
            and any(re.search(r'\b\d{2}:\d{2}:\d{2}\b', span.get_text()) for span in spans)
            and any(span.get_text(strip=True) == 'invalid'
                    and span.get('style', '').replace(' ', '') == 'color:var(--loss);' for span in spans)
        )

    async def _check_old_html_rejections(self, session, db, scan, now):
        """Resolve only explicit Arena invalidations omitted by a complete API scan."""
        from app.services.campaign_cycle_store import CampaignCycleStore
        from app.services.cycle_arena_ingestion_service import CycleArenaIngestionService

        if scan is None:
            return
        inspected = set()
        cycles = db.query(CampaignCycleRecord).join(CampaignSeason).filter(
            CampaignSeason.status == 'active', CampaignCycleRecord.settled_at.is_(None),
            CampaignCycleRecord.battles_registered.is_(True)).all()
        for cycle in cycles:
            timeline = CampaignCycleStore.timeline(cycle)
            if not scan.covers(start=timeline.battle_at, deadline=timeline.replay_deadline, now=now):
                continue
            for match in CycleArenaIngestionService._matches(db, cycle=cycle, timeline=timeline, now=now, scan=None):
                payload = match.source_payload
                replay_id = match.match_id
                if (not isinstance(payload, dict) or payload.get('Source') != 'bfme_arena_html'
                        or 'PublicApiPayload' in payload or payload.get('ReplayId') != replay_id
                        or not isinstance(replay_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', replay_id)
                        or '..' in replay_id or replay_id in scan.replay_ids or replay_id in inspected
                        or not timeline.battle_at <= as_utc(match.match_date) <= timeline.battle_ends_at
                        or CycleArenaIngestionService._arena_rejected(match)):
                    continue
                if len(inspected) >= 8:
                    return
                inspected.add(replay_id)
                url = f"{settings.LADDER_REPLAY_BASE.rstrip('/')}/{quote(replay_id, safe='')}"
                try:
                    async with session.get(url, headers={'Accept': 'text/html', 'Accept-Language': 'en'},
                                           timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 429:
                            return
                        if response.status != 200 or not self._has_invalid_replay_badge(await response.text(), replay_id):
                            continue
                except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeError):
                    continue
                match.source_payload = {**payload, 'ArenaReplayRejection': {
                    'source': 'bfmeladder_replay_html', 'replay_id': replay_id, 'status': 'invalid',
                }}
                logger.info('Arena marked replay %s invalid; excluding it from cycle scoring', replay_id)
        db.flush()

    def _backfill_known_match_identity(
        self,
        db: Session,
        match: Match,
        replay: dict,
    ) -> bool:
        """Fill UUIDs and ranked metadata for a known replay."""
        changed = self._apply_api_replay_metadata(match, replay)
        from app.services.external_identity_service import ExternalIdentityService
        identities = ExternalIdentityService()
        for participant in match.participants:
            if not participant.player_uuid:
                player_uuid = identities.uuid_for_known_nickname(db, participant.nickname)
                if player_uuid:
                    participant.player_uuid = player_uuid
                    changed = True
        for prefix in ('winner', 'loser'):
            uuid_field = f'{prefix}_player_uuid'
            if not getattr(match, uuid_field):
                player_uuid = identities.uuid_for_known_nickname(db, getattr(match, f'{prefix}_player'))
                if player_uuid:
                    setattr(match, uuid_field, player_uuid)
                    changed = True

        players = [
            player
            for player in replay.get("Players", [])
            if not player.get("IsObserver")
        ]
        winners = [player for player in players if player.get("IsWinner")]
        losers = [player for player in players if not player.get("IsWinner")]

        def same_player(player: dict, nickname: str, player_uuid: Optional[str]) -> bool:
            external_uuid = player.get("PlayerAccountUuid")
            display_name = str(player.get("DisplayName") or "").strip()
            return bool(
                (player_uuid and external_uuid and player_uuid == external_uuid)
                or (not (player_uuid and external_uuid) and display_name
                    and display_name.casefold() == nickname.strip().casefold())
            )

        for field_prefix, nickname, player_uuid, candidates in (
            ("winner", match.winner_player, match.winner_player_uuid, winners),
            ("loser", match.loser_player, match.loser_player_uuid, losers),
        ):
            source_player = next(
                (
                    player
                    for player in candidates
                    if same_player(player, nickname, player_uuid)
                ),
                None,
            )
            if source_player:
                faction = self._normalize_faction(source_player.get("FactionName"))
                faction_field = f"{field_prefix}_faction"
                if faction and getattr(match, faction_field) != faction:
                    setattr(match, faction_field, faction)
                    changed = True

        for participant in match.participants:
            source_player = next(
                (
                    player
                    for player in players
                    if same_player(player, participant.nickname, participant.player_uuid)
                ),
                None,
            )
            if source_player:
                external_uuid = source_player.get('PlayerAccountUuid')
                if external_uuid and not participant.player_uuid:
                    participant.player_uuid = external_uuid
                    changed = True
                faction = self._normalize_faction(source_player.get("FactionName"))
                if faction and participant.faction != faction:
                    participant.faction = faction
                    changed = True

        if len(winners) == 1 and len(losers) == 1:
            winner_uuid = winners[0].get("PlayerAccountUuid")
            loser_uuid = losers[0].get("PlayerAccountUuid")
            if winner_uuid and match.winner_player_uuid != winner_uuid:
                match.winner_player_uuid = winner_uuid
                changed = True
            if loser_uuid and match.loser_player_uuid != loser_uuid:
                match.loser_player_uuid = loser_uuid
                changed = True

        if changed:
            db.commit()

        winner_uuid = match.winner_player_uuid
        loser_uuid = match.loser_player_uuid
        if not winner_uuid or not loser_uuid:
            return changed

        from app.services.user_service import UserService

        profile_service = UserService()
        profile_service.ensure_ladder_profile(
            db,
            match.winner_player,
            winner_uuid,
        )
        profile_service.ensure_ladder_profile(
            db,
            match.loser_player,
            loser_uuid,
        )
        return changed

    async def _fetch_replay_players(self, session, replay_id: str, api_item: dict):
        """Resolve names for one new replay; API exposes empty DisplayName."""
        visible_players = [
            player
            for player in api_item.get("Players", [])
            if not player.get("IsObserver") and player.get("DisplayName")
        ]
        if visible_players:
            winners = [
                (
                    player["DisplayName"],
                    player.get("FactionName"),
                    player.get("PlayerAccountUuid"),
                )
                for player in visible_players
                if player.get("IsWinner")
            ]
            losers = [
                (
                    player["DisplayName"],
                    player.get("FactionName"),
                    player.get("PlayerAccountUuid"),
                )
                for player in visible_players
                if not player.get("IsWinner")
            ]
            if winners and losers:
                await self._enrich_replay_ratings(session, api_item)
                return winners, losers

        url = f"{settings.LADDER_REPLAY_BASE}/{replay_id}"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    return [], []
                html_content = await response.text()
        except Exception as exc:
            logger.warning("Не удалось получить детали replay %s: %s", replay_id, exc)
            return [], []

        soup = BeautifulSoup(html_content, "html.parser")
        await self._enrich_replay_ratings(session, api_item, html=html_content)
        winners, losers = self._extract_team_players_from_replay_page(soup, api_item)
        if winners and losers:
            return winners, losers

        winners_section = None
        losers_section = None
        for big_text in soup.find_all("div", {"class": "bigText"}):
            text = big_text.get_text(" ", strip=True).lower()
            if "winner" in text:
                winners_section = big_text.find_parent()
            elif "loser" in text:
                losers_section = big_text.find_parent()

        winners = self._extract_players_from_section(winners_section) if winners_section else []
        losers = self._extract_players_from_section(losers_section) if losers_section else []
        if winners and losers:
            return winners, losers

        names = []
        for link in soup.select('a[href^="/u/"]'):
            name = link.get_text(" ", strip=True)
            if name and name not in names:
                names.append(name)
        api_players = [p for p in api_item.get("Players", []) if not p.get("IsObserver")]
        winners = [(name, player.get("FactionName")) for name, player in zip(names, api_players) if player.get("IsWinner")]
        losers = [(name, player.get("FactionName")) for name, player in zip(names, api_players) if not player.get("IsWinner")]
        return winners, losers

    async def _capture_match_ratings(
        self,
        session,
        replay: dict,
        winner_name: str,
        loser_name: str,
        cache: dict,
        fallback_rating: int,
    ) -> Optional[dict]:
        patch_family = get_patch_family(
            replay.get("PatchName"),
            replay.get("PatchId"),
        )
        if not patch_family:
            return None

        profile_service = self.profile_rating_service

        async def get_rating(nickname: str) -> Optional[int]:
            candidates = [p for p in replay.get('Players', []) if
                          str(p.get('DisplayName', '')).strip().casefold() == nickname.strip().casefold()]
            player_uuid = candidates[0].get('PlayerAccountUuid') if len(candidates) == 1 else None
            cache_key = (player_uuid or nickname.casefold(), patch_family)
            if cache_key not in cache:
                cache[cache_key] = await profile_service.fetch_elo(
                    session,
                    nickname,
                    patch_family,
                    player_uuid=player_uuid,
                )
            return cache[cache_key]

        winner_elo, loser_elo = await asyncio.gather(
            get_rating(winner_name),
            get_rating(loser_name),
        )
        return {
            "winner_elo": winner_elo,
            "loser_elo": loser_elo,
            "patch_family": patch_family,
            "captured_at": rating_capture_timestamp(),
            "source": "bfmeladder_current" if winner_elo is not None and loser_elo is not None else "bfmeladder_rating_incomplete",
        }

    async def _capture_team_ratings(
        self,
        session,
        replay: dict,
        winners: List[tuple],
        losers: List[tuple],
        cache: dict,
        fallback_rating: int,
    ) -> Optional[dict]:
        patch_family = get_patch_family(
            replay.get("PatchName"),
            replay.get("PatchId"),
        )
        if not patch_family:
            return None

        profile_service = self.profile_rating_service
        names = [entry[0] for entry in [*winners, *losers] if entry and entry[0]]

        entries = {entry[0].casefold(): entry for entry in [*winners, *losers]}

        async def get_rating(nickname: str) -> Optional[int]:
            entry = entries[nickname.casefold()]
            player_uuid = entry[2] if len(entry) > 2 else None
            cache_key = (player_uuid or nickname.casefold(), patch_family)
            if cache_key not in cache:
                cache[cache_key] = await profile_service.fetch_elo(
                    session,
                    nickname,
                    patch_family,
                    player_uuid=player_uuid,
                )
            return cache[cache_key]

        values = await asyncio.gather(*(get_rating(name) for name in names))
        participant_ratings = {
            name.casefold(): rating
            for name, rating in zip(names, values)
        }
        winner_values = [participant_ratings[entry[0].casefold()] for entry in winners]
        loser_values = [participant_ratings[entry[0].casefold()] for entry in losers]
        return {
            "winner_elo": sum(winner_values) / len(winner_values) if winner_values and all(v is not None for v in winner_values) else None,
            "loser_elo": sum(loser_values) / len(loser_values) if loser_values and all(v is not None for v in loser_values) else None,
            "participant_ratings": participant_ratings,
            "patch_family": patch_family,
            "captured_at": rating_capture_timestamp(),
            "source": "bfmeladder_current" if all(v is not None for v in values) else "bfmeladder_rating_incomplete",
        }

    def _extract_team_players_from_replay_page(self, soup, api_item: dict):
        """Bind visible nicknames to API results through Team N winner/loser cards."""
        api_by_team = {}
        for player in api_item.get("Players", []):
            if player.get("IsObserver"):
                continue
            api_by_team.setdefault(player.get("Team"), []).append(player)

        winners = []
        losers = []
        for status_text in soup.find_all(string=lambda value: value and value.strip().lower() in {"winners", "losers"}):
            status = status_text.strip().lower()
            status_element = status_text.parent
            header = status_element.parent if status_element else None
            card = header.parent if header else None
            if not card:
                continue

            team_match = re.search(r"Team\s+(-?\d+)", header.get_text(" ", strip=True), re.IGNORECASE)
            if not team_match:
                continue
            team_id = int(team_match.group(1))
            expected_winner = status == "winners"
            api_players = api_by_team.get(team_id, [])
            links = card.select('a[href^="/u/"]')
            if api_players and any(bool(player.get("IsWinner")) != expected_winner for player in api_players):
                logger.warning(
                    "Replay page and API disagree about Team %s result; replay skipped",
                    team_id,
                )
                return [], []

            for index, link in enumerate(links):
                nickname = link.get_text(" ", strip=True)
                if not nickname:
                    continue
                api_player = api_players[index] if index < len(api_players) else None
                row = link.find_parent("div")
                row_texts = list(row.stripped_strings) if row else []
                faction = row_texts[1] if len(row_texts) > 1 else None
                if not faction and api_player:
                    faction = api_player.get("FactionName")
                external_uuid = None
                if api_player:
                    external_uuid = (
                        api_player.get("PlayerAccountUuid")
                        or api_player.get("PlayerAccountUUID")
                    )
                (winners if expected_winner else losers).append(
                    (nickname, faction, external_uuid)
                )

        return winners, losers

    async def fetch_and_save_matches_from_api(
        self,
        db: Session,
        new_limit: int = 15,
        *,
        gamemodes: Optional[set[str]] = None,
        start_override_ms: Optional[int] = None,
        end_override_ms: Optional[int] = None,
        advance_cursor: bool = True,
        max_per_mode: Optional[int] = None,
        player_query: Optional[str] = None,
        full_player_history: bool = False,
    ) -> int:
        """Загружает матчи и подтверждает полный обход только после успешного сохранения."""
        self.last_completed_scan = None
        self._pending_public_scan = None
        if full_player_history and not (player_query or "").strip():
            raise ValueError("A player query is required for a full history import")
        pending_war_start = None
        campaign_scan = advance_cursor and not player_query and not gamemodes and max_per_mode is None
        scan_end_ms = None
        if campaign_scan:
            campaign = CampaignSettingsService().get_or_create(db)
            scan_end_ms = end_override_ms if end_override_ms is not None else int(utc_now().timestamp() * 1000)
            fallback_start = scan_end_ms - settings.LADDER_SYNC_WINDOW_HOURS * 3600 * 1000
            heartbeat = db.get(WorkerHeartbeat, "campaign")
            if heartbeat and heartbeat.replay_synced_through_at:
                fallback_start = min(fallback_start, int(as_utc(heartbeat.replay_synced_through_at).timestamp() * 1000))
            if campaign.replay_cursor_ms is None and start_override_ms is None:
                last_saved = db.query(Match.match_date).filter(
                    Match.is_live.is_(False), Match.match_id.isnot(None),
                    Match.match_date <= datetime.fromtimestamp(scan_end_ms / 1000, tz=timezone.utc)
                ).order_by(Match.match_date.desc()).limit(1).scalar()
                if last_saved is not None:
                    fallback_start = min(fallback_start, int(as_utc(last_saved).timestamp() * 1000))
            if start_override_ms is None:
                start_override_ms = max(
                    0,
                    int(campaign.replay_cursor_ms if campaign.replay_cursor_ms is not None else fallback_start)
                    - settings.LADDER_SYNC_OVERLAP_MINUTES * 60 * 1000,
                )
            end_override_ms = scan_end_ms
            pending_war_start = db.query(ClanWar.started_at).filter(
                ClanWar.status == "active",
            ).order_by(ClanWar.started_at).limit(1).scalar()
        finalization_scan = pending_war_start is not None
        if finalization_scan:
            war_start_ms = int(as_utc(pending_war_start).timestamp() * 1000)
            start_override_ms = min(start_override_ms, war_start_ms) if start_override_ms is not None else war_start_ms
        if campaign_scan:
            # A global cursor cannot discard late evidence for an unsettled cycle.
            pending_cycles = db.query(CampaignCycleRecord, CampaignSeason).join(
                CampaignSeason, CampaignSeason.id == CampaignCycleRecord.season_id).filter(
                CampaignSeason.status == 'active',
                CampaignCycleRecord.settled_at.is_(None),
                CampaignCycleRecord.orders_frozen_at.isnot(None)).all()
            for cycle, season in pending_cycles:
                if (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
                    continue
                battle_ms = int((as_utc(cycle.preparation_at) + timedelta(hours=24)).timestamp() * 1000)
                start_override_ms = min(start_override_ms, battle_ms)
        complete_scan = full_player_history or finalization_scan or campaign_scan
        import_errors = 0
        connector = ProxyConnector.from_url(self.proxy) if self.proxy else aiohttp.TCPConnector()
        timeout = aiohttp.ClientTimeout(total=90, connect=20)
        scan_limit = (
            None
            if complete_scan
            else max(new_limit, getattr(settings, "LADDER_API_SCAN_LIMIT", 500))
        )
        patch_window = max(1, getattr(settings, "LADDER_API_PATCH_WINDOW", 3))
        patch_keys = []
        saved_count = 0
        backfilled_count = 0
        known_relevant = 0
        profile_rating_cache = {}
        rule_snapshot = CampaignRuleService().get_active(db)
        fallback_rating = int(rule_snapshot.values["ELO_START_RATING"])
        active_patch_families = CampaignSettingsService().active_patch_families(db)
        sync_states = ReplaySyncStateService()
        replay_storage = ReplayStorageService()
        map_preview_storage = MapPreviewStorageService()
        map_preview_attempts = set()
        replay_backfill_count = 0

        try:
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                replay_items = await self._load_api_replays(
                    session,
                    db,
                    scan_limit,
                    gamemodes=gamemodes,
                    start_override_ms=start_override_ms,
                    end_override_ms=end_override_ms,
                    advance_cursor=advance_cursor,
                    max_per_mode=max_per_mode,
                    player_query=player_query,
                    force_html=full_player_history,
                    paginate_html=complete_scan,
                )
                known_matches = self._known_matches_for_replay_ids(
                    db,
                    replay_items,
                )
                known_ids = set(known_matches)
                await self._enrich_cycle_replay_ratings(session, db, replay_items, known_matches)
                using_public_api = bool(
                    settings.LADDER_PUBLIC_API_ENABLED
                    and settings.LADDER_PUBLIC_API_TOKEN.strip()
                )
                for match_id, replay in replay_items:
                        if not self._api_replay_matches_filters(replay):
                            continue
                        patch_family = get_patch_family(
                            replay.get("PatchName"),
                            replay.get("PatchId"),
                        )
                        patch_name = replay.get("PatchName") or replay.get("PatchId")
                        if not patch_family:
                            sync_states.record(
                                db,
                                match_id,
                                "skipped",
                                patch_name=patch_name,
                                reason="Патч replay не поддерживается кампанией",
                            )
                            continue
                        if patch_family not in active_patch_families:
                            sync_states.record(
                                db,
                                match_id,
                                "skipped",
                                patch_family=patch_family,
                                patch_name=patch_name,
                                reason="Патч отключен в настройках текущего сезона",
                            )
                            continue
                        patch_key = replay.get("PatchId") or replay.get("PatchName") or "unknown"
                        if (
                            patch_key not in patch_keys
                            and (complete_scan or len(patch_keys) < patch_window)
                        ):
                            patch_keys.append(patch_key)
                        if not complete_scan and patch_key not in patch_keys:
                            continue
                        if match_id not in known_ids and self._is_cancelled_public_replay(replay):
                            sync_states.record(db, match_id, "skipped", patch_family=patch_family,
                                patch_name=patch_name, reason="Арена: нулевая длительность и нет победителя")
                            continue
                        if match_id in known_ids:
                            known_match = known_matches[match_id]
                            try:
                                if self._backfill_known_match_identity(
                                    db,
                                    known_match,
                                    replay,
                                ):
                                    backfilled_count += 1
                            except Exception as identity_error:
                                import_errors += 1
                                db.rollback()
                                logger.warning(
                                    "Не удалось дополнить UUID replay %s: %s",
                                    match_id,
                                    identity_error,
                                )
                            if (
                                known_match.winner_elo is None
                                or known_match.loser_elo is None
                                or known_match.rating_patch_family is None
                            ):
                                stored_players = [p for p in known_match.participants or [] if not p.is_observer]
                                winners = [(p.nickname, p.faction, p.player_uuid) for p in stored_players if p.is_winner]
                                losers = [(p.nickname, p.faction, p.player_uuid) for p in stored_players if not p.is_winner]
                                if not winners or not losers:
                                    winners = [(known_match.winner_player, known_match.winner_faction, known_match.winner_player_uuid)]
                                    losers = [(known_match.loser_player, known_match.loser_faction, known_match.loser_player_uuid)]
                                rating_snapshot = await self._capture_team_ratings(
                                    session,
                                    replay,
                                    winners,
                                    losers,
                                    profile_rating_cache,
                                    fallback_rating,
                                )
                                if rating_snapshot:
                                    if known_match.winner_elo is None:
                                        known_match.winner_elo = rating_snapshot["winner_elo"]
                                    if known_match.loser_elo is None:
                                        known_match.loser_elo = rating_snapshot["loser_elo"]
                                    for participant in stored_players:
                                        if participant.elo is None:
                                            participant.elo = rating_snapshot['participant_ratings'].get(participant.nickname.casefold())
                                    known_match.rating_patch_family = rating_snapshot["patch_family"]
                                    known_match.ratings_captured_at = rating_snapshot["captured_at"]
                                    known_match.rating_source = rating_snapshot['source']
                                    db.commit()
                            ClanWarService().record_match_result(
                                db,
                                known_match.winner_player,
                                known_match.loser_player,
                                known_match.match_date,
                                match=known_match,
                            )
                            sync_states.record(
                                db,
                                match_id,
                                "known",
                                patch_family=patch_family,
                                patch_name=patch_name,
                            )
                            map_key = map_preview_storage.map_key(
                                known_match.map_name,
                            )
                            if map_key and map_key not in map_preview_attempts:
                                map_preview_attempts.add(map_key)
                                await map_preview_storage.download_match(
                                    known_match,
                                    session,
                                )
                            if (
                                known_match.replay_download_status != "downloaded"
                                and replay_backfill_count
                                < max(0, settings.REPLAY_BACKFILL_PER_SYNC)
                            ):
                                replay_backfill_count += 1
                                await replay_storage.download_match(
                                    db,
                                    known_match,
                                    session,
                                )
                            known_relevant += 1
                            if (
                                not complete_scan
                                and not using_public_api
                                and
                                known_relevant >= max(3, new_limit)
                                and len(patch_keys) >= patch_window
                            ):
                                break
                            continue
                        if (
                            not complete_scan
                            and not using_public_api
                            and saved_count >= new_limit
                        ):
                            break

                        players = [p for p in replay.get("Players", []) if not p.get("IsObserver")]
                        if not any(p.get("IsWinner") for p in players) or not any(not p.get("IsWinner") for p in players):
                            import_errors += 1
                            sync_states.record(
                                db,
                                match_id,
                                "error",
                                patch_family=patch_family,
                                patch_name=patch_name,
                                reason="Источник не указал победителя и проигравшего",
                            )
                            continue
                        winners, losers = await self._fetch_replay_players(session, match_id, replay)
                        if not winners or not losers:
                            import_errors += 1
                            logger.warning("Пропущен API replay %s: не удалось определить реальные ники", match_id)
                            sync_states.record(
                                db,
                                match_id,
                                "error",
                                patch_family=patch_family,
                                patch_name=patch_name,
                                reason="Не удалось определить реальные ники игроков",
                            )
                            continue

                        from app.services.external_identity_service import ExternalIdentityService
                        identity_service = ExternalIdentityService()
                        def with_uuid(entries):
                            return [(entry[0], entry[1],
                                     (entry[2] if len(entry) > 2 else None)
                                     or identity_service.uuid_for_known_nickname(db, entry[0]))
                                    for entry in entries]
                        winners, losers = with_uuid(winners), with_uuid(losers)
                        rating_snapshot = await self._capture_team_ratings(
                            session,
                            replay,
                            winners,
                            losers,
                            profile_rating_cache,
                            fallback_rating,
                        )
                        participant_rows = self._build_participant_rows(
                            replay,
                            winners,
                            losers,
                            rating_snapshot,
                        )

                        saved = self._save_match_to_db(
                            db=db,
                            match_id=match_id,
                            winner_players=winners,
                            loser_players=losers,
                            match_date=str(replay.get("Date", "")),
                            duration=replay.get("Duration"),
                            map_name=replay.get("MapName"),
                            patch_version=replay.get("PatchName") or replay.get("PatchId"),
                            game_mode=replay.get("GamemodeName") or self.gamemode,
                            api_metadata=replay,
                            rating_snapshot=rating_snapshot,
                            participant_rows=participant_rows,
                        )
                        if saved:
                            saved_count += 1
                            known_ids.add(match_id)
                            sync_states.record(
                                db,
                                match_id,
                                "imported",
                                patch_family=patch_family,
                                patch_name=patch_name,
                            )
                            saved_match = (
                                db.query(Match)
                                .filter(Match.match_id == match_id)
                                .first()
                            )
                            if saved_match is not None:
                                known_matches[match_id] = saved_match
                                map_key = map_preview_storage.map_key(
                                    saved_match.map_name,
                                )
                                if map_key and map_key not in map_preview_attempts:
                                    map_preview_attempts.add(map_key)
                                    await map_preview_storage.download_match(
                                        saved_match,
                                        session,
                                    )
                                await replay_storage.download_match(
                                    db,
                                    saved_match,
                                    session,
                                )
                        else:
                            import_errors += 1
                            sync_states.record(
                                db,
                                match_id,
                                "error",
                                patch_family=patch_family,
                                patch_name=patch_name,
                                reason="Replay прошел проверку, но матч не был сохранен",
                            )
                        await asyncio.sleep(0.15)
                if not import_errors and campaign_scan:
                    await self._check_old_html_rejections(session, db, self._pending_public_scan, utc_now())

            if import_errors:
                db.commit()  # Persist per-replay diagnostics, without advancing the cursor.
                raise ReplaySourceError(f"Replay scan has {import_errors} unprocessed replay(s)")
            if campaign_scan or self._pending_public_cursor_ms is not None:
                campaign = CampaignSettingsService().get_or_create(db)
                campaign.replay_cursor_ms = max(
                    campaign.replay_cursor_ms or 0,
                    scan_end_ms if campaign_scan else self._pending_public_cursor_ms,
                )
            db.commit()
            if campaign_scan and 'ennorath' in active_patch_families:
                self.last_completed_scan = self._pending_public_scan
            logger.info(
                "Синхронизация replay: источник %s, просмотрено %s, добавлено %s матчей, UUID дополнено у %s, патчи окна: %s",
                self.last_source,
                self.last_scanned_count,
                saved_count,
                backfilled_count,
                patch_keys,
            )
            return saved_count
        except Exception as exc:
            self.last_completed_scan = None
            self._pending_public_scan = None
            db.rollback()
            if not isinstance(exc, ReplayRateLimited):
                logger.exception("Ошибка синхронизации replay: %s", exc)
            raise

    async def fetch_and_save_player_history(
        self,
        db: Session,
        player_query: str,
    ) -> int:
        """Import every eligible replay exposed by Arena for one player."""
        clean_query = str(player_query or "").strip()
        if not clean_query:
            raise ValueError("A player query is required for a full history import")
        return await self.fetch_and_save_matches_from_api(
            db,
            new_limit=1,
            advance_cursor=False,
            player_query=clean_query,
            full_player_history=True,
        )

    async def fetch_and_save_matches(self, db: Session, limit: int = 300) -> int:
        return await self.fetch_and_save_matches_from_api(db, new_limit=min(limit, 15))
        """Получает матчи с bfmeladder.com и сохраняет их в базу данных"""
        try:
            connector = ProxyConnector.from_url(self.proxy) if self.proxy else aiohttp.TCPConnector()
            timeout = aiohttp.ClientTimeout(total=60)
            
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                # Параметры запроса
                params = {
                    'game': self.game,
                    'patch': self.patch,
                    'gamemode': self.gamemode,
                    'page': 1,
                    'limit': limit
                }
                
                url = f"{self.ladder_base}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
                
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка HTTP {response.status}: {response.reason}")
                        return 0
                    
                    html_content = await response.text()
                    
                    # Парсим HTML для извлечения данных о реплеях
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Ищем карточки реплеев
                    replay_items = soup.find_all('div', {'class': 'replayItem'})
                    if not replay_items:
                        logger.warning("Карточки реплеев не найдены")
                        return 0
                    
                    saved_count = 0
                    logger.info(f"Найдено {len(replay_items)} реплеев для обработки")
                    
                    # Парсим каждую карточку реплея
                    for replay_item in replay_items:
                        try:
                            # Получаем ID матча из атрибута id элемента
                            match_id = replay_item.get('id', '')
                            if not match_id:
                                continue
                            
                            # Проверяем, не является ли матч LIVE
                            live_link = replay_item.find('a', string='LIVE')
                            is_live = live_link is not None
                            if is_live:
                                continue
                            
                            # Извлекаем дату матча
                            date_element = replay_item.find('div', {'class': 'unixDate'})
                            if date_element:
                                match_date = date_element.get_text(strip=True)
                            else:
                                match_date = "Неизвестно"
                            
                            # Ищем секции Winners и Losers
                            winners_section = None
                            losers_section = None
                            
                            # Находим текст "Winners" и "Losers"
                            big_texts = replay_item.find_all('div', {'class': 'bigText'})
                            for big_text in big_texts:
                                if 'Winners' in big_text.get_text():
                                    winners_section = big_text.find_parent()
                                elif 'Losers' in big_text.get_text():
                                    losers_section = big_text.find_parent()
                            
                            if not winners_section or not losers_section:
                                continue
                            
                            # Извлекаем игроков и их фракции
                            winner_players = self._extract_players_from_section(winners_section)
                            loser_players = self._extract_players_from_section(losers_section)
                            
                            # Извлекаем дополнительную информацию о матче
                            duration = self._extract_duration(replay_item)
                            map_name = self._extract_map_name(replay_item)
                            
                            # Сохраняем матч в базу данных
                            saved = self._save_match_to_db(
                                db=db,
                                match_id=match_id,
                                winner_players=winner_players,
                                loser_players=loser_players,
                                match_date=match_date,
                                duration=duration,
                                map_name=map_name,
                                is_live=is_live
                            )
                            if saved:
                                saved_count += 1
                                
                        except Exception as e:
                            logger.warning(f"Ошибка парсинга карточки реплея: {e}")
                            continue
                    
                    logger.info(f"Успешно сохранено {saved_count} новых матчей")
                    return saved_count
                    
        except Exception as e:
            logger.error(f"Ошибка при получении матчей: {e}")
            return 0

    async def get_live_matches(self) -> List[Dict]:
        """Получает LIVE матчи с bfmeladder.com"""
        try:
            connector = ProxyConnector.from_url(self.proxy) if self.proxy else aiohttp.TCPConnector()
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                # Параметры запроса
                params = {
                    'game': self.game,
                    'patch': self.patch,
                    'gamemode': self.gamemode,
                    'page': 1,
                    'limit': 50
                }
                
                url = f"{self.ladder_base}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
                
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка HTTP {response.status}: {response.reason}")
                        return []
                    
                    html_content = await response.text()
                    
                    # Парсим HTML для извлечения LIVE матчей
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Ищем карточки реплеев
                    replay_items = soup.find_all('div', {'class': 'replayItem'})
                    
                    if not replay_items:
                        logger.warning("Карточки реплеев не найдены")
                        return []
                    
                    live_matches = []
                    
                    logger.info(f"Найдено {len(replay_items)} реплеев для поиска LIVE матчей")
                    
                    # Парсим каждую карточку реплея
                    live_count = 0
                    for i, replay_item in enumerate(replay_items):
                        try:
                            # Получаем ID матча из атрибута id элемента
                            match_id = replay_item.get('id', '')
                            if not match_id:
                                continue
                            
                            # Проверяем, является ли матч LIVE
                            live_link = replay_item.find('a', string='LIVE')
                            is_live = live_link is not None
                            
                            if is_live:
                                live_count += 1
                            
                            if not is_live:
                                continue  # Пропускаем не LIVE матчи
                            
                            # Извлекаем дату матча
                            date_element = replay_item.find('div', {'class': 'unixDate'})
                            if date_element:
                                match_date = date_element.get_text(strip=True)
                                match_datetime = self._parse_match_date(match_date)
                            else:
                                match_datetime = datetime.now()
                            
                            # Для LIVE матчей структура отличается - ищем игроков напрямую
                            
                            # Ищем всех игроков в матче (для LIVE матчей может быть 2+ игроков)
                            all_players = []
                            
                            # Ищем контейнеры с игроками
                            player_containers = replay_item.find_all('div', style=lambda x: x and 'align-items: center' in x)
                            
                            for container in player_containers:
                                try:
                                    # Ищем имя игрока
                                    player_name_div = container.find('div', style=lambda x: x and 'font-weight: 800' in x)
                                    if not player_name_div:
                                        continue
                                    
                                    # Ищем иконку армии
                                    army_icon = player_name_div.find('img', {'class': 'armyIcon'})
                                    if not army_icon:
                                        continue
                                    
                                    # Извлекаем имя игрока
                                    player_name = player_name_div.get_text(strip=True)
                                    
                                    # Определяем фракцию по иконке
                                    faction = self._get_faction_from_icon_url(army_icon.get('src', ''))
                                    if faction:
                                        all_players.append((player_name, faction))
                                        
                                except Exception as e:
                                    logger.warning(f"Ошибка извлечения игрока: {e}")
                                    continue
                            
                            # Для LIVE матчей нужно минимум 2 игрока
                            if len(all_players) < 2:
                                continue
                            
                            # Берем первых двух игроков как участников матча
                            player1_name, player1_faction = all_players[0]
                            player2_name, player2_faction = all_players[1]
                            
                            # Извлекаем дополнительную информацию о матче
                            duration = self._extract_duration(replay_item)
                            map_name = self._extract_map_name(replay_item)
                            
                            # Добавляем в список LIVE матчей
                            live_matches.append({
                                'id': match_id,
                                'player1': player1_name,
                                'player1_faction': self.factions.get(player1_faction, player1_faction),
                                'player2': player2_name,
                                'player2_faction': self.factions.get(player2_faction, player2_faction),
                                'match_date': match_datetime.isoformat() if match_datetime else datetime.now().isoformat(),
                                'duration': duration,
                                'map_name': map_name,
                                'game_mode': self.gamemode,
                                'patch_version': self.patch,
                                'is_live': True
                            })
                                
                        except Exception as e:
                            logger.warning(f"Ошибка парсинга LIVE матча: {e}")
                            continue
                    
                    logger.info(f"Найдено {len(live_matches)} LIVE матчей")
                    return live_matches
                    
        except Exception as e:
            logger.error(f"Ошибка при получении LIVE матчей: {e}")
            return []

# Глобальный экземпляр сервиса
ladder_service = BFMELadderService() 
