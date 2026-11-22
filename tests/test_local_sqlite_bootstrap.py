import importlib.util
import sqlite3
import subprocess
import sys
from pathlib import Path


def _load_bootstrap_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "bootstrap_local_sqlite.py"
    )
    assert script_path.exists()
    spec = importlib.util.spec_from_file_location("bootstrap_local_sqlite", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_local_sqlite_database_creates_current_schema(tmp_path):
    module = _load_bootstrap_module()
    database_path = tmp_path / "local.db"

    result = module.build_local_sqlite_database(database_path, seed=False)

    assert result == database_path
    with sqlite3.connect(database_path) as connection:
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
        territory_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(territories)")
        }
        clan_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(clans)")
        }
        user_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(users)")
        }
        clan_member_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(clan_members)")
        }
        deployment_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(war_deployments)")
        }
        session_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(user_sessions)")
        }
        external_identity_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(external_player_identities)"
            )
        }
        arena_backfill_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(arena_match_backfill_jobs)"
            )
        }
        session_foreign_keys = list(
            connection.execute("PRAGMA foreign_key_list(user_sessions)")
        )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert revision == "u3i4j5k6l7m8"
    assert {'campaign_preseasons', 'campaign_preseason_choices', 'campaign_preseason_candidates'} <= tables
    assert "campaign_season_archives" in tables
    assert {"cycle_defence_templates", "cycle_arena_scan_state"} <= tables
    assert {"campaign_cycles", "cycle_territory_battles", "cycle_match_contributions",
            "cycle_reinforcement_states", "cycle_economy_states", "cycle_startups",
            "cycle_ownership_corrections", "cycle_interceptions", "cycle_interception_contributions",
            "cycle_interception_review_commands", "cycle_interception_adjustments",
            "cycle_dispatch_routes", "cycle_late_replay_decisions"} <= tables
    assert {"discord_links", "discord_link_codes", "discord_resources", "discord_deliveries"} <= tables
    assert "war_score_adjustments" in tables
    assert not {"petitions", "petition_votes", "petition_comments", "petition_reactions"} & tables
    assert "display_name" in user_columns
    assert "is_impersonation" in session_columns
    assert "current_nickname_key" in external_identity_columns
    assert {
        "identity_id",
        "status",
        "attempts",
        "next_attempt_at",
        "scanned_count",
        "imported_count",
    }.issubset(arena_backfill_columns)
    assert any(
        row[3] == "impersonated_by_user_id"
        and row[2] == "users"
        and row[6] == "CASCADE"
        for row in session_foreign_keys
    )
    assert "map_emblem_url" in clan_columns
    assert "relic_loadout_locked_until" in clan_columns
    assert {"is_recruiting", "is_deleted", "deleted_at"}.issubset(clan_columns)
    assert "is_warlord" in clan_member_columns
    assert {"warlord_user_id", "warlord_username_snapshot"}.issubset(
        deployment_columns
    )
    assert {
        "port_level",
        "fleet_level",
        "influence_value",
        "required_influence",
        "resource_income_ready_at",
        "last_resource_payout_at",
    }.issubset(territory_columns)
    assert {
        "campaign_rule_sets",
        "clan_war_match_results",
        "user_notifications",
        "password_recovery_tokens",
        "clan_diplomatic_relations",
        "clan_diplomacy_events",
        "direct_conversations",
        "direct_messages",
        "user_blocks",
        "direct_message_reports",
        "feedback_tickets",
        "feedback_messages",
        "arena_match_backfill_jobs",
    }.issubset(tables)


def test_bootstrap_script_can_run_directly_from_project_root():
    project_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts" / "bootstrap_local_sqlite.py"),
            "--help",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--rebuild" in result.stdout
