const REGION_AWARDS = [
  ['angmar', 'region-angmar.png', 'clan_award_angmar'],
  ['arnor', 'region-arnor.png', 'clan_award_arnor'],
  ['eriador', 'region-arnor.png', 'clan_award_eriador'],
  ['dwarf', 'region-dwarves.png', 'clan_award_dwarf'],
  ['misty', 'region-dwarves.png', 'clan_award_misty'],
  ['goblin', 'region-goblins.png', 'clan_award_goblin'],
  ['gondor', 'region-gondor.png', 'clan_award_gondor'],
  ['harad', 'region-harad.png', 'clan_award_harad'],
  ['imladris', 'region-imladris.png', 'clan_award_imladris'],
  ['isengard', 'region-isengard.png', 'clan_award_isengard'],
  ['isen', 'region-isengard.png', 'clan_award_isengard'],
  ['lothlorien', 'region-lothlorien.png', 'clan_award_lothlorien'],
  ['mordor', 'region-mordor.png', 'clan_award_mordor'],
  ['rhun', 'region-rhun.png', 'clan_award_rhun'],
  ['rohan', 'region-rohan.png', 'clan_award_rohan'],
];

export const getTerritoryAwards = (territories = [], t = (key) => key) => {
  const awards = new Map();
  territories.forEach((territory) => {
    const source = `${territory.region || ''} ${territory.name || ''}`.toLowerCase();
    const match = REGION_AWARDS.find(([needle]) => source.includes(needle));
    if (!match) return;
    const [, image, labelKey] = match;
    awards.set(image, {
      image: `/assets/awards/clan/${image}`,
      label: t(labelKey),
      description: t('clan_award_regional_description'),
    });
  });
  return [...awards.values()];
};

export const getSeasonAward = (rank, t = (key) => key) => {
  const awards = {
    1: ['season-champion.png', 'clan_award_season_champion'],
    2: ['season-runner-up.png', 'clan_award_season_second'],
    3: ['season-third.png', 'clan_award_season_third'],
  };
  const award = awards[Number(rank)];
  if (!award) return null;
  return {
    image: `/assets/awards/clan/${award[0]}`,
    label: t(award[1]),
    description: t('clan_award_season_description'),
  };
};
