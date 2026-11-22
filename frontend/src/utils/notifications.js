import { translate } from '../i18n/messages';

const iconByType = {
  success: '✓',
  error: '×',
  warning: '!',
  info: 'i',
};

const getUiText = (key, fallback) => {
  let language = 'ru';
  try {
    language = window.localStorage.getItem('language') || language;
  } catch {
    // Storage can be unavailable in privacy modes; Russian remains the application fallback.
  }
  return translate(key, language, fallback);
};

const getNotificationRegion = () => {
  let region = document.querySelector('[data-notification-region]');
  if (!region) {
    region = document.createElement('div');
    region.className = 'notification-region';
    region.dataset.notificationRegion = 'true';
    region.setAttribute('aria-live', 'polite');
    region.setAttribute('aria-relevant', 'additions');
    document.body.appendChild(region);
  }
  return region;
};

export const showNotification = (message, type = 'info', duration = 5000) => {
  const notification = document.createElement('article');
  notification.className = `notification notification-${type}`;
  notification.setAttribute('role', type === 'error' ? 'alert' : 'status');

  const icon = document.createElement('span');
  icon.className = 'notification__icon';
  icon.setAttribute('aria-hidden', 'true');
  icon.textContent = iconByType[type] || iconByType.info;

  const text = document.createElement('span');
  text.className = 'notification__text';
  text.textContent = String(message || '');

  const close = document.createElement('button');
  close.className = 'notification__close';
  close.type = 'button';
  close.setAttribute('aria-label', getUiText('common_close', 'Закрыть'));
  close.textContent = '×';

  let removeTimer;
  const remove = () => {
    window.clearTimeout(removeTimer);
    notification.dataset.closing = 'true';
    const finish = () => notification.remove();
    notification.addEventListener('transitionend', finish, { once: true });
    window.setTimeout(finish, 240);
  };

  close.addEventListener('click', remove);
  notification.append(icon, text, close);
  getNotificationRegion().appendChild(notification);
  requestAnimationFrame(() => { notification.dataset.open = 'true'; });
  removeTimer = window.setTimeout(remove, duration);
  return remove;
};

export const showSuccess = (message, duration) => showNotification(message, 'success', duration);
export const showError = (message, duration) => showNotification(message, 'error', duration);
export const showWarning = (message, duration) => showNotification(message, 'warning', duration);
export const showInfo = (message, duration) => showNotification(message, 'info', duration);

export const confirmAction = (message, title = null) => new Promise((resolve) => {
  const previouslyFocused = document.activeElement;
  const backdrop = document.createElement('div');
  backdrop.className = 'cw-confirm-backdrop';

  const dialog = document.createElement('section');
  const titleId = `confirm-title-${Date.now()}`;
  const descriptionId = `confirm-description-${Date.now()}`;
  dialog.className = 'cw-confirm-dialog';
  dialog.setAttribute('role', 'alertdialog');
  dialog.setAttribute('aria-modal', 'true');
  dialog.setAttribute('aria-labelledby', titleId);
  dialog.setAttribute('aria-describedby', descriptionId);
  dialog.tabIndex = -1;

  const eyebrow = document.createElement('span');
  eyebrow.className = 'cw-confirm-dialog__eyebrow';
  eyebrow.textContent = getUiText('common_decision_required', 'Требуется решение');

  const heading = document.createElement('h2');
  heading.id = titleId;
  heading.textContent = String(title || getUiText('common_confirmation', 'Подтверждение'));

  const description = document.createElement('p');
  description.id = descriptionId;
  description.textContent = String(message || '');

  const actions = document.createElement('div');
  actions.className = 'cw-confirm-dialog__actions';
  const cancel = document.createElement('button');
  cancel.type = 'button';
  cancel.className = 'cw-confirm-dialog__cancel';
  cancel.textContent = getUiText('common_cancel', 'Отмена');
  const confirm = document.createElement('button');
  confirm.type = 'button';
  confirm.className = 'cw-confirm-dialog__confirm';
  confirm.textContent = getUiText('common_confirm', 'Подтвердить');
  actions.append(cancel, confirm);
  dialog.append(eyebrow, heading, description, actions);
  backdrop.appendChild(dialog);
  document.body.appendChild(backdrop);

  const finish = (result) => {
    document.removeEventListener('keydown', handleKeyDown, true);
    backdrop.remove();
    if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
    resolve(result);
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      finish(false);
      return;
    }
    if (event.key !== 'Tab') return;
    const controls = [cancel, confirm];
    const current = controls.indexOf(document.activeElement);
    if (event.shiftKey && current <= 0) {
      event.preventDefault();
      confirm.focus();
    } else if (!event.shiftKey && current === controls.length - 1) {
      event.preventDefault();
      cancel.focus();
    }
  };

  cancel.addEventListener('click', () => finish(false));
  confirm.addEventListener('click', () => finish(true));
  backdrop.addEventListener('pointerdown', (event) => {
    if (event.target === backdrop) finish(false);
  });
  document.addEventListener('keydown', handleKeyDown, true);
  requestAnimationFrame(() => {
    backdrop.dataset.open = 'true';
    cancel.focus();
  });
});
