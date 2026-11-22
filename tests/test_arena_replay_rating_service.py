from copy import deepcopy
from importlib.util import find_spec
from uuid import UUID

import pytest


RID = 'd5cf039b-c149-438c-b695-e57013974fdc.BfME2Replay'
RID_2 = '420e8641-0903-4b30-afb2-9cde85994685.BfME2Replay'
WINNER = 'e2ed47fa-53b5-4313-9f3b-b3cb50d38589'
LOSER = '0ed4c890-0bb1-43e0-a1af-68b695976054'
SECOND_WINNER = 'ed2ea846-06b7-4695-998b-dc9e5f171e2f'
FIRST_LOSER = '0cc1f78b-939a-4005-9ce6-d997cbdcd9a5'
SECOND_LOSER = '0a255cab-8b3a-497f-8863-714a8d049337'


def service():
    assert find_spec('app.services.arena_replay_rating_service') is not None
    from app.services.arena_replay_rating_service import ArenaReplayRatingService
    return ArenaReplayRatingService


def raw_1v1():
    return dict(replayId=RID, gameName='RotWK', patchId='ennorath:1.9.7.7d',
        patchName='Ennorath (1.9.7.7d)', arenaId='rotwk-ennorath',
        gamemode='1 versus 1', date=1792400000000, duration='00:10:00',
        players=[dict(uuid=WINNER, team=0, isWinner=True, oldRank=34, newRank=31),
                 dict(uuid=LOSER, team=1, isWinner=False, oldRank=25, newRank=27)])


def raw_2v2():
    raw = raw_1v1()
    raw.update(replayId=RID_2, gamemode='2 versus 2', players=[
        dict(uuid=LOSER, team=0, isWinner=True, oldRank=115, newRank=104),
        dict(uuid=SECOND_WINNER, team=0, isWinner=True, oldRank=2, newRank=2),
        dict(uuid=FIRST_LOSER, team=1, isWinner=False, oldRank=58, newRank=105),
        dict(uuid=SECOND_LOSER, team=1, isWinner=False, oldRank=133, newRank=133)])
    return raw


def row(old, new, before, after, name='Same visible name'):
    delta = after - before
    return (f'<div><span><a href="/u/unrelated-name">{name}</a></span>'
        f'<span><span>rank {old} &rarr; {new}</span> '
        f'<span class="rx"><button class="rx-btn"><span>{delta:+d} ELO</span></button>'
        f'<span class="rx-pop"><strong>How this was worked out</strong><ul>'
        f'<li>Rating before: {before}</li><li>Opponent rating: 1101.</li>'
        f'<li>Rating after: {after}</li></ul></span></span></span></div>')


def page(raw, rows=None, reverse=False):
    if rows is None:
        rows = {0: [row(34, 31, 1079, 1088)], 1: [row(25, 27, 1101, 1092)]}
    teams = list(rows)
    if reverse:
        teams.reverse()
    cards = []
    for team in teams:
        result = 'Winners' if team == 0 else 'Losers'
        body = list(rows[team])
        if reverse:
            body.reverse()
        cards.append(f'<div><div><span>Team {team}</span> &middot; '
            f'<span>{result}</span></div>{"".join(body)}</div>')
    return ('<!doctype html><html><head><title>Replay</title></head><body><main>'
        f'<div><h1>Fords of Isen</h1><p>RotWK &middot; {raw["patchName"]} '
        f'&middot; {raw["gamemode"]}</p></div>'
        f'<a href="/api/replays/download?replayId={raw["replayId"]}">Download</a>'
        f'{"".join(cards)}</main></body></html>')


def rows_2v2():
    return {0: [row(115, 104, 980, 988), row(2, 2, 1022, 1030)],
            1: [row(58, 105, 995, 987), row(133, 133, 953, 945)]}


