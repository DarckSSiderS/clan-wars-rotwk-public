import { getCycleClanWarHandbook } from './cycleClanWarHandbook.js';

const DEFAULT_VALUES = {
  CAMPAIGN_STARTING_INFLUENCE: 100, CAMPAIGN_STARTING_GOLD: 100,
  CAMPAIGN_STARTING_IRON: 6, CAMPAIGN_STARTING_WOOD: 6,
  CAMPAIGN_STARTING_FOOD: 3, CAMPAIGN_STARTING_MITHRIL: 0,
  WAR_DURATION_HOURS: 60, CLAN_ATTACK_COOLDOWN_HOURS: 60,
  WAR_MIN_MATCH_DURATION_SECONDS: 60, WAR_ELO_BASE_POINTS: 10,
  WAR_ELO_MIN_POINTS: 5, WAR_ELO_MAX_POINTS: 15,
  WAR_FULL_CLAN_TEAM_BONUS_PERCENT: 10, WAR_MODIFIER_CAP_PERCENT: 35,
  TERRITORY_RESOURCE_READY_HOURS: 48, TERRITORY_RESOURCE_PAYOUT_HOURS: 24,
  POPULATION_DEVELOPMENT_BONUS_FIRST_LEVELS_PERCENT: 8,
  POPULATION_DEVELOPMENT_BONUS_LATER_LEVELS_PERCENT: 4,
  POPULATION_INCOME_BONUS_CAP_PERCENT: 20,
  CARAVAN_HOURS_PER_STEP: 6, CARAVAN_SEA_HOURS_PER_STEP: 8,
  ELO_START_RATING: 1000, ELO_PROVISIONAL_MATCHES: 30,
  CLAN_LEVEL_1_ATTACK_CAPACITY: 1,
  CLAN_LEVEL_2_ACTIVE_MEMBERS: 11, CLAN_LEVEL_2_TERRITORIES: 2,
  CLAN_LEVEL_2_INFLUENCE: 140, CLAN_LEVEL_2_ATTACK_CAPACITY: 2,
  CLAN_LEVEL_3_ACTIVE_MEMBERS: 17, CLAN_LEVEL_3_TERRITORIES: 4,
  CLAN_LEVEL_3_INFLUENCE: 230, CLAN_LEVEL_3_ATTACK_CAPACITY: 3,
  CLAN_LEVEL_4_ACTIVE_MEMBERS: 22, CLAN_LEVEL_4_TERRITORIES: 6,
  CLAN_LEVEL_4_INFLUENCE: 340, CLAN_LEVEL_4_ATTACK_CAPACITY: 4,
  CLAN_LEVEL_5_ACTIVE_MEMBERS: 30, CLAN_LEVEL_5_TERRITORIES: 10,
  CLAN_LEVEL_5_INFLUENCE: 500, CLAN_LEVEL_5_ATTACK_CAPACITY: 5,
};

const valueReader = (values) => (key) => values?.[key] ?? DEFAULT_VALUES[key];
const rejectionLink = '/feedback?from=%2Frules%3Fsection%3Dmatches';


