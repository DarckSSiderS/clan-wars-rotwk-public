const resources = ['gold', 'iron', 'wood', 'food', 'mithril'];
const prefix = 'cw:admin-cycle-command:';

const amount = value => {
  if (typeof value !== 'string' || !/^\d{1,37}(?:\.\d{1,36})?$/.test(value)) throw Error('Invalid resource amount');
  const [integer, fraction = ''] = value.split('.');
  const whole = integer.replace(/^0+(?=\d)/, '');
  const decimal = fraction.replace(/0+$/, '');
  return whole + (decimal ? `.${decimal}` : '');
};
const reasonText = (value, maxLength = 2000) => {
  const reason = String(value || '').trim();
  if (reason.length < 3 || reason.length > maxLength) throw Error('invalid_reason_length');
  return reason;
};

export function treasuryDraft(context, clan) {
  if (context?.mechanics_version === 'legacy') {
    return { ...Object.fromEntries([...resources, 'influence'].map(key => [key, clan[key]])), reason: '' };
  }
  if (context?.mechanics_version !== 'cycle_v1' || !context.state
      || context.state.season_id !== context.season_id || !Number.isSafeInteger(context.state.revision)
      || context.state.revision < 1) throw Error('Seasonal treasury is not ready');
  return { ...Object.fromEntries(resources.map(key => [key, amount(context.state.wallet[key])])), reason: '' };
}

export function treasuryCommand(context, draft) {
  if (context?.mechanics_version !== 'cycle_v1') throw Error('Cycle season required');
  treasuryDraft(context, {});
  return { season_id: context.season_id, expected_revision: context.state.revision,
    reason: reasonText(draft.reason), wallet: Object.fromEntries(resources.map(key => [key, amount(draft[key])])) };
}

export function readAdminCommand(storage, scope) {
  const value = storage.getItem(prefix + scope);
  if (value === null) return null;
  const command = JSON.parse(value);
  if (!command || typeof command !== 'object' || typeof command.command_id !== 'string' || !command.command_id) {
    throw Error('Invalid pending command');
  }
  return command;
}

export function rememberAdminCommand(storage, scope, payload, newId = () => crypto.randomUUID()) {
  const prior = readAdminCommand(storage, scope);
  if (prior) {
    const { command_id: _id, ...terms } = prior;
    if (JSON.stringify(terms) !== JSON.stringify(payload)) throw Error('Resolve the pending command first');
    return prior;
  }
  const command = { ...payload, command_id: newId() };
  storage.setItem(prefix + scope, JSON.stringify(command));
  return command;
}

export function forgetAdminCommand(storage, scope) {
  storage.removeItem(prefix + scope);
}

export function recoveryCommand(cycle, reason, confirmed) {
  if (cycle?.recovery_available !== true || !confirmed || !Number.isSafeInteger(cycle.revision) || cycle.revision < 1) {
    throw Error('Recovery requires confirmation and an eligible cycle');
  }
  return { expected_revision: cycle.revision, reason: reasonText(reason, 500) };
}

export function canRecoverPreparation(cycle, pending) {
  return Boolean(Number.isSafeInteger(cycle?.id) && cycle.id > 0
    && (cycle.recovery_available === true || pending?.command_id));
}
