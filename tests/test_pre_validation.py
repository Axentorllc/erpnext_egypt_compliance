import frappe
import pytest
from pydantic import BaseModel

import erpnext_egypt_compliance.erpnext_eta.pre_validation as pre_validation


def _patch_company(monkeypatch):
    # company lookup + custom_enable_ereceipt (off)
    monkeypatch.setattr(
        frappe,
        "get_value",
        lambda doctype, *args, **kwargs: "Test Co" if doctype == "Sales Invoice" else 0,
    )


def test_no_connector_submits(monkeypatch):
    _patch_company(monkeypatch)
    monkeypatch.setattr(frappe, "get_list", lambda *args, **kwargs: [])

    def fail(*args, **kwargs):
        raise AssertionError("ETA validation must not run without a connector")

    monkeypatch.setattr(pre_validation, "get_invoice_asjson", fail)

    pre_validation.validate_eta_before_submit(
        frappe._dict(name="SINV-0001", posting_date="2026-10-13")
    )


def test_connector_runs_validation(monkeypatch):
    _patch_company(monkeypatch)
    monkeypatch.setattr(
        pre_validation,
        "get_company_eta_connector",
        lambda *args, **kwargs: frappe._dict(signature_start_date=None),
    )

    class _Model(BaseModel):
        x: int

    def invalid(*args, **kwargs):
        _Model(x="not-an-int")

    monkeypatch.setattr(pre_validation, "get_invoice_asjson", invalid)
    monkeypatch.setattr(pre_validation, "parse_pydantic_errors", lambda e: ["x"])

    def throw(msg, *args, **kwargs):
        raise frappe.ValidationError(msg)

    monkeypatch.setattr(frappe, "throw", throw)

    with pytest.raises(frappe.ValidationError):
        pre_validation.validate_eta_before_submit(
            frappe._dict(name="SINV-0002", posting_date="2026-10-13")
        )