const buildEn = ({ values, season, version }) => {
  const rule = valueReader(values);
  const seasonName = season?.name || 'Test campaign';
  const minMinutes = Math.round(rule('WAR_MIN_MATCH_DURATION_SECONDS') / 60);
  return {
    eyebrow: 'Rules for players', title: 'ClanWars Handbook',
    intro: 'A practical guide to accounts, clans, the map, wars, economy, trade, and personal progress.',
    versionLabel: `Rules v${version}`, seasonLabel: seasonName,
    updatedLabel: 'Updated 9 September 2026', navigationLabel: 'Handbook sections',
    sectionMeta: `Season “${seasonName}” · rules v${version}`,
    fallbackNotice: 'Current season settings could not be loaded. The main rules are shown below; exact prices and available actions are always displayed before confirmation.',
    incompleteNotice: 'Only some numerical settings were preserved for this completed season. The general way to play is described in full.',
    categories: [
      { id: 'overview', label: 'Project overview', title: 'How ClanWars works', summary: 'Normal ranked matches become part of a shared war for Middle-earth.', sections: [
        { title: 'The main idea', paragraphs: ['ClanWars connects ranked Battle for Middle-earth II: Rise of the Witch-king matches to a large clan campaign. Players keep playing familiar matches, while eligible victories help their clan capture and defend territory.', 'The match map does not need to match the attacked territory. There is no separate war queue: players may choose their time, opponents, and maps as long as the scoring rules are met.'] },
        { title: 'The basic game loop', steps: ['Link an Arena game profile and join a clan.', 'Help the clan develop land, gather resources, and prepare campaigns.', 'Play eligible ranked matches while a war is active.', 'Earn territory, achievements, and a place in the season history.'] },
      ] },
      { id: 'getting-started', label: 'Getting started', title: 'Account and campaign entry', summary: 'Make sure your matches, rating, and achievements belong to you.', sections: [
        { title: 'Game profile', paragraphs: ['Participation requires an Arena profile linked to a ClanWars account. This lets the site recognize the player in match results without confusing similar nicknames.', 'Changing a display name does not create a new player. Personal statistics stay with the profile owner.'] },
        { title: 'Create or join a clan', paragraphs: ['A player without a clan may create one or apply to an existing clan. A player cannot belong to two clans at the same time.', 'Matches begin contributing to a clan only after joining. Games played before joining or after leaving remain in personal statistics.'], links: [{ label: 'Find a clan', to: '/clans' }] },
      ] },
      { id: 'clan-roles', label: 'Clan and roles', title: 'Responsibilities inside a clan', summary: 'Roles separate leadership, trading, and participation in campaigns.', sections: [
        { title: 'Main roles', bullets: ['The Clan Leader manages members, declares wars, selects squads and Commanders, develops land, and manages relics and the treasury.', 'A Merchant creates, accepts, and cancels available trade offers for the clan.', 'A Warrior participates in clan life and may be selected for an attacking squad.', 'A Recruit is a regular member without management powers and may still fight and defend land.'] },
        { title: 'Commander', paragraphs: ['Commander is an additional status for a member with any main role, including the Leader. Each clan level allows as many Commanders as the clan has attack points.', 'A Commander must personally join the squad they lead. They cannot be replaced or removed during that campaign, and one Commander cannot lead two attacks at once.'] },
      ] },
      { id: 'territories', label: 'Map and land', title: 'Reading the map of Middle-earth', summary: 'Territories provide routes, influence, income, and war advantages.', sections: [
        { title: 'Territory states', bullets: ['Neutral land has no owner and may be captured.', 'Owned land uses its clan colour and benefits that clan.', 'Contested land is already in an active war; a third clan cannot open another war for it.'] },
        { title: 'Benefits of ownership', paragraphs: ['Every territory has its own gold, influence, population, rare resource, and development levels. Influence is added on capture and removed on loss; it is not spent like currency.', 'Great strongholds are richer and produce two different rare resources, but attacking one requires 5 territories and 350 influence.'] },
        { title: 'Land and sea routes', paragraphs: ['A land attack starts from owned land and targets a neighbour. A port territory opens approved sea routes to coastal land.', 'The source military camp matters for land attacks. Port and fleet development replace it during a sea attack.'], links: [{ label: 'Open map', to: '/map' }] },
      ] },
      { id: 'attacks', label: 'Starting a war', title: 'How a clan declares an attack', summary: 'The Leader chooses a route, a Commander, and the players who will score for the campaign.', sections: [
        { title: 'Declaration steps', steps: ['Choose an owned source territory and an available target.', 'Make sure the clan has enough influence, territories, and a free attack point.', 'Choose an available Commander and include them in the squad.', 'Select the remaining fighters and confirm. The squad cannot be changed after the war begins.'] },
        { title: 'Squad size and attack points', paragraphs: [`At level I a clan may run ${rule('CLAN_LEVEL_1_ATTACK_CAPACITY')} attack and the Commander may be the only squad member. From level II onward, every attacking squad needs at least 5 players. A spent attack point returns ${rule('CLAN_ATTACK_COOLDOWN_HOURS')} hours after that war was declared.`], bullets: [
          `Level II: ${rule('CLAN_LEVEL_2_ACTIVE_MEMBERS')} members, ${rule('CLAN_LEVEL_2_TERRITORIES')} territories, ${rule('CLAN_LEVEL_2_INFLUENCE')} influence — up to ${rule('CLAN_LEVEL_2_ATTACK_CAPACITY')} attacks.`, `Level III: ${rule('CLAN_LEVEL_3_ACTIVE_MEMBERS')} members, ${rule('CLAN_LEVEL_3_TERRITORIES')} territories, ${rule('CLAN_LEVEL_3_INFLUENCE')} influence — up to ${rule('CLAN_LEVEL_3_ATTACK_CAPACITY')} attacks.`, `Level IV: ${rule('CLAN_LEVEL_4_ACTIVE_MEMBERS')} members, ${rule('CLAN_LEVEL_4_TERRITORIES')} territories, ${rule('CLAN_LEVEL_4_INFLUENCE')} influence — up to ${rule('CLAN_LEVEL_4_ATTACK_CAPACITY')} attacks.`, `Level V: ${rule('CLAN_LEVEL_5_ACTIVE_MEMBERS')} members, ${rule('CLAN_LEVEL_5_TERRITORIES')} territories, ${rule('CLAN_LEVEL_5_INFLUENCE')} influence — up to ${rule('CLAN_LEVEL_5_ATTACK_CAPACITY')} attacks.`,
        ] },
      ] },
      { id: 'matches', label: 'Match scoring', title: 'Which matches score war points', summary: 'Eligible matches are counted automatically and rejected results show a clear reason.', sections: [
        { title: 'Required conditions', bullets: [`A ranked 1v1, 2v2, 3v3, or 4v4 in Ennorath or Patch 2.02 lasting at least ${minMinutes} ${minMinutes === 1 ? 'minute' : 'minutes'}.`, `The match must begin during the ${rule('WAR_DURATION_HOURS')}-hour war period.`, 'Only selected squad members score for attack. Any current member of the owner clan may defend occupied land.', 'The opponent may be any eligible player except a clanmate. A clan’s preferred mod is informational only.'] },
        { title: 'If a match was rejected', paragraphs: ['Open the match card to see the exact reason. If the match details were recognized incorrectly, send a report with links to the war and match.'] },
      ], rejections: [
        ['Wrong mode', 'The game was not ranked 1v1–4v4 or did not use one of the two supported mods.', 'Check the mode and mod shown on the match card.'], ['Match too short', `The game lasted less than ${minMinutes} ${minMinutes === 1 ? 'minute' : 'minutes'}.`, 'This match cannot provide war points.'], ['Outside the war period', 'The game began before the attack or after the battle period ended.', 'Compare the match start time with the war deadline.'], ['Player not in squad', 'A different attacking squad was selected.', 'Check the fighter list on the war page.'], ['Player had not joined or had left', 'The player was not in the required clan when the match began.', 'Check the membership dates.'], ['Played against a clanmate', 'The match remains in personal statistics but gives no territory points.', 'Play a member of another clan or a free player.'], ['Match under review', 'The result has not appeared yet or needs clarification.', 'Wait briefly; report it if the status does not change.'],
      ].map(([title, reason, action]) => ({ title, reason, action, to: rejectionLink })) },
      { id: 'war-result', label: 'War result', title: 'How the winner is decided', summary: 'Opponent strength changes the value of a win, and ties favour the defender.', sections: [
        { title: 'Points from victories', paragraphs: [`A normal victory is worth about ${rule('WAR_ELO_BASE_POINTS')} points. Elo difference adjusts it to between ${rule('WAR_ELO_MIN_POINTS')} and ${rule('WAR_ELO_MAX_POINTS')}: beating a stronger opponent is worth more than an expected win against a weaker one.`, `A fully clan-based winning team receives another ${rule('WAR_FULL_CLAN_TEAM_BONUS_PERCENT')}%. Land and active relic bonuses also apply, but together cannot increase the result by more than ${rule('WAR_MODIFIER_CAP_PERCENT')}%.`] },
        { title: 'Completion and capture', paragraphs: [`The battle period lasts ${rule('WAR_DURATION_HOURS')} hours. After the last eligible results are included, the side with more points wins. A tie leaves the territory with the defender.`, 'When clan-owned land is captured, development levels are halved and rounded down (for example: attack 6 → 3, defence 8 → 4). Population and port access remain. Neutral captures and successful defences do not reduce development.'], links: [{ label: 'Open battles', to: '/battles' }] },
      ] },
      { id: 'economy', label: 'Economy', title: 'Treasury, income, and land development', summary: 'Gold and rare resources improve territory and purchase relics.', sections: [
        { title: 'Starting resources', paragraphs: [`A new clan begins with ${rule('CAMPAIGN_STARTING_INFLUENCE')} influence, ${rule('CAMPAIGN_STARTING_GOLD')} gold, ${rule('CAMPAIGN_STARTING_IRON')} iron, ${rule('CAMPAIGN_STARTING_WOOD')} wood, ${rule('CAMPAIGN_STARTING_FOOD')} food, and ${rule('CAMPAIGN_STARTING_MITHRIL')} mithril.`] },
        { title: 'Territory income', paragraphs: [`Gold arrives daily. Normal land provides about 40–60 gold and a great stronghold 140–160. Rare production begins after ${rule('TERRITORY_RESOURCE_READY_HOURS')} hours of uninterrupted ownership and repeats every ${rule('TERRITORY_RESOURCE_PAYOUT_HOURS')} hours. Losing the land stops preparation.`, 'Normal land produces one assigned resource and a great stronghold produces two. Mithril is available only from Moria and Caradhras.'] },
        { title: 'Development', bullets: [`Population raises gold income. Levels I–V add ${rule('POPULATION_DEVELOPMENT_BONUS_FIRST_LEVELS_PERCENT')}% each and VI–X add ${rule('POPULATION_DEVELOPMENT_BONUS_LATER_LEVELS_PERCENT')}% each; residents add up to another ${rule('POPULATION_INCOME_BONUS_CAP_PERCENT')}%.`, 'Fortifications improve defence on that territory.', 'A military camp improves land attacks launched from that territory.', 'A port opens sea routes and a fleet improves sea attacks. Fleet level cannot exceed port level.', 'The next level price is always shown before purchase and rises with development.'] },
      ] },
      { id: 'relics', label: 'Relics', title: 'Permanent clan relics', summary: 'Relics are long-term goals that let a clan choose its strengths.', sections: [
        { title: 'Purchase and upgrades', paragraphs: ['A purchased relic stays in the clan collection permanently. It may have up to three levels, with later levels requiring more gold, rare resources, and influence.', 'Influence unlocks the purchase but is not spent. Every relic card shows the exact price and effect.'] },
        { title: 'Active loadout', paragraphs: ['Up to four owned relics may be active at once. Only the Clan Leader selects the loadout.', 'New effects prepare for 48 hours after a change. Wars already in progress continue with the bonuses shown when they began.'], links: [{ label: 'Open clans', to: '/clans' }] },
      ] },
      { id: 'market', label: 'Market', title: 'Resource exchange and caravans', summary: 'Clans may trade rare resources when a delivery route connects their lands.', sections: [
        { title: 'Complete a trade', steps: ['A Leader or Merchant chooses what the clan offers, what it wants, and how long the offer remains open.', 'Another clan accepts and pays delivery for its part of the cargo.', 'Both cargoes become unavailable for other purchases and travel along the selected route.', 'Each clan receives the agreed cargo when it arrives.'] },
        { title: 'Time and cost', paragraphs: [`A land step takes ${rule('CARAVAN_HOURS_PER_STEP')} hours and a sea step ${rule('CARAVAN_SEA_HOURS_PER_STEP')} hours. Longer routes and larger cargoes cost more. The final fee and arrival time are shown before acceptance.`, 'An open offer may be cancelled before acceptance. A travelling caravan cannot be cancelled. If delivery cannot finish, the cargo remains protected until the journey continues or it is returned.'], links: [{ label: 'Open clan market', to: '/clans' }] },
      ] },
      { id: 'progress', label: 'Profile and progress', title: 'Elo, statistics, achievements, and titles', summary: 'A profile shows personal results in both mods and contribution to the campaign.', sections: [
        { title: 'Rating and statistics', paragraphs: [`Ennorath and Patch 2.02 have separate Elo ratings. A new rating starts at ${rule('ELO_START_RATING')}, and the first ${rule('ELO_PROVISIONAL_MATCHES')} games find the player’s level more quickly. Results in one mod never change the other rating.`, 'Profiles show matches, wins and losses, favourite factions and maps, achievements, titles, and clan-war contribution.'], links: [{ label: 'Open ranking', to: '/ranking' }, { label: 'Open statistics', to: '/statistics' }] },
        { title: 'Achievements and rewards', paragraphs: ['Achievements unlock from confirmed results such as matches, wins, streaks, modes, factions, and maps. If available Arena history is imported, eligible earlier games also count toward progress.', 'Titles, frames, backgrounds, and badges decorate the profile and player name. They never provide Elo, resources, or combat advantages.'] },
      ] },
      { id: 'fairplay', label: 'Fair play', title: 'Violations, disputed matches, and help', summary: 'Results should come from fair play, and disputed situations can be reviewed.', sections: [
        { title: 'Forbidden behaviour', bullets: ['Arranged wins or deliberate losses for points, rating, or rewards.', 'Account sharing or playing under another person’s profile.', 'Changing match results, resubmitting one match, or exploiting errors for duplicate rewards.', 'Attempts to bypass squad, war-time, trade, or development restrictions.'] },
        { title: 'When something goes wrong', paragraphs: ['Do not try to fix a disputed match by submitting it again. Include links to the war or trade, the players, and the approximate time in your report.', 'A suspicious match does not automatically mean punishment; the situation is reviewed together with available game data.'], links: [{ label: 'Report a problem', to: '/feedback?from=%2Frules' }] },
      ] },
    ],
  };
};

