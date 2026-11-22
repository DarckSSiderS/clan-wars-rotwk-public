const prefix = 'cw:barter-command:';
function read(storage, scope) {
  const value = JSON.parse(storage.getItem(prefix + scope) || '[]');
  if (!Array.isArray(value) || value.some(row => !Array.isArray(row) || row.length !== 2 || row.some(v => typeof v !== 'string'))) throw new Error('Invalid command cache');
  return new Map(value);
}
export function rememberBarterCommand(storage, scope, signature, newId = () => crypto.randomUUID()) {
  const values = read(storage, scope);
  const id = values.get(signature) || newId();
  values.set(signature, id);
  // Fail before spending if an uncertain command cannot survive a refresh.
  storage.setItem(prefix + scope, JSON.stringify([...values]));
  return id;
}
export function forgetBarterCommand(storage, scope, signature) {
  const values = read(storage, scope); values.delete(signature);
  storage.setItem(prefix + scope, JSON.stringify([...values]));
}
const units = value => {
  const match = /^(\d+)(?:\.(\d{1,6}))?$/.exec(String(value));
  if (!match) throw new Error('Invalid amount');
  return BigInt(match[1]) * 1_000_000n + BigInt((match[2] || '').padEnd(6, '0'));
};
const decimal = (number, digits) => {
  const scale = 10n ** BigInt(digits);
  const fraction = (number % scale).toString().padStart(digits, '0').replace(/0+$/, '');
  return `${number / scale}${fraction ? `.${fraction}` : ''}`;
};
export const canonicalAmount = value => decimal(units(value), 6);
export function barterFee(cargo, prices) {
  const value = Object.entries(cargo || {}).reduce((sum, [key, amount]) => {
    const quantity = units(amount);
    if (!quantity) return sum;
    if (!/^\d+$/.test(String(prices[key]))) throw new Error('Integral market price required');
    return sum + quantity * BigInt(prices[key]);
  }, 0n);
  return decimal(value, 7);
}
