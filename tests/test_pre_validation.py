import frappe

from erpnext_egypt_compliance.erpnext_eta import pre_validation


def _invoice_stub():
    return frappe._dict(name="SINV-PREVAL-TEST", pos_profile=None, posting_date="2026-01-01")


def test_missing_connector_does_not_block_submission(db_transaction, monkeypatch):
    """A company with no default ETA Connector must not block Sales Invoice submit.

    `validate_eta_before_submit` is wired to Sales Invoice `before_submit`, so a
    throw here rejects *every* sales invoice on the site — including sites that
    have not configured e-invoicing yet, and sites that never will. The
    `if not connector: return` guard immediately below the lookup already encodes
    the intended behaviour; the lookup just defaulted to `throw_if_no_connector=True`,
    making that guard unreachable.
    """
    monkeypatch.setattr(frappe, "get_value", lambda *args, **kwargs: None)
    seen = {}

    def lookup(company, throw_if_no_connector=True):
        seen["throw_if_no_connector"] = throw_if_no_connector
        return None

    monkeypatch.setattr(pre_validation, "get_company_eta_connector", lookup)

    # Must return quietly rather than raising "No Default Connector Set."
    pre_validation.validate_eta_before_submit(_invoice_stub())

    assert seen["throw_if_no_connector"] is False


def test_existing_connector_still_runs_validation(db_transaction, monkeypatch):
    """The happy path is unchanged: a configured connector still validates.

    Pairs with the test above so the fix cannot degrade into "always skip" — that
    would silence real ETA master-data errors instead of surfacing them.
    """
    monkeypatch.setattr(frappe, "get_value", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pre_validation,
        "get_company_eta_connector",
        lambda *args, **kwargs: frappe._dict(signature_start_date=None),
    )
    validated = {}
    monkeypatch.setattr(
        pre_validation,
        "get_invoice_asjson",
        lambda name, as_dict=False: validated.setdefault("name", name),
    )

    pre_validation.validate_eta_before_submit(_invoice_stub())

    assert validated["name"] == "SINV-PREVAL-TEST"
