"""Читает рейтинг до игры из реплея и связывает его с UUID публичного API.

Ник и порядок строк не участвуют в сопоставлении. Места в таблице нужны только
для однозначного соединения строк внутри одной команды конкретного реплея.
"""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import re
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from bs4 import BeautifulSoup

from app.services.elo_service import get_patch_family
from app.services.match_eligibility_service import RANKED_MODE_TEAM_SIZES


_FIELDS = {'schema', 'source', 'rating_reference', 'replay_id', 'patch_family',
           'raw_fingerprint', 'players'}
_PLAYER_FIELDS = {'uuid', 'team', 'old_rank', 'new_rank', 'before', 'after'}


def _integer(value, minimum=0):
    return type(value) is int and minimum <= value <= 2**53 - 1


def _rank_pair(old, new):
    return (_integer(old, 1) or type(old) is int and old == -1) and _integer(new, 1)


def _facts(raw):
    if not isinstance(raw, dict) or raw.get('gameName') != 'RotWK':
        raise ValueError('Нужен исходный ответ реплея RotWK')
    replay_id = raw.get('replayId')
    if not isinstance(replay_id, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}', replay_id) or '..' in replay_id:
        raise ValueError('Некорректный идентификатор реплея')
    name, patch_id = raw.get('patchName'), raw.get('patchId')
    if not isinstance(name, str) or patch_id is not None and not isinstance(patch_id, str):
        raise ValueError('Не указан патч реплея')
    family = get_patch_family(name)
    id_family = get_patch_family(None, patch_id)
    if family is None or id_family is not None and id_family != family:
        raise ValueError('Неизвестный или противоречивый патч')
    mode = raw.get('gamemode')
    size = RANKED_MODE_TEAM_SIZES.get(mode) if isinstance(mode, str) else None
    date, duration = raw.get('date'), raw.get('duration')
    if (not size or not _integer(date) or not isinstance(duration, str)
            or not re.fullmatch(r'[0-9]{1,6}:(?:[0-5][0-9]:)?[0-5][0-9]', duration)):
        raise ValueError('Нужны режим, время начала и длительность игры')
    try:
        datetime.fromtimestamp(date / 1000, tz=timezone.utc)
    except (ValueError, OverflowError, OSError) as error:
        raise ValueError('Некорректная дата реплея') from error
    source_players = raw.get('players')
    if not isinstance(source_players, list) or len(source_players) > 64:
        raise ValueError('Нужен полный состав игроков')
    players, identities, signatures, results = [], set(), set(), {}
    for source in source_players:
        if not isinstance(source, dict) or type(source.get('isObserver', False)) is not bool:
            raise ValueError('Некорректная запись участника')
        if source.get('isObserver', False):
            continue
        try:
            identity = str(UUID(source.get('uuid')))
        except (ValueError, AttributeError, TypeError) as error:
            raise ValueError('Нужен UUID участника Арены') from error
        team, win = source.get('team'), source.get('isWinner')
        old, new = source.get('oldRank'), source.get('newRank')
        if not _integer(team) or type(win) is not bool or not _rank_pair(old, new):
            raise ValueError('Нужны команда, исход и места игрока')
        signature = team, win, old, new
        if identity in identities or signature in signatures or team in results and results[team] != win:
            raise ValueError('Неоднозначные участники реплея')
        identities.add(identity)
        signatures.add(signature)
        results[team] = win
        players.append(dict(uuid=identity, team=team, isWinner=win, oldRank=old, newRank=new))
    if len(results) != 2 or set(results.values()) != {True, False} or set(Counter(p['team'] for p in players).values()) != {size}:
        raise ValueError('Нужны две полные команды с известным исходом')
    facts = {key: raw.get(key) for key in ('replayId', 'gameName', 'patchId', 'patchName',
             'arenaId', 'gamemode', 'date', 'duration')}
    if facts['arenaId'] is not None and not isinstance(facts['arenaId'], str):
        raise ValueError('Некорректная арена')
    facts['players'] = sorted(players, key=lambda p: p['uuid'])
    return facts, family


