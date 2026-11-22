const priority = (member, leaderId) => {
  if (leaderId != null && String(member.user_id) === String(leaderId)) return 0;
  if (member.is_warlord) return 1;
  if (member.is_trader || member.rank === 'Торговец') return 2;
  return member.rank === 'Воин' ? 3 : 4;
};

export function orderClanMembers(members, leaderId) {
  return [...members].sort((a, b) => priority(a, leaderId) - priority(b, leaderId)
    || String(a.display_name || a.username || '').localeCompare(String(b.display_name || b.username || ''), 'ru', { numeric: true })
    || Number(a.user_id) - Number(b.user_id));
}