const buildDe = ({ values, season, version }) => {
  const rule = valueReader(values);
  const seasonName = season?.name || 'Testkampagne';
  const minMinutes = Math.round(rule('WAR_MIN_MATCH_DURATION_SECONDS') / 60);
  return {
    eyebrow: 'Regeln für Spieler', title: 'ClanWars-Handbuch',
    intro: 'Ein verständlicher Leitfaden zu Konto, Clans, Karte, Kriegen, Wirtschaft, Handel und persönlichem Fortschritt.',
    versionLabel: `Regeln v${version}`, seasonLabel: seasonName,
    updatedLabel: 'Aktualisiert am 9. September 2026', navigationLabel: 'Kapitel des Handbuchs',
    sectionMeta: `Saison „${seasonName}“ · Regeln v${version}`,
    fallbackNotice: 'Die aktuellen Saisoneinstellungen konnten nicht geladen werden. Die Grundregeln stehen unten; genaue Preise und verfügbare Aktionen werden vor der Bestätigung angezeigt.',
    incompleteNotice: 'Für diese abgeschlossene Saison sind nur einige Zahlen erhalten. Der allgemeine Spielablauf ist vollständig beschrieben.',
    categories: [
      { id: 'overview', label: 'Projektüberblick', title: 'So funktioniert ClanWars', summary: 'Normale Ranglistenspiele werden Teil eines gemeinsamen Krieges um Mittelerde.', sections: [
        { title: 'Die Grundidee', paragraphs: ['ClanWars verbindet Ranglistenspiele von Battle for Middle-earth II: Rise of the Witch-king mit einer großen Clankampagne. Passende Siege helfen dem Clan bei Eroberung und Verteidigung.', 'Die Spielkarte muss nicht dem angegriffenen Gebiet entsprechen. Es gibt keine besondere Kriegswarteschlange: Zeit, Gegner und Karte sind frei, solange die Wertungsbedingungen erfüllt sind.'] },
        { title: 'Der Spielablauf', steps: ['Arena-Spielprofil verbinden und einem Clan beitreten.', 'Gebiete ausbauen, Ressourcen sammeln und Feldzüge vorbereiten.', 'Während eines Krieges passende Ranglistenspiele spielen.', 'Gebiete, Erfolge und einen Platz in der Saisongeschichte gewinnen.'] },
      ] },
      { id: 'getting-started', label: 'Erste Schritte', title: 'Konto und Kampagneneinstieg', summary: 'So gehören Spiele, Wertung und Erfolge eindeutig zu dir.', sections: [
        { title: 'Spielprofil', paragraphs: ['Für die Teilnahme wird ein mit ClanWars verbundenes Arena-Profil benötigt. Dadurch erkennt die Seite den Spieler und verwechselt keine ähnlichen Namen.', 'Ein neuer Anzeigename erstellt keinen neuen Spieler. Die persönliche Statistik bleibt beim Profilinhaber.'] },
        { title: 'Clan gründen oder beitreten', paragraphs: ['Ein Spieler ohne Clan darf einen eigenen gründen oder sich bei einem bestehenden Clan bewerben. Zwei Clans gleichzeitig sind nicht möglich.', 'Spiele tragen erst nach dem Beitritt zum Clan bei. Frühere und nach dem Austritt gespielte Partien bleiben persönliche Statistik.'], links: [{ label: 'Clan finden', to: '/clans' }] },
      ] },
      { id: 'clan-roles', label: 'Clan und Rollen', title: 'Aufgaben im Clan', summary: 'Rollen trennen Führung, Handel und Teilnahme an Feldzügen.', sections: [
        { title: 'Hauptrollen', bullets: ['Der Clananführer verwaltet Mitglieder, erklärt Kriege, wählt Trupps und Heerführer, baut Gebiete aus und verwaltet Relikte sowie Schatzkammer.', 'Ein Händler erstellt, akzeptiert und beendet verfügbare Handelsangebote.', 'Ein Krieger kann für einen Angriffstrupp gewählt werden.', 'Ein Rekrut hat keine Verwaltungsrechte, darf aber kämpfen und Gebiete verteidigen.'] },
        { title: 'Heerführer', paragraphs: ['Heerführer ist ein Zusatzstatus für Mitglieder jeder Hauptrolle, auch für den Clananführer. Je Clanstufe sind so viele Heerführer verfügbar wie Angriffspunkte.', 'Der Heerführer muss selbst im eigenen Trupp stehen. Während des Feldzugs kann er nicht ersetzt oder abgesetzt werden und darf nicht zwei Angriffe gleichzeitig führen.'] },
      ] },
      { id: 'territories', label: 'Karte und Gebiete', title: 'Die Karte von Mittelerde lesen', summary: 'Gebiete geben Wege, Einfluss, Einkommen und Vorteile im Krieg.', sections: [
        { title: 'Gebietszustände', bullets: ['Neutrales Land hat keinen Besitzer und kann erobert werden.', 'Besetztes Land trägt die Clanfarbe und unterstützt den Besitzer.', 'Umkämpftes Land steht bereits in einem Krieg; ein dritter Clan darf dort keinen weiteren Krieg beginnen.'] },
        { title: 'Vorteile des Besitzes', paragraphs: ['Jedes Gebiet hat eigenes Gold, Einfluss, Bevölkerung, seltene Ressourcen und Ausbaustufen. Einfluss kommt bei Eroberung hinzu und verschwindet bei Verlust; er wird nicht wie Geld ausgegeben.', 'Große Festungen fördern zwei verschiedene seltene Ressourcen. Für einen Angriff braucht ein Clan 5 Gebiete und 350 Einfluss.'] },
        { title: 'Land- und Seewege', paragraphs: ['Ein Landangriff beginnt im eigenen Gebiet und zielt auf einen Nachbarn. Ein Hafen öffnet erlaubte Seewege zu Küstengebieten.', 'Für Landangriffe zählt das Militärlager des Ausgangsgebiets. Bei Seeangriffen gelten Hafen und Flotte.'], links: [{ label: 'Karte öffnen', to: '/map' }] },
      ] },
      { id: 'attacks', label: 'Krieg beginnen', title: 'So erklärt ein Clan einen Angriff', summary: 'Der Anführer wählt Weg, Heerführer und die Spieler, die Punkte sammeln.', sections: [
        { title: 'Schritte', steps: ['Eigenes Ausgangsgebiet und verfügbares Ziel wählen.', 'Genügend Einfluss, Gebiete und einen freien Angriffspunkt prüfen.', 'Freien Heerführer wählen und in den Trupp aufnehmen.', 'Weitere Kämpfer wählen und bestätigen. Danach bleibt der Trupp unverändert.'] },
        { title: 'Truppgröße und Angriffspunkte', paragraphs: [`Auf Stufe I darf ein Clan ${rule('CLAN_LEVEL_1_ATTACK_CAPACITY')} Angriff führen; der Heerführer darf allein antreten. Ab Stufe II braucht jeder Angriffstrupp mindestens 5 Spieler. Ein Angriffspunkt kehrt ${rule('CLAN_ATTACK_COOLDOWN_HOURS')} Stunden nach der Kriegserklärung zurück.`], bullets: [
          `Stufe II: ${rule('CLAN_LEVEL_2_ACTIVE_MEMBERS')} Mitglieder, ${rule('CLAN_LEVEL_2_TERRITORIES')} Gebiete, ${rule('CLAN_LEVEL_2_INFLUENCE')} Einfluss — bis zu ${rule('CLAN_LEVEL_2_ATTACK_CAPACITY')} Angriffe.`, `Stufe III: ${rule('CLAN_LEVEL_3_ACTIVE_MEMBERS')} Mitglieder, ${rule('CLAN_LEVEL_3_TERRITORIES')} Gebiete, ${rule('CLAN_LEVEL_3_INFLUENCE')} Einfluss — bis zu ${rule('CLAN_LEVEL_3_ATTACK_CAPACITY')} Angriffe.`, `Stufe IV: ${rule('CLAN_LEVEL_4_ACTIVE_MEMBERS')} Mitglieder, ${rule('CLAN_LEVEL_4_TERRITORIES')} Gebiete, ${rule('CLAN_LEVEL_4_INFLUENCE')} Einfluss — bis zu ${rule('CLAN_LEVEL_4_ATTACK_CAPACITY')} Angriffe.`, `Stufe V: ${rule('CLAN_LEVEL_5_ACTIVE_MEMBERS')} Mitglieder, ${rule('CLAN_LEVEL_5_TERRITORIES')} Gebiete, ${rule('CLAN_LEVEL_5_INFLUENCE')} Einfluss — bis zu ${rule('CLAN_LEVEL_5_ATTACK_CAPACITY')} Angriffe.`,
        ] },
      ] },
      { id: 'matches', label: 'Spielwertung', title: 'Welche Spiele Kriegspunkte bringen', summary: 'Passende Spiele werden automatisch gewertet; bei Ablehnung erscheint ein verständlicher Grund.', sections: [
        { title: 'Pflichtbedingungen', bullets: [`Ranglistenspiel 1v1, 2v2, 3v3 oder 4v4 in Ennorath oder Patch 2.02 mit mindestens ${minMinutes} ${minMinutes === 1 ? 'Minute' : 'Minuten'} Dauer.`, `Das Spiel muss während der ${rule('WAR_DURATION_HOURS')} Kriegsstunden beginnen.`, 'Für den Angriff zählen nur gewählte Truppmitglieder. Besetztes Land darf jedes aktuelle Mitglied des Besitzerclans verteidigen.', 'Der Gegner darf jeder passende Spieler außer einem Clanmitglied sein. Der bevorzugte Mod ist nur eine Information.'] },
        { title: 'Wenn ein Spiel nicht zählt', paragraphs: ['Die Spielkarte zeigt den genauen Grund. Bei falsch erkannten Angaben eine Meldung mit Links zu Krieg und Spiel senden.'] },
      ], rejections: [
        ['Falscher Modus', 'Das Spiel war kein Ranglisten-1v1–4v4 oder nutzte keinen der zwei unterstützten Mods.', 'Modus und Mod auf der Spielkarte prüfen.'], ['Spiel zu kurz', `Die Dauer lag unter ${minMinutes} ${minMinutes === 1 ? 'Minute' : 'Minuten'}.`, 'Dieses Spiel kann keine Kriegspunkte geben.'], ['Außerhalb der Kriegszeit', 'Das Spiel begann vor dem Angriff oder nach Ende der Kampfzeit.', 'Startzeit und Kriegsfrist vergleichen.'], ['Spieler nicht im Trupp', 'Für den Angriff wurde ein anderer Trupp gewählt.', 'Kämpferliste auf der Kriegsseite prüfen.'], ['Spieler war noch nicht oder nicht mehr Mitglied', 'Beim Spielstart gehörte der Spieler nicht zum benötigten Clan.', 'Ein- und Austrittsdatum prüfen.'], ['Gegen Clanmitglied gespielt', 'Das Spiel bleibt persönliche Statistik, gibt aber keine Gebietspunkte.', 'Gegen einen anderen Clan oder freien Spieler spielen.'], ['Spiel wird geprüft', 'Das Ergebnis fehlt noch oder muss geklärt werden.', 'Kurz warten und melden, falls sich der Status nicht ändert.'],
      ].map(([title, reason, action]) => ({ title, reason, action, to: rejectionLink })) },
      { id: 'war-result', label: 'Kriegsergebnis', title: 'So wird der Sieger bestimmt', summary: 'Die Stärke des Gegners beeinflusst den Siegwert; bei Gleichstand gewinnt die Verteidigung.', sections: [
        { title: 'Punkte für Siege', paragraphs: [`Ein normaler Sieg gibt ungefähr ${rule('WAR_ELO_BASE_POINTS')} Punkte. Der Elo-Unterschied verändert den Wert auf ${rule('WAR_ELO_MIN_POINTS')} bis ${rule('WAR_ELO_MAX_POINTS')}: Ein stärkerer Gegner ist wertvoller als ein erwarteter Sieg über einen schwächeren.`, `Ein siegreiches Team nur aus Clanmitgliedern erhält weitere ${rule('WAR_FULL_CLAN_TEAM_BONUS_PERCENT')}%. Gebiets- und Reliktboni dürfen das Ergebnis zusammen höchstens um ${rule('WAR_MODIFIER_CAP_PERCENT')}% erhöhen.`] },
        { title: 'Abschluss und Eroberung', paragraphs: [`Die Kampfzeit beträgt ${rule('WAR_DURATION_HOURS')} Stunden. Danach gewinnt die Seite mit mehr Punkten. Bei Gleichstand bleibt das Gebiet bei der Verteidigung.`, 'Bei Eroberung von Clanland werden Ausbaustufen halbiert und abgerundet (zum Beispiel: Angriff 6 → 3, Verteidigung 8 → 4). Einwohner und Hafenzugang bleiben. Neutrale Eroberungen und erfolgreiche Verteidigungen senken den Ausbau nicht.'], links: [{ label: 'Kriege öffnen', to: '/battles' }] },
      ] },
      { id: 'economy', label: 'Wirtschaft', title: 'Schatzkammer, Einkommen und Ausbau', summary: 'Gold und seltene Ressourcen verbessern Gebiete und kaufen Relikte.', sections: [
        { title: 'Startressourcen', paragraphs: [`Ein neuer Clan beginnt mit ${rule('CAMPAIGN_STARTING_INFLUENCE')} Einfluss, ${rule('CAMPAIGN_STARTING_GOLD')} Gold, ${rule('CAMPAIGN_STARTING_IRON')} Eisen, ${rule('CAMPAIGN_STARTING_WOOD')} Holz, ${rule('CAMPAIGN_STARTING_FOOD')} Nahrung und ${rule('CAMPAIGN_STARTING_MITHRIL')} Mithril.`] },
        { title: 'Gebietseinkommen', paragraphs: [`Gold kommt täglich. Normales Land bringt etwa 40–60 Gold, eine große Festung 140–160. Seltene Förderung beginnt nach ${rule('TERRITORY_RESOURCE_READY_HOURS')} Stunden ununterbrochenen Besitzes und wiederholt sich alle ${rule('TERRITORY_RESOURCE_PAYOUT_HOURS')} Stunden.`, 'Normales Land fördert eine feste Ressource, eine große Festung zwei. Mithril gibt es nur in Moria und Caradhras.'] },
        { title: 'Ausbau', bullets: [`Bevölkerung steigert Goldeinkommen. Stufen I–V geben je ${rule('POPULATION_DEVELOPMENT_BONUS_FIRST_LEVELS_PERCENT')}%, VI–X je ${rule('POPULATION_DEVELOPMENT_BONUS_LATER_LEVELS_PERCENT')}%; Einwohner geben zusätzlich bis zu ${rule('POPULATION_INCOME_BONUS_CAP_PERCENT')}%.`, 'Befestigungen erhöhen die Verteidigung dieses Gebiets.', 'Ein Militärlager stärkt Landangriffe aus diesem Gebiet.', 'Ein Hafen öffnet Seewege, die Flotte stärkt Seeangriffe. Die Flotte darf nicht höher als der Hafen sein.', 'Der Preis der nächsten Stufe wird vor dem Kauf angezeigt und steigt mit dem Ausbau.'] },
      ] },
      { id: 'relics', label: 'Relikte', title: 'Dauerhafte Clanrelikte', summary: 'Relikte sind langfristige Ziele und bestimmen die Stärken eines Clans.', sections: [
        { title: 'Kauf und Verbesserung', paragraphs: ['Ein gekauftes Relikt bleibt dauerhaft in der Clansammlung. Es besitzt bis zu drei Stufen; spätere Stufen brauchen mehr Gold, seltene Ressourcen und Einfluss.', 'Einfluss schaltet den Kauf frei, wird aber nicht ausgegeben. Jede Reliktkarte zeigt Preis und Wirkung.'] },
        { title: 'Aktive Ausrüstung', paragraphs: ['Bis zu vier erworbene Relikte können gleichzeitig aktiv sein. Nur der Clananführer wählt die Ausrüstung.', 'Nach einem Wechsel bereiten sich neue Effekte 48 Stunden vor. Laufende Kriege behalten die beim Start angezeigten Boni.'], links: [{ label: 'Clans öffnen', to: '/clans' }] },
      ] },
      { id: 'market', label: 'Markt', title: 'Ressourcentausch und Karawanen', summary: 'Clans können seltene Ressourcen handeln, wenn ein Lieferweg ihre Gebiete verbindet.', sections: [
        { title: 'Handel abschließen', steps: ['Anführer oder Händler bestimmt Angebot, Wunsch und Laufzeit.', 'Ein anderer Clan nimmt an und bezahlt die Lieferung seines Frachtteils.', 'Beide Frachten sind für andere Käufe gesperrt und reisen auf dem gewählten Weg.', 'Bei Ankunft erhält jeder Clan die vereinbarte Fracht.'] },
        { title: 'Zeit und Kosten', paragraphs: [`Ein Landschritt dauert ${rule('CARAVAN_HOURS_PER_STEP')} Stunden, ein Seeschritt ${rule('CARAVAN_SEA_HOURS_PER_STEP')} Stunden. Längere Wege und größere Frachten kosten mehr. Endpreis und Ankunftszeit stehen vor der Annahme fest.`, 'Ein offenes Angebot kann vor der Annahme beendet werden. Eine reisende Karawane nicht. Bei einem Problem bleibt die Fracht geschützt, bis die Reise weitergeht oder sie zurückkehrt.'], links: [{ label: 'Clanmarkt öffnen', to: '/clans' }] },
      ] },
      { id: 'progress', label: 'Profil und Fortschritt', title: 'Elo, Statistik, Erfolge und Titel', summary: 'Das Profil zeigt persönliche Ergebnisse in beiden Mods und den Beitrag zur Kampagne.', sections: [
        { title: 'Wertung und Statistik', paragraphs: [`Ennorath und Patch 2.02 haben getrennte Elo-Wertungen. Eine neue Wertung startet bei ${rule('ELO_START_RATING')}; die ersten ${rule('ELO_PROVISIONAL_MATCHES')} Spiele bestimmen das Niveau schneller. Ergebnisse eines Mods verändern den anderen nicht.`, 'Profile zeigen Spiele, Siege und Niederlagen, bevorzugte Fraktionen und Karten, Erfolge, Titel und Beiträge zu Clankriegen.'], links: [{ label: 'Rangliste öffnen', to: '/ranking' }, { label: 'Statistik öffnen', to: '/statistics' }] },
        { title: 'Erfolge und Belohnungen', paragraphs: ['Erfolge werden durch bestätigte Ergebnisse wie Spiele, Siege, Serien, Modi, Fraktionen und Karten freigeschaltet. Wird verfügbare Arena-Geschichte importiert, zählen passende frühere Spiele ebenfalls.', 'Titel, Rahmen, Hintergründe und Abzeichen schmücken Profil und Spielernamen. Sie geben weder Elo noch Ressourcen oder Kampfvorteile.'] },
      ] },
      { id: 'fairplay', label: 'Fairplay', title: 'Verstöße, strittige Spiele und Hilfe', summary: 'Ergebnisse sollen durch ehrliches Spiel entstehen; Streitfälle können geprüft werden.', sections: [
        { title: 'Verboten', bullets: ['Abgesprochene Siege oder absichtliche Niederlagen für Punkte, Wertung oder Belohnungen.', 'Kontoweitergabe oder Spielen unter einem fremden Profil.', 'Veränderung von Ergebnissen, erneute Einsendung desselben Spiels oder Ausnutzung von Fehlern für doppelte Belohnungen.', 'Versuche, Grenzen für Trupp, Kriegszeit, Handel oder Ausbau zu umgehen.'] },
        { title: 'Bei Problemen', paragraphs: ['Ein strittiges Spiel nicht erneut einsenden. In der Meldung Links zu Krieg oder Handel, Spieler und ungefähre Zeit angeben.', 'Ein verdächtiges Spiel bedeutet nicht automatisch eine Strafe; die Situation wird zusammen mit den verfügbaren Spieldaten geprüft.'], links: [{ label: 'Problem melden', to: '/feedback?from=%2Frules' }] },
      ] },
    ],
  };
};

