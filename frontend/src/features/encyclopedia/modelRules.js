export const levelStats = (profile, level) => {
  const maximum = profile.maxLevel || profile.levelUps.length;
  const selected = Math.min(maximum, Math.max(1, Number(level) || 1));
  const gained = profile.levelUps.slice(0, selected).reduce((total, step) => ({
    health: total.health + step.health,
    damage: total.damage + step.damage,
  }), { health: 0, damage: 0 });
  return { ...profile.baseStats, health: profile.baseStats.health + gained.health, damage: profile.baseStats.damage + gained.damage };
};

export const matchesMesh = (name, names = [], prefixes = []) => (
  names.includes(name) || prefixes.some((prefix) => name.startsWith(prefix))
);

export function meshVisible(name, variant, weapon, action) {
  const sources = [variant, weapon].filter(Boolean);
  const actionMatches = (source, type, key) => matchesMesh(name, source[type]?.[key] || source[`${type}Meshes`]?.[key], source[`${type}Prefixes`]?.[key]);
  const attackProp = sources.some((source) => matchesMesh(name, source.attackShowMeshes, source.attackShowPrefixes));
  const conditional = attackProp || sources.some((source) => (
    [...Object.keys(source.actionShow || {}), ...Object.keys(source.actionShowMeshes || {}), ...Object.keys(source.actionShowPrefixes || {})]
      .some((key) => actionMatches(source, 'actionShow', key))
  ));
  if (conditional) return (action === 'attack' && attackProp) || sources.some((source) => actionMatches(source, 'actionShow', action));
  if (sources.some((source) => actionMatches(source, 'actionHide', action))) return false;
  if (sources.some((source) => matchesMesh(name, source.keepMeshes, source.keepPrefixes))) return true;
  return !sources.some((source) => matchesMesh(name, source.hideMeshes, source.hidePrefixes));
}
