import React from 'react';
import CosmeticItemPreview from '../CosmeticItemPreview';

const ProfileInventoryTab = ({
  inventory,
  getLocalizedText,
  getCategoryIcon,
  onEquip,
  onOpenShop,
}) => (
  <div id="userInventoryContainer">
    <div className="d-flex justify-content-between align-items-center gap-3 mb-4">
      <div>
        <h5 className="mb-1">{getLocalizedText('profile_inventory_title', 'Ваши предметы')}</h5>
        <p className="text-secondary mb-0">
          {getLocalizedText('profile_inventory_theme_hint', 'Купленные темы включаются здесь и меняют весь сайт.')}
        </p>
      </div>
      <button className="btn btn-outline-primary flex-shrink-0" onClick={onOpenShop}>
        {getLocalizedText('profile_inventory_go_to_shop', 'Перейти в магазин')}
      </button>
    </div>
    {inventory.length === 0 ? (
      <div className="text-center text-muted">
        <img src="/icons/vswb.png" alt="Box" style={{ width: '60px', height: '60px', marginBottom: '1rem' }} />
        <h6>{getLocalizedText('profile_inventory_empty_title', 'Инвентарь пуст')}</h6>
        <p>{getLocalizedText('profile_inventory_empty_description', 'У вас пока нет купленных предметов')}</p>
        <button onClick={onOpenShop} className="btn btn-primary">
          <img src="/icons/sauronwb.png" alt="Shop" style={{ width: '16px', height: '16px', marginRight: '8px' }} />
          {getLocalizedText('profile_inventory_go_to_shop', 'Перейти в магазин')}
        </button>
      </div>
    ) : (
      <div className="inventory-grid">
        {inventory.map((userItem) => (
          <div key={userItem.id} className={`inventory-item ${userItem.is_equipped ? 'equipped' : ''}`} style={{ position: 'relative' }}>
            {userItem.is_equipped && (
              <div className="equipped-badge">{getLocalizedText('profile_inventory_equipped', 'Экипировано')}</div>
            )}
            <div className="item-image">
              <CosmeticItemPreview item={userItem.item} getFallbackIcon={getCategoryIcon} />
            </div>
            <div className="item-name">{userItem.item.name}</div>
            <div className="item-description">
              {userItem.item.description || getLocalizedText('profile_no_description', 'Описание отсутствует')}
            </div>
            <div className="item-actions">
              <button
                className={`btn ${userItem.is_equipped ? 'btn-secondary' : 'btn-primary'}`}
                onClick={() => onEquip(userItem.id, !userItem.is_equipped)}
              >
                <img
                  src={userItem.is_equipped ? '/icons/towerwb.png' : '/icons/sauronwb.png'}
                  alt="Action"
                  style={{ width: '12px', height: '12px', marginRight: '4px' }}
                />
                {userItem.is_equipped
                  ? getLocalizedText('profile_inventory_unequip', 'Снять')
                  : getLocalizedText('profile_inventory_equip', 'Экипировать')}
              </button>
            </div>
          </div>
        ))}
      </div>
    )}
  </div>
);

export default ProfileInventoryTab;
