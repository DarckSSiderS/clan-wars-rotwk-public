import { economyMessage, positiveQuantity, resources } from './cycleEconomyView';
import { canonicalAmount } from './cycleBarterCommands';

const messages = {
  give: ['Отдать', 'Offer'], receive: ['Получить', 'Request'], target: ['Кому', 'Recipient'], public: ['Общее предложение', 'Public offer'],
  youGive: ['Отдаёте', 'You give'], youReceive: ['Получаете', 'You receive'],
  create: ['Выставить обмен', 'Create offer'], review: ['Проверить предложение', 'Review offer'], accept: ['Принять обмен', 'Accept offer'], cancel: ['Отменить предложение', 'Cancel offer'],
  fee: ['Комиссия золотом', 'Gold fee'], arrive: ['Ожидаемое прибытие', 'Estimated arrival'],
  terms: ['Обмен материалами · комиссия каждой стороны: 10% золотом от рыночной стоимости получаемого груза.', 'Materials only · each side pays a 10% gold fee on the market value of incoming cargo.'],
  deliveryNote: ['Принятые грузы доставляются даже после объявления войны.', 'Accepted cargo arrives even if war is declared.'],
  offers: ['Предложения обмена', 'Barter offers'], transit: ['Караваны', 'Caravans'], offersEmpty: ['Предложений нет.', 'No offers.'], transitEmpty: ['Нет грузов в пути.', 'No cargo in transit.'],
  history: ['История обменов', 'Exchange history'], refund: ['Возврат резерва', 'Reserved cargo refund'], confirmOffer: ['Подтвердить обмен?', 'Confirm exchange?'],
  pending: ['Открыто', 'Open'], accepted: ['Принято', 'Accepted'], cancelled: ['Отменено', 'Cancelled'], expired: ['Срок истёк', 'Expired'],
  delivered: ['Доставлен', 'Delivered'], travelling: ['В пути', 'Travelling'], expires: ['До расчёта цикла', 'Until cycle settlement'],
  noLand: ['Для обмена нужна территория и доступный маршрут.', 'Trading requires land and an available route.'],
  deliveryPending: ['Маршрут и срок доставки определяются после выбора второго клана при принятии предложения.', 'Route and delivery time are determined when the second clan accepts the offer.'],
  routeConfirmed: ['Маршрут доступен', 'Route available'], travel: ['Доставка, ч', 'Delivery, hours'],
  add: ['добавить ресурс', 'add material'], remove: ['убрать ресурс', 'remove material'], material: ['ресурс', 'material'],
  own: ['Ваше предложение', 'Your offer'], loading: ['Загрузка предложений...', 'Loading offers...'],
};
export const barterMessage = (key, language) => messages[key]?.[String(language).startsWith('en') ? 1 : 0] || economyMessage(key, language);
export const materials = resources.slice(1);
export const validCargoRows = rows => rows.length > 0 && new Set(rows.map(row => row.resource)).size === rows.length && rows.every(row => materials.includes(row.resource) && positiveQuantity(row.amount));
export const cargoFromRows = rows => Object.fromEntries(materials.filter(key => rows.some(row => row.resource === key)).map(key => [key, canonicalAmount(rows.find(row => row.resource === key).amount)]));
export const offerPerspective = (offer, clanId) => String(offer.sender_clan_id) === String(clanId)
  ? { give: offer.offered, receive: offer.requested, own: true }
  : { give: offer.requested, receive: offer.offered, own: false };
