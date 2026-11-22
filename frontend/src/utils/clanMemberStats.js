export async function loadClanMemberStats(members, fetchStats) {
  const result = {};
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(4, members.length) }, async () => {
    while (next < members.length) {
      const member = members[next++];
      try { result[member.user_id] = await fetchStats(member.user_id); }
      catch { result[member.user_id] = null; }
    }
  }));
  return result;
}
