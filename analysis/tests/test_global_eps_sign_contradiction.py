from global_markets.models import GlobalCompany
from global_markets.service import _derive_metrics


def _co(eps, net_income, pe=None):
    return GlobalCompany(country="SE", exchange="XSTO", mic_code="XSTO", currency="SEK", ticker="VOLCAR.B",
                         name="Volvo Cars", price=25.0, reporting_currency="SEK", eps=eps,
                         net_income=net_income, pe=pe)


def test_positive_eps_with_net_loss_suppresses_eps_and_pe():
    out = _derive_metrics(_co(0.06, -2_968e6, pe=241.0))
    assert out.eps is None and out.pe is None
    assert any(d.startswith("eps_withheld:sign_contradicts_net_income") for d in out.raw_provider_fields["derived_metrics"])


def test_negative_eps_with_net_profit_is_not_flipped():
    out = _derive_metrics(_co(-0.5, 1e9))
    assert out.eps is None and out.pe is None


def test_consistent_signs_still_derive_pe():
    out = _derive_metrics(_co(2.0, 1e9))
    assert out.eps == 2.0 and out.pe == 12.5


def test_missing_net_income_leaves_eps_alone():
    out = _derive_metrics(_co(2.0, None))
    assert out.pe == 12.5
