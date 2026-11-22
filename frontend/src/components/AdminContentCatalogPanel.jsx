import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Paper,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import {
  Add,
  AutoAwesome,
  DeleteOutline,
  Edit,
  EmojiEvents,
  Inventory2,
  Search,
} from '@mui/icons-material';
import api from '../services/api';
import { useLocalizationContext } from '../contexts/LocalizationContext';

const RARITIES = ['common', 'uncommon', 'rare', 'epic', 'legendary'];
const RARITY_LABELS = {
  common: 'admin_rarity_common',
  uncommon: 'admin_rarity_uncommon',
  rare: 'admin_rarity_rare',
  epic: 'admin_rarity_epic',
  legendary: 'admin_rarity_legendary',
};

const SHOP_EMPTY = {
  name: '',
  description: '',
  price: 0,
  item_type: 'relic',
  rarity: 'common',
  image_url: '',
  css_class: '',
  slot: '',
  category: 'relic',
  is_available: true,
};

const ACHIEVEMENT_EMPTY = {
  name: '',
  description: '',
  icon: 'emoji_events',
  category: 'combat',
  rarity: 'common',
  points: 0,
  requirement_type: 'wins',
  requirement_value: 1,
  target_value: 1,
  reward_amount: 0,
  achievement_type: '',
  is_available: true,
};

const CONFIG = {
  shop: {
    endpoint: '/shop/items/',
    singularKey: 'admin_catalog_shop_singular',
    titleKey: 'admin_catalog_shop_title',
    eyebrowKey: 'admin_catalog_shop_eyebrow',
    descriptionKey: 'admin_catalog_shop_description',
    addLabelKey: 'admin_catalog_shop_add',
    empty: SHOP_EMPTY,
    icon: Inventory2,
  },
  achievements: {
    endpoint: '/achievements/',
    singularKey: 'admin_catalog_achievement_singular',
    titleKey: 'admin_catalog_achievement_title',
    eyebrowKey: 'admin_catalog_achievement_eyebrow',
    descriptionKey: 'admin_catalog_achievement_description',
    addLabelKey: 'admin_catalog_achievement_add',
    empty: ACHIEVEMENT_EMPTY,
    icon: EmojiEvents,
  },
};

