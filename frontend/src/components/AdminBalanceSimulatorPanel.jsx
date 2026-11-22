import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress, FormControlLabel, MenuItem, Paper, Stack,
  Switch, Tab, Tabs, TextField, Typography,
} from '@mui/material';
import {
  AccountBalanceOutlined, DownloadOutlined, LocalShippingOutlined, MapOutlined,
  MilitaryTechOutlined, PlayArrowRounded, ScienceOutlined, TrendingUpRounded,
  WarningAmberRounded,
} from '@mui/icons-material';
import api from '../services/api';
import { publicFetch } from '../services/apiFetch';
import { useLocalizationContext } from '../contexts/LocalizationContext';

const PROFILE = { new: 'admin_balance_profile_new', growing: 'admin_balance_profile_growing', developed: 'admin_balance_profile_developed', large: 'admin_balance_profile_large' };
const PACE = { slow: 'admin_balance_pace_slow', normal: 'admin_balance_pace_normal', aggressive: 'admin_balance_pace_aggressive' };
const STRATEGY = { economic: 'admin_balance_strategy_economic', military: 'admin_balance_strategy_military', balanced: 'admin_balance_strategy_balanced' };
const RESOURCE = { gold: 'resource_gold', iron: 'resource_iron', wood: 'resource_wood', food: 'resource_food', mithril: 'resource_mithril' };
const OUTCOME = { attacker_advantage: 'admin_balance_outcome_attacker', defender_advantage: 'admin_balance_outcome_defender', uncertain: 'admin_balance_outcome_uncertain' };
const WAR_INPUTS = [
  ['attacker_rating', 'admin_balance_attacker_elo'],
  ['defender_rating', 'admin_balance_defender_elo'],
  ['match_count', 'admin_balance_war_matches'],
  ['team_size', 'admin_balance_team_players'],
  ['attacker_offense_level', 'admin_balance_attacker_camp'],
  ['attacker_naval_level', 'admin_balance_naval_power'],
  ['attacker_relic_power', 'admin_balance_attacker_relic_bonus'],
  ['defender_fortification_level', 'admin_balance_defender_fortifications'],
  ['defender_development_level', 'admin_balance_territory_development'],
  ['defender_relic_power', 'admin_balance_defender_relic_bonus'],
];

const percent = (value) => `${Math.round(Number(value || 0) * 100)}%`;
const number = (value, language) => Math.round(Number(value || 0)).toLocaleString(language);

const makeSandbox = (report) => {
  const territories = report?.inputs?.territories || [];
  const first = territories[0];
  const adjacent = territories.find((item) => first?.adjacent_territory_ids?.includes(item.id)) || territories[1] || first;
  const ports = territories.filter((item) => item.has_port);
  const portA = ports[0] || first;
  const portB = ports[1] || adjacent;
  const start = report?.inputs?.starting_resources || {};
  return {
    economy: {
      days: 30, active_members: 12, starting_territory_ids: first ? [first.id] : [],
      starting_resources: { gold: start.gold || 500, iron: start.iron || 10, wood: start.wood || 10, food: start.food || 5, mithril: start.mithril || 2, influence: start.influence || 100 },
      capture_interval_days: 5, strategy: 'balanced', automatic_captures: true,
      production_multiplier_percent: 100, cost_multiplier_percent: 100,
    },
    war: {
      source_territory_id: first?.id || 1, target_territory_id: adjacent?.id || 2, route_mode: 'auto',
      attacker_rating: 1000, defender_rating: 1000, match_count: 10, team_size: 1, clan_team: true,
      attacker_offense_level: 0, attacker_naval_level: 0, attacker_relic_power: 0,
      defender_fortification_level: 0, defender_development_level: 0, defender_relic_power: 0,
    },
    trade: {
      source_territory_id: portA?.id || 1, target_territory_id: portB?.id || 2, route_mode: 'auto',
      give_resource: 'wood', give_amount: 20, receive_resource: 'iron', receive_amount: 20,
      disruption_risk_percent: 0,
    },
  };
};

