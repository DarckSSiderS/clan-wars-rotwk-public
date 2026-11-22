"""Подтверждение стартовых подарков без запуска сезона и начисления дохода."""
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID

from app.core.time import as_utc
from app.models.campaign import CampaignSeason, CampaignRuleSet
from app.models.clan import Clan, ClanMember
from app.models.external_identity import ExternalPlayerIdentity
from app.models.preseason import CampaignPreseason, CampaignPreseasonChoice, CampaignPreseasonCandidate
from app.models.season_archive import CampaignSeasonArchive
from app.models.territory import Territory, TerritoryOwnershipHistory, TerritoryAttackingClans, TerritoryDefendingClans
from app.models.user import User
from app.models.war import ClanWar
from app.services.cycle_economy import RELICS, START_RESOURCES, RESOURCE_NAMES, starting_relics
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_starting_lands import selection_world, validate_starting_triple
from app.services.cycle_startup_service import CycleStartupService


class PreseasonService:
    def lock_rosters(self, db):
        """До изменения состава/UUID: параллельные третий и четвёртый не теряют порог."""
        if self._parent(db) is not None:
            db.query(Clan).filter_by(is_deleted=False, is_admin_clan=False).order_by(Clan.id).with_for_update().all()

    @staticmethod
    def _validate(selected, *, clan_id, initial, virtual):
        try:
            return validate_starting_triple(selected, clan_id=clan_id, initial_owned=initial, territories=virtual)
        except ValueError as error:
            messages = {
                'Exactly three distinct existing territories required': 'Выберите ровно три разные существующие земли.',
                'Starting lands must be connected, available, non-port and non-fortress': 'Нужны три связанные доступные земли без портов и крепостей.',
                'Must retain existing eligible land when a connected triple is possible': 'Сохраните прежние подходящие земли: если их три или больше, выберите тройку среди них; если одна или две — дополните нейтральными.',
                'Impossible retention must be replaced by an available neutral triple': 'Прежние земли нельзя объединить: выберите вместо них три связанные нейтральные земли.',
            }
            raise ValueError(messages.get(str(error), 'Не удалось подтвердить стартовые земли. Проверьте доступность и соседство.')) from error

    @staticmethod
    def _parent(db, *, lock=False):
        if db.query(CampaignSeason.id).filter(CampaignSeason.status != 'completed').first():
            return None
        latest = db.query(CampaignSeason).order_by(CampaignSeason.number.desc()).first()
        if latest is None:
            return None
        query = db.query(CampaignPreseason).filter_by(source_season_id=latest.id, status='open')
        row = query.with_for_update().populate_existing().one_or_none() if lock else query.one_or_none()
        if lock and db.query(CampaignSeason.id).filter(CampaignSeason.status != 'completed').first():
            return None
        return row

    def status(self, db):
        row = self._parent(db)
        return dict(open=row is not None, preparation_id=row.source_season_id if row else None)

    @staticmethod
    def _actor(db, clan_id, actor_id, *, write=False):
        user, clan = db.get(User, actor_id), db.get(Clan, clan_id)
        if (user is None or not user.is_active or clan is None or clan.is_deleted or clan.is_admin_clan
                or (clan.leader_id != actor_id and not db.query(ClanMember.id).filter_by(clan_id=clan_id, user_id=actor_id).first())):
            raise PermissionError('Выбор доступен только участникам своего клана')
        if write and (clan.leader_id != actor_id or user.onboarding_completed_at is None):
            raise PermissionError('Подтвердить выбор может только глава клана после привязки Арены')
        return clan, user

    @staticmethod
    def _choices(db, parent):
        return {r.clan_id: r for r in db.query(CampaignPreseasonChoice).filter_by(preparation_id=parent.source_season_id).populate_existing().all() if r.clan_id is not None}

    @staticmethod
    def _initial(parent, clan_id):
        return sorted(int(i) for i, owner in parent.initial_owners.items() if owner == clan_id)

    @staticmethod
    def _members(db, now):
        clans = {c.id for c in db.query(Clan).filter_by(is_deleted=False, is_admin_clan=False)}
        verified = {}
        for identity in db.query(ExternalPlayerIdentity).filter_by(source='bfmeladder', verification_status='verified').populate_existing():
            try:
                uuid = str(UUID(identity.external_uuid))
            except (ValueError, TypeError, AttributeError):
                continue
            verified_at = as_utc(identity.verified_at) if identity.verified_at else None
            if verified_at is None or verified_at <= now:
                verified[identity.user_id] = (uuid, verified_at)
        members = {clan_id: [] for clan_id in clans}
        for member in db.query(ClanMember).order_by(ClanMember.clan_id, ClanMember.user_id).populate_existing():
            if member.clan_id not in clans or member.user_id not in verified or member.joined_at is None:
                continue
            uuid, verified_at = verified[member.user_id]
            joined = max(as_utc(member.joined_at), verified_at or as_utc(member.joined_at))
            if joined <= now:
                members[member.clan_id].append(dict(user_id=member.user_id, source='bfmeladder', uuid=uuid, joined_at=joined.isoformat()))
        for values in members.values():
            values.sort(key=lambda m: (m['joined_at'], m['user_id']))
        return members

    def _qualifications(self, db, parent, now, *, persist=False):
        qualifications = dict(parent.qualifications or {})
        members = self._members(db, now)
        used = {m['uuid'] for receipt in qualifications.values() for m in receipt['selected_four']}
        # Достигнутая четвёрка переживает выход участника и удаление клана.
        events = db.query(CampaignPreseasonCandidate).filter_by(preparation_id=parent.source_season_id).order_by(
            CampaignPreseasonCandidate.qualified_at, CampaignPreseasonCandidate.id).all()
        for event in events:
            if len(qualifications) >= 6:
                break
            if str(event.clan_id) in qualifications or self._initial(parent, event.clan_id):
                continue
            four = event.selected_four
            if len(four) != 4 or len({m['uuid'] for m in four}) != 4 or any(m['uuid'] in used for m in four):
                continue
            qualifications[str(event.clan_id)] = dict(slot=len(qualifications)+1,
                qualified_at=as_utc(event.qualified_at).isoformat(), selected_four=four)
            used.update(m['uuid'] for m in four)
        candidates = []
        for clan_id, available in members.items():
            if str(clan_id) in qualifications or self._initial(parent, clan_id):
                continue
            four, seen = [], set(used)
            for member in available:
                if member['uuid'] not in seen:
                    four.append(member)
                    seen.add(member['uuid'])
                if len(four) == 4:
                    candidates.append((four[-1]['joined_at'], clan_id, four))
                    break
        for attained, clan_id, four in sorted(candidates):
            if len(qualifications) >= 6:
                break
            if any(m['uuid'] in used for m in four):
                continue
            qualifications[str(clan_id)] = dict(slot=len(qualifications) + 1, qualified_at=attained, selected_four=four)
            used.update(m['uuid'] for m in four)
        if persist and qualifications != parent.qualifications:
            parent.qualifications = qualifications
            db.flush()
        return qualifications, members

    def capture_candidates(self, db, *, now):
        """До commit сохраняет факт квалификации, не блокируя регистрационную строку."""
        db.flush()
        parent = self._parent(db)
        if parent is None:
            return
        planned, _ = self._qualifications(db, parent, as_utc(now))
        existing = {(row.clan_id, tuple(m['uuid'] for m in row.selected_four)) for row in db.query(
            CampaignPreseasonCandidate).filter_by(preparation_id=parent.source_season_id)}
        for clan_id, receipt in planned.items():
            key = (int(clan_id), tuple(m['uuid'] for m in receipt['selected_four']))
            if clan_id in (parent.qualifications or {}) or key in existing:
                continue
            db.add(CampaignPreseasonCandidate(preparation_id=parent.source_season_id, clan_id=int(clan_id),
                qualified_at=as_utc(now), selected_four=receipt['selected_four']))
        db.flush()

    def finish_qualification(self, db):
        from app.core.time import utc_now
        if self.qualify_open(db, now=utc_now()):
            db.commit()

    def qualify_open(self, db, *, now):
        parent = self._parent(db, lock=True)
        if parent is None:
            return False
        self._qualifications(db, parent, as_utc(now), persist=True)
        return True

    def open(self, db, *, actor_user_id, now):
        actor = db.get(User, actor_user_id)
        if actor is None or not actor.is_active or actor.role is None or actor.role.name != 'admin':
            raise PermissionError('Открыть выбор может только администратор')
        now = as_utc(now)
        with CycleEconomyStore._atomic(db):
            rule = db.query(CampaignRuleSet).filter_by(is_active=True).with_for_update().one_or_none()
            if rule is None:
                raise ValueError('Не опубликованы правила кампании')
            existing = self._parent(db, lock=True)
            if existing:
                return existing
            latest = db.query(CampaignSeason).order_by(CampaignSeason.number.desc()).first()
            if latest is None or db.query(CampaignSeason.id).filter(CampaignSeason.status != 'completed').first():
                raise ValueError('Сначала завершите текущий сезон')
            archive = db.get(CampaignSeasonArchive, latest.id)
            if archive is None or not archive.checksum or not archive.payload.get('territories'):
                raise ValueError('Нужен сохранённый архив завершённого сезона')
            if db.query(ClanWar.id).filter_by(status='active').first():
                raise ValueError('Сначала завершите оставшиеся битвы')
            from app.services.cycle_season_launch_service import CycleSeasonLaunchService
            assignments = CycleSeasonLaunchService._map(db, lock=True)
            clans = db.query(Clan).filter_by(is_deleted=False, is_admin_clan=False).order_by(Clan.id).with_for_update().all()
            ids = {clan.id for clan in clans}
            archived = archive.payload['territories']
            if {t['id'] for t in archived} != {t.id for t, _ in assignments}:
                raise ValueError('Карта отличается от сохранённого архива')
            parent = CampaignPreseason(source_season_id=latest.id, source_archive_checksum=archive.checksum,
                status='open', opened_at=now, initial_owners={str(t['id']): t['owner_clan_id'] if t['owner_clan_id'] in ids else None for t in archived}, qualifications={})
            db.add(parent)
            db.flush()
            for clan in clans:
                db.add(CampaignPreseasonChoice(preparation_id=latest.id, clan_id=clan.id, selected_lands=[], selected_relics=[]))
            for land, entry in assignments:
                CycleStartupService._transfer(db, land, None, now, 'preseason_reset', SimpleNamespace(starts_at=latest.starts_at))
                land.status = 'neutral'
                land.is_playable, land.has_port = entry.is_playable, entry.has_port
                land.stronghold_power = max(1, land.stronghold_power or 0) if entry.fortress else 0
                land.influence_value = entry.influence_value
                if entry.profile_material:
                    land.resource_type = entry.profile_material
                    land.resource_output = int(getattr(entry.base, entry.profile_material))
            for history in db.query(TerritoryOwnershipHistory).filter_by(ended_at=None).with_for_update():
                if as_utc(history.started_at) > now:
                    raise ValueError('В истории владения есть дата из будущего; требуется проверка перед открытием выбора')
                history.ended_at = now
            db.query(TerritoryAttackingClans).delete(synchronize_session=False)
            db.query(TerritoryDefendingClans).delete(synchronize_session=False)
            from app.services.clan_level_service import ClanLevelService
            from app.services.campaign_rule_service import CampaignRuleService
            snapshot = CampaignRuleService._snapshot(rule)
            for clan in clans:
                clan.base_influence = clan.territory_points = 0
                ClanLevelService().evaluate(db, clan, rule_set=snapshot, now=now, record=True)
            self._qualifications(db, parent, now, persist=True)
            from app.services.operation_service import AdminAuditService
            AdminAuditService().record(db, actor_user_id=actor_user_id, action='preseason_opened', entity_type='campaign_season',
                entity_id=latest.id, after_data=dict(archive_checksum=archive.checksum), reason='Выбор стартовых земель и реликвий без запуска сезона')
            db.flush()
            return parent

    def _context(self, db, *, clan_id, actor_id, now, lock=False, write=False):
        parent = self._parent(db, lock=lock)
        if parent is None:
            raise ValueError('Стартовый выбор сейчас закрыт')
        clan, user = self._actor(db, clan_id, actor_id, write=write)
        choices = self._choices(db, parent)
        choice = choices.get(clan_id)
        qualifications, members = self._qualifications(db, parent, as_utc(now), persist=write)
        qualification = qualifications.get(str(clan_id))
        initial = self._initial(parent, clan_id)
        eligible = bool(initial)
        if not initial and qualification:
            current = {(m['user_id'], m['uuid']) for m in members.get(clan_id, [])}
            eligible = all((m['user_id'], m['uuid']) in current for m in qualification['selected_four'])
        lands = db.query(Territory).filter_by(is_playable=True).order_by(Territory.id).populate_existing().all()
        resolved = {key for key, value in choices.items() if value.lands_chosen_at is not None}
        active = {c.id for c in db.query(Clan).filter_by(is_deleted=False, is_admin_clan=False)}
        resolved.update(owner for owner in parent.initial_owners.values() if owner not in active)
        virtual = selection_world(CycleStartupService._world(lands), parent.initial_owners, resolved)
        return parent, clan, user, choice, initial, qualification, eligible, lands, virtual

    def read(self, db, *, clan_id, actor_id, now):
        parent, clan, user, choice, initial, qualification, eligible, lands, virtual = self._context(db, clan_id=clan_id, actor_id=actor_id, now=now)
        head = clan.leader_id == actor_id
        ready = head and user.onboarding_completed_at is not None
        chosen = bool(choice and choice.lands_chosen_at)
        owners = {t.id: t.owner_clan_id for t in virtual}
        return dict(open=True, preparation_id=parent.source_season_id, clan_id=clan_id, clan_name=clan.name,
            revision=choice.revision if choice else 1, is_head=head,
            can_choose_lands=bool(ready and eligible and not chosen), can_choose_relics=bool(ready and not (choice and choice.relics_chosen_at)),
            land_status='claimed' if chosen else 'pending' if eligible else 'ineligible',
            selected_lands=list(choice.selected_lands) if choice else [], selected_relics=list(choice.selected_relics) if choice else [],
            initial_owned=initial, eligibility='retention' if initial else 'gift' if qualification else None,
            slot=qualification['slot'] if qualification else None,
            treasury={k: str(getattr(START_RESOURCES, k)) for k in RESOURCE_NAMES},
            relics=[dict(key=k, name=r.name, effect=r.effect, effects=[str(v) for v in r.effects]) for k, r in RELICS.items()],
            territories=[dict(id=t.id, name=t.name, region=t.region, owner_clan_id=t.owner_clan_id,
                selection_owner_clan_id=owners[t.id], has_port=bool(t.has_port), fortress=t.is_great_stronghold,
                neighbours=list(t.adjacent_territory_ids or [])) for t in lands])

    def preview(self, db, *, clan_id, actor_id, selected, now):
        _, _, _, choice, initial, _, eligible, _, virtual = self._context(db, clan_id=clan_id, actor_id=actor_id, now=now, write=False)
        self._actor(db, clan_id, actor_id, write=True)
        if not eligible or (choice and choice.lands_chosen_at):
            raise ValueError('Выбор земель уже подтверждён или недоступен этому клану')
        chosen = self._validate(selected, clan_id=clan_id, initial=initial, virtual=virtual)
        return dict(selected=list(chosen), release=sorted(set(initial) - set(chosen)))

    def _claim(self, db, *, clan_id, actor_id, selected, expected_revision, now, relics):
        if not isinstance(selected, (list, tuple)) or len(selected) != (2 if relics else 3) or len(set(selected)) != len(selected):
            raise ValueError('Выберите две разные реликвии или три разные земли')
        if not relics and any(type(i) is not int for i in selected):
            raise ValueError('Нужны числовые идентификаторы земель')
        selected = sorted(selected)
        with CycleEconomyStore._atomic(db):
            parent, _, _, choice, initial, _, eligible, lands, virtual = self._context(db, clan_id=clan_id,
                actor_id=actor_id, now=now, lock=True, write=True)
            field, date_field = ('selected_relics', 'relics_chosen_at') if relics else ('selected_lands', 'lands_chosen_at')
            if choice and getattr(choice, date_field) is not None:
                if getattr(choice, field) != selected:
                    raise ValueError('Подтверждённый стартовый выбор нельзя изменить')
                return self.read(db, clan_id=clan_id, actor_id=actor_id, now=now)
            if type(expected_revision) is not int or expected_revision != (choice.revision if choice else 1):
                raise ValueError('Выбор изменился: обновите страницу')
            if relics:
                starting_relics(selected)
            else:
                if not eligible:
                    raise ValueError('Клан пока не получил право на стартовые земли')
                self._validate(selected, clan_id=clan_id, initial=initial, virtual=virtual)
                for land in lands:
                    if land.id in selected:
                        CycleStartupService._transfer(db, land, clan_id, as_utc(now), 'preseason_claim', SimpleNamespace(starts_at=parent.opened_at))
                        land.status = 'active'
            if choice is None:
                choice = CampaignPreseasonChoice(preparation_id=parent.source_season_id, clan_id=clan_id,
                    selected_lands=[], selected_relics=[], revision=1)
                db.add(choice)
            setattr(choice, field, selected)
            setattr(choice, date_field, as_utc(now))
            choice.revision += 1
            db.flush()
            return self.read(db, clan_id=clan_id, actor_id=actor_id, now=now)

    def claim_lands(self, db, **kwargs):
        return self._claim(db, relics=False, **kwargs)

    def claim_relics(self, db, **kwargs):
        return self._claim(db, relics=True, **kwargs)

    def import_into(self, db, *, parent, season, cycle):
        """Вызывается только внутри атомарного ручного запуска сезона."""
        from app.models.cycle_startup import CycleStartup, CycleStartupClan, CycleStartupIdentity
        startup = db.get(CycleStartup, season.id)
        startup.initial_owners = dict(parent.initial_owners)
        rows = CycleStartupService._rows(db, season.id)
        choices = self._choices(db, parent)
        clans = {c.id: c for c in db.query(Clan)}
        for clan_id, clan in clans.items():
            initial = self._initial(parent, clan_id)
            qualification = (parent.qualifications or {}).get(str(clan_id))
            choice = choices.get(clan_id)
            if not initial and not qualification and not (choice and choice.lands_chosen_at):
                continue
            row = rows.get(clan_id)
            if row is None:
                row = CycleStartupClan(season_id=season.id, clan_id=clan_id)
                db.add(row)
            row.initial_owned = initial
            if qualification:
                row.slot = qualification['slot']
                row.qualified_at = datetime.fromisoformat(qualification['qualified_at'])
                row.selected_four = qualification['selected_four']
                for member in row.selected_four:
                    db.add(CycleStartupIdentity(season_id=season.id, clan_id=clan_id, source=member['source'], external_uuid=member['uuid']))
            if choice and choice.lands_chosen_at and not clan.is_deleted:
                row.selected_lands = list(choice.selected_lands)
                row.status, row.claimed_at = 'claimed', season.starts_at
        for clan_id, choice in choices.items():
            if choice.relics_chosen_at and clan_id in clans and not clans[clan_id].is_deleted and not clans[clan_id].is_admin_clan:
                wallet = CycleEconomyStore().ensure_state(db, season_id=season.id, clan_id=clan_id)
                wallet.relics = starting_relics(choice.selected_relics)
                wallet.starters_chosen = True
        parent.status, parent.launched_season_id = 'launched', season.id
        db.flush()
