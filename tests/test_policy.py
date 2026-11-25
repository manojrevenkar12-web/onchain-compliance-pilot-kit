import pytest

from ocp import config
from ocp.kit.policy import DiscoveryError, compile_policy, vendor_default


def disc(**ra: object) -> dict[str, object]:
    base = {"prohibited": ["sanctions", "ransomware", "darknet_market"], "high_risk": ["mixer"], "restricted": ["gambling"], "max_indirect_hops": 3}
    return {"name": "x", "risk_appetite": {**base, **ra}, "travel_rule": {"unhosted_threshold_eur": 1000}}


def test_compiles_readable_rules() -> None:
    p = compile_policy(disc(), config.kit())
    names = [r["rule"] for r in p.rules()]
    assert names[:4] == ["prohibited-direct", "prohibited-indirect", "high-risk-direct", "high-risk-indirect"]
    assert {"structuring-7d", "escalating-payments", "pass-through", "rescreen"} <= set(names)


def test_refuses_unknown_and_contradictory_categories() -> None:
    with pytest.raises(DiscoveryError, match="unknown"):
        compile_policy(disc(high_risk=["casino"]), config.kit())
    with pytest.raises(DiscoveryError, match="both"):
        compile_policy(disc(high_risk=["sanctions"]), config.kit())
    with pytest.raises(DiscoveryError, match="hops"):
        compile_policy(disc(max_indirect_hops=0), config.kit())


def test_a_missing_severe_category_is_added_and_flagged() -> None:
    p = compile_policy(disc(prohibited=["sanctions"]), config.kit())
    assert "ransomware" in p.prohibited and any("ransomware" in n for n in p.notes)


def test_vendor_default_has_no_behaviour_and_alerts_restricted_directly() -> None:
    v = vendor_default(disc())
    assert not v.behavioral and v.rescreen_days == 0
    assert any(r["rule"] == "restricted-direct" for r in v.rules())


def test_every_prospect_file_compiles() -> None:
    for name in config.prospect_names() + config.prospect_names("heldout"):
        assert compile_policy(config.prospect(name), config.kit()).rules()
