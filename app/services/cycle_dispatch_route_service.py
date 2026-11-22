"""Маршрут отображается на карте, не меняя время пути и условия перехвата."""
from collections import deque

from app.models.cycle_dispatch_route import CycleDispatchRoute
from app.models.territory import Territory


class CycleDispatchRouteService:
    @staticmethod
    def territories(db, *, lock=False):
        query = db.query(Territory).filter(Territory.is_playable.is_(True)).order_by(Territory.id)
        if lock:
            query = query.with_for_update().populate_existing()
        return query.all()

    @staticmethod
    def origins(territories, clan_id):
        return [dict(territory_id=t.id, name=t.name) for t in territories if t.owner_clan_id == clan_id]

    @staticmethod
    def snapshot(territories, origin_id, target_id):
        by_id = {t.id: t for t in territories}
        if target_id not in by_id:
            raise ValueError('Целевая территория недоступна на карте')
        path = []
        status = 'no_origin' if origin_id is None else 'unreachable'
        if origin_id in by_id:
            parents = {origin_id: None}
            queue = deque([origin_id])
            while queue and target_id not in parents:
                current = queue.popleft()
                for neighbor in sorted(set(by_id[current].adjacent_territory_ids or [])):
                    if neighbor in by_id and neighbor not in parents:
                        parents[neighbor] = current
                        queue.append(neighbor)
            if target_id in parents:
                current = target_id
                while current is not None:
                    path.append(current)
                    current = parents[current]
                path.reverse()
                status = 'mapped'
        # Без связного пути показываем только реальную цель, не рисуя дорогу.
        nodes = [dict(territory_id=tid, name=by_id[tid].name, svg_path_data=by_id[tid].svg_path_data)
                 for tid in (path or [target_id])]
        return dict(origin_territory_id=origin_id, target_territory_id=target_id,
                    status=status, territory_ids=path, nodes=nodes)

    def prepare(self, db, *, clan_id, origin_id, target_id):
        territories = self.territories(db, lock=True)
        own_ids = {t.id for t in territories if t.owner_clan_id == clan_id}
        if origin_id is None and own_ids:
            raise ValueError('Выберите свою землю отправления')
        if origin_id is not None and (type(origin_id) is not int or origin_id not in own_ids):
            raise ValueError('Земля отправления больше не принадлежит вашему клану')
        return self.snapshot(territories, origin_id, target_id)

    @staticmethod
    def check_retry(db, *, cycle_id, dispatch_id, origin_id):
        stored = db.query(CycleDispatchRoute).filter_by(cycle_id=cycle_id, dispatch_id=dispatch_id).one_or_none()
        # Повтор сравнивает исходную команду, а не пересчитанный путь. Старые
        # отправки без исходной земли остаются повторяемыми после смены владельца.
        expected = stored.origin_territory_id if stored else None
        if origin_id != expected or (origin_id is not None and type(origin_id) is not int):
            raise ValueError('Повторная отправка должна содержать прежнюю землю отправления')

    @staticmethod
    def save(db, *, cycle_id, dispatch_id, snapshot):
        db.add(CycleDispatchRoute(cycle_id=cycle_id, dispatch_id=dispatch_id,
                                 origin_territory_id=snapshot['origin_territory_id'], snapshot=snapshot))
        db.flush()

    @staticmethod
    def project(db, *, cycle_id, view):
        routes = {r.dispatch_id: r.snapshot for r in db.query(CycleDispatchRoute).filter_by(cycle_id=cycle_id)}
        for dispatch in view['dispatches']:
            dispatch['route'] = routes.get(dispatch['id'])
        return view

    def context(self, db, *, clan_id, target_ids):
        territories = self.territories(db)
        origins = self.origins(territories, clan_id)
        return dict(origins=origins, route_previews=[
            self.snapshot(territories, origin_id, target_id)
            for origin_id in ([t['territory_id'] for t in origins] or [None])
            for target_id in sorted(set(target_ids))])