const buildRuPlayerGuide = ({ values, season, version }) => {
  const rule = valueReader(values);
  const seasonName = season?.name || 'Тестовая кампания';
  const minMinutes = Math.round(rule('WAR_MIN_MATCH_DURATION_SECONDS') / 60);
  const reportLink = '/feedback?from=%2Frules';
  return {
    eyebrow: 'Путеводитель для игроков',
    title: 'Справочник мира ClanWars',
    intro: 'Здесь собраны правила и ответы на обычные вопросы: с чего начать, как устроены кланы, почему засчитываются не все матчи и что дают земли, ресурсы и реликвии.',
    versionLabel: `Правила v${version}`,
    seasonLabel: seasonName,
    updatedLabel: 'Обновлено 16 сентября 2026',
    navigationLabel: 'Разделы справочника',
    sectionMeta: `Сезон «${seasonName}» · правила v${version}`,
    fallbackNotice: 'Текущие настройки сезона временно не загрузились. Основные правила доступны ниже, а точные цены и сроки всегда показываются на сайте перед подтверждением действия.',
    incompleteNotice: 'Для завершённого сезона сохранилась только часть числовых настроек. Порядок игры и смысл механик описаны полностью.',
    categories: [
      {
        id: 'overview',
        label: 'О проекте',
        title: 'Что такое ClanWars и зачем здесь карта',
        summary: 'Ваши обычные рейтинговые матчи становятся частью общей кампании кланов за Средиземье.',
        sections: [
          {
            title: 'Самое простое объяснение',
            paragraphs: [
              'ClanWars — это общий игровой мир поверх матчей Rise of the Witch-king. Вы играете на Arena как обычно, а сайт собирает подходящие результаты, ведёт личную статистику и превращает победы участников клана в очки войны за территории.',
              'На карте кланы захватывают земли, получают с них доход, развивают укрепления и готовят новые походы. При этом вам не нужно запускать игру через сайт или искать отдельную очередь ClanWars.',
            ],
          },
          {
            title: 'Что делает обычный игрок',
            steps: [
              'Входит через Arena и завершает создание профиля.',
              'Вступает в клан или создаёт свой.',
              'Играет рейтинговые матчи в одном из поддерживаемых модов.',
              'Во время войн помогает клану атаковать или защищать территорию.',
              'Получает личную статистику, достижения, опыт и место в истории кампании.',
            ],
          },
          {
            title: 'Что делает глава клана',
            paragraphs: [
              'Глава собирает участников, назначает роли и Воевод, выбирает направление походов, развивает территории, управляет реликвиями и решает, какие предложения выставлять на рынке.',
              'Глава не обязан делать всё один. Торговлю можно поручить Торговцу, а походы распределить между Воеводами.',
            ],
          },
          {
            title: 'Что важно понять сразу',
            bullets: [
              'Название территории на глобальной карте не связано с игровой картой, на которой проходит матч.',
              'Предпочитаемый мод клана показывает интересы участников, но не ограничивает зачёт матчей.',
              'Личная статистика и результат войны — разные вещи: матч может остаться в профиле, но не дать клану очков.',
              'Влияние показывает развитие клана и открывает возможности; золото и редкие ресурсы расходуются на покупки.',
              'Все сроки на сайте показываются по московскому времени, если рядом не указано другое.',
            ],
          },
        ],
      },
      {
        id: 'site-guide',
        label: 'Разделы сайта',
        title: 'Где что находится',
        summary: 'Короткая карта сайта, чтобы новый игрок не искал нужную кнопку вслепую.',
        sections: [
          {
            title: 'Главная',
            paragraphs: ['На главной собрана общая картина кампании: состояние карты, активные войны, последние изменения владений, ведущие кланы и быстрый переход к правилам. Смотреть главную можно без авторизации.'],
            links: [{ label: 'Открыть главную', to: '/' }],
          },
          {
            title: 'Кланы',
            paragraphs: ['Здесь можно найти клан, посмотреть его состав и владения, подать заявку или создать собственный. Внутри страницы вашего клана находятся участники, статистика, реликвии, рынок и военная история.'],
            links: [{ label: 'Открыть кланы', to: '/clans' }],
          },
          {
            title: 'Карта и войны',
            paragraphs: ['Карта показывает владельцев земель, развитие территорий, соседние направления и места текущих войн. Раздел войн показывает активные и завершённые сражения, составы сторон, срок и засчитанные матчи.'],
            links: [{ label: 'Открыть карту', to: '/map' }, { label: 'Открыть войны', to: '/battles' }],
          },
          {
            title: 'Рейтинг, статистика и матчи',
            paragraphs: ['В рейтинге Elo разделён по модам Ennorath и Patch 2.02. Общая статистика помогает сравнивать игроков, кланы, фракции и карты. В списке матчей можно открыть конкретную игру и посмотреть участников, результат и данные повтора.'],
            links: [{ label: 'Открыть рейтинг', to: '/ranking' }, { label: 'Открыть статистику', to: '/statistics' }, { label: 'Открыть матчи', to: '/all-matches' }],
          },
          {
            title: 'Профиль, сообщения и уведомления',
            paragraphs: ['В профиле находятся ваша история игр, достижения, задания и доступное оформление. Личные сообщения позволяют связаться с другим игроком; нежелательный диалог можно заблокировать. Колокольчик в верхнем меню сообщает о приглашениях, решениях по заявкам, войнах, покупках и наградах.'],
            links: [{ label: 'Открыть профиль', to: '/profile' }, { label: 'Открыть сообщения', to: '/messages' }],
          },
          {
            title: 'Помощь и энциклопедия',
            paragraphs: ['Этот справочник объясняет правила сервиса. Энциклопедия посвящена понятиям игрового мира. Если нужного ответа нет или сайт повёл себя неправильно, создайте обращение и следите за ответом в том же разделе.'],
            links: [{ label: 'Открыть энциклопедию', to: '/encyclopedia' }, { label: 'Написать в поддержку', to: reportLink }],
          },
        ],
      },
      {
        id: 'getting-started',
        label: 'Первый вход',
        title: 'Аккаунт, Arena и начало игры',
        summary: 'Как связать игровой профиль с сайтом и не потерять старые матчи после смены ника.',
        sections: [
          {
            title: 'Почему вход проходит через Arena',
            paragraphs: [
              'Arena подтверждает, какой игровой профиль принадлежит вам. Благодаря этому сайт отличает настоящего владельца от человека с похожим ником и правильно связывает матчи, Elo и достижения.',
              'После подтверждения вы возвращаетесь на ClanWars и завершаете настройку аккаунта. Ник в профиле берётся из Arena.',
            ],
          },
          {
            title: 'Новая история или полная история',
            bullets: [
              'Новая история — прогресс на ClanWars начинается с момента присоединения. Старые матчи могут быть видны как данные Arena, но не участвуют в вашем новом прогрессе.',
              'Полная история — сайт загружает доступные прошлые матчи и учитывает их в статистике и достижениях настолько полно, насколько Arena сохранила эти данные.',
              'Если старого матча нет в доступной истории Arena, сайт не сможет восстановить его только по словам игрока.',
            ],
          },
          {
            title: 'Что будет после смены ника',
            paragraphs: [
              'Смена ника в Arena не создаёт нового игрока. После следующего входа или появления нового матча сайт узнает тот же профиль, покажет актуальный ник и сохранит матчи, достижения, Elo и членство в клане.',
              'Старый ник может использоваться внутри системы для поиска старых матчей, но в рейтинге и на публичных страницах игрок отображается под актуальным именем.',
            ],
          },
          {
            title: 'Если сайт просит войти снова',
            paragraphs: ['Авторизация действует ограниченное время и может завершиться после долгого перерыва или выхода со всех устройств. Повторный вход не создаёт второй профиль, если используется тот же аккаунт Arena.'],
          },
          {
            title: 'Что доступно без входа',
            paragraphs: ['Без авторизации можно открыть главную страницу, правила и энциклопедию. При переходе в кланы, карту, рейтинг, матчи или профили сайт предложит войти. После входа откроется запрошенный раздел.'],
          },
        ],
      },
      {
        id: 'clan-roles',
        label: 'Клан и роли',
        title: 'Создание клана, вступление и права участников',
        summary: 'Кто управляет кланом, как принимают людей и почему некоторые кнопки видит только глава.',
        sections: [
          {
            title: 'Как вступить в клан',
            steps: [
              'Откройте список кланов и выберите подходящий.',
              'Прочитайте описание, посмотрите состав, предпочитаемый мод и владения.',
              'Отправьте заявку и дождитесь решения главы.',
              'После принятия вы появитесь в составе и сможете приносить клану пользу.',
            ],
          },
          {
            title: 'Приглашения',
            paragraphs: ['Глава может отправить игроку приглашение. Его можно принять или отклонить. Приглашение не добавляет человека в клан автоматически: окончательное решение остаётся за самим игроком.'],
          },
          {
            title: 'Создание собственного клана',
            paragraphs: [
              'Игрок без клана может создать собственный. При создании задаются название, короткий тег, описание, предпочитаемый мод, аватар, эмблема для карты и цвет владений.',
              'Аватар используется на странице клана. Эмблема предназначена для карты; если отдельной эмблемы нет, используется аватар. Цвет помогает отличать владения, но не даёт игрового бонуса.',
            ],
          },
          {
            title: 'Основные роли',
            bullets: [
              'Глава управляет участниками, заявками, ролями, войнами, развитием владений, реликвиями и торговлей.',
              'Торговец может создавать, принимать и отменять предложения на рынке от имени клана.',
              'Воин — обычная боевая роль. Он может входить в отряд, участвовать в защите и приносить очки.',
              'Салага — начальная роль без управленческих прав. Это не штраф: такой участник всё равно может играть за клан.',
            ],
          },
          {
            title: 'Воевода',
            paragraphs: [
              'Воевода — дополнительное назначение поверх обычной роли. Воеводой может быть Глава, Торговец, Воин или Салага.',
              'Назначать и снимать Воевод может только глава. Воевода обязан лично входить в состав похода, который ведёт. Пока этот поход продолжается, снять или заменить его нельзя.',
            ],
            bullets: [
              'На I уровне доступен 1 Воевода, на II — 2, и так далее до 5.',
              'Один Воевода не может одновременно вести два действующих похода.',
              'Назначение Воеводой само по себе не даёт права тратить казну или менять роли.',
            ],
          },
          {
            title: 'Выход, исключение и передача лидерства',
            paragraphs: [
              `После выхода или исключения действует ожидание ${rule('CLAN_JOIN_TIMEOUT_HOURS') || 72} часа перед вступлением в другой клан. Это мешает переходить между кланами прямо во время войн.`,
              'Глава не может просто покинуть клан, пока отвечает за него. Сначала нужно передать лидерство другому участнику или удалить клан, если это действие доступно и подтверждено.',
              'Удаление клана — окончательное действие для его владельца. Перед подтверждением нужно убедиться, что клан действительно больше не нужен.',
            ],
          },
        ],
      },
      {
        id: 'territories',
        label: 'Карта и земли',
        title: 'Как устроена карта Средиземья',
        summary: 'Что обозначают цвета и значки, что получает владелец земли и откуда разрешено атаковать.',
        sections: [
          {
            title: 'Три состояния земли',
            bullets: [
              'Нейтральная земля свободна и не приносит доход ни одному клану.',
              'Занятая земля принадлежит клану, окрашена его цветом и приносит владельцу влияние и доход.',
              'Спорная земля участвует в активной войне. На карте такое место отмечено отдельно.',
            ],
          },
          {
            title: 'Что находится в карточке территории',
            bullets: [
              'Название и текущий владелец.',
              'Постоянное влияние, которое получает владеющий клан.',
              'Золотой доход и население.',
              'Добываемый редкий ресурс.',
              'Уровни населения, укреплений и военного лагеря.',
              'Наличие порта и уровень морской силы для прибрежных земель.',
              'Текущая война и срок её завершения, если земля оспаривается.',
            ],
          },
          {
            title: 'Соседство и сухопутная атака',
            paragraphs: ['Чтобы начать обычный сухопутный поход, клан выбирает свою исходную территорию и соседнюю цель. Нельзя начать атаку из любой точки карты только потому, что земля принадлежит вашему клану.'],
          },
          {
            title: 'Порты и море',
            paragraphs: ['Порт открывает предусмотренные морские пути между прибрежными землями. Морская цель не обязана касаться исходной территории границей, но между ними должен существовать разрешённый морской маршрут. Силу такого похода определяет морское развитие исходной земли.'],
          },
          {
            title: 'Великие крепости',
            paragraphs: ['Великие крепости дают больше золота и два разных редких ресурса. Для нападения на любую такую крепость клану требуется не меньше 5 владений и 350 постоянного влияния. Все три разновидности великих целей считаются крепостями и подчиняются одному правилу.'],
          },
          {
            title: 'Почему карта может не разрешить атаку',
            bullets: [
              'Цель не соседняя и к ней нет подходящего морского пути.',
              'Исходная территория не принадлежит вашему клану.',
              'За цель уже идёт война.',
              'У клана нет свободного очка атаки или подходящего Воеводы.',
              'Не выполнены требования великой крепости.',
              'Кампания временно приостановлена.',
            ],
            links: [{ label: 'Открыть карту', to: '/map' }],
          },
        ],
      },
      {
        id: 'attacks',
        label: 'Подготовка войны',
        title: 'Уровни клана, очки атаки и походный отряд',
        summary: 'Что проверяет сайт до объявления войны и кого глава должен включить в поход.',
        sections: [
          {
            title: 'Уровень клана',
            paragraphs: ['Уровень пересчитывается по трём условиям одновременно: числу участников, числу владений и постоянному влиянию. Недостаточно выполнить только одно из них. Уровень определяет число Воевод и параллельных атак.'],
            bullets: [
              `I уровень: без требований — ${rule('CLAN_LEVEL_1_ATTACK_CAPACITY')} очко атаки.`,
              `II уровень: ${rule('CLAN_LEVEL_2_ACTIVE_MEMBERS')} участников, ${rule('CLAN_LEVEL_2_TERRITORIES')} владения, ${rule('CLAN_LEVEL_2_INFLUENCE')} влияния — ${rule('CLAN_LEVEL_2_ATTACK_CAPACITY')} очка.`,
              `III уровень: ${rule('CLAN_LEVEL_3_ACTIVE_MEMBERS')} участников, ${rule('CLAN_LEVEL_3_TERRITORIES')} владения, ${rule('CLAN_LEVEL_3_INFLUENCE')} влияния — ${rule('CLAN_LEVEL_3_ATTACK_CAPACITY')} очка.`,
              `IV уровень: ${rule('CLAN_LEVEL_4_ACTIVE_MEMBERS')} участника, ${rule('CLAN_LEVEL_4_TERRITORIES')} владений, ${rule('CLAN_LEVEL_4_INFLUENCE')} влияния — ${rule('CLAN_LEVEL_4_ATTACK_CAPACITY')} очка.`,
              `V уровень: ${rule('CLAN_LEVEL_5_ACTIVE_MEMBERS')} участников, ${rule('CLAN_LEVEL_5_TERRITORIES')} владений, ${rule('CLAN_LEVEL_5_INFLUENCE')} влияния — ${rule('CLAN_LEVEL_5_ATTACK_CAPACITY')} очков.`,
            ],
          },
          {
            title: 'Что такое очко атаки',
            paragraphs: [`Каждая объявленная война занимает одно очко атаки. Оно возвращается отдельно через ${rule('CLAN_ATTACK_COOLDOWN_HOURS')} часов после объявления этой войны. Если у клана несколько очков, остальные можно использовать, не дожидаясь восстановления первого.`],
          },
          {
            title: 'Размер отряда',
            paragraphs: ['На I уровне клан может отправить любое доступное количество участников, даже одного Воеводу. Начиная со II уровня в атакующем отряде должно быть не меньше 5 игроков. Верхняя граница определяется доступным составом клана и условиями формы объявления войны.'],
          },
          {
            title: 'Как объявить поход',
            steps: [
              'Выбрать принадлежащую клану исходную территорию.',
              'Выбрать доступную соседнюю или морскую цель.',
              'Проверить свободное очко атаки и требования цели.',
              'Выбрать свободного Воеводу.',
              'Включить Воеводу и остальных бойцов в отряд.',
              'Проверить показанные бонусы, срок и состав.',
              'Подтвердить начало войны.',
            ],
          },
          {
            title: 'Почему состав нельзя поменять после старта',
            paragraphs: ['Состав фиксируется, чтобы клан не подставлял нужного игрока задним числом после уже сыгранного матча. Для атаки очки приносят только выбранные участники. Назначенный Воевода остаётся связан с походом до его завершения.'],
          },
        ],
      },
      {
        id: 'matches',
        label: 'Зачёт матчей',
        title: 'Какие матчи дают очки в войне',
        summary: 'Матч загружается автоматически, но получает военные очки только при выполнении всех условий.',
        sections: [
          {
            title: 'Обязательные условия',
            bullets: [
              `Рейтинговый формат 1v1, 2v2, 3v3 или 4v4.`,
              'Мод Ennorath или Patch 2.02.',
              `Продолжительность не меньше ${minMinutes} ${minMinutes === 1 ? 'минуты' : 'минут'}.`,
              `Начало матча попадает в ${rule('WAR_DURATION_HOURS')}-часовой период войны.`,
              'В матче есть подходящий участник атакующей или защищающейся стороны.',
              'Соперники не являются соклановцами на момент игры.',
              'Arena передала определённый результат и необходимых участников.',
            ],
          },
          {
            title: 'Кто приносит очки атаке',
            paragraphs: ['Только участники зафиксированного походного отряда. Победа другого участника того же клана останется в его личной статистике, но не усилит эту атаку.'],
          },
          {
            title: 'Кто приносит очки защите',
            paragraphs: ['При защите занятой территории учитывается текущий состав клана-владельца с учётом времени вступления. Человек, присоединившийся уже во время войны, не получает право задним числом засчитать более ранние матчи.'],
          },
          {
            title: 'С кем можно играть',
            paragraphs: ['Соперником может быть участник вражеского клана, другого клана или игрок без клана. Главное, чтобы это был допустимый рейтинговый матч и соперник не состоял в вашем собственном клане.'],
          },
          {
            title: 'На какой карте играть',
            paragraphs: ['На любой карте, разрешённой выбранным рейтинговым режимом. Игровая карта не обязана совпадать с названием территории, за которую идёт война. Например, за Рохан можно получить очки матчем, сыгранным на другой игровой карте.'],
          },
          {
            title: 'Какой мод выбирать',
            paragraphs: ['Оба поддерживаемых мода засчитываются. Выбор предпочитаемого мода в карточке клана нужен, чтобы другие игроки понимали, где чаще играет этот клан. Это не фильтр военных матчей.'],
          },
          {
            title: 'Командные игры',
            paragraphs: ['В командном матче очки распределяются по участникам стороны, которые имеют право помогать этой войне. Если вся победившая команда состоит из участников одного клана, сторона получает дополнительный командный бонус. Наблюдатели не считаются бойцами.'],
          },
          {
            title: 'Когда результат появляется не сразу',
            paragraphs: ['Сайт получает завершённые матчи из Arena через регулярное обновление. Иногда между окончанием игры и появлением результата проходит время. После конца войны предусмотрена проверка последних повторов, поэтому не нужно отправлять один матч несколько раз.'],
          },
        ],
        rejections: [
          { title: 'Неподдерживаемый режим', reason: 'Матч сыгран не в рейтинговом формате 1v1–4v4 или не в одном из двух поддерживаемых модов.', action: 'Сверьте режим и мод в карточке матча.', to: reportLink },
          { title: 'Матч слишком короткий', reason: `Игра длилась меньше ${minMinutes} ${minMinutes === 1 ? 'минуты' : 'минут'}.`, action: 'Такой матч остаётся в истории, но не даёт очков территории.', to: reportLink },
          { title: 'Матч вне времени войны', reason: 'Игра началась раньше похода или после окончания боевого периода.', action: 'Сравните время начала матча со сроками в карточке войны.', to: reportLink },
          { title: 'Атакующий не в отряде', reason: 'Игрок состоит в клане, но не был выбран в состав именно этого похода.', action: 'Проверьте список бойцов на странице войны.', to: reportLink },
          { title: 'Участник вступил позже', reason: 'На момент начала матча игрок ещё не состоял в нужном клане.', action: 'Учитывается реальная дата вступления, а не текущий состав.', to: reportLink },
          { title: 'Матч против соклановца', reason: 'Оба соперника находились в одном клане.', action: 'Личная статистика сохранится, но военные очки не начисляются.', to: reportLink },
          { title: 'Результат ещё проверяется', reason: 'Матч найден, но данных пока недостаточно для уверенного зачёта.', action: 'Подождите обновления. Если статус не меняется, отправьте обращение со ссылками.', to: reportLink },
        ],
      },
      {
        id: 'war-result',
        label: 'Очки и итог',
        title: 'Как считается война и кому достаётся земля',
        summary: 'Цена победы зависит от силы соперника, состава команды и бонусов клана.',
        sections: [
          {
            title: 'Базовые очки',
            paragraphs: [`Обычная победа даёт примерно ${rule('WAR_ELO_BASE_POINTS')} очков. Разница Elo меняет награду в пределах от ${rule('WAR_ELO_MIN_POINTS')} до ${rule('WAR_ELO_MAX_POINTS')}: победить более сильного соперника выгоднее, чем ожидаемо обыграть заметно более слабого.`],
          },
          {
            title: 'Командный бонус',
            paragraphs: [`Если вся победившая команда состоит из участников одного клана, к результату стороны добавляется ${rule('WAR_FULL_CLAN_TEAM_BONUS_PERCENT')}%. Смешанная команда может принести очки подходящим игрокам, но полного кланового бонуса не получает.`],
          },
          {
            title: 'Сила исходной территории',
            paragraphs: ['Для сухопутной атаки действует военный лагерь исходной земли. Для морской атаки — морская сила порта и флота. При защите помогают укрепления атакуемой территории. Эти значения фиксируются при начале войны, поэтому покупка улучшения позже не меняет уже идущий поход.'],
          },
          {
            title: 'Реликвии и предел бонусов',
            paragraphs: [`Активные реликвии могут добавить военные преимущества. Суммарное усиление ограничено ${rule('WAR_MODIFIER_CAP_PERCENT')}%, чтобы одна развитая сторона не получала бесконечно растущий перевес.`],
          },
          {
            title: 'Кто побеждает',
            paragraphs: [`Боевой период длится ${rule('WAR_DURATION_HOURS')} часов. После загрузки последних подходящих результатов сравниваются очки сторон. Атакующий захватывает землю, только если набрал больше. При равном счёте защита удерживает территорию.`],
          },
          {
            title: 'Что происходит с территорией после захвата',
            paragraphs: ['При захвате земли другого клана уровни военного лагеря, укреплений, населения и морского развития уменьшаются вдвое с округлением вниз. Население как число жителей и наличие порта сохраняются. Захват нейтральной земли и успешная защита уровни не уменьшают.'],
          },
          {
            title: 'Где посмотреть расчёт',
            paragraphs: ['Откройте конкретную войну. Там показаны стороны, срок, участники, общий счёт и матчи с их статусом. По карточке результата можно понять, какая сторона получила очки и какие прибавки сработали.'],
            links: [{ label: 'Открыть войны', to: '/battles' }],
          },
        ],
      },
      {
        id: 'economy',
        label: 'Экономика',
        title: 'Казна, влияние и развитие земель',
        summary: 'Откуда берутся ценности клана, на что они расходуются и почему влияние не похоже на обычную валюту.',
        sections: [
          {
            title: 'С чем начинает новый клан',
            paragraphs: [`В начале кампании клан получает ${rule('CAMPAIGN_STARTING_INFLUENCE')} влияния, ${rule('CAMPAIGN_STARTING_GOLD')} золота, ${rule('CAMPAIGN_STARTING_IRON')} железа, ${rule('CAMPAIGN_STARTING_WOOD')} дерева, ${rule('CAMPAIGN_STARTING_FOOD')} еды и ${rule('CAMPAIGN_STARTING_MITHRIL')} мифрила.`],
          },
          {
            title: 'Золото',
            paragraphs: ['Золото — основная расходуемая валюта клана. Оно приходит с территорий и тратится на развитие, реликвии и доставку торговых грузов. Доход начисляется постепенно, поэтому сумма может обновиться при открытии экономики клана.'],
          },
          {
            title: 'Влияние',
            paragraphs: ['Влияние показывает политический вес клана. Базовое влияние остаётся за кланом, а влияние территорий добавляется при захвате и исчезает при потере. Требование влияния проверяется для уровней клана, крепостей и части реликвий, но само влияние обычно не списывается как золото.'],
          },
          {
            title: 'Железо, дерево, еда и мифрил',
            bullets: [
              'Железо чаще требуется для укреплений и военных улучшений.',
              'Дерево нужно для населения, портов, флота и ряда реликвий.',
              'Еда используется в военном и морском развитии, а также в отдельных покупках.',
              'Мифрил — самый редкий ресурс для дорогих уровней и сильных реликвий.',
            ],
          },
          {
            title: 'Доход с территорий',
            paragraphs: [`Золото поступает каждый день. Обычные земли дают примерно 40–60 золота в сутки, великие крепости — 140–160 до учёта развития и бонусов. Точное значение видно в карточке конкретной территории.`],
          },
          {
            title: 'Редкая добыча',
            paragraphs: [`Подготовка добычи начинается после захвата. Первая партия появляется после ${rule('TERRITORY_RESOURCE_READY_HOURS')} часов непрерывного владения, следующие — каждые ${rule('TERRITORY_RESOURCE_PAYOUT_HOURS')} часа. Если землю потерять, подготовка прекращается.`, 'Обычная земля добывает один закреплённый ресурс, великая крепость — два. Мифрил добывается только в Мории и Карадрасе.'],
          },
          {
            title: 'Развитие владений',
            bullets: [
              `Население повышает золотой доход. Уровни I–V дают по ${rule('POPULATION_DEVELOPMENT_BONUS_FIRST_LEVELS_PERCENT')}%, уровни VI–X — по ${rule('POPULATION_DEVELOPMENT_BONUS_LATER_LEVELS_PERCENT')}%; число жителей добавляет ещё до ${rule('POPULATION_INCOME_BONUS_CAP_PERCENT')}%.`,
              'Укрепления усиливают защиту именно этой территории.',
              'Военный лагерь усиливает сухопутные походы, начатые именно с этой территории.',
              'Порт открывает морские пути, а флот усиливает морские походы. Морское развитие доступно только портовым землям.',
              'Цена следующего уровня показывается до подтверждения и растёт по мере развития.',
            ],
          },
          {
            title: 'Почему баланс мог измениться',
            paragraphs: ['Казна меняется после дохода территорий, покупки улучшения или реликвии, создания и принятия сделки, оплаты доставки либо возврата груза. Если сумма кажется неправильной, укажите в обращении клан, действие и примерное время.'],
          },
        ],
      },
      {
        id: 'relics',
        label: 'Реликвии',
        title: 'Коллекция и активный набор реликвий',
        summary: 'Реликвии покупаются навсегда, но одновременно действуют только выбранные главой.',
        sections: [
          {
            title: 'Покупка',
            paragraphs: ['Реликвия приобретается за казну клана и навсегда остаётся в его коллекции текущей кампании. Карточка заранее показывает требования, цену и эффект. Если указано требование влияния, оно открывает покупку, но не тратится.'],
          },
          {
            title: 'Улучшение',
            paragraphs: ['У реликвии может быть до трёх уровней. Каждый уровень покупается отдельно и усиливает указанный эффект. Высокий уровень обычно требует больше золота и редких ресурсов.'],
          },
          {
            title: 'Активный набор',
            paragraphs: ['Одновременно могут действовать не больше четырёх купленных реликвий. Выбирать набор может только глава. Остальные реликвии не пропадают: они остаются в коллекции и могут быть включены позже.'],
          },
          {
            title: 'Почему новая реликвия не заработала сразу',
            paragraphs: ['После изменения набора новые эффекты готовятся 48 часов. Таймер защищает кампанию от мгновенного переключения бонусов под каждую покупку или войну. На странице клана видно, когда набор станет готов.'],
          },
          {
            title: 'Реликвии и уже начавшаяся война',
            paragraphs: ['Война использует набор и значения, зафиксированные при её начале. Если реликвию включить, отключить или улучшить позже, это повлияет только на будущие события.'],
            links: [{ label: 'Открыть кланы', to: '/clans' }],
          },
        ],
      },
      {
        id: 'market',
        label: 'Рынок',
        title: 'Обмен ресурсами и путь каравана',
        summary: 'Кланы договариваются об обмене, резервируют груз и оплачивают его доставку по карте.',
        sections: [
          {
            title: 'Кто может торговать',
            paragraphs: ['Создавать, принимать и отменять предложения могут глава и назначенный Торговец. Обычный участник видит рынок, но не распоряжается общими ресурсами без соответствующей роли.'],
          },
          {
            title: 'Как создать предложение',
            steps: [
              'Выбрать ресурс и количество, которое клан отдаёт.',
              'Указать ресурс и количество, которое клан хочет получить.',
              'Выбрать срок действия предложения.',
              'Проверить доступность груза и опубликовать сделку.',
            ],
          },
          {
            title: 'Что происходит при принятии',
            paragraphs: ['Принимающий клан видит маршрут, стоимость доставки и время прибытия до подтверждения. После принятия груз обеих сторон резервируется, а каждый клан оплачивает перевозку своей части. Нельзя потратить зарезервированный ресурс второй раз.'],
          },
          {
            title: 'Маршрут, цена и время',
            paragraphs: [`Один сухопутный переход занимает ${rule('CARAVAN_HOURS_PER_STEP')} часов, морской — ${rule('CARAVAN_SEA_HOURS_PER_STEP')} часов. Чем длиннее путь и больше груз, тем дороже перевозка. Маршрут существует только между владениями, связанными доступными дорогами или морскими переходами.`],
          },
          {
            title: 'Отмена и возврат',
            paragraphs: ['Открытое предложение можно отменить, пока его никто не принял. Уже отправленный караван отменить нельзя. Если доставка больше не может продолжаться, груз не исчезает: он остаётся защищённым до продолжения пути или возврата.'],
          },
          {
            title: 'Почему сделку нельзя принять',
            bullets: [
              'У одного из кланов уже не хватает обещанного ресурса.',
              'Не хватает золота на доставку.',
              'Между владениями нет доступного маршрута.',
              'Предложение закончилось или уже принято другим кланом.',
              'Вашей роли недостаточно для управления рынком.',
            ],
          },
        ],
      },
      {
        id: 'progress',
        label: 'Личный прогресс',
        title: 'Elo, матчи, задания и достижения',
        summary: 'Что принадлежит лично игроку и чем личный рейтинг отличается от успехов клана.',
        sections: [
          {
            title: 'Два отдельных Elo',
            paragraphs: [`Ennorath и Patch 2.02 имеют независимые рейтинги. В каждом новый рейтинг начинается с ${rule('ELO_START_RATING')}, а первые ${rule('ELO_PROVISIONAL_MATCHES')} матчей быстрее определяют подходящий уровень. Игра в одном моде не меняет Elo другого.`],
          },
          {
            title: 'Что показывает профиль',
            bullets: [
              'Общее число матчей, побед, поражений и процент побед.',
              'Отдельное Elo по поддерживаемым модам.',
              'Любимые и наиболее успешные фракции и карты.',
              'Достижения, выбранный титул и оформление.',
              'Текущий клан, роль и вклад в его войны.',
              'Историю подходящих матчей.',
            ],
          },
          {
            title: 'Достижения',
            paragraphs: ['Достижения открываются по подтверждённым данным: за матчи, победы, серии, режимы, фракции, карты и другие указанные условия. Уже полученное достижение не отбирается при смене ника и не выдаёт награду повторно.'],
            links: [{ label: 'Открыть достижения', to: '/achievements' }],
          },
          {
            title: 'Ежедневные и недельные задания',
            paragraphs: ['В профиле есть Путь героя с ежедневными и недельными заданиями. Прогресс обновляется по подходящим матчам. Когда условие выполнено, награду нужно забрать кнопкой в карточке задания до его обновления.'],
          },
          {
            title: 'Опыт и уровень',
            paragraphs: ['Опыт выдаётся за предусмотренные личные действия и награды. При накоплении опыта повышается уровень профиля. Уровень игрока не заменяет Elo: Elo отражает результаты матчей, а уровень — общий прогресс на сайте.'],
          },
          {
            title: 'Титулы и оформление',
            paragraphs: ['Полученные титулы, рамки, фоны и значки меняют внешний вид профиля и имени. Они не дают Elo, ресурсов, очков войны или скрытого преимущества в матчах.'],
          },
          {
            title: 'Почему цифры профиля и войны различаются',
            paragraphs: ['Профиль считает ваши подходящие матчи как личную историю. Война дополнительно проверяет время, клан, состав похода и соперника. Поэтому матч может увеличить личную статистику, но не изменить счёт конкретной войны.'],
          },
        ],
      },
      {
        id: 'fairplay',
        label: 'Общение и помощь',
        title: 'Сообщения, обращения и честная игра',
        summary: 'Как связаться с игроком или администрацией и какие способы получения преимущества запрещены.',
        sections: [
          {
            title: 'Личные сообщения',
            paragraphs: ['Через профиль можно открыть диалог с другим игроком. Сообщения предназначены для обычного общения и договорённостей о честной игре. Если человек мешает или оскорбляет, его можно заблокировать в диалоге.'],
          },
          {
            title: 'Уведомления',
            paragraphs: ['Колокольчик сообщает о важных событиях: приглашениях, решениях по заявкам, изменениях роли, начале и завершении войн, покупках и наградах. Прочитанное уведомление не исчезает из истории самого события.'],
          },
          {
            title: 'Как правильно сообщить о проблеме',
            steps: [
              'Откройте раздел обращений.',
              'Выберите: ошибка, предложение, вопрос или другое.',
              'Коротко напишите, что произошло.',
              'Добавьте ссылку на матч, войну, территорию или клан.',
              'Укажите примерное время и ожидаемый результат.',
              'При необходимости приложите изображение.',
              'Следите за ответом в созданном обращении.',
            ],
            links: [{ label: 'Создать обращение', to: reportLink }],
          },
          {
            title: 'Что запрещено',
            bullets: [
              'Договорные победы и намеренные поражения ради Elo, очков войны или наград.',
              'Передача аккаунта и игра под чужим профилем.',
              'Попытки подменить или повторно отправить результат ради двойной награды.',
              'Использование ошибок для обхода состава похода, сроков, цен, ролей или ограничений.',
              'Оскорбления, угрозы и нежелательные сообщения другим участникам.',
            ],
          },
          {
            title: 'Проверка спорной ситуации',
            paragraphs: ['Подозрительный матч не означает автоматическое наказание. Сначала рассматриваются доступные сведения и контекст. Не отправляйте один результат многократно: это не ускорит проверку и может усложнить разбор.'],
          },
        ],
      },
      {
        id: 'faq',
        label: 'Частые вопросы',
        title: 'Простые ответы на вопросы, которые обычно возникают первыми',
        summary: 'Если что-то кажется очевидным только старым игрокам, ответ должен быть здесь.',
        sections: [
          { title: 'Нужно ли скачивать отдельную игру или программу?', paragraphs: ['Нет. Вы играете в поддерживаемые рейтинговые матчи через привычную Arena. ClanWars показывает кампанию и использует результаты этих матчей.'] },
          { title: 'Нужно ли запускать матч со страницы войны?', paragraphs: ['Нет. После объявления войны просто играйте подходящие рейтинговые матчи. Результаты появятся автоматически.'] },
          { title: 'Нужно ли играть на карте с названием территории?', paragraphs: ['Нет. Глобальная территория и игровая карта — разные вещи. Выбирайте любую карту, разрешённую рейтинговым режимом.'] },
          { title: 'Обязательно ли играть против клана-защитника?', paragraphs: ['Нет. Подходящим соперником может быть любой игрок не из вашего клана. Для зачёта важны условия матча и ваше право участвовать в атаке или защите.'] },
          { title: 'Засчитываются ли оба мода?', paragraphs: ['Да. Ennorath и Patch 2.02 одинаково могут приносить очки войне. Их Elo при этом считается отдельно.'] },
          { title: 'Почему клан выбрал один мод, а матч другого мода засчитался?', paragraphs: ['Выбранный мод — только подсказка другим игрокам о предпочтениях клана. Он не запрещает второй поддерживаемый мод.'] },
          { title: 'Почему мой матч есть в профиле, но его нет в очках войны?', paragraphs: ['Личная история требует только корректного матча. Для войны дополнительно проверяются срок, состав похода, членство в клане, соперник и минимальная продолжительность.'] },
          { title: 'Я выиграл во время атаки. Почему очков нет?', paragraphs: ['Сначала проверьте, включены ли вы в зафиксированный атакующий отряд. Простого членства в атакующем клане недостаточно.'] },
          { title: 'Кто может защищать территорию?', paragraphs: ['Текущие участники клана-владельца, которые имели право представлять клан на момент матча. Отдельный атакующий отряд для защиты занятой земли не требуется.'] },
          { title: 'Может ли свободный игрок помочь войне?', paragraphs: ['Игрок без клана может быть соперником, но не приносит очки какой-либо стороне как её участник.'] },
          { title: 'Что происходит при ничьей в войне?', paragraphs: ['Защита удерживает территорию. Чтобы захватить землю, атакующая сторона должна набрать строго больше очков.'] },
          { title: 'Можно ли поменять отряд после начала?', paragraphs: ['Нет. Состав фиксируется при объявлении похода. Это относится и к Воеводе.'] },
          { title: 'Можно ли вести несколько войн?', paragraphs: ['Да, если уровень клана даёт несколько очков атаки, есть свободные Воеводы и выполняются остальные требования. Каждое очко восстанавливается по своему таймеру.'] },
          { title: 'Почему я не могу назначить ещё одного Воеводу?', paragraphs: ['Число Воевод не может быть выше уровня клана. Кроме того, участника нельзя снять или заменить, пока он ведёт действующий поход.'] },
          { title: 'Исчезают ли ресурсы при поражении?', paragraphs: ['Казна клана напрямую не передаётся победителю. При захвате меняется владелец территории, а уровни её развития уменьшаются по правилам захвата.'] },
          { title: 'Почему редкий ресурс не пришёл сразу после захвата?', paragraphs: [`Первая добыча требует ${rule('TERRITORY_RESOURCE_READY_HOURS')} часов непрерывного владения. После этого выплаты идут раз в ${rule('TERRITORY_RESOURCE_PAYOUT_HOURS')} часа.`] },
          { title: 'Почему купленная реликвия не действует?', paragraphs: ['Покупка добавляет реликвию в коллекцию. Глава должен включить её в активный набор, после чего новый эффект готовится 48 часов.'] },
          { title: 'Можно ли вернуть отправленный караван?', paragraphs: ['Самостоятельно отменить уже принятую сделку нельзя. Если маршрут нарушен, груз остаётся защищённым до продолжения пути или возврата по правилам рынка.'] },
          { title: 'Что будет, если я сменю ник?', paragraphs: ['Сайт сохранит ваш профиль и покажет новый ник после подтверждения через Arena. Матчи, Elo, достижения и клан останутся у того же игрока.'] },
          { title: 'Можно ли состоять сразу в двух кланах?', paragraphs: ['Нет. Один игрок может быть участником только одного обычного клана одновременно.'] },
          { title: 'Когда можно вступить в новый клан после выхода?', paragraphs: [`После выхода или исключения действует ожидание ${rule('CLAN_JOIN_TIMEOUT_HOURS') || 72} часа. Оставшееся время показывается на сайте.`] },
          { title: 'Почему я не вижу кнопку управления?', paragraphs: ['Кнопки зависят от вашей роли. Управление участниками и войнами доступно главе, торговые действия — главе и Торговцу, а административные функции обычным игрокам не показываются.'] },
          { title: 'Что делать, если ответ здесь не найден?', paragraphs: ['Создайте обращение в категории «Вопрос». Опишите ситуацию обычными словами и приложите ссылку на нужную страницу.'], links: [{ label: 'Задать вопрос', to: reportLink }] },
        ],
      },
    ],
  };
};