def test_real_1v1_before_is_not_rank_or_after_and_envelope_is_metadata_only():
    raw = raw_1v1()
    original = deepcopy(raw)
    evidence = service().parse(page(raw), raw)
    assert evidence is not None
    assert set(evidence) == {'schema', 'source', 'rating_reference', 'replay_id',
        'patch_family', 'raw_fingerprint', 'players'}
    assert evidence['schema'] == 1
    assert evidence['source'] == 'bfmeladder_replay_html'
    assert evidence['rating_reference'] == 'arena_replay_before'
    assert evidence['replay_id'] == RID
    assert evidence['patch_family'] == 'ennorath'
    assert evidence['raw_fingerprint'] == service().fingerprint(raw)
    assert sorted(evidence['players'], key=lambda p: p['uuid']) == [
        dict(uuid=LOSER, team=1, old_rank=25, new_rank=27, before=1101, after=1092),
        dict(uuid=WINNER, team=0, old_rank=34, new_rank=31, before=1079, after=1088)]
    assert service().read(evidence, raw) == {WINNER: 1079, LOSER: 1101}
    assert raw == original


@pytest.mark.parametrize('html_reverse,api_reverse', [(False, True), (True, False), (True, True)])
def test_real_2v2_binds_rank_pairs_not_names_or_order(html_reverse, api_reverse):
    raw = raw_2v2()
    html = page(raw, rows_2v2(), reverse=html_reverse)
    if api_reverse:
        raw['players'].reverse()
    for player in raw['players']:
        player.update(name='Renamed again', nickname='Same visible name')
    evidence = service().parse(html, raw)
    assert service().read(evidence, raw) == {
        LOSER: 980, SECOND_WINNER: 1022, FIRST_LOSER: 995, SECOND_LOSER: 953}


def test_equal_rank_pairs_in_different_teams_are_safe():
    raw = raw_1v1()
    raw['players'][1].update(oldRank=34, newRank=31)
    html = page(raw, {0: [row(34, 31, 1079, 1088)], 1: [row(34, 31, 1101, 1092)]})
    assert service().read(service().parse(html, raw), raw) == {WINNER: 1079, LOSER: 1101}


def test_live_page_faction_span_wraps_rank_and_rating_without_changing_uuid_binding():
    raw = raw_1v1()
    html = page(raw).replace('<span><span>rank ', '<span><span>Mordor <span>rank ')
    html = html.replace('</ul></span></span></span></div>', '</ul></span></span></span></span></div>')
    assert service().read(service().parse(html, raw), raw) == {WINNER: 1079, LOSER: 1101}


@pytest.mark.parametrize('suffix', ['', ' &middot; Solo queue', ' &middot; Unexpected mode'])
def test_live_ranked_badge_and_optional_queue_label(suffix):
    raw = raw_1v1()
    html = page(raw).replace('1 versus 1</p>', '1 versus 1' + suffix + ' <span>Ranked</span></p>')
    ratings = service().read(service().parse(html, raw), raw)
    assert ratings == ({} if 'Unexpected' in suffix else {WINNER: 1079, LOSER: 1101})


def test_unchanged_rank_is_hidden_on_live_team_page_and_binds_only_unique_candidate():
    raw = raw_2v2()
    html = page(raw, rows_2v2()).replace('<span>rank 2 &rarr; 2</span>', '')
    html = html.replace('<span>rank 133 &rarr; 133</span>', '')
    assert service().read(service().parse(html, raw), raw) == {
        LOSER: 980, SECOND_WINNER: 1022, FIRST_LOSER: 995, SECOND_LOSER: 953}


def test_multiple_hidden_unchanged_ranks_in_same_team_are_ambiguous():
    raw = raw_2v2()
    raw['players'][0].update(oldRank=115, newRank=115)
    rows = rows_2v2()
    rows[0][0] = row(115, 115, 980, 988)
    html = page(raw, rows).replace('<span>rank 2 &rarr; 2</span>', '')
    html = html.replace('<span>rank 115 &rarr; 115</span>', '')
    assert service().parse(html, raw) is None


