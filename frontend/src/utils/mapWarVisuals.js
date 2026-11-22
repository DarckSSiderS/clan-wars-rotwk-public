const nonNegativePoints = (value) => {
  const points = Number(value);
  return Number.isFinite(points) ? Math.max(0, points) : 0;
};

const roundPercentage = (value) => Math.round(value * 100) / 100;

export const getWarScoreSplit = (war) => {
  const scores = Array.isArray(war?.clan_scores) ? war.clan_scores : [];
  const pointsForClan = (clanId) => nonNegativePoints(
    scores.find((score) => Number(score.clan_id) === Number(clanId))?.points,
  );
  const attackerPoints = pointsForClan(war?.attacking_clan_id);
  const defenderPoints = pointsForClan(war?.defending_clan_id);
  const totalPoints = attackerPoints + defenderPoints;
  const attackerShare = totalPoints > 0
    ? roundPercentage(attackerPoints / totalPoints * 100)
    : 50;

  return {
    attackerPoints,
    defenderPoints,
    attackerShare,
    defenderShare: roundPercentage(100 - attackerShare),
  };
};