const addCompanionSections = (handbook, language) => {
  if (handbook.categories.some(({ id }) => id === 'site-guide')) return handbook;
  const copy = {
    en: {
      site: { id: 'site-guide', label: 'Site guide', title: 'Where to find everything', summary: 'A map of the player-facing pages and the purpose of each one.', sections: [{ title: 'Main sections', paragraphs: ['Home shows the campaign overview. Clans contains membership, relics and trade. Map and Battles explain the territorial war. Ranking, Statistics and Matches cover player results. Profile contains personal progress, quests and appearance. Messages and Feedback provide communication and support.'] }] },
      faq: { id: 'faq', label: 'Common questions', title: 'Quick answers for new players', summary: 'Short answers to the questions most players ask first.', sections: [{ title: 'The essentials', bullets: ['You do not need a separate ClanWars game client.', 'The game map does not have to match the territory name.', 'Both Ennorath and Patch 2.02 may score war points.', 'A personal match may be valid without scoring for a particular war.', 'Changing your Arena nickname does not create a new player profile.'] }] },
    },
    de: {
      site: { id: 'site-guide', label: 'Seitennavigation', title: 'Wo du alles findest', summary: 'Ein Überblick über die Seiten und ihre Aufgaben.', sections: [{ title: 'Hauptbereiche', paragraphs: ['Die Startseite zeigt die Kampagne. Clans enthält Mitglieder, Relikte und Handel. Karte und Schlachten erklären den Gebietskrieg. Rangliste, Statistik und Spiele zeigen Ergebnisse. Im Profil findest du Fortschritt, Aufgaben und Gestaltung. Nachrichten und Meldungen dienen Kommunikation und Hilfe.'] }] },
      faq: { id: 'faq', label: 'Häufige Fragen', title: 'Kurze Antworten für neue Spieler', summary: 'Antworten auf die Fragen, die am Anfang am häufigsten entstehen.', sections: [{ title: 'Das Wichtigste', bullets: ['Du brauchst keinen eigenen ClanWars-Spielclient.', 'Die Spielkarte muss nicht wie das umkämpfte Gebiet heißen.', 'Ennorath und Patch 2.02 können beide Kriegspunkte bringen.', 'Ein persönliches Spiel kann gültig sein, ohne für einen Krieg zu zählen.', 'Ein neuer Arena-Name erstellt kein neues Spielerprofil.'] }] },
    },
  }[language];
  if (!copy) return handbook;
  return {
    ...handbook,
    categories: [
      handbook.categories[0],
      copy.site,
      ...handbook.categories.slice(1),
      copy.faq,
    ],
  };
};

