# Импорт всех моделей для создания таблиц
from app.models.user import User
from app.models.role import Role
from app.models.clan import (
    Clan,
    ClanMember,
    ClanMembershipPeriod,
    ClanInvite,
    ClanApplication,
)
from app.models.territory import (
    Territory,
    TerritoryAttackingClans,
    TerritoryDefendingClans,
    TerritoryOwnershipHistory,
)
from app.models.war import (
    ClanWar,
    ClanWarParticipant,
    ClanWarMatchResult,
    ClanTimeout,
)
from app.models.clan_warfare import ClanAttackPointSpend, ClanLevelEvent
from app.models.war_deployment import WarDeployment, WarDeploymentMember
from app.models.shop import ShopItem, UserItem
from app.models.achievement import Achievement, UserAchievement
from app.models.match import Match, MatchParticipant
from app.models.localization import Localization
from app.models.quest import Quest, UserQuest, QuestType, QuestCategory
from app.models.clan_asset import ClanAsset, ClanOwnedAsset
from app.models.operation import ResourceLedgerEntry, AdminAuditLog
from app.models.worker import WorkerHeartbeat
from app.models.external_identity import ExternalPlayerIdentity, ExternalPlayerAlias
from app.models.campaign import (
    CampaignRuleSet,
    CampaignSettings,
    ReplaySyncState,
    CampaignSeason,
    CampaignSeasonClanResult,
)
from app.models.season_archive import CampaignSeasonArchive
from app.models.campaign_cycle import CampaignCycleRecord, CampaignCyclePlan, CampaignCyclePlanRevision, CycleScoutRequest
from app.models.cycle_battle import CycleTerritoryBattle, CycleMatchContribution, CycleScoreAdjustment, CycleOwnershipCorrection, CycleLateReplayDecision
from app.models.cycle_economy import CycleEconomyState, CycleTerritoryUpgrade, CycleEconomySnapshot
from app.models.cycle_diplomacy import CycleDiplomacyPair, CycleDiplomacyProposal, CycleDiplomacyEvent
from app.models.cycle_income import CycleTerritoryProfile, CycleIncomeAccrual
from app.models.cycle_market import CycleMarketOffer, CycleMarketCaravan, CycleMarketCommand
from app.models.cycle_startup import CycleStartup, CycleStartupClan, CycleStartupIdentity
from app.models.cycle_reinforcement_state import CycleReinforcementState
from app.models.cycle_interception import CycleInterception, CycleInterceptionContribution, CycleInterceptionAdjustment, CycleInterceptionReviewCommand
from app.models.cycle_dispatch_route import CycleDispatchRoute
from app.models.cycle_arena_scan import CycleArenaScanState
from app.models.market import MarketOffer, TradeCaravan
from app.models.title import Title, UserTitle
from app.models.notification import UserNotification
from app.models.password_recovery import PasswordRecoveryToken
from app.models.diplomacy import ClanDiplomaticRelation, ClanDiplomacyEvent
from app.models.messaging import DirectConversation, DirectMessage, UserBlock, DirectMessageReport
from app.models.auth_session import OAuthLoginState, SecurityAuditEvent, UserSession
from app.models.feedback import FeedbackMessage, FeedbackTicket
from app.models.arena_match_backfill import ArenaMatchBackfillJob
from app.models.cycle_defence_template import CycleDefenceTemplate
from app.models.war_adjustment import WarScoreAdjustment

from app.models.discord import DiscordLink, DiscordLinkCode, DiscordResource, DiscordDelivery

from app.models.preseason import CampaignPreseason, CampaignPreseasonChoice, CampaignPreseasonCandidate

__all__ = [
    'CampaignPreseason', 'CampaignPreseasonChoice', 'CampaignPreseasonCandidate',
    "User",
    "Role",
    "Clan", 
    "ClanMember", 
    "ClanMembershipPeriod",
    "ClanInvite", 
    "ClanApplication",
    "Territory",
    "TerritoryAttackingClans",
    "TerritoryDefendingClans",
    "TerritoryOwnershipHistory",
    "ClanWar",
    "ClanWarParticipant",
    "ClanWarMatchResult",
    "ClanTimeout",
    "ShopItem",
    "UserItem",
    "Achievement",
    "UserAchievement",
    "Match",
    "MatchParticipant",
    "Localization",
    "Quest",
    "UserQuest",
    "QuestType",
    "QuestCategory"
    ,"ClanAsset", "ClanOwnedAsset",
    "ResourceLedgerEntry", "AdminAuditLog", "WorkerHeartbeat",
    "ExternalPlayerIdentity", "ExternalPlayerAlias",
    "CampaignRuleSet", "CampaignSettings", "ReplaySyncState", "CampaignSeason", "CampaignSeasonClanResult",
    "CampaignSeasonArchive",
    "MarketOffer", "TradeCaravan", "Title", "UserTitle",
    "ClanAttackPointSpend", "ClanLevelEvent", "WarDeployment", "WarDeploymentMember",
    "UserNotification", "PasswordRecoveryToken", "ClanDiplomaticRelation", "ClanDiplomacyEvent",
    "DirectConversation", "DirectMessage", "UserBlock", "DirectMessageReport",
    "OAuthLoginState", "UserSession", "SecurityAuditEvent",
    "FeedbackTicket", "FeedbackMessage",
    "ArenaMatchBackfillJob",
]
