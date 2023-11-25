import pytest

import frappe

from erpnext_egypt_compliance.erpnext_eta.utils import eta_round
import erpnext_egypt_compliance.erpnext_eta.einvoice_schema as einvoice_schema
from erpnext_egypt_compliance.erpnext_eta.einvoice_schema import (
    _get_item_code_and_type,
    _get_item_unit_value,
    _get_sales_and_net_totals,
    get_net_total_amount,
    Value,
)


def test_eta_round(db_transaction):
    assert eta_round(1.2345) == 1.23
    assert eta_round(1.2355) == 1.24
    assert eta_round(1.2345, 0) == 1.23
    assert eta_round(1.2355, 0) == 1.24
    assert eta_round(1.2345, 3) == 1.234
    assert eta_round(1.2355, 3) == 1.236
    assert eta_round(1.2345, 4) == 1.2345
    assert eta_round(1.2355, 4) == 1.2355


@pytest.mark.parametrize(
    "item_data, expected",
    [
        (
            {
                "eta_item_code": "123",
                "eta_code_type": "EGS",
                "eta_inherit_brand": False,
                "eta_inherit_item_group": False,
            },
            ("123", "EGS"),
        ),
        (
            {
                "eta_item_code": None,
                "eta_code_type": "EGS",
                "eta_inherit_brand": False,
                "eta_inherit_item_group": False,
            },
            ("456", "EGS"),
        ),
        (
            {
                "eta_item_code": "123",
                "eta_code_type": "EGS",
                "eta_inherit_brand": True,
                "eta_inherit_item_group": False,
            },
            ("Brand_code", "Brand_type"),
        ),
        (
            {
                "eta_item_code": "123",
                "eta_code_type": "EGS",
                "eta_inherit_brand": False,
                "eta_inherit_item_group": True,
            },
            ("Item_group_code", "Item_group_type"),
        ),
    ],
)
def test_get_item_code_and_type(monkeypatch, item_data, expected, db_transaction):
    mock_values = {
        ("ETA Settings", "ETA Settings", "eta_item_code"): "456",
        ("Brand", None, "eta_item_code"): "Brand_code",
        ("Brand", None, "eta_code_type"): "Brand_type",
        ("Item Group", None, "eta_item_code"): "Item_group_code",
        ("Item Group", None, "eta_code_type"): "Item_group_type",
    }

    def _mocked_get_value(*args, **kwargs):
        return mock_values.get(args)

    monkeypatch.setattr(frappe, "get_value", _mocked_get_value)
    assert _get_item_code_and_type(item_data) == expected


@pytest.mark.parametrize(
    "invoice_data, item_data, expected",
    [
        (
            {"currency": "USD", "_exchange_rate": 30, "_foreign_company_currency": True},
            {"net_rate": 1, "rate": 100},
            Value(currencySold="USD", amountEGP=1 * 30, amountSold=100, currencyExchangeRate=30),
        ),
        (
            {"currency": "USD", "_exchange_rate": 30, "_foreign_company_currency": False},
            {"net_rate": 1, "rate": 100},
            Value(currencySold="USD", amountEGP=1 * 30),
        ),
        (
            {"currency": "EGP", "_exchange_rate": 30, "_foreign_company_currency": True},
            {"net_rate": 4, "rate": 100},
            Value(currencySold="EGP", amountEGP=4 * 30),
        ),
        (
            {"currency": "EGP", "_exchange_rate": 30, "_foreign_company_currency": False},
            {"net_rate": 4, "rate": 100},
            Value(currencySold="EGP", amountEGP=4 * 30),
        ),
    ],
)
def test_get_item_unit_value(monkeypatch, item_data, expected, invoice_data, db_transaction):
    monkeypatch.setattr(einvoice_schema, "INVOICE_RAW_DATA", invoice_data)

    assert _get_item_unit_value(item_data) == expected


@pytest.mark.parametrize(
    "invoice_data, item_data, expected",
    [
        (
            {"_foreign_company_currency": True},
            {"base_amount": 10, "_exchange_rate": 30, "net_amount": 20},
            (10 * 30, 10 * 30),
        ),
        (
            {"_foreign_company_currency": False},
            {"base_amount": 10, "_exchange_rate": 30, "net_amount": 20},
            (20 * 30, 20 * 30),
        ),
    ],
)
def test_get_sales_and_net_totals(monkeypatch, invoice_data, item_data, expected, db_transaction):
    monkeypatch.setattr(einvoice_schema, "INVOICE_RAW_DATA", invoice_data)

    assert _get_sales_and_net_totals(item_data) == expected


@pytest.mark.parametrize(
    "invoice_data, expected",
    [
        (
            {
                "_foreign_company_currency": True,
                "base_total": 10,
                "net_total": 30,
                "base_grand_total": 20,
                "_exchange_rate": 5,
            },
            (10 * 5, 30 * 5),
        ),
        (
            {
                "_foreign_company_currency": False,
                "base_total": 10,
                "net_total": 30,
                "base_grand_total": 20,
                "_exchange_rate": 5,
            },
            (30 * 5, 20),
        ),
    ],
)
def test_get_net_total_amount(monkeypatch, invoice_data, expected, db_transaction):
    monkeypatch.setattr(einvoice_schema, "INVOICE_RAW_DATA", invoice_data)

    assert get_net_total_amount() == expected
