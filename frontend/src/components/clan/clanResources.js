import {
  FoodResourceIcon as KebabDining,
  GoldResourceIcon as MonetizationOn,
  IronResourceIcon as Hardware,
  MithrilResourceIcon as Diamond,
  TerritoryPointsResourceIcon as FlagCircle,
  WoodResourceIcon as Forest,
} from '../ResourceIcon';

export const CLAN_RESOURCES = [
  { key: 'gold', labelKey: 'resource_gold', color: '#f6c453', Icon: MonetizationOn },
  { key: 'iron', labelKey: 'resource_iron', color: '#aeb7c2', Icon: Hardware },
  { key: 'wood', labelKey: 'resource_wood', color: '#62a66f', Icon: Forest },
  { key: 'food', labelKey: 'resource_food', color: '#ef6c5b', Icon: KebabDining },
  { key: 'mithril', labelKey: 'resource_mithril', color: '#65c7e8', Icon: Diamond },
  { key: 'territory_points', labelKey: 'clan_resource_influence', color: '#c69cff', Icon: FlagCircle },
];

export const CLAN_RESOURCE_BY_KEY = Object.fromEntries(
  CLAN_RESOURCES.map((resource) => [resource.key, resource]),
);