def _digest(facts):
    return hashlib.sha256(json.dumps(facts, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _patch_matches(label, raw):
    if get_patch_family(label) != get_patch_family(raw['patchName']):
        return False
    # Если API сообщает версию, нельзя принимать страницу другой версии патча.
    version = re.search(r'\(([^()]+)\)', raw['patchName'])
    if version is None and raw.get('patchId') and ':' in raw['patchId']:
        version_text = raw['patchId'].rsplit(':', 1)[1]
    else:
        version_text = version.group(1) if version else None
    return version_text is None or re.search(r'\(' + re.escape(version_text) + r'\)', label) is not None


class ArenaReplayRatingService:
    @staticmethod
    def fingerprint(raw):
        facts, _ = _facts(raw)
        return _digest(facts)

    @staticmethod
    def read(evidence, raw):
        """Повторно проверяет сохранённое свидетельство; ничего не исправляет по догадке."""
        try:
            facts, family = _facts(raw)
            if (not isinstance(evidence, dict) or set(evidence) != _FIELDS
                    or type(evidence['schema']) is not int or evidence['schema'] != 1
                    or evidence['source'] != 'bfmeladder_replay_html'
                    or evidence['rating_reference'] != 'arena_replay_before'
                    or evidence['replay_id'] != facts['replayId'] or evidence['patch_family'] != family
                    or evidence['raw_fingerprint'] != _digest(facts)):
                return {}
            rows = evidence['players']
            if not isinstance(rows, list) or len(rows) != len(facts['players']):
                return {}
            source = {p['uuid']: p for p in facts['players']}
            ratings = {}
            for row in rows:
                if not isinstance(row, dict) or set(row) != _PLAYER_FIELDS:
                    return {}
                identity = row['uuid']
                if not isinstance(identity, str) or identity not in source or identity in ratings:
                    return {}
                player = source[identity]
                if (not _integer(row['team']) or not _rank_pair(row['old_rank'], row['new_rank'])
                        or not _integer(row['before'])
                        or not _integer(row['after']) or row['team'] != player['team']
                        or row['old_rank'] != player['oldRank'] or row['new_rank'] != player['newRank']
                        or (row['after'] - row['before']) * (1 if player['isWinner'] else -1) < 0):
                    return {}
                ratings[identity] = row['before']
            return ratings
        except (ValueError, TypeError, AttributeError, KeyError, OverflowError):
            return {}

    @staticmethod
    def parse(html, raw):
        """Принимает только полную страницу и однозначное соответствие всех UUID."""
        try:
            facts, family = _facts(raw)
            if not isinstance(html, str) or not html or len(html) > 4_000_000:
                return None
            for tag in ('html', 'body', 'main'):
                if re.search(r'<' + tag + r'(?:\s|>)', html, re.I) and not re.search(r'</' + tag + r'\s*>', html, re.I):
                    return None
            soup = BeautifulSoup(html, 'html.parser')
            headings = soup.find_all('h1')
            if len(headings) != 1:
                return None
            contexts = headings[0].parent.find_all('p', recursive=False)
            if len(contexts) != 1:
                return None
            tags = contexts[0].find_all(recursive=False)
            if tags and (len(tags) != 1 or tags[0].name != 'span'
                         or tags[0].get_text(strip=True) != 'Ranked'):
                return None
            context = [part.strip() for part in ''.join(
                contexts[0].find_all(string=True, recursive=False)).split('·')]
            if (len(context) < 3 or context[3:] not in ([], ['Solo queue']) or context[0] != facts['gameName']
                    or context[2] != facts['gamemode'] or not _patch_matches(context[1], raw)):
                return None
            downloads = [parse_qs(urlparse(link.get('href', '')).query).get('replayId')
                         for link in soup.find_all('a', href=True)
                         if urlparse(link['href']).path == '/api/replays/download']
            if not downloads or any(ids != [facts['replayId']] for ids in downloads):
                return None
            source = {(p['team'], p['isWinner'], p['oldRank'], p['newRank']): p for p in facts['players']}
            teams, players = set(), {}
            for team_span in soup.find_all('span', string=re.compile(r'^Team [0-9]+$')):
                team = int(team_span.get_text().split()[1])
                header, card = team_span.parent, team_span.parent.parent
                if header.name != 'div' or card.name != 'div' or team in teams:
                    return None
                header_text = header.get_text(' ', strip=True)
                result = re.fullmatch(r'Team [0-9]+\s*(?:·\s*)?(Winners|Losers)', header_text)
                children = card.find_all('div', recursive=False)
                if result is None or not children or children[0] is not header:
                    return None
                win = result.group(1) == 'Winners'
                teams.add(team)
                for row in children[1:]:
                    links, ratings = row.select('a[href^="/u/"]'), row.select('.rx')
                    if (len(links) != 1 or len(ratings) != 1 or row.find('div') is not None
                            or links[0].parent.parent is not row or ratings[0].parent.name != 'span'):
                        return None
                    rating = ratings[0]
                    buttons, tooltips = rating.select('.rx-btn'), rating.select('.rx-pop')
                    if len(buttons) != 1 or len(tooltips) != 1:
                        return None
                    delta = re.fullmatch(r'([+\-−]?[0-9]+) ELO', buttons[0].get_text(' ', strip=True))
                    rank_texts = [span.get_text(' ', strip=True) for span in rating.parent.find_all('span', recursive=False)
                                  if span is not rating and re.search(r'\brank\b', span.get_text(' ', strip=True), re.I)]
                    rank_pairs = [re.fullmatch(r'rank ([0-9]+)\s*→\s*([0-9]+)', text) for text in rank_texts]
                    if any(pair is None for pair in rank_pairs):
                        return None
                    if delta is None or len(rank_pairs) > 1:
                        return None
                    values = {}
                    for item in tooltips[0].find_all('li'):
                        text = item.get_text(' ', strip=True)
                        if text.startswith(('Rating before:', 'Rating after:')):
                            value = re.fullmatch(r'Rating (before|after): ([0-9]+)', text)
                            if value is None or value.group(1) in values:
                                return None
                            values[value.group(1)] = int(value.group(2))
                    if set(values) != {'before', 'after'} or values['after'] - values['before'] != int(delta.group(1).replace('−', '-')):
                        return None
                    if rank_pairs:
                        old, new = map(int, rank_pairs[0].groups())
                        player = source.get((team, win, old, new))
                    else:
                        # Арена скрывает прежнее место -1 и неизменившееся место. Допустим только
                        # единственный такой участник команды, без угадывания по нику.
                        candidates = [p for p in source.values() if p['team'] == team
                            and p['isWinner'] == win and p['oldRank'] in (-1, p['newRank'])]
                        player = candidates[0] if len(candidates) == 1 else None
                        old, new = (player['oldRank'], player['newRank']) if player else (None, None)
                    if player is None or player['uuid'] in players:
                        return None
                    players[player['uuid']] = dict(uuid=player['uuid'], team=team, old_rank=old, new_rank=new, **values)
            if len(teams) != 2 or len(players) != len(source):
                return None
            evidence = dict(schema=1, source='bfmeladder_replay_html', rating_reference='arena_replay_before',
                replay_id=facts['replayId'], patch_family=family, raw_fingerprint=_digest(facts),
                players=[players[key] for key in sorted(players)])
            return evidence if ArenaReplayRatingService.read(evidence, raw) else None
        except (ValueError, TypeError, AttributeError, KeyError, OverflowError):
            return None