const builders = { ru: buildRuPlayerGuide, en: buildEn, de: buildDe };

export const getClanWarHandbook = (language, payload = {}, { seasonId, loading = false, loadError = false } = {}) => {
  const upcoming = !loading && !loadError && seasonId == null && payload.season == null
    && payload.guide?.mechanics_version === 'cycle_v1' && payload.guide.status === 'upcoming'
    && Number.isInteger(payload.guide.previous_season_id) && payload.guide.previous_season_id > 0;
  if (upcoming) {
    return getCycleClanWarHandbook(payload, { upcoming: true, previousSeasonId: payload.guide.previous_season_id });
  }
  if (!loading && !loadError && payload.mechanics_version === 'cycle_v1'
      && payload.season?.id != null
      && (seasonId == null || String(payload.season.id) === String(seasonId))) {
    return getCycleClanWarHandbook(payload);
  }
  const builder = builders[language] || builders.ru;
  const ruleSet = payload.rule_set || {};
  const handbook = builder({ values: ruleSet.values || DEFAULT_VALUES, season: payload.season || null, version: ruleSet.version || 5 });
  return addCompanionSections(handbook, language);
};

export const CLAN_WAR_HANDBOOK_SECTION_IDS = [
  'overview', 'site-guide', 'getting-started', 'clan-roles', 'territories', 'attacks',
  'matches', 'war-result', 'economy', 'relics', 'market', 'progress', 'fairplay', 'faq',
];
