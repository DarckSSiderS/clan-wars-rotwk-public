import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogTitle, Divider, FormControlLabel, MenuItem, Paper,
  Stack, Switch, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, TextField, Typography,
} from '@mui/material';
import {
  Anchor, Castle, Edit, Groups, Paid, Public, Search, Shield, TrendingUp,
} from '@mui/icons-material';
import api from '../services/api';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { getTerritoryName } from '../i18n/territories';

const RESOURCES = {
  gold: 'resource_gold', iron: 'resource_iron', wood: 'resource_wood', food: 'resource_food', mithril: 'resource_mithril',
};

const editableFields = [
  'owner_clan_id', 'resource_wealth', 'resource_type', 'resource_output',
  'secondary_resource_type', 'population', 'influence_value', 'required_influence',
  'development_level', 'fortifications', 'offense_level', 'is_playable',
  'is_coastal', 'has_port', 'port_level', 'fleet_level', 'required_territories',
  'stronghold_power',
];

const makeForm = (territory) => ({
  ...Object.fromEntries(editableFields.map((field) => [field, territory[field]])),
  owner_clan_id: territory.owner_clan_id || '',
  secondary_resource_type: territory.secondary_resource_type || '',
  reason: '',
});

const strategicValue = (form) => {
  const levels = [form.development_level, form.fortifications, form.offense_level];
  if (form.has_port) levels.push(Math.max(form.port_level || 0, form.fleet_level || 0));
  return (levels.reduce((sum, value) => sum + Number(value || 0), 0) / levels.length).toFixed(1);
};

const dailyIncome = (form) => {
  const population = Math.min(2000, Math.max(0, Number(form.population || 0)));
  const level = Math.min(10, Math.max(0, Number(form.development_level || 0)));
  const populationBonus = population / 100;
  const developmentBonus = Math.min(level, 5) * 12 + Math.max(0, level - 5) * 6;
  return (
    Number(form.resource_wealth || 0)
    * (1 + (populationBonus + developmentBonus) / 100)
  ).toFixed(2);
};

