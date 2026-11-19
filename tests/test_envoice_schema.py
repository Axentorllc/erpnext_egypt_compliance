import pytest

import frappe

from erpnext_egypt_compliance.erpnext_eta.utils import eta_round
import erpnext_egypt_compliance.erpnext_eta.einvoice_schema as einvoice_schema
from erpnext_egypt_compliance.erpnext_eta.einvoice_schema import (
    Discount,
    ReceiverAddress,
    _get_item_code_and_type,
    _get_item_unit_value,
    _get_sales_and_net_totals,
    _resolve_show_discount,
    get_net_total_amount,
    get_receiver,
    Value,
)


class _FakeDoc(dict):
    """Minimal stand-in for a frappe Document: supports both attribute and dict-style access."""

    def __getattr__(self, name):
        return self.get(name)

    def as_dict(self):
        return dict(self)


def test_eta_round(db_transaction):
    assert eta_round(1.2345) == 1.23
    assert eta_round(1.2355) == 1.24
    assert eta_round(1.2345, 0) == 1.23
    assert eta_round(1.2355) == 1.24
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
        # EGP invoice, item has a price list rate (discount case) — amountEGP must be pre-discount
        (
            {"currency": "EGP"},
            {"net_rate": 90.0, "base_price_list_rate": 100.0},
            Value(currencySold="EGP", amountEGP=100.0),
        ),
        # EGP invoice, no price list rate (manual price entry, no discount) — falls back to net_rate
        (
            {"currency": "EGP"},
            {"net_rate": 100.0, "base_price_list_rate": 0.0},
            Value(currencySold="EGP", amountEGP=100.0),
        ),
        # Foreign currency invoice, item has a price list rate — amountEGP uses base_price_list_rate
        (
            {"currency": "USD", "conversion_rate": 30.0},
            {"net_rate": 3.0, "rate": 3.0, "price_list_rate": 3.5, "base_price_list_rate": 105.0},
            Value(currencySold="USD", amountEGP=105.0, amountSold=3.5, currencyExchangeRate=30.0),
        ),
        # Foreign currency invoice, no price list rate — falls back to net_rate * conversion_rate
        (
            {"currency": "USD", "conversion_rate": 30.0},
            {"net_rate": 3.0, "rate": 3.0, "price_list_rate": 0.0, "base_price_list_rate": 0.0},
            Value(currencySold="USD", amountEGP=90.0, amountSold=3.0, currencyExchangeRate=30.0),
        ),
    ],
)
def test_get_item_unit_value(monkeypatch, item_data, expected, invoice_data):
    monkeypatch.setattr(einvoice_schema, "INVOICE_RAW_DATA", invoice_data)
    assert _get_item_unit_value(item_data) == expected


@pytest.mark.parametrize(
    "invoice_data, item_data, expected",
    [
        # EGP invoice, item has a discount — salesTotal (pre-discount) != netTotal (post-discount)
        (
            {"currency": "EGP"},
            {"base_amount": 90.0, "net_amount": 90.0, "qty": 1.0, "base_price_list_rate": 100.0},
            (100.0, 90.0),
        ),
        # EGP invoice, no price list rate — salesTotal falls back to netTotal (no discount)
        (
            {"currency": "EGP"},
            {"base_amount": 100.0, "net_amount": 100.0, "qty": 1.0, "base_price_list_rate": 0.0},
            (100.0, 100.0),
        ),
        # Foreign currency invoice, item has a discount
        (
            {"currency": "USD", "conversion_rate": 30.0},
            {"base_amount": 2700.0, "net_amount": 90.0, "qty": 1.0, "base_price_list_rate": 3300.0},
            (3300.0, 2700.0),
        ),
        # Foreign currency invoice, no price list rate — falls back to net_amount * conversion_rate
        (
            {"currency": "USD", "conversion_rate": 30.0},
            {"base_amount": 3000.0, "net_amount": 100.0, "qty": 1.0, "base_price_list_rate": 0.0},
            (3000.0, 3000.0),
        ),
    ],
)
def test_get_sales_and_net_totals(monkeypatch, invoice_data, item_data, expected):
    monkeypatch.setattr(einvoice_schema, "INVOICE_RAW_DATA", invoice_data)
    assert _get_sales_and_net_totals(item_data) == expected


def test_discount_object_construction():
    """Discount object is built from the salesTotal/netTotal split, not from discount_percentage."""
    # item with 20% discount: list price 100, sold at 80
    sales_total = 100.0
    net_total = 80.0
    discount_amt = eta_round(sales_total - net_total)
    discount_rate = round(discount_amt / sales_total * 100, 5)
    item_discount = [Discount(rate=discount_rate, amount=discount_amt)] if discount_amt > 0 else None

    assert item_discount is not None
    assert len(item_discount) == 1
    assert item_discount[0].amount == 20.0
    assert item_discount[0].rate == 20.0

    # item with no discount: salesTotal == netTotal → discount is None (absent from JSON)
    sales_total = 100.0
    net_total = 100.0
    discount_amt = eta_round(sales_total - net_total)
    item_discount = [Discount(rate=round(discount_amt / sales_total * 100, 5), amount=discount_amt)] if discount_amt > 0 else None

    assert item_discount is None


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


