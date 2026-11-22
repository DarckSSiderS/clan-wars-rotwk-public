export function previewScenarioReturnPath(pathname, search, cycleId) {
  if (!Number.isSafeInteger(cycleId) || cycleId < 1) throw new TypeError('Invalid preview cycle');
  if (!/^\/(map|clans(?:\/[1-9][0-9]*)?|campaign\/cycles\/[1-9][0-9]*(?:\/(?:orders|reinforcements|diplomacy|preparation|interception))?)$/.test(pathname)) return '/map';
  return pathname.replace(/^\/campaign\/cycles\/[1-9][0-9]*/, `/campaign/cycles/${cycleId}`) + search;
}