const AdminTerritoriesPanel = ({ clans, onMessage, onChanged }) => {
  const { language, getLocalizedText: t } = useLocalizationContext();
  const [territories, setTerritories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [ownerFilter, setOwnerFilter] = useState('all');
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);

  const loadTerritories = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get('/admin/territories');
      setTerritories(response.data.territories || []);
    } catch (error) {
      onMessage({ type: 'error', text: error.response?.data?.detail || t('admin_territories_load_error') });
    } finally {
      setLoading(false);
    }
  }, [onMessage, t]);

  useEffect(() => { loadTerritories(); }, [loadTerritories]);

  const filtered = useMemo(() => {
    const query = search.trim().toLocaleLowerCase(language);
    return territories.filter((territory) => {
      const matchesSearch = !query || `${territory.name} ${territory.region} ${territory.owner_clan_name || ''}`.toLocaleLowerCase(language).includes(query);
      const matchesOwner = ownerFilter === 'all'
        || (ownerFilter === 'neutral' && !territory.owner_clan_id)
        || String(territory.owner_clan_id) === ownerFilter;
      return matchesSearch && matchesOwner;
    });
  }, [language, ownerFilter, search, territories]);

  const summary = useMemo(() => ({
    total: territories.length,
    owned: territories.filter((item) => item.owner_clan_id).length,
    strongholds: territories.filter((item) => item.stronghold_power > 0).length,
    ports: territories.filter((item) => item.has_port).length,
  }), [territories]);

  const openEditor = (territory) => {
    setSelected(territory);
    setForm(makeForm(territory));
  };

  const setNumber = (field, value, max = null) => {
    let next = Math.max(0, Number(value));
    if (max !== null) next = Math.min(max, next);
    setForm((current) => ({ ...current, [field]: next }));
  };

  const save = async () => {
    if (!selected || !form) return;
    setSaving(true);
    try {
      const payload = Object.fromEntries(editableFields.map((field) => [field, form[field]]));
      payload.owner_clan_id = form.owner_clan_id === '' ? null : Number(form.owner_clan_id);
      payload.secondary_resource_type = form.stronghold_power > 0
        ? (form.secondary_resource_type || null)
        : null;
      if (!form.has_port) {
        payload.port_level = 0;
        payload.fleet_level = 0;
      }
      payload.reason = form.reason.trim();
      const response = await api.patch(`/admin/territories/${selected.id}`, payload);
      const updated = response.data.territory;
      setTerritories((current) => current.map((item) => item.id === updated.id ? updated : item));
      setSelected(null);
      setForm(null);
      onMessage({ type: 'success', text: t('admin_territory_saved', null, { territory: updated.name }) });
      if (onChanged) await onChanged();
    } catch (error) {
      onMessage({ type: 'error', text: error.response?.data?.detail || t('admin_territory_save_error') });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Paper className="admin-section">
      <Box className="admin-section__title">
        <Box>
          <Typography variant="h6">{t("admin_ui_c628b457cd")}</Typography>
          <Typography variant="body2" color="text.secondary">{t("admin_ui_f3281ae70d")}</Typography>
        </Box>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
          <TextField size="small" label={t("admin_ui_6433b522a1")} value={search} onChange={(event) => setSearch(event.target.value)} InputProps={{ startAdornment: <Search fontSize="small" sx={{ mr: 1, color: 'text.secondary' }} /> }} />
          <TextField select size="small" label={t("admin_ui_926e3b436e")} value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)} sx={{ minWidth: 190 }}>
            <MenuItem value="all">{t("admin_ui_735c7b606c")}</MenuItem>
            <MenuItem value="neutral">{t("admin_ui_f014baf27c")}</MenuItem>
            {clans.map((clan) => <MenuItem key={clan.id} value={String(clan.id)}>{clan.name}</MenuItem>)}
          </TextField>
        </Stack>
      </Box>

      <Box className="admin-territory-summary">
        <Box><Public /><span>{t("admin_ui_3b5143902e")}</span><b>{summary.total}</b></Box>
        <Box><Groups /><span>{t("admin_ui_436cb5d868")}</span><b>{summary.owned}</b></Box>
        <Box><Castle /><span>{t("admin_ui_2d82f5afde")}</span><b>{summary.strongholds}</b></Box>
        <Box><Anchor /><span>{t("admin_ui_6225bc2c97")}</span><b>{summary.ports}</b></Box>
      </Box>

      {loading ? <Box className="admin-inline-loading"><CircularProgress size={30} /></Box> : (
        <TableContainer className="admin-territory-table"><Table size="small" stickyHeader>
          <TableHead><TableRow>
            <TableCell>{t("admin_ui_61540b9e95")}</TableCell><TableCell>{t("admin_ui_926e3b436e")}</TableCell><TableCell>{t("admin_ui_40b65a7546")}</TableCell>
            <TableCell>{t("admin_ui_999f172bf8")}</TableCell><TableCell>{t("admin_ui_b0151ba273")}</TableCell><TableCell>{t("admin_ui_9c141c86d8")}</TableCell><TableCell />
          </TableRow></TableHead>
          <TableBody>{filtered.map((territory) => <TableRow key={territory.id} hover>
            <TableCell><Typography fontWeight={800}>{getTerritoryName(territory.name, language)}</Typography><Stack direction="row" spacing={.5} mt={.5}>{territory.has_active_war && <Chip size="small" color="error" label={t("admin_ui_0d03fe2baf")} />}{territory.stronghold_power > 0 && <Chip size="small" color="warning" label={t("admin_ui_306e8bf1ed")} />}{!territory.is_playable && <Chip size="small" label={t("admin_ui_b0beb52f96")} />}</Stack></TableCell>
            <TableCell>{territory.owner_clan_name || t("admin_ui_75bb4ed1b6")}</TableCell>
            <TableCell><b>{territory.daily_income}</b>{t("admin_ui_9a063c138b")}<Typography variant="caption" display="block" color="text.secondary">{t("admin_ui_group_581e0bc48f", null, { value0: territory.resource_wealth })}</Typography></TableCell>
            <TableCell>{RESOURCES[territory.resource_type] ? t(RESOURCES[territory.resource_type]) : territory.resource_type}{territory.secondary_resource_type ? ` + ${t(RESOURCES[territory.secondary_resource_type])}` : ''}<Typography variant="caption" display="block" color="text.secondary">{t("admin_ui_group_4d0c9b19be", null, { value0: territory.stronghold_power > 0 ? 1 : territory.resource_output })}</Typography></TableCell>
            <TableCell><b>+{territory.influence_value}</b><Typography variant="caption" display="block" color="text.secondary">{t("admin_ui_group_2a7c2de5c1", null, { value0: territory.required_influence })}</Typography></TableCell>
            <TableCell>{t("admin_ui_a22a75404b")}{territory.strategic_value}/10<Typography variant="caption" display="block" color="text.secondary">{territory.development_level} / {territory.fortifications} / {territory.offense_level}</Typography></TableCell>
            <TableCell align="right"><Button size="small" startIcon={<Edit />} onClick={() => openEditor(territory)}>{t("admin_ui_9d809f884b")}</Button></TableCell>
          </TableRow>)}
          {filtered.length === 0 && <TableRow><TableCell colSpan={7} align="center">{t("admin_ui_15788167ce")}</TableCell></TableRow>}
          </TableBody>
        </Table></TableContainer>
      )}

      <Dialog open={Boolean(selected)} onClose={() => !saving && setSelected(null)} fullWidth maxWidth="md">
        <DialogTitle>{selected ? t("admin_ui_4670518d1a", null, { value0: selected.name }) : t("admin_ui_fac6e8c297")}</DialogTitle>
        <DialogContent dividers>{form && <Stack spacing={2.5}>
          {selected.has_active_war && <Alert severity="warning">{t("admin_ui_2a5b5faffc")}</Alert>}
          <Box>
            <Typography className="admin-form-heading"><Groups />{t("admin_ui_b5b7cd357a")}</Typography>
            <Box className="admin-territory-form-grid">
              <TextField select label={t("admin_ui_926e3b436e")} value={form.owner_clan_id} disabled={selected.has_active_war} onChange={(event) => setForm((current) => ({ ...current, owner_clan_id: event.target.value }))}>
                <MenuItem value="">{t("admin_ui_75bb4ed1b6")}</MenuItem>
                {clans.map((clan) => <MenuItem key={clan.id} value={clan.id}>{clan.name}</MenuItem>)}
              </TextField>
              <TextField label={t("admin_ui_4f162ca697")} type="number" value={form.required_territories} onChange={(event) => setNumber('required_territories', event.target.value, 76)} inputProps={{ min: 0, max: 76 }} />
            </Box>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap mt={1}>
              <FormControlLabel control={<Switch checked={form.is_playable} onChange={(event) => setForm((current) => ({ ...current, is_playable: event.target.checked }))} />} label={t("admin_ui_c8cd802a90")} />
              <FormControlLabel control={<Switch checked={form.is_coastal} onChange={(event) => setForm((current) => ({ ...current, is_coastal: event.target.checked }))} />} label={t("admin_ui_1220e8b533")} />
              <FormControlLabel control={<Switch checked={form.has_port} onChange={(event) => setForm((current) => ({ ...current, has_port: event.target.checked }))} />} label={t("admin_ui_fd64f41940")} />
            </Stack>
          </Box>
          <Divider />
          <Box>
            <Typography className="admin-form-heading"><Paid />{t("admin_ui_2215973075")}</Typography>
            <Box className="admin-territory-form-grid">
              <TextField label={t("admin_ui_b896aa3288")} type="number" value={form.resource_wealth} onChange={(event) => setNumber('resource_wealth', event.target.value)} helperText={t('admin_territory_income_help', null, { income: dailyIncome(form) })} />
              <TextField
                label={t("admin_ui_9a85e45059")}
                type="number"
                value={form.population}
                onChange={(event) => setNumber('population', event.target.value, 4000)}
                helperText={t('admin_territory_population_help')}
                inputProps={{ min: 0, max: 4000 }}
              />
              <TextField select label={t("admin_ui_d074b0e4bf")} value={form.resource_type} onChange={(event) => setForm((current) => ({ ...current, resource_type: event.target.value, secondary_resource_type: current.secondary_resource_type === event.target.value ? '' : current.secondary_resource_type }))}>{Object.entries(RESOURCES).map(([key, labelKey]) => <MenuItem key={key} value={key}>{t(labelKey)}</MenuItem>)}</TextField>
              <TextField label={t("admin_ui_cf4152ef2c")} type="number" value={form.resource_output} onChange={(event) => setNumber('resource_output', event.target.value, 1000)} helperText={t('admin_territory_output_help')} />
              {form.stronghold_power > 0 && <TextField select required label={t("admin_ui_9017bc32bc")} value={form.secondary_resource_type} onChange={(event) => setForm((current) => ({ ...current, secondary_resource_type: event.target.value }))}>{Object.entries(RESOURCES).filter(([key]) => key !== form.resource_type).map(([key, labelKey]) => <MenuItem key={key} value={key}>{t(labelKey)}</MenuItem>)}</TextField>}
            </Box>
          </Box>
          <Divider />
          <Box>
            <Typography className="admin-form-heading"><TrendingUp />{t("admin_ui_74c2b4b88d")}</Typography>
            <Box className="admin-territory-form-grid">
              <TextField label={t("admin_ui_f6fff27e26")} type="number" value={form.influence_value} onChange={(event) => setNumber('influence_value', event.target.value)} helperText={t('admin_territory_influence_help')} />
              <TextField label={t("admin_ui_1beb23aeee")} type="number" value={form.required_influence} onChange={(event) => setNumber('required_influence', event.target.value)} helperText={t('admin_territory_threshold_help')} />
              <TextField label={t("admin_ui_3ece268c9d")} type="number" value={form.development_level} onChange={(event) => setNumber('development_level', event.target.value, 10)} inputProps={{ min: 0, max: 10 }} />
              <TextField label={t("admin_ui_037ca6d060")} type="number" value={form.fortifications} onChange={(event) => setNumber('fortifications', event.target.value, 10)} inputProps={{ min: 0, max: 10 }} />
              <TextField label={t("admin_ui_cb7948f9da")} type="number" value={form.offense_level} onChange={(event) => setNumber('offense_level', event.target.value, 10)} inputProps={{ min: 0, max: 10 }} />
              <TextField label={t("admin_ui_5973f2f812")} type="number" value={form.stronghold_power} onChange={(event) => setNumber('stronghold_power', event.target.value, 10)} helperText={t('admin_territory_regular_help')} inputProps={{ min: 0, max: 10 }} />
            </Box>
            <Alert severity="info" sx={{ mt: 1.5 }}>{t("admin_ui_group_aaa4aa2bb0", null, { value0: strategicValue(form) })}</Alert>
          </Box>
          {form.has_port && <><Divider /><Box>
            <Typography className="admin-form-heading"><Anchor />{t("admin_ui_c09f68de12")}</Typography>
            <Box className="admin-territory-form-grid">
              <TextField label={t("admin_ui_85bbec26cd")} type="number" value={Math.max(form.port_level || 0, form.fleet_level || 0)} onChange={(event) => { const level = Math.min(10, Math.max(0, Number(event.target.value))); setForm((current) => ({ ...current, port_level: level, fleet_level: level })); }} helperText={t('admin_territory_naval_help')} inputProps={{ min: 0, max: 10 }} />
            </Box>
          </Box></>}
          <Divider />
          <TextField required multiline minRows={3} label={t("admin_ui_8deb8920a7")} value={form.reason} onChange={(event) => setForm((current) => ({ ...current, reason: event.target.value }))} helperText={t('admin_territory_audit_help')} />
        </Stack>}</DialogContent>
        <DialogActions><Button onClick={() => setSelected(null)}>{t("admin_ui_0ec753be8d")}</Button><Button variant="contained" disabled={saving || !form || form.reason.trim().length < 3 || (form.stronghold_power > 0 && !form.secondary_resource_type)} startIcon={saving ? <CircularProgress size={18} /> : <Shield />} onClick={save}>{saving ? t("admin_ui_632fd0d93d") : t("admin_ui_4864057d62")}</Button></DialogActions>
      </Dialog>
    </Paper>
  );
};

export default AdminTerritoriesPanel;
