"""Offline (no key, no servers): the dataset is a well-formed contract."""

from validate import validate


def test_dataset_is_valid():
    _cases, errors, _warnings = validate()
    assert not errors, "\n".join(errors)


def test_known_and_blocked_cases_are_not_silently_promoted():
    cases, _errors, warnings = validate()
    promotions = [w for w in warnings if "promote this case" in w]
    assert not promotions, "\n".join(promotions)


def test_every_critical_category_has_cases():
    cases, _e, _w = validate()
    crit = {c.category.value for c in cases if c.critical}
    assert {"refund_gate", "safety", "refund_domain", "triage_routing"} <= crit
