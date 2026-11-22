import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Refresh, ShoppingCart, TrendingUp, Save } from '@mui/icons-material';
import { Dialog, DialogTitle, DialogContent, DialogActions, Tabs, Tab, ToggleButtonGroup, ToggleButton } from '@mui/material';
import { PageShell } from '../components/ui';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { clanService } from '../services/clanService';
import { cycleCampaignService } from '../services/cycleCampaignService';
import { cycleEconomyService } from '../services/cycleEconomyService';
import { getRelicArtwork } from '../content/clanRelics';
import { canAfford, costText, currentUpgradeEffect, economyMessage, marketTotal, positiveQuantity, resources, upgradeEffectText } from '../utils/cycleEconomyView';
import { CLAN_RESOURCE_BY_KEY } from '../components/clan/clanResources';
import { cycleMessage } from '../utils/cycleBattleView';
import './CycleEconomyPage.css';
import CycleBarter, { ResourceAmounts } from '../components/CycleBarter';

export function EconomyContent({ cycleId, activeTab, tradeMode, onTradeModeChange, embedded = false, clanId, labelledBy, visible = true }) {
  const { language } = useLocalizationContext();
  const copy = key => economyMessage(key, language);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [clanless, setClanless] = useState(false);
  const [busy, setBusy] = useState(false);
  const [localTab, setTab] = useState('relics');
  const tab = activeTab ?? localTab;
  const [localTradeMode, setTradeMode] = useState('market');
  const mode = tradeMode ?? localTradeMode;
  const [active, setActive] = useState([]);
  const [starters, setStarters] = useState([]);
  const [dirty, setDirty] = useState(false);
  const [confirmation, setConfirmation] = useState(null);
  const [notice, setNotice] = useState('');
  const [resource, setResource] = useState('iron');
  const [quantity, setQuantity] = useState('1');
  const [buying, setBuying] = useState(true);
  const mounted = useRef(false);
  const generation = useRef(0);
  const writing = useRef(false);
  const draftDirty = useRef(false);
  const ownClan = useRef(null);
  const dialogId = React.useId();
  const load = useCallback(async () => {
    const token = ++generation.current;
    setLoading(true);
    try {
      const clan = await clanService.getMyClan();
      if (!mounted.current || token !== generation.current) return;
      if (!clan || (clanId != null && String(clan.id) !== String(clanId))) {
        setData(null); setClanless(true); setFailed(false); setConfirmation(null); return;
      }
      const cycle = await cycleCampaignService.getCycle(cycleId);
      const next = await cycleEconomyService.context(cycle.season_id, clan.id);
      if (!mounted.current || token !== generation.current) return;
      const changedClan = ownClan.current !== next.clan_id;
      ownClan.current = next.clan_id;
      setData(next);
      if (changedClan || !draftDirty.current) { setActive(next.state?.active_relics || []); setDirty(false); draftDirty.current = false; }
      if (changedClan) setStarters([]);
      setFailed(false); setClanless(false);
    } catch (error) {
      if (!mounted.current || token !== generation.current) return;
      setFailed(true); setConfirmation(null);
      if ([403, 404].includes(error.response?.status)) setData(null);
    } finally { if (mounted.current && token === generation.current) setLoading(false); }
  }, [cycleId, clanId]);
  useEffect(() => { mounted.current = true; load(); return () => { mounted.current = false; }; }, [load]);
  async function act(action, payload = {}) {
    if (writing.current || failed || !data) return;
    writing.current = true; setBusy(true); setConfirmation(null); setNotice(''); generation.current += 1;
    try {
      await cycleEconomyService.command(data.season_id, data.clan_id, action,
        action === 'initialize' ? {} : { ...payload, expected_revision: data.state.revision });
      if (!mounted.current) return;
      if (action === 'active-relics') { draftDirty.current = false; setDirty(false); }
      if (action === 'starters') setStarters([]);
      await load(); setNotice('saved');
    } catch {
      if (!mounted.current) return;
      await load(); setNotice('conflict');
    } finally { writing.current = false; if (mounted.current) setBusy(false); }
  }
  function propose(action, payload, description) { setConfirmation({ action, payload, description }); }
  const disabled = busy || failed || loading;
  const wallet = data?.state?.wallet;
  const total = marketTotal(quantity, (buying ? data?.market_buy : data?.market_sell)?.[resource]);
  const marketGive = buying ? { gold: total } : { [resource]: quantity };
  const marketReceive = buying ? { [resource]: quantity } : { gold: total };
  const branchName = branch => copy(branch === 'gold' ? 'goldBranch' : branch === 'mithril' ? 'mithrilBranch' : branch);
  const refreshButton = <button title={copy('refresh')} aria-label={copy('refresh')} disabled={busy || loading || dirty} onClick={load}><Refresh aria-hidden="true" /></button>;
  return <PageShell as={embedded ? 'div' : 'main'} className={`cycle-economy${embedded ? ' cycle-economy--embedded' : ''}`} aria-busy={busy || loading}>
    {embedded ? <div className="ce-embedded-toolbar">{refreshButton}</div> : <>
      <header><h1>{copy('heading')}</h1>{refreshButton}</header>
      <Link to={`/campaign/cycles/${cycleId}`}>{cycleMessage('cycle_battles_title', language)}</Link>
    </>}
    {loading && !data ? <p role="status">{copy('loading')}</p> : clanless ? <p>{copy('clanless')}</p> : <>
      {failed && <p role="alert" className="ce-error">{copy('failed')}</p>}
      {data && <>{!embedded && <h2>{data.clan_name}</h2>}
        {notice && <p role={notice === 'saved' ? 'status' : 'alert'}>{copy(notice)}</p>}
        {!data.ready ? data.can_manage && <button disabled={disabled} onClick={() => act('initialize')}>{copy('init')}</button> : <>
          <dl className="ce-wallet">{resources.map(key => { const { Icon } = CLAN_RESOURCE_BY_KEY[key]; return <div key={key}><dt><Icon aria-hidden="true" />{copy(key)}</dt><dd>{Number(wallet[key]).toLocaleString(language, { maximumFractionDigits: 2 })}</dd></div>; })}</dl>
          {!embedded && <Tabs value={tab} onChange={(_, value) => setTab(value)} aria-label={copy('heading')} className="ce-tabs" variant="scrollable">{['relics', 'lands', 'market'].map(value => <Tab id={`ce-tab-${value}`} aria-controls={`ce-panel-${value}`} key={value} value={value} label={copy(value === 'market' ? 'trade' : value)} />)}</Tabs>}
          <section role="tabpanel" id={`ce-panel-${tab}`} aria-labelledby={embedded ? labelledBy : `ce-tab-${tab}`}>
            {tab === 'market' && <div className="ce-trade-toolbar"><ToggleButtonGroup exclusive value={mode} aria-label={copy('tradeMode')} onChange={(_, value) => { if (value) { setTradeMode(value); onTradeModeChange?.(value); } }}>
              <ToggleButton value="market">{copy('goldMarket')}</ToggleButton><ToggleButton value="barter">{copy('barter')}</ToggleButton>
            </ToggleButtonGroup></div>}
            {tab === 'market' && mode === 'barter' && <CycleBarter key={`${data.clan_id}:${data.cycle_id}`} data={data} refreshWallet={load} suspended={disabled} />}
            {tab === 'relics' && <>
              {!data.state.starters_chosen && data.can_manage && <div className="ce-starters"><div className="ce-toolbar"><strong>{copy('starters')} · {starters.length} / 2</strong><button disabled={disabled || starters.length !== 2}
                onClick={() => act('starters', { selected: starters })}>{copy('claim')}</button></div><p className="ce-starter-help" id={`${dialogId}-gifts`}>{copy('starterHelp')}</p></div>}
              <p>{copy('frozen')}</p>
              {data.can_select && <div className="ce-toolbar"><strong>{active.length} / 4</strong><button disabled={disabled || !dirty || active.length > 4} onClick={() => act('active-relics', { cycle_id: data.cycle_id, selected: active })}><Save aria-hidden="true" />{copy('save')}</button>
                {dirty && <button onClick={() => { setActive(data.state.active_relics); setDirty(false); draftDirty.current = false; }}>{copy('cancel')}</button>}</div>}
              <div className="ce-relics">{data.catalog.map(relic => {
                const level = data.state.relics[relic.key] || 0;
                return <article className="ce-relic" key={relic.key}>
                  <img src={getRelicArtwork(relic.key)} alt="" loading="lazy" /><div><h3>{relic.name}</h3><p>{copy(relic.effect === 'gold' ? 'territoryGold' : relic.effect)}</p><p>{copy('level')}: {level} / 3</p></div>
                  <table><thead><tr><th>{copy('levelShort')}</th><th>{copy('effect')}</th><th>{copy('price')}</th></tr></thead><tbody>{relic.effects.map((effect, i) => <tr key={i}><th scope="row">{i + 1}</th><td>+{effect}%</td><td>{costText(relic.costs[i], copy)}</td></tr>)}</tbody></table>
                  {!data.state.starters_chosen && data.can_manage && !level && <label className="ce-check ce-gift"><input type="checkbox" aria-describedby={`${dialogId}-gifts`} aria-label={`${copy('starter')}: ${relic.name}`} checked={starters.includes(relic.key)} disabled={disabled || (!starters.includes(relic.key) && starters.length >= 2)}
                    onChange={e => setStarters(e.target.checked ? [...starters, relic.key] : starters.filter(k => k !== relic.key))} />{copy('starter')}</label>}
                  {level > 0 && <label className="ce-check"><input type="checkbox" checked={active.includes(relic.key)} disabled={disabled || !data.can_select || (!active.includes(relic.key) && active.length >= 4)}
                    onChange={e => { setActive(e.target.checked ? [...active, relic.key] : active.filter(k => k !== relic.key)); setDirty(true); draftDirty.current = true; }} />{copy('active')}</label>}
                  {data.can_manage && (level === 3 ? <p>{copy('max')}</p> : <button className="ce-gold" disabled={disabled || !canAfford(wallet, relic.costs[level])}
                    onClick={() => propose('relics', { key: relic.key }, `${relic.name} · ${copy('level')} ${level + 1} · ${costText(relic.costs[level], copy)}`)}><ShoppingCart aria-hidden="true" />{copy(level ? 'upgrade' : 'buy')}</button>)}
                </article>;
              })}</div>
            </>}
            {tab === 'lands' && (!data.lands.length ? <p>{copy('noLands')}</p> : data.lands.map((land, index) => <details className="ce-land" name={`${dialogId}-lands`} key={land.territory_id} open={index === 0 ? true : undefined}>
              <summary><span className="ce-land-summary-line"><strong>{land.name}</strong><span className="ce-land-levels">{Object.entries(land.quotes).map(([branch, quote]) => <span key={branch}>{copy(`${branch}Short`)} <b>{quote.level}</b></span>)}</span>
                <span className="ce-land-income">{['gold', 'profile', 'mithril'].filter(branch => land.quotes[branch]?.level > 0).map(branch => <span key={branch}>{copy(`${branch}Short`)} {upgradeEffectText(branch, currentUpgradeEffect(branch, land.quotes[branch]), copy)}</span>)}</span>
              </span></summary>
              <ul>{Object.entries(land.quotes).map(([branch, quote]) => <li className="ce-upgrade-row" key={branch}>
                <div className="ce-upgrade-name"><strong>{branchName(branch)}</strong><span>{copy('level')} {quote.level} / 3</span></div>
                <div className="ce-upgrade-effect"><span>{copy('currentEffect')}: <b>{upgradeEffectText(branch, currentUpgradeEffect(branch, quote), copy)}</b></span>
                  {quote.cost && <span>{copy('nextEffect')}: {upgradeEffectText(branch, quote.next_effect, copy)}</span>}</div>
                <div className="ce-upgrade-cost">{quote.cost ? <ResourceAmounts cargo={quote.cost} copy={copy} /> : copy(quote.level === 3 ? 'max' : 'unavailable')}</div>
                {data.can_manage && <button title={`${land.name}: ${branchName(branch)}`} disabled={disabled || !canAfford(wallet, quote.cost)} onClick={() => propose('upgrades', { territory_id: land.territory_id, branch, expected_upgrade_revision: land.revision }, `${land.name} · ${branchName(branch)} · ${copy('level')} ${quote.level + 1} · ${upgradeEffectText(branch, quote.next_effect, copy)} · ${costText(quote.cost, copy)}`)}><TrendingUp aria-hidden="true" />{copy('upgrade')}</button>}</li>)}</ul>
            </details>))}
            {tab === 'market' && mode === 'market' && <form className="ce-market" onSubmit={e => { e.preventDefault(); if (data.can_trade && total) propose('market', { resource, quantity, buying }, `${copy('give')}: ${costText(marketGive, copy)}. ${copy('receive')}: ${costText(marketReceive, copy)}`); }}>
              <div className="ce-market-fields">
              <label>{copy('resource')}<select value={resource} disabled={disabled || !data.can_trade} onChange={e => setResource(e.target.value)}>{resources.slice(1).map(key => <option key={key} value={key}>{copy(key)}</option>)}</select></label>
              <label>{copy('direction')}<select value={buying ? 'buy' : 'sell'} disabled={disabled || !data.can_trade} onChange={e => setBuying(e.target.value === 'buy')}><option value="buy">{copy('buying')}</option><option value="sell">{copy('selling')}</option></select></label>
              <label>{copy('quantity')}<input type="text" inputMode="decimal" value={quantity} disabled={disabled || !data.can_trade} onChange={e => setQuantity(e.target.value)} /></label>
              </div>
              <p>{copy('unit')}: {(buying ? data.market_buy : data.market_sell)[resource]} {copy('gold')}</p>
              <div className="ce-market-summary"><div><span>{copy('give')}</span>{total ? <ResourceAmounts cargo={marketGive} copy={copy} /> : '-'}</div><span aria-hidden="true">→</span><div><span>{copy('receive')}</span>{total ? <ResourceAmounts cargo={marketReceive} copy={copy} /> : '-'}</div></div>
              {data.can_trade && <button className="ce-gold" disabled={disabled || !positiveQuantity(quantity) || !total || !canAfford(wallet, marketGive)}>{copy('perform')}</button>}
            </form>}
          </section>
        </>}
      </>}
    </>}
    <Dialog open={visible && Boolean(confirmation)} onClose={() => setConfirmation(null)} aria-labelledby={dialogId}><DialogTitle id={dialogId}>{copy('confirm')}</DialogTitle><DialogContent>{confirmation?.description}</DialogContent>
      <DialogActions><button className="ce-dialog-button" autoFocus onClick={() => setConfirmation(null)}>{copy('cancel')}</button><button className="ce-dialog-button" disabled={disabled} onClick={() => act(confirmation.action, confirmation.payload)}>{copy('confirmAction')}</button></DialogActions></Dialog>
  </PageShell>;
}
export default function CycleEconomyPage() {
  const { cycleId } = useParams(); const { user } = useAuth();
  return <EconomyContent key={`${user?.id}:${cycleId}`} cycleId={cycleId} />;
}