def test_unplaced_player_with_hidden_rank_keeps_exact_elo():
    raw = raw_1v1()
    raw['players'][1].update(oldRank=-1, newRank=60)
    html = page(raw).replace('<span>rank 25 &rarr; 27</span>', '')
    assert service().read(service().parse(html, raw), raw) == {WINNER: 1079, LOSER: 1101}


def test_hidden_unplaced_and_unchanged_players_cannot_be_guessed():
    raw = raw_2v2()
    raw['players'][0].update(oldRank=-1)
    html = page(raw, rows_2v2()).replace('<span>rank 115 &rarr; 104</span>', '')
    html = html.replace('<span>rank 2 &rarr; 2</span>', '')
    assert service().parse(html, raw) is None


@pytest.mark.parametrize('broken', ['rank 999 → unknown', 'rank 2 → 2.5', 'rank unavailable'])
def test_malformed_rank_is_not_an_absent_unchanged_rank(broken):
    raw = raw_2v2()
    html = page(raw, rows_2v2()).replace('rank 2 &rarr; 2', broken)
    assert service().parse(html, raw) is None


@pytest.mark.parametrize('size', [3, 4])
def test_complete_larger_balanced_modes(size):
    raw = raw_1v1()
    raw['gamemode'] = f'{size} versus {size}'
    raw['players'] = []
    rows = {0: [], 1: []}
    expected = {}
    for team in (0, 1):
        for index in range(size):
            identity = str(UUID(int=1 + team * size + index))
            rank = 1 + index
            before = 1000 + index + 100 * team
            raw['players'].append(dict(uuid=identity, team=team, isWinner=team == 0,
                oldRank=rank, newRank=rank + 1))
            rows[team].append(row(rank, rank + 1, before, before + (8 if team == 0 else -8)))
            expected[identity] = before
    assert service().read(service().parse(page(raw, rows, reverse=True), raw), raw) == expected


def test_patch_202_and_family_only_api_name():
    raw = raw_1v1()
    raw.update(patchId='official-2:v9.0.0', patchName='Patch 2.02 (v9.0.0)')
    html = page(raw)
    raw['patchName'] = 'Patch 2.02'
    evidence = service().parse(html, raw)
    assert evidence is not None and evidence['patch_family'] == 'patch_202'
    assert service().read(evidence, raw) == {WINNER: 1079, LOSER: 1101}


@pytest.mark.parametrize('change', [
    'cw', 'unspecified', 'patch', 'patch_version', 'game', 'mode', 'download',
    'no_download', 'no_tooltip', 'no_elo', 'delta', 'result', 'negative', 'decimal',
    'duplicate_before', 'duplicate_row', 'duplicate_card', 'missing_row',
    'truncated', 'truncated_balanced_rows', 'rank_mismatch', 'no_profile',
    'nested_row', 'rank_outside_rx_sibling', 'duplicate_context',
])
def test_invalid_or_ambiguous_html_fails_closed(change):
    raw = raw_1v1()
    html = page(raw)
    replacements = {
        'cw': ('+9 ELO', '+9 CW'),
        'unspecified': ('+9 ELO', '+9'),
        'patch': ('Ennorath (1.9.7.7d)', 'Patch 2.02 (v9.0.0)'),
        'patch_version': ('Ennorath (1.9.7.7d)', 'Ennorath (1.0.0)'),
        'game': ('RotWK', 'BfME2'),
        'mode': ('1 versus 1', '2 versus 2'),
        'download': (RID, RID_2),
        'no_download': ('/api/replays/download?', '/other?'),
        'no_tooltip': ('class="rx-pop"', 'class="other"'),
        'no_elo': ('class="rx-btn"', 'class="other"'),
        'delta': ('+9 ELO', '+10 ELO'),
        'result': ('Winners', 'Losers'),
        'negative': ('Rating before: 1079', 'Rating before: -1079'),
        'decimal': ('Rating before: 1079', 'Rating before: 1079.5'),
        'duplicate_before': ('<li>Rating before: 1079</li>', '<li>Rating before: 1079</li>' * 2),
        'duplicate_row': (row(34, 31, 1079, 1088), row(34, 31, 1079, 1088) * 2),
        'missing_row': (row(25, 27, 1101, 1092), ''),
        'rank_mismatch': ('rank 34 &rarr; 31', 'rank 35 &rarr; 31'),
        'no_profile': ('/u/unrelated-name', '/elsewhere'),
        'nested_row': (row(34, 31, 1079, 1088), '<div>' + row(34, 31, 1079, 1088) + '</div>'),
        'rank_outside_rx_sibling': ('<span>rank 34 &rarr; 31</span>', ''),
        'duplicate_context': ('<h1>Fords of Isen</h1>', '<h1>Fords of Isen</h1><h1>Other</h1>'),
    }
    if change in replacements:
        html = html.replace(*replacements[change])
    elif change == 'duplicate_card':
        html = html.replace('</main>', '<div><div><span>Team 0</span>'
            '<span>Winners</span></div>' + row(34, 31, 1079, 1088) + '</div></main>')
    elif change == 'truncated':
        html = html[:html.index('Rating after: 1092')]
    else:
        html = html.removesuffix('</main></body></html>')
    assert service().parse(html, raw) is None


