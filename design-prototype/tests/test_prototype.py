from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_PAGES = {
    'home.html': ['data-section="season"','data-section="active-battles"','data-section="leaders"','data-section="activity"'],
    'index.html': ['data-section="map-controls"','data-section="territory-details"','data-section="map-legend"','data-section="territory-history"'],
    'clans.html': ['data-section="clan-filters"','data-section="clan-grid"','data-section="clan-standings"','data-section="alliances"'],
    'clan.html': ['data-tab-panel="overview"','data-tab-panel="players"','data-tab-panel="territories"','data-tab-panel="trade"','data-tab-panel="clan-relics"','data-tab-panel="battles"','data-tab-panel="history"','data-section="clan-trade"','data-section="clan-relics"'],
    'battles.html': ['data-tab-panel="active"','data-tab-panel="planned"','data-tab-panel="completed"','data-section="battle-feed"','href="battle-detail.html"'],
    'battle-detail.html': ['data-section="battle-summary"','data-section="battle-lineups"','data-section="battle-rounds"','data-section="battle-timeline"','data-section="battle-territory-result"','data-section="battle-relics"'],
    'ranking.html': ['data-tab-panel="players"','data-tab-panel="clans"','data-tab-panel="season"','data-section="ranking-filters"'],
    'statistics.html': ['data-section="kpis"','data-section="match-chart"','data-section="territory-chart"','data-section="faction-stats"','data-section="season-progress"'],
    'shop.html': ['data-tab-panel="catalog"','data-tab-panel="inventory"','data-tab-panel="equipped"','data-section="shop-filters"','data-section="relic-grid"'],
    'achievements.html': ['data-tab-panel="all"','data-tab-panel="combat"','data-tab-panel="territories"','data-tab-panel="seasonal"','data-section="achievement-progress"'],
    'profile.html': ['data-tab-panel="overview"','data-tab-panel="matches"','data-tab-panel="statistics"','data-tab-panel="achievements"','data-tab-panel="relics"','data-tab-panel="territories"','data-section="profile-xp"'],
    'chronicle.html': ['data-section="chronicle-filters"','data-section="global-timeline"','data-section="territory-log"','data-section="season-archive"'],
    'login.html': ['data-tab-panel="login"','data-tab-panel="register"','data-tab-panel="recover"'],
    'admin.html': ['data-admin-panel="dashboard"','data-admin-panel="territories"','data-admin-panel="clans"','data-admin-panel="players"','data-admin-panel="battles"','data-admin-panel="relics"','data-admin-panel="achievements"','data-admin-panel="seasons"','data-admin-panel="settings"'],
}

def test_expected_pages_exist_and_are_complete():
    missing=[]
    for page, markers in EXPECTED_PAGES.items():
        p=ROOT/page
        if not p.exists():
            missing.append(f'{page}: file missing')
            continue
        text=p.read_text(encoding='utf-8')
        for marker in markers:
            if marker not in text:
                missing.append(f'{page}: missing {marker}')
    assert not missing, '\n'.join(missing)


def test_internal_html_links_resolve():
    broken=[]
    for p in ROOT.glob('*.html'):
        text=p.read_text(encoding='utf-8')
        for href in re.findall(r'href=["\']([^"\']+\.html(?:#[^"\']*)?)["\']', text):
            target=href.split('#',1)[0]
            if not (ROOT/target).exists():
                broken.append(f'{p.name} -> {href}')
    assert not broken, '\n'.join(broken)


def test_all_tab_buttons_have_panels():
    errors=[]
    for p in ROOT.glob('*.html'):
        text=p.read_text(encoding='utf-8')
        tabs=re.findall(r'data-tab="([^"]+)"',text)
        panels=set(re.findall(r'data-tab-panel="([^"]+)"',text))
        for tab in tabs:
            if tab not in panels:
                errors.append(f'{p.name}: tab {tab} has no panel')
    assert not errors, '\n'.join(errors)


def test_core_assets_and_styles_exist():
    required=['style.css','script.js','assets/logo.png','assets/favicon.png','assets/home.webp','assets/map.webp','assets/shop.webp']
    missing=[x for x in required if not (ROOT/x).exists()]
    assert not missing, missing


def test_clan_relics_use_all_available_icons():
    text=(ROOT/'clan.html').read_text(encoding='utf-8')
    for i in range(1,13):
        assert f'assets/relic_{i}.webp' in text, f'clan.html missing relic_{i}'


def test_battle_list_links_to_full_summary():
    text=(ROOT/'battles.html').read_text(encoding='utf-8')
    assert text.count('battle-detail.html') >= 4
