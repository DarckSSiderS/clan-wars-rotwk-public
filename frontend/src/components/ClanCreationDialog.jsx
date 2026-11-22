import React, { useEffect, useId, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import {
  CheckCircle,
  Close,
  DeleteOutline,
  Groups,
  MapOutlined,
  PhotoCamera,
  Upload,
} from '@mui/icons-material';

import { useLocalizationContext } from '../contexts/LocalizationContext';
import { clanService } from '../services/clanService';
import {
  getClanCreationSubmitAction,
  getClanMapPreviewSource,
  getContrastingClanColor,
  validateClanCreationDetails,
  validateClanImageFile,
} from '../utils/clanCreation';
import ClanColorPicker from './ClanColorPicker';
import './ClanCreationDialog.css';

const INITIAL_DATA = {
  name: '',
  motto: '',
  description: '',
  preferred_patch: 'all',
  map_color: null,
};

const useObjectUrl = (file) => {
  const [url, setUrl] = useState(null);

  useEffect(() => {
    if (!file) {
      setUrl(null);
      return undefined;
    }
    const nextUrl = URL.createObjectURL(file);
    setUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [file]);

  return url;
};

const ImageUploadField = ({
  file,
  icon,
  label,
  previewShape,
  onChange,
  onRemove,
  error,
  helper,
  t,
}) => {
  const inputId = useId();
  const previewUrl = useObjectUrl(file);

  return (
    <Box className={`clan-create-upload${error ? ' has-error' : ''}`}>
      <Box className="clan-create-upload__heading">
        {icon}
        <Typography component="label" htmlFor={inputId} fontWeight={900}>
          {label}
        </Typography>
      </Box>
      <Box className="clan-create-upload__body">
        <Avatar
          src={previewUrl || undefined}
          variant={previewShape === 'square' ? 'rounded' : 'circular'}
          className={`clan-create-upload__preview is-${previewShape}`}
        >
          {previewShape === 'square' ? <Groups /> : <MapOutlined />}
        </Avatar>
        <Box minWidth={0} flex={1}>
          <Typography className="clan-create-upload__filename">
            {file?.name || t('clans_image_not_selected', 'Файл не выбран')}
          </Typography>
          <Typography variant="caption" color={error ? 'error.main' : 'text.secondary'}>
            {error || helper}
          </Typography>
          <Box className="clan-create-upload__actions">
            <Button component="label" htmlFor={inputId} size="small" startIcon={<Upload />}>
              {file
                ? t('clans_image_replace', 'Заменить')
                : t('clans_image_choose', 'Выбрать файл')}
              <input
                id={inputId}
                hidden
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                onChange={onChange}
              />
            </Button>
            {file && (
              <IconButton
                size="small"
                onClick={onRemove}
                aria-label={t('clans_image_remove', 'Удалить выбранное изображение')}
              >
                <DeleteOutline fontSize="small" />
              </IconButton>
            )}
          </Box>
        </Box>
      </Box>
    </Box>
  );
};

const ClanCreationDialog = ({ open, onClose, onCreated }) => {
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down('sm'));
  const { getLocalizedText: t } = useLocalizationContext();
  const [data, setData] = useState(INITIAL_DATA);
  const [avatar, setAvatar] = useState(null);
  const [mapEmblem, setMapEmblem] = useState(null);
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [step, setStep] = useState(1);
  const avatarPreview = useObjectUrl(avatar);
  const emblemPreview = useObjectUrl(mapEmblem);

  useEffect(() => {
    if (!open) return;
    setData(INITIAL_DATA);
    setAvatar(null);
    setMapEmblem(null);
    setErrors({});
    setServerError('');
    setStep(1);
  }, [open]);

  const secondaryColor = getContrastingClanColor(data.map_color);
  const displayedEmblem = getClanMapPreviewSource(emblemPreview, avatarPreview);
  const initial = data.name.trim().charAt(0).toUpperCase() || 'C';

  const imageErrorText = (reason) => {
    if (reason === 'too_large') return t('clans_image_too_large', 'Файл должен быть не больше 5 МБ');
    if (reason === 'unsupported_type') {
      return t('clans_image_unsupported', 'Используйте PNG, JPG, WebP или GIF');
    }
    return '';
  };

  const selectImage = (field, setter) => (event) => {
    const file = event.target.files?.[0] || null;
    event.target.value = '';
    const reason = validateClanImageFile(file);
    setErrors((current) => ({ ...current, [field]: imageErrorText(reason) }));
    if (!reason) setter(file);
  };

  const validateDetails = () => {
    const nextErrors = validateClanCreationDetails(data, t);
    setErrors((current) => ({ ...current, ...nextErrors }));
    return Object.keys(nextErrors).length === 0;
  };

  const validate = () => {
    const nextErrors = validateClanCreationDetails(data, t);
    if (!data.map_color) nextErrors.map_color = t('clans_color_required', 'Выберите цвет владений');
    setErrors((current) => ({ ...current, ...nextErrors }));
    return Object.keys(nextErrors).length === 0;
  };

  const continueToAppearance = () => {
    if (!validateDetails()) return;
    setServerError('');
    setStep(2);
  };

  const submit = async (event) => {
    event.preventDefault();
    if (getClanCreationSubmitAction(step) === 'continue') {
      continueToAppearance();
      return;
    }
    if (!validate()) return;
    setSubmitting(true);
    setServerError('');
    try {
      const created = await clanService.createClanWithAssets(data, avatar, mapEmblem);
      onCreated(created);
    } catch (error) {
      const detail = error.response?.data?.detail;
      setServerError(
        typeof detail === 'string'
          ? detail
          : t('clans_create_error', 'Не удалось создать клан'),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={submitting ? undefined : onClose}
      maxWidth="md"
      fullWidth
      fullScreen={fullScreen}
      PaperProps={{ className: 'clan-create-dialog' }}
    >
      <Box component="form" onSubmit={submit} noValidate>
        <DialogTitle className="clan-create-dialog__title">
          <Box>
            <Typography variant="h5" component="h2" fontWeight={900}>
              {t('clans_create_dialog_title', 'Создание клана')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('clans_create_dialog_subtitle', 'Соберите стиль клана и подготовьте его к кампании')}
            </Typography>
          </Box>
          <IconButton
            onClick={onClose}
            disabled={submitting}
            aria-label={t('common_close', 'Закрыть')}
          >
            <Close />
          </IconButton>
        </DialogTitle>

        <DialogContent className="clan-create-dialog__content">
          {serverError && <Alert severity="error" className="clan-create-dialog__error">{serverError}</Alert>}

          <Box className="clan-create-dialog__steps" aria-label={t('clans_create_progress', 'Этапы создания клана')}>
            <Box className={`clan-create-dialog__step${step === 1 ? ' is-active' : ' is-complete'}`}>
              <span>1</span>
              {t('clans_create_step_details', 'Сведения')}
            </Box>
            <Box className={`clan-create-dialog__step${step === 2 ? ' is-active' : ''}`}>
              <span>2</span>
              {t('clans_create_step_appearance', 'Оформление')}
            </Box>
          </Box>

          <Box className={`clan-create-dialog__grid is-step-${step}`}>
            {step === 1 && (
            <Box className="clan-create-dialog__column">
              <Typography className="clan-create-dialog__section-title">
                {t('clans_create_details', 'Основные сведения')}
              </Typography>
              <TextField
                autoFocus
                required
                fullWidth
                label={t('clans_name_label', 'Название клана')}
                value={data.name}
                error={Boolean(errors.name)}
                helperText={errors.name}
                inputProps={{ maxLength: 80 }}
                onChange={(event) => {
                  setData((current) => ({ ...current, name: event.target.value }));
                  if (errors.name) setErrors((current) => ({ ...current, name: '' }));
                }}
              />
              <TextField
                fullWidth
                label={t('clans_motto_label', 'Девиз клана')}
                value={data.motto}
                inputProps={{ maxLength: 160 }}
                helperText={`${data.motto.length}/160`}
                onChange={(event) => setData((current) => ({ ...current, motto: event.target.value }))}
              />
              <TextField
                fullWidth
                multiline
                minRows={2}
                label={t('clans_description_label', 'Описание')}
                value={data.description}
                onChange={(event) => setData((current) => ({ ...current, description: event.target.value }))}
              />

              <Box>
                <Typography className="clan-create-dialog__field-label">
                  {t('clans_preferred_mod', 'Предпочитаемый мод')}
                </Typography>
                <ToggleButtonGroup
                  exclusive
                  fullWidth
                  value={data.preferred_patch}
                  onChange={(_, value) => {
                    if (value) setData((current) => ({ ...current, preferred_patch: value }));
                  }}
                  aria-label={t('clans_preferred_mod', 'Предпочитаемый мод')}
                >
                  <ToggleButton value="patch_202">Patch 2.02</ToggleButton>
                  <ToggleButton value="ennorath">Ennorath</ToggleButton>
                  <ToggleButton value="all">{t('clans_both_mods', 'Оба мода')}</ToggleButton>
                </ToggleButtonGroup>
                <Typography variant="caption" color="text.secondary">
                  {t('clans_patch_hint', 'Выбор показывает основной мод клана и не ограничивает зачёт матчей.')}
                </Typography>
              </Box>

              <Typography className="clan-create-dialog__section-title is-spaced">
                {t('clans_create_images', 'Изображения клана')}
              </Typography>
              <Box className="clan-create-dialog__uploads">
                <ImageUploadField
                  file={avatar}
                  icon={<PhotoCamera fontSize="small" />}
                  label={t('clans_avatar_label', 'Аватарка клана')}
                  previewShape="square"
                  onChange={selectImage('avatar', setAvatar)}
                  onRemove={() => setAvatar(null)}
                  error={errors.avatar}
                  helper={t('clans_avatar_hint', 'Для страниц клана, войн и статистики · до 5 МБ')}
                  t={t}
                />
                <ImageUploadField
                  file={mapEmblem}
                  icon={<MapOutlined fontSize="small" />}
                  label={t('clans_map_emblem_label', 'Эмблема на карте')}
                  previewShape="round"
                  onChange={selectImage('map_emblem', setMapEmblem)}
                  onRemove={() => setMapEmblem(null)}
                  error={errors.map_emblem}
                  helper={t('clans_map_emblem_hint', 'Статичный знак территории; без него используется аватарка')}
                  t={t}
                />
              </Box>
            </Box>
            )}

            {step === 2 && (
            <Box className="clan-create-dialog__column is-visual">
              <Typography className="clan-create-dialog__section-title">
                {t('clans_create_appearance', 'Владения на карте')}
              </Typography>
              <ClanColorPicker
                value={data.map_color}
                showPreview={false}
                onChange={(mapColor) => {
                  setData((current) => ({ ...current, map_color: mapColor }));
                  setErrors((current) => ({ ...current, map_color: '' }));
                }}
              />
              {errors.map_color && (
                <Typography color="error.main" variant="caption" role="alert">
                  {errors.map_color}
                </Typography>
              )}

              <Box
                className="clan-create-preview"
                style={{
                  '--clan-primary': data.map_color || '#626270',
                  '--clan-secondary': secondaryColor,
                }}
              >
                <Box className="clan-create-preview__header">
                  <Typography className="clan-create-dialog__section-title">
                    {t('clans_preview_title', 'Предпросмотр')}
                  </Typography>
                  {data.map_color && <CheckCircle fontSize="small" color="success" />}
                </Box>
                <Box className="clan-create-preview__card">
                  <Avatar src={avatarPreview || undefined} variant="rounded">{initial}</Avatar>
                  <Box minWidth={0}>
                    <Typography fontWeight={900} noWrap>
                      {data.name || t('clans_preview_name', 'Название клана')}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" noWrap>
                      {data.motto || t('clans_preview_motto', 'Девиз появится здесь')}
                    </Typography>
                  </Box>
                </Box>
                <Box className="clan-create-preview__map" aria-hidden="true">
                  <Box className="clan-create-preview__territory">
                    <Avatar src={displayedEmblem || undefined}>{initial}</Avatar>
                  </Box>
                </Box>
                <Typography variant="caption" color="text.secondary">
                  {mapEmblem
                    ? t('clans_preview_uses_emblem', 'На карте будет отдельная эмблема.')
                    : avatar
                      ? t('clans_preview_uses_avatar', 'На карте будет использована статичная версия аватарки.')
                      : t('clans_preview_uses_initial', 'Без изображения карта покажет инициал клана.')}
                </Typography>
              </Box>
            </Box>
            )}
          </Box>
        </DialogContent>

        <DialogActions className="clan-create-dialog__actions">
          <Button onClick={onClose} disabled={submitting} color="inherit">
            {t('clans_cancel_button', 'Отмена')}
          </Button>
          <Box className="clan-create-dialog__actions-main">
            {step === 2 && (
              <Button onClick={() => setStep(1)} disabled={submitting} color="inherit">
                {t('clans_create_back', 'Назад')}
              </Button>
            )}
            {step === 1 ? (
              <Button type="button" variant="contained" onClick={continueToAppearance}>
                {t('clans_create_continue', 'Продолжить')}
              </Button>
            ) : (
              <Button
                type="submit"
                variant="contained"
                disabled={submitting}
                startIcon={submitting ? <CircularProgress size={18} color="inherit" /> : <Groups />}
              >
                {submitting
                  ? t('clans_creating', 'Создание...')
                  : t('clans_create_button', 'Создать клан')}
              </Button>
            )}
          </Box>
        </DialogActions>
      </Box>
    </Dialog>
  );
};

export default ClanCreationDialog;
