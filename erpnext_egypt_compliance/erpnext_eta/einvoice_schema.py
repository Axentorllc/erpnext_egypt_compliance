import collections
import json
import re

from typing import List, Dict, Optional

from pydantic import BaseModel, validator, Field, root_validator

import frappe

from erpnext_egypt_compliance.erpnext_eta.utils import (
    eta_datetime_issued_format,
    validate_allowed_values,
    eta_round,
)
from erpnext_egypt_compliance.erpnext_eta.ereceipt_schema import ItemWiseTaxDetails
from erpnext_egypt_compliance.erpnext_eta.legacy_einvoice import _abs_values
INVOICE_RAW_DATA = {}
COMPANY_DATA = {}


class Signature(BaseModel):
    signatureType: str = Field(default="I")
    value: str = Field(...)


class TaxTotals(BaseModel):
    taxType: str
    amount: float = Field(default=0.0)

    @validator("amount")
    def apply_eta_round_tax_totals(cls, value, values):
        return eta_round(value)


class TaxableItem(BaseModel):
    taxType: str = Field(...)
    subType: str = Field(...)
    amount: float = Field(default=0.0)
    rate: float = Field(default=14)


class Discount(BaseModel):
    rate: float = Field(default=0.0)
    amount: float = Field(default=0.0)


class Value(BaseModel):
    currencySold: str = Field(...)
    amountEGP: float = Field(...)
    amountSold: float = Field(default=None)
    currencyExchangeRate: float = Field(default=None)

    @validator("amountEGP")
    def apply_eta_round_amount_egp(cls, value, values):
        return eta_round(value)


class InvoiceLine(BaseModel):
    description: str
    itemType: str
    itemCode: str
    internalCode: str = Field(default=None)
    unitType: str
    quantity: float
    salesTotal: float
    netTotal: float
    total: float
    discount: Optional[List[Discount]] = Field(default=None)
    taxableItems: List[TaxableItem]
    unitValue: Value
    valueDifference: float = Field(default=0.0)
    totalTaxableFees: float = Field(default=0.0)
    itemsDiscount: float = Field(default=0.0)

    @root_validator(pre=True)
    def validate_mandatories(cls, values):
        return validate_mandatory_fields(cls, values)

    @validator("itemType")
    def item_type_must_be_one_of(cls, value, values):
        allowed_types = ["GS1", "EGS"]
        return validate_allowed_values(value, allowed_types)

    @validator("salesTotal", "netTotal", "total")
    def apply_eta_round_sales_total(cls, value, values):
        return eta_round(value)

    @validator("taxableItems")
    def apply_eta_round_taxable_items(cls, value, values):
        for tax in value:
            tax.amount = eta_round(tax.amount)
        return value


class Delivery(BaseModel):
    approach: Optional[str] = Field(default=None)
    packaging: Optional[str] = Field(default=None)
    dateValidity: Optional[str] = Field(default=None)
    exportPort: Optional[str] = Field(default=None)
    countryOfOrigin: Optional[str] = Field(default=None)
    grossWeight: Optional[float] = Field(default=None)
    netWeight: Optional[float] = Field(default=None)
    terms: Optional[str] = Field(default=None)


    @classmethod
    def get_delivery_data(cls, invoice):
        from datetime import date, datetime
        from frappe.core.utils import html2text

        if not invoice.get("custom_eta_more_details", []):
            return cls()

        delivery = invoice.get("custom_eta_more_details")[0]
        
        date_validity = delivery.get("date_validity")

        if isinstance(date_validity, str):
            date_validity = datetime.strptime(date_validity, "%Y-%m-%d").strftime("%Y-%m-%dT%H:%M:%SZ")
        elif isinstance(date_validity, date):
            date_validity = date_validity.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            date_validity = None

        # strip terms
        if delivery.get("terms"):
            terms = frappe.get_value("Terms and Conditions", delivery.get("terms"), "terms", as_dict=True)
            if terms:
                delivery["terms"] = html2text(terms.get("terms"))


        return cls(
            approach=delivery.get("approach"),
            packaging=delivery.get("packaging"),
            dateValidity=date_validity,
            exportPort=delivery.get("export_port"),
            countryOfOrigin=delivery.get("country_of_origin"),
            grossWeight=delivery.get("gross_weight"),
            netWeight=delivery.get("net_weight"),
            terms=delivery.get("terms"),
        )
    

