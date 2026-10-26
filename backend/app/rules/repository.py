"""Loads irdai_rules.json and picks the version of a rule in force on a given date."""

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel

RULES_FILE = Path(__file__).with_name("irdai_rules.json")


class RuleSource(BaseModel):
    name: str
    reference: str
    url: str
    also: str | None = None


class Rule(BaseModel):
    id: str
    group: str
    title: str
    plain: str
    effective_from: date | None = None
    effective_to: date | None = None
    status: str
    date_note: str | None = None
    source: RuleSource
    months: int | None = None
    amount: float | None = None

    def in_force_on(self, on: date) -> bool:
        if self.effective_from and on < self.effective_from:
            return False
        if self.effective_to and on > self.effective_to:
            return False
        return True


@lru_cache(maxsize=1)
def _load() -> tuple[Rule, ...]:
    raw: dict[str, Any] = json.loads(RULES_FILE.read_text(encoding="utf-8"))
    return tuple(Rule(**r) for r in raw["rules"])


def all_rules() -> list[Rule]:
    return list(_load())


def get_rule(rule_id: str) -> Rule:
    for rule in _load():
        if rule.id == rule_id:
            return rule
    raise KeyError(rule_id)


def rule_for(group: str, on: date | None = None) -> Rule | None:
    """The version of a rule group in force on `on` (today if not given)."""
    on = on or date.today()
    for rule in _load():
        if rule.group == group and rule.in_force_on(on):
            return rule
    return None
