import test from 'node:test';
import assert from 'node:assert/strict';
import { loadClanMemberStats } from './clanMemberStats.js';

test('статистика участников загружается пакетами, не последовательной очередью', async () => {
  let active = 0, maximum = 0;
  const result = await loadClanMemberStats(Array.from({ length: 9 }, (_, user_id) => ({ user_id })), async id => {
    maximum = Math.max(maximum, ++active);
    await new Promise(resolve => setTimeout(resolve, 2));
    active--;
    if (id === 3) throw Error('недоступно');
    return { total_matches: id };
  });
  assert.equal(maximum, 4);
  assert.equal(result[8].total_matches, 8);
  assert.equal(result[3], null);
});
