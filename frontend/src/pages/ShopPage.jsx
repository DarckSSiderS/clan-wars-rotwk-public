import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
} from '@mui/material';
import { CloseRounded } from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { useSiteTheme } from '../contexts/SiteThemeContext';
import CosmeticItemPreview from '../components/CosmeticItemPreview';
import { PageShell, Surface } from '../components/ui';
import { SITE_THEME_ITEM_TYPE } from '../theme/siteThemes';
import { showSuccess, showError } from '../utils/notifications';
import { apiFetch } from '../services/apiFetch';
import './PrototypeFeaturePages.css';
import './ShopPage.css';

const rarityOrder = { legendary: 5, epic: 4, rare: 3, uncommon: 2, common: 1 };

const ShopPage = () => {
  const { user, updateUser } = useAuth();
  const { getLocalizedText: t, loadPageTexts, language } = useLocalizationContext();
  const { refreshSiteTheme } = useSiteTheme();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [shopItems, setShopItems] = useState([]);
  const [userInventory, setUserInventory] = useState([]);
  const [userBalance, setUserBalance] = useState(0);
  const [activeTab, setActiveTab] = useState('catalog');
  const [search, setSearch] = useState('');
  const [rarity, setRarity] = useState('all');
  const [itemType, setItemType] = useState('all');
  const [sort, setSort] = useState('rarity');
  const [purchasingItemIds, setPurchasingItemIds] = useState([]);
  const [details, setDetails] = useState(null);
  const [compareOpen, setCompareOpen] = useState(false);
  const [purchaseCandidate, setPurchaseCandidate] = useState(null);
  const formatNumber = useMemo(() => new Intl.NumberFormat(language), [language]);

  const loadShopData = useCallback(async () => {
    if (!user?.id) return;
    setLoading(true);
    setError('');
    try {
      const [catalogResponse, inventoryResponse] = await Promise.all([
        apiFetch('/api/v1/shop/items/available/'),
        apiFetch(`/api/v1/shop/users/${user.id}/items/`),
      ]);
      if (!catalogResponse.ok || !inventoryResponse.ok) throw new Error('shop');
      setShopItems(await catalogResponse.json());
      setUserInventory(await inventoryResponse.json());
    } catch {
      setError(t('shop_loading_error', 'Не удалось загрузить магазин'));
    } finally {
      setLoading(false);
    }
  }, [t, user?.id]);

  useEffect(() => { loadPageTexts('shop', language); }, [language, loadPageTexts]);
  useEffect(() => { loadShopData(); }, [loadShopData]);
  useEffect(() => { setUserBalance(user?.balance || 0); }, [user?.balance]);

  const catalog = shopItems;
  const inventoryByItemId = useMemo(() => new Map(userInventory.map((entry) => [entry.item_id, entry])), [userInventory]);
  const equipped = useMemo(() => userInventory.filter((entry) => entry.is_equipped), [userInventory]);
  const rarestOwned = useMemo(() => [...userInventory].sort((left, right) => (
    (rarityOrder[right.item?.rarity] || 0) - (rarityOrder[left.item?.rarity] || 0)
  ))[0], [userInventory]);
  const collectionPercent = catalog.length ? Math.round(userInventory.length / catalog.length * 100) : 0;
  const itemTypes = useMemo(() => [...new Set([
    ...catalog.map((item) => item.item_type),
    ...userInventory.map((entry) => entry.item?.item_type),
  ].filter(Boolean))], [catalog, userInventory]);

  const filterItems = (items, inventory = false) => {
    const query = search.trim().toLocaleLowerCase(language);
    return items
      .filter((entry) => {
        const item = inventory ? entry.item : entry;
        return (!query || `${item.name} ${item.description || ''}`.toLocaleLowerCase(language).includes(query))
          && (rarity === 'all' || item.rarity === rarity)
          && (itemType === 'all' || item.item_type === itemType);
      })
      .sort((left, right) => {
        const a = inventory ? left.item : left;
        const b = inventory ? right.item : right;
        if (sort === 'price') return (a.price || 0) - (b.price || 0);
        if (sort === 'name') return String(a.name).localeCompare(String(b.name), language);
        return (rarityOrder[b.rarity] || 0) - (rarityOrder[a.rarity] || 0) || (a.price || 0) - (b.price || 0);
      });
  };

  const filteredCatalog = useMemo(
    () => filterItems(catalog),
    // filterItems is intentionally derived only from the listed UI state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [catalog, itemType, language, rarity, search, sort],
  );
  const filteredInventory = useMemo(
    () => filterItems(activeTab === 'equipped' ? equipped : userInventory, true),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeTab, equipped, itemType, language, rarity, search, sort, userInventory],
  );

  const purchaseItem = async (itemId) => {
    if (purchasingItemIds.includes(itemId)) return;
    const purchasedItem = shopItems.find((item) => item.id === itemId);
    setPurchasingItemIds((current) => [...current, itemId]);
    try {
      const response = await apiFetch('/api/v1/shop/purchase/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_id: itemId }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || t('shop_purchase_error', 'Ошибка при покупке предмета'));
      const userItem = result.user_item || {
        id: `pending-${itemId}`,
        user_id: user?.id,
        item_id: itemId,
        is_equipped: false,
        item: purchasedItem,
      };
      setUserInventory((current) => current.some((entry) => entry.item_id === itemId) ? current : [...current, userItem]);
      setUserBalance(result.new_balance);
      const updatedUser = { ...user, balance: result.new_balance };
      updateUser(updatedUser);
      setDetails(null);
      setPurchaseCandidate(null);
      showSuccess(t('shop_purchase_success', 'Предмет куплен'));
    } catch (requestError) {
      showError(requestError.message || t('shop_purchase_error'));
    } finally {
      setPurchasingItemIds((current) => current.filter((id) => id !== itemId));
    }
  };

  const requestPurchase = (item) => {
    setDetails(null);
    setPurchaseCandidate(item);
  };

  const openDetails = (item, inventoryEntry) => {
    setCompareOpen(false);
    setDetails({ item, inventoryEntry });
  };

  const equipItem = async (userItemId, shouldEquip) => {
    try {
      const response = await apiFetch(
        shouldEquip ? '/api/v1/shop/equip/' : `/api/v1/shop/unequip/${userItemId}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          ...(shouldEquip ? { body: JSON.stringify({ user_item_id: userItemId }) } : {}),
        },
      );
      if (!response.ok) throw new Error(t('shop_equip_error', 'Ошибка экипировки предмета'));
      await loadShopData();
      await refreshSiteTheme();
      setDetails(null);
      showSuccess(shouldEquip ? t('profile_item_equipped') : t('profile_item_unequipped'));
    } catch (requestError) {
      showError(requestError.message || t('shop_equip_error'));
    }
  };

  const getCategoryIcon = (category) => {
    const icons = {
      profile_frame: '/icons/profilewb.png',
      stat_card_style: '/icons/axeswb.png',
      avatar_frame: '/icons/sauronwb.png',
      profile_background: '/icons/towerwb.png',
      [SITE_THEME_ITEM_TYPE]: '/icons/ennorathtvwb.png',
    };
    return icons[category] || '/icons/vswb.png';
  };

  const categoryLabel = (type) => t(`shop_category_${type}`, type?.replaceAll('_', ' ') || t('shop_all_types'));
  const rarityLabel = (value) => t(`shop_rarity_${value || 'common'}`, value || 'common');
  const renderVisual = (item) => <CosmeticItemPreview item={item} getFallbackIcon={getCategoryIcon} />;
  const shownItems = activeTab === 'catalog' ? filteredCatalog : filteredInventory;
  const loadoutSlots = [
    ['site_theme', t('shop_category_site_theme', 'Тема сайта')],
    ['avatar_frame', t('shop_category_avatar_frame', 'Рамка аватара')],
    ['profile_background', t('shop_category_profile_background', 'Фон профиля')],
    ['stat_card_style', t('shop_category_stat_card_style', 'Карточки статистики')],
  ];
  const comparedItem = details?.item ? equipped.find((entry) => (
    entry.id !== details.inventoryEntry?.id
    && (entry.item?.slot || entry.item?.item_type) === (details.item.slot || details.item.item_type)
  )) : null;

  return (
    <PageShell className="shop-page prototype-exact-page">
      <div className="page-title">
        <div><div className="eyebrow">{t('shop_unified_title')}</div><h1 className="serif">{t('nav_relics')}</h1><p className="subtitle">{t('shop_unified_subtitle')}</p></div>
        <div className="wallet shop-wallet"><small>{t('shop_balance')}</small><b>{formatNumber.format(userBalance)} ◈</b></div>
      </div>

      {activeTab === 'inventory' && (
        <div className="grid g3 shop-summary">
          <div className="card panel inventory-summary"><div className="eyebrow">{t('shop_collection_tab')}</div><h2>{formatNumber.format(userInventory.length)} / {formatNumber.format(catalog.length)}</h2><div className="progress"><i style={{ width: `${collectionPercent}%` }} /></div><p className="muted">{collectionPercent}% · {t('shop_collection_progress')}</p></div>
          <div className="card panel"><div className="eyebrow">{t('shop_rarest_owned', 'Самая редкая')}</div><h2>{rarestOwned?.item?.name || '—'}</h2><p className="muted">{rarestOwned?.item ? rarityLabel(rarestOwned.item.rarity) : t('shop_inventory_empty_title')}</p></div>
          <div className="card panel"><div className="eyebrow">{t('shop_active_loadout')}</div><h2>{equipped.length} / {loadoutSlots.length}</h2><p className="muted">{t('shop_loadout_copy', 'Активные предметы применены ко всему профилю.')}</p></div>
        </div>
      )}

      <div className="tabs shop-tabs" role="tablist">
        {[
          ['catalog', `${t('shop_catalog_tab')} · ${catalog.length}`],
          ['inventory', `${t('shop_collection_tab')} · ${userInventory.length}`],
          ['equipped', `${t('shop_equipped_tab')} · ${equipped.length}`],
        ].map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={activeTab === value} className={`tab${activeTab === value ? ' active' : ''}`} onClick={() => setActiveTab(value)}>{label}</button>)}
      </div>

      {activeTab === 'catalog' && <Surface className="card filterbar shop-filterbar" data-section="shop-filters">
        <input className="input" aria-label={t('common_search')} value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t('shop_search_placeholder')} />
        <select className="input" aria-label={t('shop_all_rarities')} value={rarity} onChange={(event) => setRarity(event.target.value)}><option value="all">{t('shop_all_rarities')}</option>{Object.keys(rarityOrder).map((value) => <option value={value} key={value}>{rarityLabel(value)}</option>)}</select>
        <select className="input" aria-label={t('shop_all_types')} value={itemType} onChange={(event) => setItemType(event.target.value)}><option value="all">{t('shop_all_types')}</option>{itemTypes.map((type) => <option value={type} key={type}>{categoryLabel(type)}</option>)}</select>
        <select className="input" aria-label={t('shop_sort_label', 'Сортировка')} value={sort} onChange={(event) => setSort(event.target.value)}><option value="rarity">{t('shop_sort_rarity', 'По редкости')}</option><option value="price">{t('shop_sort_price', 'По цене')}</option><option value="name">{t('shop_sort_name', 'По названию')}</option></select>
      </Surface>}

      {loading ? (
        <section className="shop-grid" aria-label={t('common_loading')}>{Array.from({ length: 8 }, (_, index) => <Surface className="shop-skeleton" key={index} />)}</section>
      ) : error ? (
        <div className="prototype-state is-error" role="alert"><p>{error}</p><button type="button" className="prototype-button" onClick={loadShopData}>{t('clan_statistics_refresh')}</button></div>
      ) : activeTab === 'equipped' ? (
        <>
          <section className="loadout shop-loadout" data-section="shop-loadout" role="tabpanel">
            {loadoutSlots.map(([slot, label]) => {
              const entry = equipped.find((candidate) => (candidate.item?.slot || candidate.item?.item_type) === slot);
              return entry ? (
                <button type="button" className="card equip-slot filled" key={slot} onClick={() => openDetails(entry.item, entry)}>
                  <span>{label}</span>{renderVisual(entry.item)}<b>{entry.item.name}</b><small>{entry.item.description}</small>
                </button>
              ) : (
                <div className="card equip-slot empty" key={slot}><span>{label}</span><b>{t('shop_empty_slot', 'Пустой слот')}</b><small>{t('shop_empty_slot_copy', 'Экипируйте совместимый предмет из коллекции')}</small></div>
              );
            })}
          </section>
          <section className="section grid g2 shop-loadout-summary">
            <div className="card panel"><h2>{t('shop_total_bonuses', 'Суммарные бонусы')}</h2><div className="bonus-grid">{equipped.length ? equipped.map((entry) => <span key={entry.id}><b>+</b>{entry.item?.name}</span>) : <span>{t('shop_no_active_bonuses', 'Нет активных бонусов')}</span>}</div></div>
            <div className="card panel"><h2>{t('shop_set_title', 'Комплект')}</h2><p className="muted">{t('shop_set_copy', 'Соберите предметы одной серии, чтобы завершить визуальный комплект профиля.')}</p><div className="progress"><i style={{ width: `${Math.min(100, equipped.length / loadoutSlots.length * 100)}%` }} /></div></div>
          </section>
        </>
      ) : shownItems.length === 0 ? (
        <Surface className="shop-empty"><img src="/design-prototype/relic_12.webp" alt="" /><h2>{activeTab === 'catalog' ? t('shop_no_items_title') : t('shop_inventory_empty_title')}</h2><p>{activeTab === 'catalog' ? t('shop_no_items_description') : t('shop_inventory_empty_description')}</p></Surface>
      ) : (
        <section className="section grid g4 shop-grid" data-section="relic-grid" role="tabpanel">
          {shownItems.map((entry) => {
            const inventoryEntry = activeTab === 'catalog' ? inventoryByItemId.get(entry.id) || null : entry;
            const item = inventoryEntry?.item || entry;
            const isPurchasing = purchasingItemIds.includes(item.id);
            return (
              <Surface as="article" interactive className={`${inventoryEntry ? 'inventory-item' : 'shop-item-card'} shop-card rarity-${item.rarity || 'common'} ${inventoryEntry?.is_equipped ? 'equipped' : ''}`} key={inventoryEntry?.id || item.id}>
                <div className={`shop-img rarity-${item.rarity || 'common'}`}>
                  {renderVisual(item)}
                  {inventoryEntry && <span className="owned">{inventoryEntry.is_equipped ? t('shop_equipped_tab') : t('shop_owned', 'В коллекции')}</span>}
                </div>
                <div className="shop-body">
                  <div className={`rarity ${item.rarity || 'common'}`}>{rarityLabel(item.rarity)}</div>
                  <h3>{item.name}</h3>
                  <p className="muted">{item.description || t('profile_no_description')}</p>
                  <div className="shop-foot">
                    <span className="price">{formatNumber.format(item.price || 0)} ◈</span>
                    <button type="button" className="btn" onClick={() => openDetails(item, inventoryEntry)} disabled={isPurchasing}>{t('shop_details')}</button>
                  </div>
                </div>
              </Surface>
            );
          })}
        </section>
      )}

      <Dialog className="shop-detail-dialog" open={Boolean(details)} onClose={() => { setDetails(null); setCompareOpen(false); }} maxWidth={false} aria-labelledby="shop-details-title">
        <DialogTitle id="shop-details-title" className="shop-details__title">
          <span>{rarityLabel(details?.item?.rarity)}</span>
          {details?.item?.name}
          <IconButton onClick={() => { setDetails(null); setCompareOpen(false); }} aria-label={t('common_close')}><CloseRounded /></IconButton>
        </DialogTitle>
        <DialogContent dividers className="shop-details__content">
          <p>{details?.item?.description || t('profile_no_description')}</p>
          <dl><div><dt>{t('shop_slot', 'Слот')}</dt><dd>{categoryLabel(details?.item?.slot || details?.item?.item_type)}</dd></div><div><dt>{t('shop_all_rarities')}</dt><dd>{rarityLabel(details?.item?.rarity)}</dd></div><div><dt>{t('shop_bonus', 'Эффект')}</dt><dd>{details?.item?.description || '—'}</dd></div></dl>
          {compareOpen && <div className="shop-compare"><span>{t('shop_compare_with', 'Сравнение с экипированным')}</span><b>{comparedItem?.item?.name || t('shop_compare_empty', 'В этом слоте ничего не экипировано')}</b><small>{comparedItem?.item?.description || t('shop_compare_hint', 'Предмет займёт свободный слот.')}</small></div>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCompareOpen((value) => !value)}>{t('shop_compare', 'Сравнить')}</Button>
          <Button onClick={() => { setDetails(null); setCompareOpen(false); }}>{t('common_close')}</Button>
          {details && (details.inventoryEntry ? (
            <Button variant="contained" onClick={() => equipItem(details.inventoryEntry.id, !details.inventoryEntry.is_equipped)}>{details.inventoryEntry.is_equipped ? t('shop_unequip_button') : t('shop_equip_button')}</Button>
          ) : (
            <Button variant="contained" disabled={purchasingItemIds.includes(details.item.id) || userBalance < details.item.price} onClick={() => requestPurchase(details.item)}>{purchasingItemIds.includes(details.item.id) ? <CircularProgress size={18} color="inherit" /> : t('shop_buy_button')}</Button>
          ))}
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(purchaseCandidate)} onClose={() => setPurchaseCandidate(null)} fullWidth maxWidth="xs" aria-labelledby="shop-purchase-title">
        <DialogTitle id="shop-purchase-title">{t('shop_purchase_dialog_title', 'Подтверждение покупки')}</DialogTitle>
        <DialogContent className="shop-purchase-dialog">
          <p>{t('shop_purchase_dialog_description', null, { name: purchaseCandidate?.name || '', price: formatNumber.format(purchaseCandidate?.price || 0) })}</p>
          <dl>
            <div><dt>{t('shop_balance')}</dt><dd>{formatNumber.format(userBalance)} ◈</dd></div>
            <div><dt>{t('shop_buy_button')}</dt><dd>{formatNumber.format(purchaseCandidate?.price || 0)} ◈</dd></div>
          </dl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPurchaseCandidate(null)}>{t('clans_cancel_button', 'Отмена')}</Button>
          <Button variant="contained" disabled={!purchaseCandidate || purchasingItemIds.includes(purchaseCandidate.id)} onClick={() => purchaseItem(purchaseCandidate.id)}>
            {purchaseCandidate && purchasingItemIds.includes(purchaseCandidate.id) ? <CircularProgress size={18} color="inherit" /> : t('shop_purchase_confirm', 'Подтвердить покупку')}
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
};

export default ShopPage;
