from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any


def serialize_simulation_json(
    result: dict[str, Any],
    *,
    calculation_date: date | None = None,
) -> str:
    payload = {
        **result,
        "calculation_date": (calculation_date or date.today()).isoformat(),
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    ) + "\n"


def render_simulation_markdown(
    result: dict[str, Any],
    *,
    calculation_date: date | None = None,
) -> str:
    calculated_on = (calculation_date or date.today()).isoformat()
    lines = [
        f"# Баланс кампании: правила v{result['rule_set']['version']}",
        "",
        f"Дата расчёта: {calculated_on}",
        f"Горизонт: {result['horizon_days']} суток",
        f"Формат отчёта: v{result['report_format_version']}",
        f"Игровых территорий: {len(result['inputs']['territories'])}",
        f"Доступных реликвий: {len(result['inputs']['relics'])}",
        "",
        "## Краткий вывод",
        "",
    ]
    if result["signals"]:
        lines.append(
            f"Симулятор обнаружил {len(result['signals'])} потенциальных отклонений. "
            "Они не изменяют активные правила автоматически."
        )
    else:
        lines.append("Автоматические пороги не выявили критичных отклонений.")

    lines.extend([
        "",
        "## Сравнение сценариев",
        "",
        "| Профиль | Темп | Стратегия | День | Золото | Железо | Дерево | Еда | Мифрил | Земли | Влияние | Развитие | Реликвии |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for scenario in result["scenarios"]:
        for checkpoint in result["checkpoints"]:
            snapshot = scenario["checkpoints"].get(str(checkpoint))
            if snapshot is None:
                continue
            resources = snapshot["resources"]
            lines.append(
                "| {profile} | {pace} | {strategy} | {day} | {gold:g} | {iron:g} | "
                "{wood:g} | {food:g} | {mithril:g} | {territories} | {influence} | "
                "{development} | {relics} |".format(
                    profile=scenario["profile"],
                    pace=scenario["pace"],
                    strategy=scenario["strategy"],
                    day=checkpoint,
                    gold=resources["gold"],
                    iron=resources["iron"],
                    wood=resources["wood"],
                    food=resources["food"],
                    mithril=resources["mithril"],
                    territories=snapshot["territory_count"],
                    influence=snapshot["influence"],
                    development=snapshot["total_development_levels"],
                    relics=snapshot["relic_levels"],
                )
            )

    lines.extend(["", "## Узкие места ресурсов", ""])
    bottlenecks = [
        signal for signal in result["signals"] if signal["code"] == "resource_bottleneck"
    ]
    if bottlenecks:
        for signal in bottlenecks:
            lines.append(f"- `{signal['scenario_id']}`: {signal['detail']}")
    else:
        lines.append("- Ни один ресурс не превысил порог 60% времени ожидания.")

    lines.extend(["", "## Доступность улучшений и реликвий", ""])
    for scenario in result["scenarios"]:
        purchases = scenario["purchases"]
        first_upgrade = next(
            (row for row in purchases if not row["goal"].startswith("relic:")),
            None,
        )
        first_relic = next(
            (row for row in purchases if row["goal"].startswith("relic:")),
            None,
        )
        lines.append(
            f"- `{scenario['id']}`: первое улучшение — "
            f"{_day_label(first_upgrade)}; первая реликвия — {_day_label(first_relic)}."
        )

    lines.extend(["", "## Великие крепости", ""])
    for scenario in result["scenarios"]:
        accessible = [
            row for row in scenario["great_strongholds"] if row["both_day"] is not None
        ]
        first = min(accessible, key=lambda row: float(row["both_day"])) if accessible else None
        if first:
            lines.append(
                f"- `{scenario['id']}`: первая числовая доступность — "
                f"{first['territory_name']} на {float(first['both_day']):g}-й день."
            )
        else:
            lines.append(f"- `{scenario['id']}`: числовая доступность не достигнута.")

    lines.extend(["", "## Диагностика рынка", ""])
    market_rows = [
        (scenario["id"], scenario["market_diagnostic"])
        for scenario in result["scenarios"]
        if scenario["market_diagnostic"]
    ]
    if market_rows:
        for scenario_id, diagnostic in market_rows:
            route_summary = ", ".join(
                f"{route['mode']} {route['steps']} шаг.: {route['gold_cost']} зол., {route['eta_hours']} ч."
                for route in diagnostic["routes"]
            )
            lines.append(
                f"- `{scenario_id}`: не хватает {diagnostic['amount']} "
                f"{diagnostic['missing_resource']}; {route_summary}."
            )
    else:
        lines.append("- На финальных целях нет диагностируемого дефицита для обмена.")

    lines.extend(["", "## Автоматические сигналы", ""])
    if result["signals"]:
        lines.extend(
            f"- **{signal['code']}** (`{signal['scenario_id']}`): {signal['detail']}"
            for signal in result["signals"]
        )
    else:
        lines.append("- Сигналов нет.")

    lines.extend(["", "## Рекомендации", ""])
    if result["recommendations"]:
        for recommendation in result["recommendations"]:
            proposed = (
                recommendation["proposed_value"]
                if recommendation["proposed_value"] is not None
                else "требует ручного выбора после beta"
            )
            lines.append(
                f"- `{recommendation['parameter']}`: текущее значение "
                f"`{recommendation['current_value']}`, предлагаемая гипотеза `{proposed}`. "
                f"{recommendation['recommendation']}"
            )
    else:
        lines.append("- Изменение числовых правил до закрытой beta не требуется.")

    lines.extend(["", "## Ограничения достоверности", ""])
    lines.extend(f"- {item}" for item in result["limitations"])
    lines.append("")
    return "\n".join(lines)


def _day_label(purchase: dict[str, Any] | None) -> str:
    return f"день {float(purchase['day']):g}" if purchase else "не достигнута"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def write_simulation_reports(
    result: dict[str, Any],
    output_dir: Path,
    *,
    json_only: bool = False,
    calculation_date: date | None = None,
) -> tuple[Path, Path | None]:
    calculated_on = calculation_date or date.today()
    stem = (
        f"balance-v{result['rule_set']['version']}-"
        f"{calculated_on.isoformat()}-{result['horizon_days']}d"
    )
    json_path = Path(output_dir) / f"{stem}.json"
    markdown_path = None if json_only else Path(output_dir) / f"{stem}.md"

    json_content = serialize_simulation_json(
        result,
        calculation_date=calculated_on,
    )
    markdown_content = (
        None
        if json_only
        else render_simulation_markdown(result, calculation_date=calculated_on)
    )
    _atomic_write(json_path, json_content)
    if markdown_path is not None and markdown_content is not None:
        _atomic_write(markdown_path, markdown_content)
    return json_path, markdown_path