@pytest.mark.parametrize(
    "invoice_data, item_data, expected",
    [
        # EGP invoice with a price list rate, but discount OFF — salesTotal collapses to netTotal
        (
            {"currency": "EGP"},
            {"base_amount": 90.0, "net_amount": 90.0, "qty": 1.0, "base_price_list_rate": 100.0},
            (90.0, 90.0),
        ),
        # Foreign currency invoice with a price list rate, discount OFF — salesTotal collapses to netTotal
        (
            {"currency": "USD", "conversion_rate": 30.0},
            {"base_amount": 2700.0, "net_amount": 90.0, "qty": 1.0, "base_price_list_rate": 3300.0},
            (2700.0, 2700.0),
        ),
    ],
)
def test_get_sales_and_net_totals_discount_off(monkeypatch, invoice_data, item_data, expected):
    """When SHOW_DISCOUNT is False, salesTotal == netTotal regardless of the price list rate."""
    monkeypatch.setattr(einvoice_schema, "INVOICE_RAW_DATA", invoice_data)
    monkeypatch.setattr(einvoice_schema, "SHOW_DISCOUNT", False)
    assert _get_sales_and_net_totals(item_data) == expected


@pytest.mark.parametrize(
    "invoice_data, item_data, expected",
    [
        # EGP invoice, discount OFF — amountEGP falls back to net_rate even though a price list rate exists
        (
            {"currency": "EGP"},
            {"net_rate": 90.0, "base_price_list_rate": 100.0},
            Value(currencySold="EGP", amountEGP=90.0),
        ),
        # Foreign currency invoice, discount OFF — amountEGP uses net_rate * rate, amountSold uses rate
        (
            {"currency": "USD", "conversion_rate": 30.0},
            {"net_rate": 3.0, "rate": 3.0, "price_list_rate": 3.5, "base_price_list_rate": 105.0},
            Value(currencySold="USD", amountEGP=90.0, amountSold=3.0, currencyExchangeRate=30.0),
        ),
    ],
)
def test_get_item_unit_value_discount_off(monkeypatch, invoice_data, item_data, expected):
    """When SHOW_DISCOUNT is False, the price list rate is ignored (net_rate / rate used instead)."""
    monkeypatch.setattr(einvoice_schema, "INVOICE_RAW_DATA", invoice_data)
    monkeypatch.setattr(einvoice_schema, "SHOW_DISCOUNT", False)
    assert _get_item_unit_value(item_data) == expected


@pytest.mark.parametrize(
    "company_flag, price_list_flag, selling_price_list, expected",
    [
        # Company ON, price list OFF → company default applies → shown
        (1, 0, "Wholesale", True),
        # Company OFF, price list ON → price list override turns it on
        (0, 1, "Retail", True),
        # Company OFF, price list OFF → not shown
        (0, 0, "Wholesale", False),
        # Company ON, price list ON → shown
        (1, 1, "Retail", True),
        # Company ON, invoice has no selling price list → company default applies → shown
        (1, 0, None, True),
        # Company OFF, invoice has no selling price list → not shown
        (0, 0, None, False),
    ],
)
def test_resolve_show_discount(monkeypatch, company_flag, price_list_flag, selling_price_list, expected):
    """show = company OR price_list; a missing selling price list falls back to the Company flag."""
    monkeypatch.setattr(frappe, "get_value", lambda *args, **kwargs: price_list_flag)
    company_data = {"show_discount_on_tax_invoice": company_flag}
    assert _resolve_show_discount(company_data, selling_price_list) is expected


def _mock_customer(**overrides):
    customer = {
        "name": "Cust A",
        "customer_name": "Cust A",
        "eta_receiver_type": "B",
        "tax_id": "123456789",
        "customer_primary_address": None,
    }
    customer.update(overrides)
    return customer


def test_get_receiver_without_primary_address_uses_placeholder(monkeypatch):
    """Customer with no primary address must not crash — falls back to the placeholder address."""
    monkeypatch.setattr(einvoice_schema, "INVOICE_RAW_DATA", {"customer": "Cust A"})
    monkeypatch.setattr(frappe, "get_doc", lambda doctype, name=None: _FakeDoc(_mock_customer()))

    receiver = get_receiver()

    assert receiver.address == ReceiverAddress(
        country="EG", governate="Egypt", regionCity="EG City", street="Street 1", buildingNumber="B0"
    )


def test_get_receiver_falls_back_to_city_when_state_missing(monkeypatch):
    """governate/regionCity must never be None even when the Address doctype's state is blank."""
    monkeypatch.setattr(einvoice_schema, "INVOICE_RAW_DATA", {"customer": "Cust A"})

    def _fake_get_doc(doctype, name=None):
        if doctype == "Customer":
            return _FakeDoc(_mock_customer(customer_primary_address="Addr-1"))
        return _FakeDoc(
            {"country": "Egypt", "state": None, "city": "giza", "address_line1": "Street X", "building_number": None}
        )

    monkeypatch.setattr(frappe, "get_doc", _fake_get_doc)
    monkeypatch.setattr(frappe.db, "get_value", lambda *args, **kwargs: "eg")

    receiver = get_receiver()

    assert receiver.address == ReceiverAddress(
        country="EG", governate="giza", regionCity="giza", street="Street X", buildingNumber="B0"
    )


def test_get_receiver_uses_complete_customer_address(monkeypatch):
    """A fully populated Address is passed through as-is (country code uppercased)."""
    monkeypatch.setattr(einvoice_schema, "INVOICE_RAW_DATA", {"customer": "Cust A"})

    def _fake_get_doc(doctype, name=None):
        if doctype == "Customer":
            return _FakeDoc(_mock_customer(customer_primary_address="Addr-1"))
        return _FakeDoc(
            {
                "country": "Egypt",
                "state": "Giza",
                "city": "6th of October",
                "address_line1": "Industrial Zone",
                "building_number": "12",
            }
        )

    monkeypatch.setattr(frappe, "get_doc", _fake_get_doc)
    monkeypatch.setattr(frappe.db, "get_value", lambda *args, **kwargs: "eg")

    receiver = get_receiver()

    assert receiver.address == ReceiverAddress(
        country="EG", governate="Giza", regionCity="6th of October", street="Industrial Zone", buildingNumber="12"
    )
