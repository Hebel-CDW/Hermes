from shared.taxonomy import load_taxonomy, validate_taxonomy_completeness


def test_taxonomy_complete():
    tax = load_taxonomy()
    errors = validate_taxonomy_completeness(tax)
    assert errors == []
    assert len(tax.all_skills()) >= 5
