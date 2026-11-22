const documents = {
  ru: {
    gettingStarted: {
      title: 'Быстрый старт игрока',
      intro: 'Короткий маршрут от первого входа до участия в жизни клана и кампании.',
      sections: [
        {
          title: '1. Подтвердите игровой профиль',
          body: 'В профиле привяжите свой ник из рейтинговой системы. Подтверждённая личность нужна, чтобы сервер мог связать replay с вами, показать Elo по модам и учитывать матчи в войнах клана.',
        },
        {
          title: '2. Вступите в клан',
          body: 'Найдите подходящий клан в общем списке и договоритесь с его главой. После вступления станут доступны клановая статистика, казна, территория и вклад в активные войны. Создать собственный клан можно только свободным подтверждённым профилем.',
        },
        {
          title: '3. Продолжайте играть рейтинг',
          body: 'Отдельная очередь не нужна. Играйте рейтинговые матчи 1v1–4v4 в Ennorath или Patch 2.02 и сохраняйте replay. Если вы входите в назначенный атакующий отряд или защищающийся клан, валидный матч автоматически попадёт в активную войну.',
        },
        {
          title: '4. Следите за результатом',
          body: 'На странице войны видны счёт, участники, зачтённые матчи и причины отклонения. Профиль показывает личную статистику и достижения, а страницы клана и карты — общий прогресс, земли и влияние.',
        },
      ],
    },
    economy: {
      title: 'Экономика и развитие',
      intro: 'Практический справочник по клановой казне, доходам земель и долгосрочному развитию.',
      sections: [
        {
          title: 'Казна и ресурсы',
          body: 'Клан хранит золото, железо, дерево, еду и мифрил в общей казне. Расходы на развитие, реликвии и доставку торговых грузов списываются только через серверные операции и остаются в журнале.',
        },
        {
          title: 'Доходы территорий',
          body: 'Каждая удерживаемая земля приносит влияние и ежедневный доход. Редкие ресурсы начинают поступать после 48 часов непрерывного владения; потеря земли сбрасывает этот срок. Великие города могут добывать два разных ресурса.',
        },
        {
          title: 'Улучшения земель',
          body: 'Население повышает золотой доход, укрепления усиливают защиту, лагерь — сухопутную атаку, а единая морская мощь развивает порт и боевой флот. Перед покупкой карта показывает стоимость следующего уровня и доступные средства клана.',
        },
        {
          title: 'Влияние и реликвии',
          body: 'Влияние не тратится как валюта: оно показывает силу владений и открывает цели и уровни реликвий. Сами реликвии покупаются за золото и редкие ресурсы и дают постоянные бонусы к войне, экономике или развитию.',
        },
        {
          title: 'Рынок и караваны',
          body: 'Клан с территорией может обменивать ресурсы через публичные предложения. После сделки груз резервируется и отправляется между землями; расстояние, маршрут и объём определяют цену и время доставки.',
        },
      ],
    },
    privacy: {
      title: 'Обработка данных аккаунта',
      intro: 'Этот документ объясняет, на что вы соглашаетесь при регистрации или первом входе через BFME Arena.',
      sections: [
        { title: 'Какие данные используются', body: 'Сервис хранит ник и идентификатор профиля Arena, выбранный язык, e-mail при регистрации по паролю, защищённый хэш локального пароля, сведения о входах, настройках профиля, клане, матчах, достижениях и действиях в кампании. Пароль в открытом виде не сохраняется.' },
        { title: 'Для чего это нужно', body: 'Данные используются для входа, устойчивой привязки игрового профиля при смене ника, учёта рейтинга и replay, работы кланов, войн, экономики, уведомлений, сообщений, предотвращения злоупотреблений и восстановления доступа.' },
        { title: 'Кому видны данные', body: 'Публичные страницы могут показывать ник, аватар, игровой рейтинг, матчи, достижения, клан и результаты кампании. E-mail, данные входа и технические идентификаторы не публикуются. Передача третьим лицам возможна только для работы подключённых сервисов, хостинга и требований закона.' },
        { title: 'Хранение и защита', body: 'Доступ к административным операциям ограничен ролями, а важные изменения записываются в аудит. Данные хранятся, пока аккаунт нужен для работы проекта или пока это требуется для целостности истории матчей, войн и финансовых операций.' },
        { title: 'Ваш выбор', body: 'Устанавливая галочку, вы подтверждаете, что прочитали правила проекта и разрешаете описанную обработку данных. По вопросам исправления или удаления личных данных обратитесь к администрации; часть обезличенной истории может сохраниться для корректности результатов кампании.' },
      ],
    },
    overview: {
      title: 'Общие сведения о проекте',
      intro: 'ROTWK ClanWars представляет собой стратегическую клановую кампанию поверх реальных рейтинговых матчей Rise of the Witch-king.',
      sections: [
        {
          title: 'Назначение проекта',
          body: 'Проект придаёт обычным матчам долгосрочный смысл. Победы игроков помогают клану захватывать Средиземье, удерживать крепости, развивать экономику и создавать собственную историю сезона. Проект не заменяет игру и не требует отдельной очереди на конкретную карту.',
        },
        {
          title: 'Как проходит кампания',
          body: 'Игрок подтверждает ник, вступает в клан и продолжает играть рейтинговые матчи. Глава выбирает территорию и атакующий отряд. Сервер получает replay через API, проверяет результат и начисляет очки активной войне. Через 60 часов победитель получает землю и её будущие преимущества.',
        },
        {
          title: 'Карта и стратегия',
          body: 'На интерактивной карте 76 земель с разными доходами, ресурсами, влиянием и маршрутами. Обычные атаки идут через общую границу, порты открывают морские походы. Великие города требуют развитого клана и становятся долгосрочными целями кампании.',
        },
        {
          title: 'Экономика клана',
          body: 'Кланы получают золото, железо, дерево, еду и мифрил. Земли можно улучшать, а ресурсы — вкладывать в население, укрепления, военные лагеря, порты, флот и постоянные реликвии. Влияние показывает территориальную силу и открывает более сложные цели.',
        },
        {
          title: 'Торговля',
          body: 'Через рынок кланы обменивают редкие ресурсы. Груз не телепортируется: он резервируется и идёт караваном или кораблём между владениями. Расстояние влияет на цену и время, а активные доставки и история сделок видны участникам.',
        },
        {
          title: 'Игроки и статистика',
          body: 'Профиль хранит Elo отдельно по модам, матчи, фракции, карты, достижения и титулы. Статистика клана учитывает только реальный период членства игрока. Завершённые войны сохраняются со всеми матчами, расчётами и итоговым владельцем территории.',
        },
        {
          title: 'Итоговая концепция',
          body: 'Проект создаёт честную метаигру, где важны и сила игроков, и решения главы: кого отправить в поход, какую землю развивать, когда торговать и на какую крепость наступать. Перед первым официальным сезоном баланс будет проверен на живых кланах, а затем правила сезона будут зафиксированы.',
        },
      ],
    },
  },
  en: {
    gettingStarted: {
      title: 'Player Quick Start',
      intro: 'A short path from your first sign-in to taking part in clan life and the campaign.',
      sections: [
        { title: '1. Verify your game profile', body: 'Link your ranked nickname from the profile page. Verification lets the server connect replays to you, show mod-specific Elo, and count your matches in clan wars.' },
        { title: '2. Join a clan', body: 'Find a suitable clan in the public list and contact its leader. Membership unlocks clan statistics, treasury context, territories, and contributions to active wars. Only a free verified profile can create a new clan.' },
        { title: '3. Keep playing ranked games', body: 'No separate queue is required. Play ranked 1v1–4v4 in Ennorath or Patch 2.02 and retain the replay. A valid game automatically reaches an active war when you belong to its attacking warband or defending clan.' },
        { title: '4. Follow the result', body: 'The war page shows the score, participants, accepted matches, and rejection reasons. Your profile contains personal statistics and achievements, while clan and map pages show shared progress, territories, and influence.' },
      ],
    },
    economy: {
      title: 'Economy and Development',
      intro: 'A practical guide to the clan treasury, territory income, and long-term development.',
      sections: [
        { title: 'Treasury and resources', body: 'A clan shares gold, iron, wood, food, and mithril in one treasury. Territory upgrades, relics, and trade delivery are paid through server-side operations and remain visible in the ledger.' },
        { title: 'Territory income', body: 'Every held territory grants influence and daily income. Rare resources begin after 48 hours of uninterrupted ownership; losing the land resets that timer. Great cities may produce two different resources.' },
        { title: 'Territory upgrades', body: 'Population increases gold income, fortifications improve defense, camps improve land attacks, and a unified naval-power upgrade develops both port and war fleet. The map shows the next level price and available clan resources before purchase.' },
        { title: 'Influence and relics', body: 'Influence is not spent as currency: it represents territorial power and unlocks objectives and relic tiers. Relics themselves cost gold and rare resources and provide permanent war, economy, or development bonuses.' },
        { title: 'Market and caravans', body: 'A clan that owns territory may exchange resources through public offers. Once accepted, cargo is reserved and travels between holdings; distance, route, and volume determine delivery price and duration.' },
      ],
    },
    privacy: {
      title: 'Account Data Processing',
      intro: 'This document explains what you accept when registering or signing in through BFME Arena for the first time.',
      sections: [
        { title: 'Data we use', body: 'The service stores your Arena nickname and profile identifier, language, email for password registration, a protected local-password hash, sign-in records, profile settings, clan data, matches, achievements, and campaign actions. Plain-text passwords are never stored.' },
        { title: 'Why we use it', body: 'The data supports sign-in, stable profile linking after nickname changes, ratings and replay processing, clans, wars, economy, notifications, messages, abuse prevention, and account recovery.' },
        { title: 'What is public', body: 'Public pages may show nickname, avatar, game rating, matches, achievements, clan, and campaign results. Email, sign-in data, and technical identifiers are not published. Data is shared only as needed for connected services, hosting, or legal obligations.' },
        { title: 'Storage and security', body: 'Administrative actions are role-restricted and important changes are audited. Data is retained while the account is needed for the project or while match, war, and financial history must remain consistent.' },
        { title: 'Your choice', body: 'Checking the box confirms that you read the project rules and permit the processing described here. Contact the administrators to correct or request deletion of personal data; anonymised history may remain where needed to preserve campaign results.' },
      ],
    },
    overview: {
      title: 'About the Project',
      intro: 'ROTWK ClanWars is a strategic clan campaign powered by real ranked Rise of the Witch-king matches.',
      sections: [
        { title: 'Purpose of the project', body: 'The project gives regular matches a long-term purpose. Player victories help a clan conquer Middle-earth, hold strongholds, develop an economy and create its own seasonal history. It does not replace the game or require a separate queue for one map.' },
        { title: 'How a campaign works', body: 'A player verifies a nickname, joins a clan and keeps playing ranked games. The leader chooses a territory and an attacking warband. The server receives replays through the API, validates them and scores the active war. After 60 hours, the winner takes the land and its future benefits.' },
        { title: 'Map and strategy', body: 'The interactive map contains 76 territories with different income, resources, influence and routes. Normal attacks cross shared borders, while ports unlock naval campaigns. Great cities require an established clan and become long-term campaign goals.' },
        { title: 'Clan economy', body: 'Clans earn gold, iron, wood, food and mithril. Resources fund population, fortifications, military camps, ports, fleets and permanent relics. Influence represents territorial power and unlocks more demanding objectives.' },
        { title: 'Trade', body: 'The market lets clans exchange rare resources. Cargo does not teleport: it is reserved and travels between holdings by caravan or ship. Distance determines price and delivery time, while active shipments and trade history remain visible.' },
        { title: 'Players and statistics', body: 'A profile stores patch-specific Elo, matches, factions, maps, achievements and titles. Clan statistics count only the player’s actual membership period. Completed wars remain archived with every match, calculation and final territory owner.' },
        { title: 'Final concept', body: 'The project creates a fair metagame where player strength and leadership decisions both matter: who joins a warband, which land is developed, when to trade and which stronghold to attack. Before the first official season, live clans will test the balance; the season rules will then be locked.' },
      ],
    },
  },
  de: {
    gettingStarted: {
      title: 'Schnellstart für Spieler',
      intro: 'Der kurze Weg von der ersten Anmeldung bis zur Teilnahme am Clanleben und an der Kampagne.',
      sections: [
        { title: '1. Spielprofil bestätigen', body: 'Verknüpfe deinen Ranglistennamen im Profil. Die Bestätigung verbindet Replays mit dir, zeigt deine Elo je Mod und ermöglicht die Wertung deiner Spiele in Clankriegen.' },
        { title: '2. Einem Clan beitreten', body: 'Suche in der öffentlichen Liste einen passenden Clan und sprich mit seinem Anführer. Danach erhältst du Zugang zu Clanstatistik, Schatzkammer, Gebieten und Beiträgen zu aktiven Kriegen. Nur ein freies bestätigtes Profil kann einen neuen Clan gründen.' },
        { title: '3. Weiter Rangliste spielen', body: 'Eine eigene Warteschlange ist nicht nötig. Spiele Ranglistenpartien von 1v1 bis 4v4 in Ennorath oder Patch 2.02 und bewahre das Replay auf. Ein gültiges Spiel wird automatisch einem aktiven Krieg zugeordnet, wenn du zum Angriffstrupp oder zum verteidigenden Clan gehörst.' },
        { title: '4. Ergebnis verfolgen', body: 'Die Kriegsseite zeigt Punktestand, Teilnehmer, gewertete Spiele und Ablehnungsgründe. Dein Profil enthält persönliche Statistiken und Erfolge; Clan- und Kartenseiten zeigen gemeinsamen Fortschritt, Gebiete und Einfluss.' },
      ],
    },
    economy: {
      title: 'Wirtschaft und Entwicklung',
      intro: 'Ein praktischer Leitfaden zu Clanschatzkammer, Gebietseinkommen und langfristigem Ausbau.',
      sections: [
        { title: 'Schatzkammer und Ressourcen', body: 'Ein Clan verwaltet Gold, Eisen, Holz, Nahrung und Mithril gemeinsam. Gebietsausbau, Relikte und Handelslieferungen werden über Servervorgänge bezahlt und bleiben im Buch sichtbar.' },
        { title: 'Gebietseinkommen', body: 'Jedes gehaltene Gebiet gibt Einfluss und tägliches Einkommen. Seltene Ressourcen beginnen nach 48 Stunden ununterbrochenem Besitz; ein Verlust setzt den Zeitraum zurück. Große Städte können zwei verschiedene Ressourcen erzeugen.' },
        { title: 'Gebietsausbau', body: 'Bevölkerung erhöht das Goldeinkommen, Befestigungen stärken die Verteidigung, Lager den Landangriff und eine gemeinsame Seemacht-Stufe entwickelt Hafen und Kampfflotte. Vor dem Kauf zeigt die Karte den Preis der nächsten Stufe und die verfügbaren Clanmittel.' },
        { title: 'Einfluss und Relikte', body: 'Einfluss wird nicht als Währung ausgegeben. Er beschreibt territoriale Macht und schaltet Ziele und Reliktstufen frei. Relikte kosten Gold und seltene Ressourcen und geben dauerhafte Boni für Krieg, Wirtschaft oder Entwicklung.' },
        { title: 'Markt und Karawanen', body: 'Ein Clan mit eigenem Gebiet kann Ressourcen über öffentliche Angebote tauschen. Nach Annahme wird die Ladung reserviert und reist zwischen Besitzungen; Entfernung, Route und Menge bestimmen Preis und Dauer.' },
      ],
    },
    privacy: {
      title: 'Verarbeitung von Kontodaten',
      intro: 'Dieses Dokument erklärt, was du bei der Registrierung oder der ersten Anmeldung über BFME Arena akzeptierst.',
      sections: [
        { title: 'Verwendete Daten', body: 'Der Dienst speichert Arena-Namen und Profilkennung, Sprache, E-Mail bei Passwortregistrierung, einen geschützten Hash des lokalen Passworts, Anmeldedaten, Profileinstellungen, Clan, Spiele, Erfolge und Kampagnenaktionen. Passwörter werden niemals im Klartext gespeichert.' },
        { title: 'Zweck', body: 'Die Daten ermöglichen Anmeldung, stabile Profilverknüpfung nach Namenswechseln, Wertung und Replay-Verarbeitung, Clans, Kriege, Wirtschaft, Benachrichtigungen, Nachrichten, Missbrauchsschutz und Kontowiederherstellung.' },
        { title: 'Öffentliche Daten', body: 'Öffentliche Seiten können Namen, Avatar, Spielwertung, Spiele, Erfolge, Clan und Kampagnenergebnisse zeigen. E-Mail, Anmeldedaten und technische Kennungen werden nicht veröffentlicht. Eine Weitergabe erfolgt nur soweit für verbundene Dienste, Hosting oder gesetzliche Pflichten nötig.' },
        { title: 'Speicherung und Schutz', body: 'Administrative Aktionen sind durch Rollen geschützt; wichtige Änderungen werden protokolliert. Daten bleiben gespeichert, solange das Konto für das Projekt benötigt wird oder Spiel-, Kriegs- und Finanzhistorie konsistent bleiben muss.' },
        { title: 'Deine Entscheidung', body: 'Mit dem Häkchen bestätigst du die Projektregeln und erlaubst diese Verarbeitung. Wende dich für Korrektur oder Löschung persönlicher Daten an die Administration; anonymisierte Historie kann zum Erhalt korrekter Kampagnenergebnisse bestehen bleiben.' },
      ],
    },
    overview: {
      title: 'Über das Projekt',
      intro: 'ROTWK ClanWars ist eine strategische Clankampagne, die auf echten gewerteten Rise-of-the-Witch-king-Spielen aufbaut.',
      sections: [
        { title: 'Zweck des Projekts', body: 'Normale Spiele sollen langfristige Bedeutung erhalten. Siege helfen einem Clan, Mittelerde zu erobern, Festungen zu halten, eine Wirtschaft aufzubauen und eine eigene Saisongeschichte zu schreiben. Das Projekt ersetzt das Spiel nicht und verlangt keine besondere Warteschlange für eine einzelne Karte.' },
        { title: 'Ablauf einer Kampagne', body: 'Ein Spieler bestätigt seinen Namen, tritt einem Clan bei und spielt weiter gewertete Partien. Der Clanführer wählt ein Gebiet und einen Angriffstrupp. Der Server erhält Replays über die API, prüft sie und wertet den aktiven Krieg. Nach 60 Stunden erhält der Sieger das Land und seine zukünftigen Vorteile.' },
        { title: 'Karte und Strategie', body: 'Die interaktive Karte enthält 76 Gebiete mit unterschiedlichen Einkommen, Ressourcen, Einflusswerten und Wegen. Normale Angriffe überschreiten gemeinsame Grenzen, Häfen ermöglichen Seeangriffe. Große Städte verlangen einen entwickelten Clan und werden zu langfristigen Kampagnenzielen.' },
        { title: 'Clanwirtschaft', body: 'Clans erhalten Gold, Eisen, Holz, Nahrung und Mithril. Damit werden Bevölkerung, Befestigungen, Militärlager, Häfen, Flotten und dauerhafte Relikte finanziert. Einfluss zeigt die territoriale Stärke und schaltet anspruchsvollere Ziele frei.' },
        { title: 'Handel', body: 'Auf dem Markt tauschen Clans seltene Ressourcen. Ladung wird reserviert und reist als Karawane oder Schiff zwischen den Besitzungen. Die Entfernung bestimmt Preis und Lieferzeit; aktive Transporte und die Handelshistorie bleiben sichtbar.' },
        { title: 'Spieler und Statistiken', body: 'Ein Profil speichert Elo getrennt nach Mod, Spiele, Fraktionen, Karten, Erfolge und Titel. Clanstatistiken berücksichtigen nur die tatsächliche Mitgliedszeit. Beendete Kriege bleiben mit allen Spielen, Berechnungen und dem endgültigen Besitzer archiviert.' },
        { title: 'Gesamtkonzept', body: 'Das Projekt schafft ein faires Metaspiel, in dem Spielstärke und Führungsentscheidungen gleichermaßen wichtig sind: wer in einen Feldzug geht, welches Land ausgebaut wird, wann gehandelt wird und welche Festung angegriffen wird. Vor der ersten offiziellen Saison testen echte Clans die Balance; anschließend werden die Saisonregeln festgeschrieben.' },
      ],
    },
  },
};

export const getPublicDocument = (language, documentId) => (
  documents[language]?.[documentId] || documents.ru[documentId]
);
