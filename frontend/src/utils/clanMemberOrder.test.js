import test from 'node:test';
import assert from 'node:assert/strict';
import { orderClanMembers } from './clanMemberOrder.js';

test('состав: глава, воеводы, торговцы, воины, новички; без изменения исходного массива', () => {
  const members = [
    { user_id: 1, username: 'Борис', rank: 'Салага' },
    { user_id: 2, username: 'Ян', rank: 'Воин' },
    { user_id: 3, username: 'Тим', is_trader: true },
    { user_id: 4, username: 'Глава', rank: 'Салага', is_warlord: true },
    { user_id: 5, username: 'Артём', rank: 'Салага', is_warlord: true },
    { user_id: 6, username: 'Антон', rank: 'Воин' },
  ];
  assert.deepEqual(orderClanMembers(members, '4').map(m => m.user_id), [4, 5, 3, 6, 2, 1]);
  assert.deepEqual(members.map(m => m.user_id), [1, 2, 3, 4, 5, 6]);
});