const ScenarioMap = ({ territories, mapState }) => {
  const { getLocalizedText: t } = useLocalizationContext();
  const hostRef = useRef(null);
  const [svg, setSvg] = useState('');
  useEffect(() => {
    publicFetch('/map-interactive.svg').then((response) => response.text()).then(setSvg).catch(() => setSvg(''));
  }, []);
  useEffect(() => {
    if (!hostRef.current || !svg) return;
    const byPath = new Map(territories.map((item) => [item.svg_path_data, item]));
    const byName = new Map(territories.map((item) => [item.name, item]));
    const route = new Set(mapState?.route_ids || []);
    hostRef.current.querySelectorAll('path.interactive-region').forEach((path) => {
      const territory = byPath.get(path.getAttribute('d')) || byName.get(path.getAttribute('data-name'));
      const id = territory?.id;
      path.style.fill = route.has(id) ? 'rgba(189, 165, 109, .32)' : 'rgba(71, 82, 73, .18)';
      path.style.stroke = id === mapState?.source_id ? '#78b98b' : id === mapState?.target_id ? '#d07868' : route.has(id) ? '#c7ad70' : 'rgba(210, 202, 174, .18)';
      path.style.strokeWidth = id === mapState?.source_id || id === mapState?.target_id ? '6' : route.has(id) ? '4' : '1.25';
      path.style.vectorEffect = 'non-scaling-stroke';
    });
  }, [mapState, svg, territories]);
  return (
    <Box className="admin-sandbox-map">
      <Box className="admin-sandbox-map__legend"><span className="is-source" />{t("admin_ui_8290a3dbc0")}<span className="is-target" />{t("admin_ui_d5627f6a61")}<span className="is-route" />{t("admin_ui_b765f32584")}</Box>
      {svg ? <div ref={hostRef} dangerouslySetInnerHTML={{ __html: svg }} /> : <div className="admin-balance-empty">{t("admin_ui_ef071a88f3")}</div>}
    </Box>
  );
};

const TimelineChart = ({ timeline = [], baseline = [] }) => {
  const { getLocalizedText: t } = useLocalizationContext();
  if (timeline.length < 2) return null;
  const width = 720; const height = 180; const pad = 24;
  const maxValue = Math.max(1, ...timeline.map((item) => Number(item.resources?.gold || 0)), ...baseline.map((item) => Number(item.resources?.gold || 0)));
  const points = (rows) => rows.map((item, index) => {
    const x = pad + (index / Math.max(1, rows.length - 1)) * (width - pad * 2);
    const y = height - pad - (Number(item.resources?.gold || 0) / maxValue) * (height - pad * 2);
    return `${x},${y}`;
  }).join(' ');
  return (
    <Box className="admin-balance-chart">
      <Box className="admin-balance-chart__legend"><b>{t("admin_ui_3f32551d39")}</b><span className="is-scenario" />{t("admin_ui_f0aa024926")}<span className="is-baseline" />{t("admin_ui_3b560e4014")}</Box>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={t("admin_ui_f57f085bb8")}>
        {[0, .25, .5, .75, 1].map((tick) => <line key={tick} x1={pad} x2={width - pad} y1={pad + tick * (height - pad * 2)} y2={pad + tick * (height - pad * 2)} />)}
        <polyline className="is-baseline" points={points(baseline)} />
        <polyline className="is-scenario" points={points(timeline)} />
      </svg>
      <Box className="admin-balance-chart__axis"><span>{t("admin_ui_926e7b25e7")}</span><span>{t("admin_ui_group_6a617a9e1f", null, { value0: timeline.at(-1)?.day })}</span></Box>
    </Box>
  );
};