@pytest.mark.parametrize('change', ['duplicate_uuid', 'duplicate_pair', 'missing_player',
    'bad_uuid', 'bool_team', 'negative_team', 'string_result', 'mixed_result',
    'no_winner', 'nullable_rank', 'bool_rank', 'negative_rank', 'zero_rank',
    'unequal_teams', 'unsupported_mode', 'wrong_game', 'wrong_patch', 'conflicting_patch',
    'bad_replay_id', 'missing_date', 'bad_duration', 'bad_observer'])
def test_invalid_raw_rejects_parse_and_fingerprint(change):
    raw = raw_2v2()
    html = page(raw, rows_2v2())
    player = raw['players'][0]
    if change == 'duplicate_uuid':
        raw['players'][1]['uuid'] = player['uuid']
    elif change == 'duplicate_pair':
        raw['players'][1].update(oldRank=115, newRank=104)
    elif change == 'missing_player':
        raw['players'].pop()
    elif change == 'bad_uuid':
        player['uuid'] = 'not-a-uuid'
    elif change == 'bool_team':
        player['team'] = False
    elif change == 'negative_team':
        player['team'] = -1
    elif change == 'string_result':
        player['isWinner'] = 'true'
    elif change == 'mixed_result':
        player['isWinner'] = False
    elif change == 'no_winner':
        for item in raw['players']:
            item['isWinner'] = False
    elif change in {'nullable_rank', 'bool_rank', 'negative_rank', 'zero_rank'}:
        player['oldRank'] = {'nullable_rank': None, 'bool_rank': True,
            'negative_rank': -2, 'zero_rank': 0}[change]
    elif change == 'unequal_teams':
        player['team'] = 1
    elif change == 'unsupported_mode':
        raw['gamemode'] = 'FFA'
    elif change == 'wrong_game':
        raw['gameName'] = 'BfME2'
    elif change == 'wrong_patch':
        raw['patchName'] = 'Unspecified'
    elif change == 'conflicting_patch':
        raw['patchId'] = 'official-2:v9.0.0'
    elif change == 'bad_replay_id':
        raw['replayId'] = '../wrong'
    elif change == 'missing_date':
        raw.pop('date')
    elif change == 'bad_duration':
        raw['duration'] = []
    else:
        player['isObserver'] = 'false'
    assert service().parse(html, raw) is None
    with pytest.raises(ValueError):
        service().fingerprint(raw)


def test_duplicate_html_pair_within_team_cannot_be_resolved_by_name():
    raw = raw_2v2()
    rows = rows_2v2()
    rows[0][1] = row(115, 104, 1022, 1030, name='Nikolaaas')
    assert service().parse(page(raw, rows), raw) is None


