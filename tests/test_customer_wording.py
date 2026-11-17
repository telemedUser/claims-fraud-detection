from app.api import customer_view as jobs


def test_check_outcomes_use_allowed_labels():
    assert jobs.check_outcome('provider_profile', 0) == 'simulated'
    assert jobs.check_outcome('invoice_check', 5) == 'no_issues'
    assert jobs.check_outcome('invoice_check', 80) == 'unavailable'


def test_outcome_text_has_no_verified_wording():
    text = str(jobs.OUTCOMES).lower()
    assert 'verified' not in text and 'passed all' not in text
    assert not hasattr(jobs, 'VERIFIED_BELOW')