class Payment(BaseModel):
    bankName: Optional[str] = Field(default=None)
    bankAddress: Optional[str] = Field(default=None)
    bankAccountNo: Optional[str] = Field(default=None)
    bankAccountIBAN: Optional[str] = Field(default=None)
    swiftCode: Optional[str] = Field(default=None)
    terms: Optional[str] = Field(default=None)

    @validator("swiftCode", pre=True)
    def validate_swift_code(cls, v):
        if not v:
            return v

        v = v.strip().upper()

        # Validate SWIFT code format
        pattern = re.compile(r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$")
        if not pattern.match(v):
            raise ValueError("Invalid SWIFT code format.")
        return v

    @classmethod
    def get_payment_data(cls, bank_account: str, terms: str | None = None):
        from frappe.utils import strip_html
        from frappe.contacts.doctype.address.address import get_address_display

        bank_account_data = frappe.get_value("Bank Account", bank_account, ["bank", "bank_account_no", "iban",], as_dict=True)
        swift_number = frappe.get_value("Bank", bank_account_data.get("bank"), "swift_number")
        # strip terms
        if terms:
            terms = strip_html(terms)

        # get Bank Address
        address_name = frappe.get_all(
            "Dynamic Link",
            filters={
                "link_doctype": "Bank",
                "link_name": bank_account_data.get("bank"),
                "parenttype": "Address",
                "parentfield": "links"
            },
            fields=["parent"],
            limit=1
        )

        bank_address = None
        if address_name:
            bank_address = frappe.get_doc("Address", address_name[0].parent)
            bank_address = get_address_display(bank_address.as_dict()).replace("<br>", " ")

        return cls(
            bankName=bank_account_data.bank,
            bankAddress=bank_address,
            bankAccountNo=bank_account_data.bank_account_no,
            bankAccountIBAN=bank_account_data.iban,
            swiftCode=swift_number,
            terms=terms,
        )


class ReceiverAddress(BaseModel):
    country: str
    governate: str
    regionCity: str
    street: str
    buildingNumber: str
    # postalCode: str
    # floor: str
    # room: str
    # landmark: str
    # additionalInformation: str


class Receiver(BaseModel):
    type: str
    id: str = Field(default=None)
    name: str = Field(...)
    address: ReceiverAddress = Field(...)

    @validator("type")
    def type_must_be_receiver(cls, value, values):
        allowed_types = ["B", "P", "F"]
        return validate_allowed_values(value, allowed_types)

    @validator("id", pre=True, always=True)
    def id_default_values(cls, value, values):
        if values.get("type") == "P" and INVOICE_RAW_DATA.get("grand_total") >= 45000:
            customer_tax_id = frappe.get_doc("Customer", INVOICE_RAW_DATA.get("customer")).get("tax_id")
            return customer_tax_id.replace("-", "")
        return value

    @validator("name")
    def name_default_values(cls, value, values):
        if values.get("type") == "P":
            return "Walkin Customer"
        return value


class IssuerAddress(BaseModel):
    branchId: str = Field(...)
    country: str = Field(default="EG")
    governate: str = Field(...)
    regionCity: str = Field(...)
    street: str = Field(...)
    buildingNumber: str = Field(...)
    postalCode: Optional[str] = None
    floor: Optional[str] = None
    room: Optional[str] = None
    landmark: Optional[str] = None
    additionalInformation: Optional[str] = None

    @root_validator(pre=True)
    def validate_mandatories(cls, values):
        return validate_mandatory_fields(cls, values)



class Issuer(BaseModel):
    id: str = Field(...)
    type: str = Field(default="B")
    name: str = Field(...)
    address: IssuerAddress = Field(...)

    @root_validator(pre=True)
    def validate_mandatories(cls, values):
        return validate_mandatory_fields(cls, values)

    @validator("type")
    def type_must_be_issuer(cls, value, values):
        allowed_types = ["B", "P", "F"]
        return validate_allowed_values(value, allowed_types)


class Invoice(BaseModel):
    issuer: Issuer
    receiver: Receiver
    documentType: str = Field(default="I")
    documentTypeVersion: str = Field(default="1.0")
    dateTimeIssued: str = Field(...)
    taxpayerActivityCode: str = Field(...)
    internalID: str = Field(...)
    invoiceLines: List[InvoiceLine]
    totalDiscountAmount: Optional[float] = Field(default=0.0)
    totalSalesAmount: float = Field(default=0.0)
    netAmount: float = Field(default=0.0)
    totalAmount: float = Field(default=0.0)
    taxTotals: List[TaxTotals]
    signatures: List[Signature] = Field(default=None)

    extraDiscountAmount: float = Field(default=0.0)
    totalItemsDiscountAmount: float = Field(default=0.0)
    purchaseOrderReference: str = Field(default=None)
    purchaseOrderDescription: str = Field(default=None)
    salesOrderReference: str = Field(default=None)
    salesOrderDescription: str = Field(default=None)
    proformaInvoiceNumber: str = Field(default=None)
    payment: Payment = Field(default=None)
    delivery: Delivery = Field(default=None)

    @root_validator(pre=True)
    def validate_mandatories(cls, values):
        return validate_mandatory_fields(cls, values)

    @validator("dateTimeIssued", pre=True, always=True)
    def eta_datetime_format(cls, value):
        seconds = INVOICE_RAW_DATA.get("posting_time").seconds
        return eta_datetime_issued_format(value, seconds)

    @validator("totalSalesAmount", "netAmount", "totalAmount")
    def apply_eta_round_total_sales_amount(cls, value, values):
        return eta_round(value)

    def json(self, **kwargs):
        return json.dumps(self.dict(exclude_none=True, exclude_unset=True), **kwargs)


def get_invoice_asjson(docname: str, as_dict: bool=False):
    # Get the raw data from the database
    set_global_raw_data(docname)

    issuer = get_issuer()
    receiver = get_receiver()
    document_type = "C" if INVOICE_RAW_DATA.get("is_return") else "I"
    document_type_version = "1.0" if INVOICE_RAW_DATA.eta_signature else "0.9"
    date_time_issued = INVOICE_RAW_DATA.get("posting_date")
    taxpayer_activity_code = COMPANY_DATA.get("eta_default_activity_code")
    internal_id = INVOICE_RAW_DATA.get("name")
    first_row = INVOICE_RAW_DATA.get("custom_eta_more_details")[0] if INVOICE_RAW_DATA.get("custom_eta_more_details") else {}
    purchase_order_reference = INVOICE_RAW_DATA.get("po_no")
    purchase_order_description = first_row.get("purchase_order_description") if INVOICE_RAW_DATA.get("custom_eta_more_details") else ""
    sales_order_reference = first_row.get("sales_order_reference") if INVOICE_RAW_DATA.get("custom_eta_more_details") else ""
    sales_order_description = first_row.get("sales_order_description") if INVOICE_RAW_DATA.get("custom_eta_more_details") else ""
    proforma_invoice_number = first_row.get("proforma_invoice_number") if INVOICE_RAW_DATA.get("custom_eta_more_details") else ""
    bank_acc = first_row.get("bank_account") if INVOICE_RAW_DATA.get("custom_eta_more_details") else None
    payment = None
    if bank_acc:
        payment = Payment.get_payment_data(bank_account=bank_acc, terms=INVOICE_RAW_DATA.get("terms"))
    invoice_lines = get_invoice_lines()
    total_discount_amount = calculate_total_discount_amount(invoice_lines)
    total_sales_amount = sum([line.salesTotal for line in invoice_lines])
    net_amount, total_amount = get_net_total_amount()
    tax_totals = get_tax_totals(invoice_lines)
    signatures = get_signatures()

    invoice = Invoice(
        issuer=issuer,
        receiver=receiver,
        documentType=document_type,
        documentTypeVersion=document_type_version,
        dateTimeIssued=date_time_issued,
        taxpayerActivityCode=taxpayer_activity_code,
        internalID=internal_id,
        purchaseOrderReference=purchase_order_reference or "",
        purchaseOrderDescription=purchase_order_description or "",
        salesOrderReference=sales_order_reference or "",
        salesOrderDescription=sales_order_description or "",
        proformaInvoiceNumber=proforma_invoice_number or "",
        payment=payment.model_dump() if payment else {},
        delivery=Delivery.get_delivery_data(INVOICE_RAW_DATA).model_dump(),
        invoiceLines=invoice_lines,
        totalDiscountAmount=total_discount_amount,
        extraDiscountAmount=0.0,
        totalSalesAmount=total_sales_amount,
        netAmount=net_amount,
        totalAmount=total_amount,
        totalItemsDiscountAmount=0.0,
        taxTotals=tax_totals,
        signatures=signatures,
    )

    return invoice.json(indent=4, ensure_ascii=False) if not as_dict else _abs_values(invoice.model_dump(exclude_none=True, exclude_unset=True))


def set_global_raw_data(docname: str) -> None:
    """Get the raw POS data from the database."""

    def _pos_total_qty():
        """Add _total_qty to the POS Invoice Item."""
        total = collections.defaultdict(int)
        for item in INVOICE_RAW_DATA.get("items"):
            total[item.get("item_code")] += item.get("qty")
        INVOICE_RAW_DATA["_total_qty"] = total

    def _add_branch_data():
        """Add branch data to the POS Invoice."""
        branch = frappe.get_doc("Branch", COMPANY_DATA.get("eta_default_branch"))
        branch_address = frappe.get_doc("Address", branch.get("eta_branch_address"))
        INVOICE_RAW_DATA["branch_data"] = {
            **branch.as_dict(),
            **branch_address.as_dict(),
        }

    global INVOICE_RAW_DATA
    global COMPANY_DATA

    # Set the global POS data
    INVOICE_RAW_DATA = frappe.get_doc("Sales Invoice", docname).as_dict()

    # Set the global company data
    COMPANY_DATA = frappe.get_doc("Company", INVOICE_RAW_DATA.get("company")).as_dict()

    _pos_total_qty()
    _add_branch_data()


def get_issuer():
    """Get the invoice issuer."""
    return Issuer(
        type=COMPANY_DATA.get("eta_issuer_type"),
        id=COMPANY_DATA.get("eta_tax_id"),
        name=COMPANY_DATA.get("eta_issuer_name"),
        address=IssuerAddress(
            branchId=INVOICE_RAW_DATA.get("branch_data").get("eta_branch_id"),
            country=frappe.db.get_value("Country", COMPANY_DATA.get("country"), "code"),
            governate=INVOICE_RAW_DATA.get("branch_data").get("state"),
            regionCity=INVOICE_RAW_DATA.get("branch_data").get("city"),
            street=INVOICE_RAW_DATA.get("branch_data").get("address_line1"),
            buildingNumber=INVOICE_RAW_DATA.get("branch_data").get("building_number"),
            postalCode=COMPANY_DATA.get("postal_code", None),
            floor=COMPANY_DATA.get("floor", None),
            room=COMPANY_DATA.get("room", None),
            landmark=COMPANY_DATA.get("landmark", None),
            additionalInformation=COMPANY_DATA.get("additional_information", None),
        ),
    )


def get_receiver():
    """Get the invoice receiver."""
    customer = frappe.get_doc("Customer", INVOICE_RAW_DATA.get("customer")).as_dict()
    customer_type = customer.get("eta_receiver_type", "P")
    customer_id = customer.get("tax_id", "").replace("-", "")

# TODO Investigate a better pydantic way to do this validation
    if customer_type == "B":
        if not customer_id:
            frappe.throw(
                _("Customer {0} must have a Tax ID to be used as Business receiver.").format(customer.get("name")),
                title=_("ETA Validation"),
            )
    if customer_type == "P" and INVOICE_RAW_DATA.get("grand_total") >= 45000 and not re.match(r"^\d{14}$", customer_id):
            frappe.throw(
                _("Customer {0} must have a valid Tax ID (14 digits) to be used as Business receiver for invoices with grand total equal or above 45,000 EGP.").format(customer.get("name")),
                title=_("ETA Validation"),
            )
    if customer_type == "F" and not customer_id:
        frappe.throw(
            _("Customer {0} must have a Tax ID to be used as Foreign receiver.").format(customer.get("name")),
            title=_("ETA Validation"),
        )

    address = ReceiverAddress(
            country="EG",
            governate="Egypt",
            regionCity="EG City",
            street="Street 1",
            buildingNumber="B0",
            # postalCode=POS_INVOICE_RAW_DATA.get("postal_code"),
            # floor=POS_INVOICE_RAW_DATA.get("floor"),
            # room=POS_INVOICE_RAW_DATA.get("room"),
            # landmark=POS_INVOICE_RAW_DATA.get("landmark"),
            # additionalInformation=POS_INVOICE_RAW_DATA.get("additional_information"),
        )
    
    customer_address_name = customer.get("customer_primary_address")
    if customer_type == "F" and not customer_address_name:
        frappe.throw(
            _("Customer {0} must have a primary address.").format(customer.get("name")),
            title=_("ETA Validation"),
        )

    if customer_address_name:
        customer_address = frappe.get_doc("Address", customer_address_name)
        address = ReceiverAddress(
            country=frappe.db.get_value("Country", customer_address.country, "code"),
            governate=customer_address.state,
            regionCity=customer_address.city,
            street=customer_address.address_line1,
            buildingNumber=customer_address.building_number or "B0"
            # postalCode=customer_address.pincode or None,
            # floor=customer_address.floor or None,
            # room=customer_address.room or None,
            # landmark=customer_address.landmark or None,
            # additionalInformation=customer_address.address_line2 or None,
        )

    eta_receiver = Receiver(
        type=customer_type,
        id=customer_id,
        name=customer.get("customer_name"),
        address=address,
    )
    return eta_receiver

def validate_tax_id(tax_id: str, customer_type: str) -> str:
    if not tax_id:
        return None
    
    tax_id = re.sub(r"[^A-Za-z0-9]", "", tax_id)

    if customer_type == "B":
        # Must be exactly 9 digits
        return tax_id if re.fullmatch(r"\d{9}", tax_id) else None

    elif customer_type == "P":
        # Must be exactly 14 digits
        return tax_id if re.fullmatch(r"\d{14}", tax_id) else None
    

def _get_item_total(_net_total: float, _taxable_items) -> float:
    return sum([_net_total, sum(tax.amount for tax in _taxable_items)])


def _get_tax_amount(item_tax_detail: float, net_rate: float, qty: float, _exchange_rate: float) -> float:
    return item_tax_detail * net_rate * qty * _exchange_rate


def _get_item_taxable_items(_item_data: Dict):
    taxable_items = []
    if INVOICE_RAW_DATA.get("taxes"):
        for tax in INVOICE_RAW_DATA.get("taxes"):
            if tax.get("disable_eta"):
                continue

            item_wise_tax_detail_asjson = json.loads(tax.get("item_wise_tax_detail"))
            items_tax_detail_list = ItemWiseTaxDetails(data=item_wise_tax_detail_asjson)
            item_tax_detail = items_tax_detail_list.data.get(_item_data.get("item_code"))

            # default values
            tax_type = tax.get("eta_tax_type")
            sub_type = tax.get("eta_tax_sub_type")
            rate, amount = None, None

            if tax.get("charge_type") in ("On Net Total", "On Previous Row Total"):
                rate = item_tax_detail[0]

                item_rate = (
                    _item_data.get("rate")
                    if INVOICE_RAW_DATA.get("_foreign_company_currency")
                    else _item_data.get("net_rate")
                )
                amount = _get_tax_amount(
                    (item_tax_detail[0] / 100),
                    item_rate,
                    _item_data.get("qty"),
                    _item_data.get("_exchange_rate") or 1,
                )
            elif tax.get("charge_type") == "Actual" and (
                INVOICE_RAW_DATA.get("is_consolidated") or INVOICE_RAW_DATA.get("is_pos")
            ):
                if tax_type == "T1":
                    rate = 14
                    item_rate = _item_data.get("net_rate")
                    amount = _get_tax_amount(
                        (item_tax_detail[0] / 100),
                        item_rate,
                        _item_data.get("qty"),
                        _item_data.get("_exchange_rate") or 1,
                    )

            taxable_items.append(
                TaxableItem(
                    taxType=tax_type,
                    amount=amount,
                    subType=sub_type,
                    rate=rate,
                )
            )
    return taxable_items


def _get_sales_and_net_totals(_item_data: Dict):

    item_base_amount = _item_data.get("base_amount")
    item_exchange_rate = INVOICE_RAW_DATA.get("conversion_rate") or _item_data.get("_exchange_rate") or 1
    item_net_amount = _item_data.get("net_amount")

    if INVOICE_RAW_DATA.get("currency") == "EGP":
        _sales_total = _net_total = item_base_amount
    else:
        _sales_total = _net_total = item_net_amount * item_exchange_rate

    return _sales_total, _net_total


def _get_item_unit_value(_item_data: Dict):
    """Get the item unit value."""

    if INVOICE_RAW_DATA.get("currency") == "EGP":
        return Value(
            currencySold="EGP",
            amountEGP=_item_data.get("net_rate"),
        )
    
    else:
        currency_sold = INVOICE_RAW_DATA.get("currency")
        currency_exchange_rate = _exchange_rate = INVOICE_RAW_DATA.get("conversion_rate")
        amount_egp = _unit_price = _item_data.get("net_rate") * (_exchange_rate or 1)
        

        amount_sold = (
            _item_data.get("rate")
        )

        return Value(
            currencySold=currency_sold,
            amountEGP=amount_egp,
            amountSold = amount_sold,
            currencyExchangeRate = currency_exchange_rate
        )

def _get_item_code_and_type(_item_data: Dict):
    # default item code and type
    _code = _item_data.get("eta_item_code") or frappe.get_value("ETA Settings", "ETA Settings", "eta_item_code")
    _type = _item_data.get("eta_code_type", "GS1")

    if _item_data.get("eta_inherit_brand"):
        _code = frappe.get_value("Brand", _item_data.get("brand"), "eta_item_code")
        _type = frappe.get_value("Brand", _item_data.get("brand"), "eta_code_type")
    elif _item_data.get("eta_inherit_item_group"):
        _code = frappe.get_value("Item Group", _item_data.get("item_group"), "eta_item_code")
        _type = frappe.get_value("Item Group", _item_data.get("item_group"), "eta_code_type")

    return _code, _type


def _get_item_data(_item_data: Dict):
    _item_doc = frappe.get_doc("Item", _item_data.get("item_code")).as_dict()
    _eta_item_code, _eta_item_type = _get_item_code_and_type(_item_doc)
    unit_type = frappe.get_value("UOM", _item_data.get("uom"), "eta_uom") or frappe.get_value(
        "ETA Settings", "ETA Settings", "eta_uom"
    )
    unit_value = _get_item_unit_value(_item_data)
    sales_total, net_total = _get_sales_and_net_totals(_item_data)
    taxable_items = _get_item_taxable_items(_item_data)
    item_total = _get_item_total(net_total, taxable_items)
    # TODO:
    item_discount = None

    return {
        "description": _item_data.get("item_name"),
        "eta_item_type": _eta_item_type,
        "eta_item_code": _eta_item_code,
        "unit_type": unit_type,
        "quantity": _item_data.get("qty"),
        "internal_code": _item_data.get("item_code"),
        "unit_value": unit_value,
        "sales_total": sales_total,
        "net_total": net_total,
        "eta_taxable_items": taxable_items,
        "total": item_total,
        "discount": item_discount,
    }


def get_invoice_lines():
    invoice_lines = []
    for item in INVOICE_RAW_DATA.get("items"):
        item_data = _get_item_data(item)
        invoice_lines.append(
            InvoiceLine(
                description=item_data.get("description"),
                itemType=item_data.get("eta_item_type"),
                itemCode=item_data.get("eta_item_code"),
                internalCode=item_data.get("internal_code"),
                unitType=item_data.get("unit_type"),
                quantity=item_data.get("quantity"),
                salesTotal=item_data.get("sales_total"),
                netTotal=item_data.get("net_total"),
                total=item_data.get("total"),
                discount=item_data.get("discount"),
                unitValue=item_data.get("unit_value"),
                taxableItems=item_data.get("eta_taxable_items"),
                valueDifference=0.0,
                totalTaxableFees=0.0,
                itemsDiscount=0.0,
            )
        )
    return invoice_lines


def calculate_total_discount_amount(_invoice_lines):
    invoice_discounts_list = [line.discount for line in _invoice_lines]
    return sum([sum([d.amount for d in discount]) for discount in invoice_discounts_list if discount])


def get_net_total_amount():
    is_foreign_currency = INVOICE_RAW_DATA.get("conversion_rate") or INVOICE_RAW_DATA.get("_foreign_company_currency")

    _base_total = INVOICE_RAW_DATA.get("base_total")
    _net_total = INVOICE_RAW_DATA.get("net_total")
    _base_grand_total = INVOICE_RAW_DATA.get("base_grand_total")
    _exchange_rate = INVOICE_RAW_DATA.get("conversion_rate") or INVOICE_RAW_DATA.get("_exchange_rate") or 1

    if is_foreign_currency:
        _net_amount = _base_total
        _total_amount = _base_total 
    else:
        _net_amount = _net_total * _exchange_rate
        _total_amount = _base_grand_total

    return _net_amount, _total_amount


def get_tax_totals(invoice_lines):
    taxes = []
    if INVOICE_RAW_DATA.get("taxes"):
        for tax in INVOICE_RAW_DATA.get("taxes"):
            if tax.get("disable_eta"):
                continue
            tax_type = tax.get("eta_tax_type")

            is_foreign_currency = INVOICE_RAW_DATA.get("_foreign_company_currency")
            _exchange_rate = INVOICE_RAW_DATA.get("_exchange_rate") or 1
            if is_foreign_currency:
                tax_amount = tax.get("base_tax_amount_after_discount_amount") * _exchange_rate
            else:
                tax_amount = tax.get("tax_amount_after_discount_amount")

            is_consolidated_or_pos = INVOICE_RAW_DATA.get("is_consolidated") or INVOICE_RAW_DATA.get("is_pos")
            if is_consolidated_or_pos:
                tax_amount = sum([line.taxableItems[0].amount for line in invoice_lines])

            taxes.append(TaxTotals(taxType=tax_type, amount=tax_amount))
    return taxes


def get_signatures():
    return [
        Signature(
            signatureType="I",
            value=INVOICE_RAW_DATA.get("eta_signature") if INVOICE_RAW_DATA.get("eta_signature") else "ANY",
        )
    ]

def validate_mandatory_fields(cls, values):
    required_fields = [
        name for name, field in cls.model_fields.items() 
        if field.is_required()
    ]

    error_fields = []
    for field_name, value in values.items():

        if isinstance(value, str):
            value = value.strip()

        if field_name in required_fields and not value:
            error_fields.append(f"Field '{field_name}' is required")

    if error_fields:
        error_fields = "<ul>" + "".join(f"<li>{error}</li>" for error in error_fields) + "</ul>"
        raise ValueError(error_fields)
    return values