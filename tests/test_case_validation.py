def test_case_spec():
    from scripts.validate_cases import CASES
    assert len(CASES)==10 and sum(len(x[5]) for x in CASES)==90