def test_observers_and_mutable_display_data_do_not_affect_fingerprint_or_read():
    raw = raw_1v1()
    fingerprint = service().fingerprint(raw)
    evidence = service().parse(page(raw), raw)
    raw.update(likes=999, downloads=800, comments=['changed'], title='Renamed')
    raw['players'].reverse()
    for player in raw['players']:
        player.update(name='Another name', nickname='Identical', profilePicture='new')
    raw['players'].append(dict(isObserver=True, uuid='observer', team=None, isWinner=None))
    assert service().fingerprint(raw) == fingerprint
    assert service().read(evidence, raw) == {WINNER: 1079, LOSER: 1101}
    assert service().parse(page(raw), raw) == evidence


@pytest.mark.parametrize('field,value', [
    ('replayId', RID_2), ('gameName', 'BfME2'), ('patchId', 'ennorath:1.9.7.7e'),
    ('patchName', 'Ennorath'), ('arenaId', 'other-arena'), ('gamemode', '2 versus 2'),
    ('date', 1792400000001), ('duration', '00:11:00'),
])
def test_stale_replay_facts_invalidate_evidence(field, value):
    raw = raw_1v1()
    evidence = service().parse(page(raw), raw)
    raw[field] = value
    assert service().read(evidence, raw) == {}


@pytest.mark.parametrize('field,value', [('uuid', SECOND_WINNER), ('team', 2),
    ('isWinner', False), ('oldRank', 35), ('newRank', 30)])
def test_stale_player_facts_invalidate_evidence(field, value):
    raw = raw_1v1()
    evidence = service().parse(page(raw), raw)
    raw['players'][0][field] = value
    assert service().read(evidence, raw) == {}


@pytest.mark.parametrize('change', ['schema', 'source', 'reference', 'replay', 'patch',
    'fingerprint', 'missing_player', 'duplicate_player', 'uuid', 'team', 'old_rank',
    'new_rank', 'before_bool', 'before_negative', 'after_float', 'result',
    'missing_before', 'missing_after', 'extra_certification', 'extra_player_field'])
def test_read_strictly_revalidates_complete_evidence(change):
    raw = raw_1v1()
    evidence = service().parse(page(raw), raw)
    assert evidence is not None
    original = deepcopy(evidence)
    fields = {'schema': ('schema', True), 'source': ('source', 'bfmeladder_current'),
        'reference': ('rating_reference', 'arena_replay_after'), 'replay': ('replay_id', RID_2),
        'patch': ('patch_family', 'patch_202'), 'fingerprint': ('raw_fingerprint', '0' * 64)}
    if change in fields:
        field, value = fields[change]
        evidence[field] = value
    elif change == 'missing_player':
        evidence['players'].pop()
    elif change == 'duplicate_player':
        evidence['players'].append(deepcopy(evidence['players'][0]))
    elif change == 'extra_certification':
        evidence['verified_scan'] = True
    else:
        player = next(p for p in evidence['players'] if p['uuid'] == WINNER)
        mutations = {'uuid': ('uuid', 'bad'), 'team': ('team', False),
            'old_rank': ('old_rank', 35), 'new_rank': ('new_rank', 30),
            'before_bool': ('before', True), 'before_negative': ('before', -1),
            'after_float': ('after', 1088.0), 'result': ('after', 1078),
            'extra_player_field': ('nickname', 'not allowed')}
        if change in mutations:
            field, value = mutations[change]
            player[field] = value
        else:
            player.pop('before' if change == 'missing_before' else 'after')
    snapshot = deepcopy(evidence)
    assert service().read(evidence, raw) == {}
    assert evidence == snapshot
    assert service().read(original, raw) == {WINNER: 1079, LOSER: 1101}


@pytest.mark.parametrize('invalid', [None, [], '', 0, {'players': []}])
def test_invalid_envelopes_are_total_fail_closed(invalid):
    assert service().read(invalid, raw_1v1()) == {}
    assert service().parse(invalid, raw_1v1()) is None
    assert service().parse(page(raw_1v1()), invalid) is None
    assert service().read({}, invalid) == {}
    with pytest.raises(ValueError):
        service().fingerprint(invalid)