const numberValue = (value, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const AdminContentCatalogPanel = ({ mode }) => {
  const { getLocalizedText: t } = useLocalizationContext();
  const config = CONFIG[mode];
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [rarity, setRarity] = useState('all');
  const [availability, setAvailability] = useState('all');
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [deleteCandidate, setDeleteCandidate] = useState(null);

  const loadItems = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await api.get(config.endpoint, { params: { limit: 500 } });
      setItems(Array.isArray(response.data) ? response.data : []);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || t("admin_ui_703ed2d00b", null, { value0: t(config.titleKey).toLocaleLowerCase() }));
    } finally {
      setLoading(false);
    }
  }, [config, t]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  const filteredItems = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('ru-RU');
    return items.filter((item) => {
      const matchesQuery = !normalized || [item.name, item.description, item.category, item.item_type]
        .some((value) => String(value || '').toLocaleLowerCase('ru-RU').includes(normalized));
      const matchesRarity = rarity === 'all' || item.rarity === rarity;
      const matchesAvailability = availability === 'all'
        || (availability === 'available' ? item.is_available : !item.is_available);
      return matchesQuery && matchesRarity && matchesAvailability;
    });
  }, [availability, items, query, rarity]);

  const metrics = useMemo(() => ({
    total: items.length,
    available: items.filter((item) => item.is_available).length,
    legendary: items.filter((item) => item.rarity === 'legendary').length,
    categories: new Set(items.map((item) => item.category).filter(Boolean)).size,
  }), [items]);

  const openCreate = () => {
    setEditing(null);
    setForm({ ...config.empty });
  };

  const openEdit = (item) => {
    setEditing(item);
    const merged = { ...config.empty, ...item };
    setForm(Object.fromEntries(
      Object.entries(merged).map(([key, value]) => [
        key,
        value ?? config.empty[key] ?? '',
      ]),
    ));
  };

  const closeEditor = () => {
    if (saving) return;
    setEditing(null);
    setForm(null);
  };

  const editorOpen = form !== null;

  const changeField = (field) => (event) => {
    const value = event.target.type === 'checkbox' ? event.target.checked : event.target.value;
    setForm((current) => ({ ...current, [field]: value }));
  };

  const buildPayload = () => {
    if (mode === 'shop') {
      return {
        name: form.name.trim(),
        description: form.description.trim() || null,
        price: numberValue(form.price),
        item_type: form.item_type.trim(),
        rarity: form.rarity,
        image_url: form.image_url.trim() || null,
        css_class: form.css_class.trim() || null,
        slot: form.slot.trim() || null,
        category: form.category.trim() || null,
        is_available: form.is_available,
      };
    }
    return {
      name: form.name.trim(),
      description: form.description.trim(),
      icon: form.icon.trim(),
      category: form.category.trim(),
      rarity: form.rarity,
      points: numberValue(form.points),
      requirement_type: form.requirement_type.trim(),
      requirement_value: Math.max(1, numberValue(form.requirement_value, 1)),
      target_value: Math.max(1, numberValue(form.target_value, 1)),
      reward_amount: Math.max(0, numberValue(form.reward_amount)),
      achievement_type: form.achievement_type.trim() || null,
      is_available: form.is_available,
    };
  };

  const formValid = mode === 'shop'
    ? Boolean(form?.name?.trim() && form?.item_type?.trim() && numberValue(form?.price, -1) >= 0)
    : Boolean(
      form?.name?.trim()
      && form?.description?.trim()
      && form?.icon?.trim()
      && form?.category?.trim()
      && form?.requirement_type?.trim()
      && numberValue(form?.target_value) > 0,
    );

  const saveItem = async () => {
    if (!formValid) return;
    setSaving(true);
    setError('');
    try {
      const payload = buildPayload();
      if (editing) await api.put(`${config.endpoint}${editing.id}`, payload);
      else await api.post(config.endpoint, payload);
      setForm(null);
      setEditing(null);
      await loadItems();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || t("admin_ui_e64f3b8a89", null, { value0: t(config.singularKey) }));
    } finally {
      setSaving(false);
    }
  };

  const deleteItem = async () => {
    if (!deleteCandidate) return;
    setSaving(true);
    setError('');
    try {
      await api.delete(`${config.endpoint}${deleteCandidate.id}`);
      setDeleteCandidate(null);
      await loadItems();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || t("admin_ui_853cfc597b", null, { value0: t(config.singularKey) }));
      setDeleteCandidate(null);
    } finally {
      setSaving(false);
    }
  };

  const Icon = config.icon;

  return (
    <Box className="admin-catalog">
      <Box className="admin-content-title">
        <Box>
          <Typography component="span" className="admin-eyebrow">{t(config.eyebrowKey)}</Typography>
          <Typography variant="h4">{t(config.titleKey)}</Typography>
          <Typography color="text.secondary">{t(config.descriptionKey)}</Typography>
        </Box>
        <Button variant="contained" startIcon={<Add />} onClick={openCreate}>
          {t(config.addLabelKey)}
        </Button>
      </Box>

      {error && <Alert severity="error" onClose={() => setError('')}>{error}</Alert>}

      <Box className="admin-catalog__metrics" aria-label={t("admin_ui_deb84b5dd7", null, { value0: t(config.titleKey) })}>
        <Paper><Icon /><strong>{metrics.total}</strong><span>{t("admin_ui_1059d612b6")}</span></Paper>
        <Paper><TaskMetricIcon /><strong>{metrics.available}</strong><span>{t("admin_ui_d821401924")}</span></Paper>
        <Paper><AutoAwesome /><strong>{metrics.legendary}</strong><span>{t("admin_ui_da408399af")}</span></Paper>
        <Paper><Inventory2 /><strong>{metrics.categories}</strong><span>{t("admin_ui_722644be15")}</span></Paper>
      </Box>

      <Paper className="admin-catalog__filters">
        <TextField
          size="small"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t("admin_ui_29bd9ebb31")}
          InputProps={{ startAdornment: <Search className="admin-catalog__search-icon" /> }}
        />
        <TextField select size="small" label={t("admin_ui_79279f646e")} value={rarity} onChange={(event) => setRarity(event.target.value)}>
          <MenuItem value="all">{t("admin_ui_fd08da7a63")}</MenuItem>
          {RARITIES.map((value) => <MenuItem key={value} value={value}>{t(RARITY_LABELS[value])}</MenuItem>)}
        </TextField>
        <TextField select size="small" label={t("admin_ui_f7f293b5c5")} value={availability} onChange={(event) => setAvailability(event.target.value)}>
          <MenuItem value="all">{t("admin_ui_fd08da7a63")}</MenuItem>
          <MenuItem value="available">{t("admin_ui_f925cafd86")}</MenuItem>
          <MenuItem value="hidden">{t("admin_ui_6bbdf8a926")}</MenuItem>
        </TextField>
        <Typography variant="caption" color="text.secondary">{t("admin_ui_group_8f85b9e850", null, { value0: filteredItems.length, value1: items.length })}
        </Typography>
      </Paper>

      <Paper className="admin-section admin-catalog__table-card">
        {loading ? (
          <Box className="admin-inline-loading" role="status"><CircularProgress /></Box>
        ) : filteredItems.length === 0 ? (
          <Box className="admin-catalog__empty">
            <Icon />
            <Typography variant="h6">{t("admin_ui_a2be393091")}</Typography>
            <Typography color="text.secondary">{t("admin_ui_d980ff2fc5")}</Typography>
            <Button startIcon={<Add />} onClick={openCreate}>{t(config.addLabelKey)}</Button>
          </Box>
        ) : (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{mode === 'shop' ? t("admin_ui_4faa8b79a3") : t("admin_ui_2e0e0b6c00")}</TableCell>
                  <TableCell>{t("admin_ui_19c85838e6")}</TableCell>
                  <TableCell>{t("admin_ui_79279f646e")}</TableCell>
                  <TableCell>{mode === 'shop' ? t("admin_ui_367e2792c1") : t("admin_ui_1d10d9c55d")}</TableCell>
                  <TableCell>{t("admin_ui_f7f293b5c5")}</TableCell>
                  <TableCell align="right">{t("admin_ui_9978ac34b2")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredItems.map((item) => (
                  <TableRow key={item.id} hover>
                    <TableCell>
                      <Stack direction="row" spacing={1.25} alignItems="center">
                        <Avatar
                          variant="rounded"
                          src={mode === 'shop' ? item.image_url || undefined : undefined}
                          className={`admin-catalog__item-icon rarity-${item.rarity || 'common'}`}
                        >
                          {mode === 'shop' ? <Inventory2 /> : <EmojiEvents />}
                        </Avatar>
                        <Box minWidth={0}>
                          <Typography fontWeight={750}>{item.name}</Typography>
                          <Typography variant="caption" color="text.secondary" className="admin-catalog__description">
                            {item.description || t("admin_ui_9852df96ca")}
                          </Typography>
                        </Box>
                      </Stack>
                    </TableCell>
                    <TableCell>{item.category || item.item_type || '—'}</TableCell>
                    <TableCell><Chip size="small" className={`admin-rarity rarity-${item.rarity || 'common'}`} label={RARITY_LABELS[item.rarity] ? t(RARITY_LABELS[item.rarity]) : item.rarity} /></TableCell>
                    <TableCell className="admin-catalog__number">
                      {mode === 'shop'
                        ? `${Number(item.price || 0).toLocaleString('ru-RU')} ◈`
                        : `${item.requirement_type}: ${item.target_value}`}
                    </TableCell>
                    <TableCell>
                      <Chip size="small" color={item.is_available ? 'success' : 'default'} label={item.is_available ? t("admin_ui_f925cafd86") : t("admin_ui_6bbdf8a926")} />
                    </TableCell>
                    <TableCell align="right">
                      <Stack direction="row" justifyContent="flex-end" spacing={0.5}>
                        <Button size="small" startIcon={<Edit />} onClick={() => openEdit(item)}>{t("admin_ui_9d809f884b")}</Button>
                        <Button size="small" color="error" aria-label={t("admin_ui_f21e778edb", null, { value0: item.name })} onClick={() => setDeleteCandidate(item)}><DeleteOutline /></Button>
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>

      <Dialog open={editorOpen} onClose={closeEditor} fullWidth maxWidth="md" className="admin-editor-dialog">
        <DialogTitle>
          <Typography component="span" className="admin-eyebrow">{editing ? t("admin_ui_29f74d4302") : t("admin_ui_ee90723b0b")}</Typography>
          <Typography variant="h5">{editing ? editing.name : t(config.addLabelKey)}</Typography>
        </DialogTitle>
        <DialogContent dividers>
          {form && (
            <Box className="admin-editor-grid">
              <TextField required label={t("admin_ui_3de49828e8")} value={form.name} onChange={changeField('name')} />
              <TextField select label={t("admin_ui_79279f646e")} value={form.rarity} onChange={changeField('rarity')}>
                {RARITIES.map((value) => <MenuItem key={value} value={value}>{t(RARITY_LABELS[value])}</MenuItem>)}
              </TextField>
              <TextField required multiline minRows={3} label={t("admin_ui_f5441f6aee")} value={form.description} onChange={changeField('description')} className="admin-editor-grid__wide" />
              {mode === 'shop' ? (
                <>
                  <TextField required type="number" inputProps={{ min: 0 }} label={t("admin_ui_367e2792c1")} value={form.price} onChange={changeField('price')} />
                  <TextField required label={t("admin_ui_c24898c291")} value={form.item_type} onChange={changeField('item_type')} />
                  <TextField label={t("admin_ui_19c85838e6")} value={form.category} onChange={changeField('category')} />
                  <TextField label={t("admin_ui_393c560b14")} value={form.slot} onChange={changeField('slot')} />
                  <TextField label={t("admin_ui_2a4bda2e75")} value={form.image_url} onChange={changeField('image_url')} className="admin-editor-grid__wide" />
                  <TextField label={t("admin_ui_279efcd28d")} value={form.css_class} onChange={changeField('css_class')} className="admin-editor-grid__wide" />
                </>
              ) : (
                <>
                  <TextField required label={t("admin_ui_19c85838e6")} value={form.category} onChange={changeField('category')} />
                  <TextField label={t("admin_ui_b331b73365")} value={form.achievement_type} onChange={changeField('achievement_type')} />
                  <TextField required label={t("admin_ui_a96c2d8399")} value={form.icon} onChange={changeField('icon')} />
                  <TextField required label={t("admin_ui_ac54ca57fa")} value={form.requirement_type} onChange={changeField('requirement_type')} />
                  <TextField type="number" inputProps={{ min: 1 }} label={t("admin_ui_ac6ad27e6f")} value={form.requirement_value} onChange={changeField('requirement_value')} />
                  <TextField required type="number" inputProps={{ min: 1 }} label={t("admin_ui_d5627f6a61")} value={form.target_value} onChange={changeField('target_value')} />
                  <TextField type="number" inputProps={{ min: 0 }} label={t("admin_ui_f45a9b9004")} value={form.points} onChange={changeField('points')} />
                  <TextField type="number" inputProps={{ min: 0 }} label={t("admin_ui_2f4933d75b")} value={form.reward_amount} onChange={changeField('reward_amount')} />
                  <Alert severity="info" className="admin-editor-grid__wide">{t("admin_ui_44f01ab1f9")}</Alert>
                </>
              )}
              <FormControlLabel
                className="admin-editor-grid__wide"
                control={<Switch checked={Boolean(form.is_available)} onChange={changeField('is_available')} />}
                label={t("admin_ui_369126b4e7")}
              />
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={closeEditor} disabled={saving}>{t("admin_ui_0ec753be8d")}</Button>
          <Button variant="contained" onClick={saveItem} disabled={saving || !formValid}>
            {saving ? t("admin_ui_632fd0d93d") : t("admin_ui_4864057d62")}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(deleteCandidate)} onClose={() => !saving && setDeleteCandidate(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{t("admin_ui_group_e8b7244566", null, { value0: t(config.singularKey) })}</DialogTitle>
        <DialogContent>
          <Alert severity="warning">{t("admin_ui_group_37fdda21fc", null, { value0: deleteCandidate?.name })}</Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteCandidate(null)} disabled={saving}>{t("admin_ui_0ec753be8d")}</Button>
          <Button color="error" variant="contained" onClick={deleteItem} disabled={saving}>{t("admin_ui_86ea33aef5")}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

const TaskMetricIcon = () => <EmojiEvents />;

export default AdminContentCatalogPanel;
