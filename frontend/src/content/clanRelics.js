const RELIC_ART_BY_KEY = {
  royal_charter: 'royal-charter.png',
  war_foundry: 'art-of-war.png',
  mithril_standard: 'mastery-of-mining.png',
  granite_bastion: 'stonemason.png',
  merchant_guild: 'wealth.png',
  white_tree: 'strength-of-men.png',
  red_arrow: 'proud-riders.png',
  iron_crown: 'iron-crown.png',
  palantir: 'inspiration.png',
  dwarf_anvil: 'masters-of-the-mountain.png',
  ents_seed: 'golden-wood.png',
  mordor_forge: 'will-of-morgoth.png',
  helms_horn: 'steadfastness.png',
  ring_of_barahir: 'ring-of-barahir.png',
  galadhrim_mirror: 'high-elves.png',
};

export const getRelicArtwork = (assetKey) => {
  const filename = RELIC_ART_BY_KEY[assetKey] || 'legacy-of-numenor.png';
  return `/assets/relics/${filename}`;
};
