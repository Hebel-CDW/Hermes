from shared.taxonomy import load_taxonomy


def test_skill_by_id_and_match():
    tax = load_taxonomy()
    skill = tax.skill_by_id("container_orchestration")
    assert skill is not None
    assert tax.skill_by_id("nope") is None
    assert "container_orchestration" in tax.match_keywords("helm on kubernetes")