const TerritorySelect = ({ label, value, onChange, territories, multiple = false }) => (
  <TextField select size="small" label={label} value={value} onChange={onChange} SelectProps={{ multiple }}>
    {territories.map((item) => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}
  </TextField>
);

const AdminBalanceSimulatorPanel = () => {
  const { getLocalizedText: t, language } = useLocalizationContext();
  const [days, setDays] = useState(30);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [workspace, setWorkspace] = useState('sandbox');
  const [sandboxTab, setSandboxTab] = useState('economy');
  const [sandbox, setSandbox] = useState(null);
  const [sandboxResult, setSandboxResult] = useState(null);
  const [sandboxLoading, setSandboxLoading] = useState(false);
  const [filter, setFilter] = useState({ profile: 'all', pace: 'all', strategy: 'all' });
  const [selectedId, setSelectedId] = useState('');

  const run = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const response = await api.get('/admin/balance-simulator', { params: { days } });
      setReport(response.data);
      setSelectedId(response.data.scenarios?.[0]?.id || '');
      setSandbox((current) => current || makeSandbox(response.data));
    } catch (requestError) {
      setError(requestError.response?.data?.detail || t("admin_ui_32a0b15368"));
    } finally { setLoading(false); }
  }, [days, t]);

  useEffect(() => { run(); }, [run]);
  const territories = report?.inputs?.territories || [];
  const scenarios = useMemo(() => (report?.scenarios || []).filter((scenario) => (
    (filter.profile === 'all' || scenario.profile === filter.profile)
    && (filter.pace === 'all' || scenario.pace === filter.pace)
    && (filter.strategy === 'all' || scenario.strategy === filter.strategy)
  )), [filter, report]);
  useEffect(() => {
    if (scenarios.length && !scenarios.some((scenario) => scenario.id === selectedId)) setSelectedId(scenarios[0].id);
  }, [scenarios, selectedId]);
  const selected = scenarios.find((scenario) => scenario.id === selectedId) || null;

  const updateSandbox = (section, field, value) => setSandbox((current) => ({
    ...current, [section]: { ...current[section], [field]: value },
  }));
  const updateResource = (field, value) => setSandbox((current) => ({
    ...current,
    economy: { ...current.economy, starting_resources: { ...current.economy.starting_resources, [field]: value } },
  }));
  const runSandbox = async () => {
    if (!sandbox) return;
    setSandboxLoading(true); setError('');
    try {
      const response = await api.post('/admin/balance-simulator/sandbox', sandbox);
      setSandboxResult(response.data);
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.map((item) => item.msg).join('; ') : detail || t("admin_ui_3a5534b136"));
    } finally { setSandboxLoading(false); }
  };

  const exportReport = () => {
    const data = workspace === 'sandbox' ? sandboxResult : report;
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob); const anchor = document.createElement('a');
    anchor.href = url; anchor.download = `clanwar-${workspace}-v${report?.rule_set?.version || 'current'}.json`; anchor.click();
    URL.revokeObjectURL(url);
  };

  const economyResult = sandboxResult?.economy;
  const activeMap = sandboxTab === 'war' ? sandboxResult?.war?.map : sandboxTab === 'trade' ? sandboxResult?.trade?.map : {
    source_id: economyResult?.scenario?.initial_territory_ids?.[0],
    target_id: economyResult?.scenario?.captured_territory_ids?.at(-1),
    route_ids: economyResult?.scenario?.final_territory_ids || sandbox?.economy?.starting_territory_ids || [],
  };

  return (
    <Box className="admin-balance-simulator">
      <Box className="admin-content-title">
        <Box><Typography variant="h4">{t("admin_ui_5898d4099e")}</Typography><Typography color="text.secondary">{t("admin_ui_ed7dae63c4")}</Typography></Box>
        <Stack direction="row" spacing={1}><Button startIcon={<DownloadOutlined />} disabled={!report || (workspace === 'sandbox' && !sandboxResult)} onClick={exportReport}>{t("admin_ui_4910a3a93b")}</Button></Stack>
      </Box>
      <Paper className="admin-balance-mode"><Tabs value={workspace} onChange={(_, value) => setWorkspace(value)}><Tab value="sandbox" label={t("admin_ui_77737ca90f")} icon={<ScienceOutlined />} iconPosition="start" /><Tab value="audit" label={t("admin_ui_e478c63ca5")} icon={<WarningAmberRounded />} iconPosition="start" /></Tabs></Paper>
      {error && <Alert severity="error">{error}</Alert>}
      {!report && loading && <Paper className="admin-balance-loading"><CircularProgress /><span>{t("admin_ui_44f0c08bcc")}</span></Paper>}

      {workspace === 'sandbox' && report && sandbox && <>
        <Paper className="admin-balance-guide">
          <b>{t("admin_ui_acfc46f00e")}</b><span>{t("admin_ui_2c7525b874")}</span>
          <Chip size="small" variant="outlined" label={t("admin_ui_cfe39310b3", null, { value0: report.rule_set.version })} />
        </Paper>
        <Box className="admin-sandbox-layout">
          <Paper className="admin-sandbox-controls">
            <Tabs value={sandboxTab} onChange={(_, value) => setSandboxTab(value)} variant="fullWidth">
              <Tab value="economy" label={t("admin_ui_2215973075")} icon={<AccountBalanceOutlined />} iconPosition="start" />
              <Tab value="war" label={t("admin_ui_7a13d8c037")} icon={<MilitaryTechOutlined />} iconPosition="start" />
              <Tab value="trade" label={t("admin_ui_61396f276f")} icon={<LocalShippingOutlined />} iconPosition="start" />
            </Tabs>
            {sandboxTab === 'economy' && <Box className="admin-sandbox-form">
              <Box className="admin-sandbox-presets"><span>{t("admin_ui_c5eb0c82e5")}</span><Button size="small" onClick={() => setSandbox((current) => ({ ...current, economy: { ...current.economy, active_members: 6, starting_territory_ids: territories[0] ? [territories[0].id] : [], capture_interval_days: 8, strategy: 'economic' } }))}>{t("admin_ui_cbde6e9fd1")}</Button><Button size="small" onClick={() => setSandbox((current) => ({ ...current, economy: { ...current.economy, active_members: 17, starting_territory_ids: territories.slice(0, 4).map((item) => item.id), capture_interval_days: 5, strategy: 'balanced' } }))}>{t("admin_ui_8110397f36")}</Button><Button size="small" onClick={() => setSandbox((current) => ({ ...current, economy: { ...current.economy, active_members: 26, starting_territory_ids: territories.slice(0, 7).map((item) => item.id), capture_interval_days: 4, strategy: 'military' } }))}>{t("admin_ui_3d76f22bfb")}</Button></Box>
              <TerritorySelect multiple label={t("admin_ui_341774d862")} value={sandbox.economy.starting_territory_ids} territories={territories} onChange={(event) => updateSandbox('economy', 'starting_territory_ids', event.target.value.map(Number))} />
              <TextField size="small" label={t("admin_ui_3a8d2b83af")} type="number" value={sandbox.economy.days} onChange={(event) => updateSandbox('economy', 'days', Number(event.target.value))} inputProps={{ min: 1, max: 90 }} />
              <TextField size="small" label={t("admin_ui_dd488b49b0")} type="number" value={sandbox.economy.active_members} onChange={(event) => updateSandbox('economy', 'active_members', Number(event.target.value))} />
              <TextField size="small" label={t("admin_ui_b57d499fdb")} type="number" value={sandbox.economy.capture_interval_days} onChange={(event) => updateSandbox('economy', 'capture_interval_days', Number(event.target.value))} />
              <TextField size="small" select label={t("admin_ui_672731adec")} value={sandbox.economy.strategy} onChange={(event) => updateSandbox('economy', 'strategy', event.target.value)}>{Object.entries(STRATEGY).map(([value, labelKey]) => <MenuItem value={value} key={value}>{t(labelKey)}</MenuItem>)}</TextField>
              <TextField size="small" label={t("admin_ui_b25d893cab")} type="number" value={sandbox.economy.production_multiplier_percent} onChange={(event) => updateSandbox('economy', 'production_multiplier_percent', Number(event.target.value))} />
              <TextField size="small" label={t("admin_ui_248745a58a")} type="number" value={sandbox.economy.cost_multiplier_percent} onChange={(event) => updateSandbox('economy', 'cost_multiplier_percent', Number(event.target.value))} />
              <FormControlLabel control={<Switch checked={sandbox.economy.automatic_captures} onChange={(event) => updateSandbox('economy', 'automatic_captures', event.target.checked)} />} label={t("admin_ui_5ba2cebfde")} />
              <Typography className="admin-sandbox-form__label">{t("admin_ui_e3a943c16c")}</Typography>
              <Box className="admin-sandbox-resources">{Object.entries({ ...RESOURCE, influence: 'common_influence' }).map(([key, labelKey]) => <TextField key={key} size="small" label={t(labelKey)} type="number" value={sandbox.economy.starting_resources[key]} onChange={(event) => updateResource(key, Number(event.target.value))} />)}</Box>
            </Box>}
            {sandboxTab === 'war' && <Box className="admin-sandbox-form">
              <Box className="admin-sandbox-presets"><span>{t("admin_ui_c5eb0c82e5")}</span><Button size="small" onClick={() => setSandbox((current) => ({ ...current, war: { ...current.war, attacker_rating: 1000, defender_rating: 1000, match_count: 10, team_size: 1, attacker_offense_level: 0, defender_fortification_level: 0 } }))}>{t("admin_ui_bbd36facd6")}</Button><Button size="small" onClick={() => setSandbox((current) => ({ ...current, war: { ...current.war, attacker_rating: 900, defender_rating: 1150, match_count: 15, team_size: 2, attacker_offense_level: 6, attacker_relic_power: 8 } }))}>{t("admin_ui_06284b99bb")}</Button></Box>
              <TerritorySelect label={t("admin_ui_b028e58586")} value={sandbox.war.source_territory_id} territories={territories} onChange={(event) => updateSandbox('war', 'source_territory_id', Number(event.target.value))} />
              <TerritorySelect label={t("admin_ui_d5627f6a61")} value={sandbox.war.target_territory_id} territories={territories} onChange={(event) => updateSandbox('war', 'target_territory_id', Number(event.target.value))} />
              <TextField size="small" select label={t("admin_ui_b765f32584")} value={sandbox.war.route_mode} onChange={(event) => updateSandbox('war', 'route_mode', event.target.value)}><MenuItem value="auto">{t("admin_ui_b613b6bc7c")}</MenuItem><MenuItem value="land">{t("admin_ui_af6b196e8e")}</MenuItem><MenuItem value="sea">{t("admin_ui_5fdaa2b054")}</MenuItem></TextField>
              {WAR_INPUTS.map(([key, labelKey]) => <TextField key={key} size="small" label={t(labelKey)} type="number" value={sandbox.war[key]} onChange={(event) => updateSandbox('war', key, Number(event.target.value))} />)}
              <FormControlLabel control={<Switch checked={sandbox.war.clan_team} onChange={(event) => updateSandbox('war', 'clan_team', event.target.checked)} />} label={t("admin_ui_03cdfe1d4d")} />
            </Box>}
            {sandboxTab === 'trade' && <Box className="admin-sandbox-form">
              <TerritorySelect label={t("admin_ui_595fbfbf1c")} value={sandbox.trade.source_territory_id} territories={territories} onChange={(event) => updateSandbox('trade', 'source_territory_id', Number(event.target.value))} />
              <TerritorySelect label={t("admin_ui_1060c5508f")} value={sandbox.trade.target_territory_id} territories={territories} onChange={(event) => updateSandbox('trade', 'target_territory_id', Number(event.target.value))} />
              <TextField size="small" select label={t("admin_ui_b765f32584")} value={sandbox.trade.route_mode} onChange={(event) => updateSandbox('trade', 'route_mode', event.target.value)}><MenuItem value="auto">{t("admin_ui_471f078716")}</MenuItem><MenuItem value="land">{t("admin_ui_849fecee5f")}</MenuItem><MenuItem value="sea">{t("admin_ui_dc2de2cc0f")}</MenuItem></TextField>
              <TextField size="small" select label={t("admin_ui_00ec23a619")} value={sandbox.trade.give_resource} onChange={(event) => updateSandbox('trade', 'give_resource', event.target.value)}>{Object.entries(RESOURCE).map(([value, labelKey]) => <MenuItem key={value} value={value}>{t(labelKey)}</MenuItem>)}</TextField>
              <TextField size="small" label={t("admin_ui_576698c4db")} type="number" value={sandbox.trade.give_amount} onChange={(event) => updateSandbox('trade', 'give_amount', Number(event.target.value))} />
              <TextField size="small" select label={t("admin_ui_cb25e513b1")} value={sandbox.trade.receive_resource} onChange={(event) => updateSandbox('trade', 'receive_resource', event.target.value)}>{Object.entries(RESOURCE).map(([value, labelKey]) => <MenuItem key={value} value={value}>{t(labelKey)}</MenuItem>)}</TextField>
              <TextField size="small" label={t("admin_ui_576698c4db")} type="number" value={sandbox.trade.receive_amount} onChange={(event) => updateSandbox('trade', 'receive_amount', Number(event.target.value))} />
              <TextField size="small" label={t("admin_ui_2af5e9aa64")} type="number" value={sandbox.trade.disruption_risk_percent} onChange={(event) => updateSandbox('trade', 'disruption_risk_percent', Number(event.target.value))} />
            </Box>}
            <Box className="admin-sandbox-run"><Button fullWidth variant="contained" startIcon={sandboxLoading ? <CircularProgress size={16} /> : <PlayArrowRounded />} onClick={runSandbox} disabled={sandboxLoading || !sandbox.economy.starting_territory_ids.length}>{t("admin_ui_493bf1c410")}</Button><small>{t("admin_ui_452187cdc7")}</small></Box>
          </Paper>

          <Box className="admin-sandbox-results">
            <ScenarioMap territories={territories} mapState={activeMap} />
            {!sandboxResult && <Paper className="admin-sandbox-placeholder"><ScienceOutlined /><Typography variant="h6">{t("admin_ui_131abbe673")}</Typography><span>{t("admin_ui_b94328b798")}</span></Paper>}
            {sandboxResult && sandboxTab === 'economy' && <Paper className="admin-sandbox-result">
              <Box className="admin-balance-section-head"><Box><TrendingUpRounded /><div><Typography variant="h6">{t("admin_ui_group_bcc275bbba", null, { value0: economyResult.scenario.parameters.days })}</Typography><Typography variant="body2" color="text.secondary">{t("admin_ui_ef280196e5")}</Typography></div></Box></Box>
              <Box className="admin-balance-scenario__kpi"><div><span>{t("admin_ui_2dcb633af3")}</span><strong>{economyResult.scenario.final.territory_count}</strong></div><div><span>{t("admin_ui_b0151ba273")}</span><strong>{number(economyResult.scenario.final.influence, language)}</strong></div><div><span>{t("admin_ui_9c141c86d8")}</span><strong>{economyResult.scenario.final.total_development_levels}</strong></div><div><span>{t("admin_ui_424260080b")}</span><strong>{economyResult.scenario.purchases.length}</strong></div></Box>
              <TimelineChart timeline={economyResult.scenario.timeline} baseline={economyResult.baseline.timeline} />
              <Box className="admin-balance-resources">{Object.entries(RESOURCE).map(([key, labelKey]) => <div key={key}><span>{t(labelKey)}</span><strong>{number(economyResult.scenario.final.resources[key], language)}</strong><small>Δ {Number(economyResult.delta_from_current_rules.resources[key]) > 0 ? '+' : ''}{number(economyResult.delta_from_current_rules.resources[key], language)}</small></div>)}</Box>
              <Box className="admin-sandbox-events"><b>{t("admin_ui_4108777b8b")}</b>{economyResult.scenario.captures.slice(0, 5).map((item) => <span key={`${item.territory_id}-${item.day}`}>{t("admin_ui_group_cdedaafbac", null, { value0: item.day, value1: item.territory_name })}</span>)}{economyResult.scenario.purchases.slice(0, 5).map((item) => <span key={`${item.goal}-${item.day}`}>{t("admin_ui_group_bee2a92ae3", null, { value0: item.day, value1: item.goal, value2: item.level })}</span>)}</Box>
            </Paper>}
            {sandboxResult && sandboxTab === 'war' && <Paper className="admin-sandbox-result">
              <Box className="admin-balance-section-head"><Box><MilitaryTechOutlined /><div><Typography variant="h6">{t("admin_ui_02b4bc2a27")}</Typography><Typography variant="body2" color="text.secondary">{t("admin_ui_group_ad32751de3", null, { value0: sandbox.war.match_count })}</Typography></div></Box></Box>
              {!sandboxResult.war.possible ? <Alert severity="warning">{sandboxResult.war.reason}</Alert> : <><Box className="admin-war-verdict"><Chip color={sandboxResult.war.verdict === 'uncertain' ? 'warning' : 'primary'} label={t(OUTCOME[sandboxResult.war.verdict])} /><b>{t("admin_ui_group_68ef3e7eb2", null, { value0: percent(sandboxResult.war.war_outcome_probability.attacker) })}</b><span>{t("admin_ui_group_3724502288", null, { value0: sandboxResult.war.route.mode === 'sea' ? t("admin_ui_7d1c308fb1") : t("admin_ui_0b1978f560"), value1: sandboxResult.war.route.steps, value2: sandboxResult.war.influence_cost })}</span></Box><Box className="admin-war-bars"><div><span>{t("admin_ui_group_8478beb05c", null, { value0: sandboxResult.war.expected_score.attacker })}</span><i style={{ width: percent(sandboxResult.war.war_outcome_probability.attacker) }} /></div><div><span>{t("admin_ui_group_896963a7aa", null, { value0: sandboxResult.war.expected_score.defender })}</span><i style={{ width: percent(sandboxResult.war.war_outcome_probability.defender) }} /></div></Box><Box className="admin-balance-scenario__kpi"><div><span>{t("admin_ui_8acc8edb6b")}</span><strong>{percent(sandboxResult.war.match_win_probability.attacker)}</strong></div><div><span>{t("admin_ui_594e620964")}</span><strong>{sandboxResult.war.power.attacker}%</strong></div><div><span>{t("admin_ui_f96a5b1975")}</span><strong>{sandboxResult.war.power.defender}%</strong></div><div><span>{t("admin_ui_9091719d29")}</span><strong>{sandboxResult.war.points_per_win.attacker}</strong></div></Box></>}
            </Paper>}
            {sandboxResult && sandboxTab === 'trade' && <Paper className="admin-sandbox-result">
              <Box className="admin-balance-section-head"><Box><LocalShippingOutlined /><div><Typography variant="h6">{t("admin_ui_6a979312fe")}</Typography><Typography variant="body2" color="text.secondary">{t("admin_ui_6d4e57c6fc")}</Typography></div></Box></Box>
              {!sandboxResult.trade.possible ? <Alert severity="warning">{sandboxResult.trade.reason}</Alert> : <><Box className="admin-trade-route"><MapOutlined /><div><b>{t("admin_ui_group_a458e142f6", null, { value0: sandboxResult.trade.route.mode === 'sea' ? t("admin_ui_dc2de2cc0f") : t("admin_ui_849fecee5f"), value1: sandboxResult.trade.route.steps })}</b><span>{t("admin_ui_group_8dd733c74b", null, { value0: sandboxResult.trade.eta_hours, value1: sandboxResult.trade.shipping_gold.creator, value2: sandboxResult.trade.shipping_gold.accepter })}</span></div></Box><Box className="admin-balance-scenario__kpi"><div><span>{t("admin_ui_00ec23a619")}</span><strong>{number(sandboxResult.trade.cargo.give_amount, language)} {t(RESOURCE[sandboxResult.trade.cargo.give_resource])}</strong></div><div><span>{t("admin_ui_cb25e513b1")}</span><strong>{number(sandboxResult.trade.cargo.receive_amount, language)} {t(RESOURCE[sandboxResult.trade.cargo.receive_resource])}</strong></div><div><span>{t("admin_ui_c704bcd2ec")}</span><strong>{sandboxResult.trade.cargo.nominal_rate}</strong></div><div><span>{t("admin_ui_d490c9bb23")}</span><strong>{sandboxResult.trade.shipping_gold.total}</strong></div></Box>{sandbox.trade.disruption_risk_percent > 0 && <Alert severity="info">{t("admin_ui_group_0101c56789", null, { value0: sandboxResult.trade.risk_model.expected_receive_delivered, value1: sandboxResult.trade.cargo.receive_amount })}</Alert>}</>}
            </Paper>}
          </Box>
        </Box>
      </>}

      {workspace === 'audit' && report && <>
        <Box className="admin-content-title admin-balance-audit-head"><Box><Typography variant="h5">{t("admin_ui_5cb2d8ab66")}</Typography><Typography color="text.secondary">{t("admin_ui_324e1426ec")}</Typography></Box><Stack direction="row" spacing={1}><TextField size="small" select label={t("admin_ui_750ccb94ce")} value={days} onChange={(event) => setDays(Number(event.target.value))}>{[7, 14, 30].map((value) => <MenuItem value={value} key={value}>{t("admin_ui_group_d3e546c95d", null, { value0: value })}</MenuItem>)}</TextField><Button variant="outlined" startIcon={loading ? <CircularProgress size={16} /> : <PlayArrowRounded />} onClick={run} disabled={loading}>{t("admin_ui_0c50d415ae")}</Button></Stack></Box>
        <Box className="admin-balance-metrics"><Paper><strong>v{report.rule_set.version}</strong><span>{t("admin_ui_6308f98e09")}</span></Paper><Paper><strong>{report.scenarios.length}</strong><span>{t("admin_ui_636f6534e1")}</span></Paper><Paper className={report.signals.length ? 'has-warning' : ''}><strong>{report.signals.length}</strong><span>{t("admin_ui_b0c7d682df")}</span></Paper><Paper><strong>{report.recommendations.length}</strong><span>{t("admin_ui_f24e01b6cb")}</span></Paper></Box>
        {report.signals.length > 0 && <Alert severity="warning">{t("admin_ui_group_b8b7ab9e30", null, { value0: report.signals.length })}</Alert>}
        {report.signals.length > 0 && <Paper className="admin-balance-signals-list"><Typography variant="h6">{t("admin_ui_1167cf4979")}</Typography><Box>{report.signals.slice(0, 12).map((signal, index) => <article key={`${signal.code}-${signal.scenario_id}-${index}`}><Chip size="small" variant="outlined" color="warning" label={signal.code} /><div><b>{signal.detail}</b><span>{signal.scenario_id} · {signal.parameter || t("admin_ui_c3ebb48f3a")}</span></div><strong>{String(signal.current_value ?? '—')} → {String(signal.proposed_value ?? t("admin_ui_70cd7f40d9"))}</strong></article>)}</Box></Paper>}
        <Paper className="admin-balance-filters"><TextField size="small" select label={t("admin_ui_eb0b9b0d90")} value={filter.profile} onChange={(event) => setFilter({ ...filter, profile: event.target.value })}><MenuItem value="all">{t("admin_ui_d56c32aa88")}</MenuItem>{Object.entries(PROFILE).map(([value, labelKey]) => <MenuItem key={value} value={value}>{t(labelKey)}</MenuItem>)}</TextField><TextField size="small" select label={t("admin_ui_e0d826c09c")} value={filter.pace} onChange={(event) => setFilter({ ...filter, pace: event.target.value })}><MenuItem value="all">{t("admin_ui_853a3797ad")}</MenuItem>{Object.entries(PACE).map(([value, labelKey]) => <MenuItem key={value} value={value}>{t(labelKey)}</MenuItem>)}</TextField><TextField size="small" select label={t("admin_ui_974319b781")} value={filter.strategy} onChange={(event) => setFilter({ ...filter, strategy: event.target.value })}><MenuItem value="all">{t("admin_ui_c0995b7849")}</MenuItem>{Object.entries(STRATEGY).map(([value, labelKey]) => <MenuItem key={value} value={value}>{t(labelKey)}</MenuItem>)}</TextField><TextField size="small" select label={t("admin_ui_f0aa024926")} value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>{scenarios.map((scenario) => <MenuItem key={scenario.id} value={scenario.id}>{t(PROFILE[scenario.profile])} · {t(PACE[scenario.pace])} · {t(STRATEGY[scenario.strategy])}</MenuItem>)}</TextField></Paper>
        {selected && <Paper className="admin-balance-scenario"><Box className="admin-balance-section-head"><Box><ScienceOutlined /><div><Typography variant="h6">{t(PROFILE[selected.profile])} · {t(PACE[selected.pace])} · {t(STRATEGY[selected.strategy])}</Typography><Typography variant="body2" color="text.secondary">{t("admin_ui_group_2a1b81868a", null, { value0: report.horizon_days, value1: selected.parameters.capture_interval_days })}</Typography></div></Box></Box><Box className="admin-balance-scenario__kpi"><div><span>{t("admin_ui_2dcb633af3")}</span><strong>{selected.final.territory_count}</strong></div><div><span>{t("admin_ui_b0151ba273")}</span><strong>{selected.final.influence}</strong></div><div><span>{t("admin_ui_e1ca8b1fe5")}</span><strong>{selected.final.clan_level}</strong></div><div><span>{t("admin_ui_9c141c86d8")}</span><strong>{selected.final.total_development_levels}</strong></div><div><span>{t("admin_ui_4deafccab6")}</span><strong>{selected.final.relic_levels}</strong></div><div><span>{t("admin_ui_424260080b")}</span><strong>{selected.purchases.length}</strong></div></Box><Box className="admin-balance-resources">{Object.entries(RESOURCE).map(([key, labelKey]) => <div key={key}><span>{t(labelKey)}</span><strong>{number(selected.final.resources[key], language)}</strong><small>+{number(selected.final.accumulated[key], language)} / −{number(selected.final.spent[key], language)}</small></div>)}</Box></Paper>}
      </>}
    </Box>
  );
};

export default AdminBalanceSimulatorPanel;
