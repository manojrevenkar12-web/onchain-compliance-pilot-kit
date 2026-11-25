import numpy as np

from ocp.world.world import build_site


def test_same_luck_for_every_build() -> None:
    a, b = build_site(3, "ch-bank"), build_site(3, "ch-bank")
    assert np.array_equal(a.book.amount, b.book.amount) and np.array_equal(a.bad, b.bad)
    assert a.book.known_cases == b.book.known_cases


def test_reportable_customers_have_scheme_transfers_and_known_cases_are_a_subset() -> None:
    s = build_site(4, "uk-emi")
    rep = s.reportable_in(0, s.book.calibration_hours)
    assert s.book.known_cases <= rep and len(s.book.known_cases) < len(rep)
    for c in rep:
        assert s.ctype[c] in s.reportable_types


def test_screening_hides_what_is_not_yet_attributed() -> None:
    s = build_site(5, "de-casp")
    d_now, *_ = s.screening.at(s.book.hour)
    d_late, *_ = s.screening.at(s.book.hour + 10_000)
    assert (d_now >= 0).sum() < (d_late >= 0).sum()
    assert ((d_now >= 0) <= (d_late >= 0)).all()  # knowledge only grows
