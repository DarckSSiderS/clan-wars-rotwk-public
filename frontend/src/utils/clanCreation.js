export const MAX_CLAN_IMAGE_BYTES = 5 * 1024 * 1024;

const SUPPORTED_CLAN_IMAGE_TYPES = new Set([
  'image/gif',
  'image/jpeg',
  'image/png',
  'image/webp',
]);

export const getContrastingClanColor = (color) => {
  const normalized = String(color || '').replace('#', '');
  if (!/^[0-9a-f]{6}$/i.test(normalized)) return '#f3dfb0';
  const red = parseInt(normalized.slice(0, 2), 16);
  const green = parseInt(normalized.slice(2, 4), 16);
  const blue = parseInt(normalized.slice(4, 6), 16);
  const luminance = (red * 299 + green * 587 + blue * 114) / 255000;
  return luminance > 0.58 ? '#24170f' : '#f3dfb0';
};

export const validateClanImageFile = (file) => {
  if (!file) return null;
  if (file.size > MAX_CLAN_IMAGE_BYTES) return 'too_large';
  if (!SUPPORTED_CLAN_IMAGE_TYPES.has(file.type)) return 'unsupported_type';
  return null;
};

export const validateClanCreationDetails = (data, translate) => {
  if (data?.name?.trim()) return {};
  return {
    name: translate('clans_name_required', 'Название клана обязательно'),
  };
};

export const getClanMapPreviewSource = (emblemUrl, avatarUrl) => emblemUrl || avatarUrl || null;

export const getClanCreationSubmitAction = (step) => (step === 1 ? 'continue' : 'submit');
