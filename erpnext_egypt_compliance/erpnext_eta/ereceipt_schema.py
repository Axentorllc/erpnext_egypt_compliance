import collections
import hashlib
import json
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

import frappe
import frappe.utils
import pytz
from pydantic import BaseModel, Field, conint, validator

from erpnext_egypt_compliance.erpnext_eta.utils import (
    eta_datetime_issued_format,
    get_company_eta_connector,
)

POS_INVOICE_RAW_DATA = {}
COMPANY_DATA = {}


def convert_datetime_to_utc_with_z_suffix(date_time: datetime) -> str:
    return (
        pytz.timezone("Africa/Cairo")
        .localize(date_time, is_dst=None)
        .astimezone(pytz.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def serialize(document_structure):
    """
    Serialize a document structure to a normalized string.
    see https://sdk.preprod.invoicing.eta.gov.eg/document-serialization-approach/
    """
    if isinstance(document_structure, dict):
        
        serialized_string = ""

        for name, value in document_structure.items():
            if isinstance(value, list):
                list_key = name
                for item in value:
                    serialized_string += '"' + list_key.upper() + '"'
                    serialized_string += '"' + name.upper() + '"'
                    serialized_string += serialize(item)

            else:
                serialized_string += '"' + name.upper() + '"'
                serialized_string += serialize(value)
        return serialized_string
    else:
         return '"' + str(document_structure) + '"'

# def serialize(document_structure):
#     if isinstance(document_structure, (int, float, str, bool)):
#         return '"' + str(document_structure) + '"'
    
#     serialized_string = ""
    
#     for name, value in document_structure.items():
#         if not isinstance(value, list):
#             serialized_string += '"' + name.upper() + '"'
#             serialized_string += serialize(value)
#         else:
#             serialized_string += '"' + name.upper() + '"'
#             for array_element in value:
#                 serialized_string += serialize(array_element)
    
#     return serialized_string


class Beneficiary(BaseModel):
    amount: float = Field(default=0.0, description="Amount of the beneficiary.")
    rate: float = Field(default=0.0, description="Rate of the beneficiary.")


class Contractor(BaseModel):
    name: str = Field(default="", description="Contractor name.")
    amount: float = Field(default=0.0, description="Amount of the contractor.")
    rate: float = Field(default=0.0, description="Rate of the contractor.")


class SingleTaxTotal(BaseModel):
    taxType: str
    amount: float


class SingleExtraReceiptDiscountData(BaseModel):
    amount: float
    description: str


class SingleTaxableItems(BaseModel):
    taxType: str = Field(..., description="Tax type.")
    amount: float = Field(default=0.0)
    subType: str = Field(default="", description="Sub type.")
    rate: int = conint(ge=0, le=100)

    @validator("taxType")
    def validate_tax_types(cls, value, values):
        allowed_taxable_types = [
            "T1",
            "T2",
            "T3",
            "T4",
            "T5",
            "T6",
            "T7",
            "T8",
            "T9",
            "T10",
            "T11",
            "T12",
        ]
        if value not in allowed_taxable_types:
            raise ValueError(f"Invalid tax type. Allowed types are {allowed_taxable_types}")
        return value

    @validator("subType")
    def validate_sub_types(cls, value, values):
        allowed_sub_types = [
            "V001",
            "V002",
            "V003",
            "V004",
            "V005",
            "V006",
            "V007",
            "V008",
            "V009",
            "V010",
        ]
        if value not in allowed_sub_types:
            raise ValueError(f"Invalid sub type. Allowed types are {allowed_sub_types}")
        return value


class SingleItemDiscountData(BaseModel):
    amount: float = Field(default=0.0, description="Amount of the discount.")
    description: str = Field(default="", description="Description of the discount.")


class SingleCommercialDiscountData(BaseModel):
    amount: float = Field(default=0.0, description="Amount of the discount.")
    description: str = Field(default="", description="Description of the discount.")


class SingleItemData(BaseModel):
    internalCode: str = Field(..., description="Internal code of the item.")
    description: str = Field(..., description="Description of the item.")
    itemType: str = Field(..., description="Item type.")
    itemCode: str = Field(..., description="Item code.")
    unitType: str = Field(..., description="Unit type.")
    quantity: float = Field(..., description="Number of units of the defined unit type being sold.")
    unitPrice: float = Field(..., description="cost per quantity of the product.")
    netSale: float = Field(..., description="Total amount for the receipt line after applying discount.")
    taxableItems: Optional[List[SingleTaxableItems]] = Field(
        description="Structure representing the taxableItems information."
    )
    totalSale: float = Field(..., description="Total amount for the receipt line after applying discount.")
    total: float = Field(..., description="Total amount for the receipt line after applying discount.")

    # commercialDiscountData: Optional[SingleCommercialDiscountData] = Field(
    #     description="discounts applied to this item."
    # )
    # itemDiscountData: Optional[SingleItemDiscountData] = Field(
    #     description="collection of objects of non-taxable items discounts."
    # )
    # valueDifference: Optional[float] = Field(
    #     default=0, description="Value difference when selling goods already taxed."
    # )
    @validator('netSale', 'quantity', 'unitPrice', 'totalSale', 'total', pre=True, always=True)
    def round_float_values(cls, value):
        return frappe.utils.flt(value, 5)


class ReceiptBuyer(BaseModel):
    type: str = Field(
        default="P",
        description="Buyer Type Codes. B:business in Egypt, P:natural person, F:foreigner.",
    )
    id: str = Field(default="29501023501952", description="Buyer ID.")
    name: str = Field(
        default="",
        description="Registration name of the company or name and surname of the person.",
    )
    mobileNumber: str = Field(default="", description="Mobile number.")
    paymentNumber: str = Field(default="", description="Payment number.")

    @validator("type")
    def validate_type(cls, value):
        allowed_types = ["B", "P", "F"]
        if value not in allowed_types:
            raise ValueError(f"Invalid type. Allowed types are {allowed_types}")
        return value

    @validator("id")
    def validate_id(cls, value, values):
        # TODO: P/F cases
        if values.get("type") == "B":
            # Company Registration No. (RIN)
            value = COMPANY_DATA.get("eta_tax_id")
        return value

    @validator("name")
    def get_default_name(cls, value, values):
        return COMPANY_DATA.get("eta_issuer_name")


class BranchAddress(BaseModel):
    country: str = Field(default="EG", description="Country represented by ISO-3166-2 2 symbol code.")
    governate: str = Field(..., description="Governate.")
    regionCity: str = Field(..., description="Region and city information.")
    street: str = Field(..., description="Street information.")
    buildingNumber: str = Field(..., description=" Building information (number, name or both).")
    postalCode: str = Field(default="", description="Postal code.")
    floor: str = Field(default="", description="Floor information.")
    room: str = Field(default="", description="Room information.")
    landmark: str = Field(default="", description="Landmark information.")
    additionalInformation: str = Field(default="", description="Additional information.")


class ReceiptSeller(BaseModel):
    rin: str = Field(..., description="Registration number.")
    companyTradeName: str = Field(..., description="Registration name of the company.")
    branchCode: str = Field(..., description="Branch code as registered with tax authority")
    # TODO: deviceSerialNumber, syndicateLicenseNumber
    deviceSerialNumber: str = Field(default="SERIAL0101", description="This is the POS serial number.")
    syndicateLicenseNumber: str = Field(default="", description="This is the syndicate license number.")
    activityCode: str = Field(..., description="Activity types define the allowed activities for the company.")
    branchAddress: BranchAddress = Field(..., description="Structure representing the branchAddress information.")


class ReceiptDocumentType(BaseModel):
    receiptType: str = Field(default="s", description="Receipt Type Codes. s: Sale Receipt")
    typeVersion: str = Field(default="1.2", description="SDK Version")


class ReceiptHeader(BaseModel):
    dateTimeIssued: datetime = Field(..., description="Date and time of the receipt issue")
    receiptNumber: str = Field(..., description="Receipt Number. Unique per branch within the same submission")
    uuid: str = Field(default_factory="", description="Unique ID for the receipt")
    previousUUID: str = Field(default="", description="When receipt type is return")
    referenceOldUUID: str = Field(
        default="",
        description="validation failure and requirement to change something.",
    )
    currency: str = Field(default="EGP", description="Currency Code")
    # exchangeRate: float = Field(default=1.0, description="Exchange rate of the currency to EGP")
    sOrderNameCode: Optional[str] = Field(
        default="",
        description="Reference to the sales order for informational purposes.",
    )
    orderdeliveryMode: str = Field(default="FC", description="Order Delivery Mode Codes.")
    grossWeight: float = Field(default=0.0, description="Total weight of the goods delivered. Unit: KG")
    netWeight: float = Field(default=0.0, description="Net weight of the goods delivered. . Unit: KG")

    @validator("dateTimeIssued", pre=True, always=True)
    def eta_datetime_format(cls, value):
        seconds = POS_INVOICE_RAW_DATA.get("posting_time").seconds
        return eta_datetime_issued_format(value, seconds)


    # @validator("exchangeRate")
    # def exchange_rate_required(cls, value, values):
    # 	# exchange rate is required if currency is not EGP.
    # 	return POS_INVOICE_RAW_DATA.get("conversion_rate") or value or 1.0

    @validator("orderdeliveryMode")
    def check_orderdelivery_mode(cls, value):
        allowed_values = ["FC", "TO", "TC"]
        # FC, default value
        if not value:
            value = "FC"
        if value not in allowed_values:
            raise ValueError(f"orderdeliveryMode must be one of {allowed_values}")
        return value

# @validator("uuid", pre=True, always=True)
def validate_and_generate_uuid(ereceipt):
    # Serialize and normalize the receipt object
    document_structure = {key: value for key, value in ereceipt.items() if key != "uuid"}
    serialized_text = serialize(document_structure)
    
    # Hash the normalized text using SHA256
    hash_value = hashlib.sha256(serialized_text.encode("utf-8")).digest()
    # Convert the hash value to a hexadecimal string of 64 characters
    uuid = hash_value.hex()

    return uuid

class Receipt(BaseModel):
    header: ReceiptHeader
    documentType: ReceiptDocumentType
    seller: ReceiptSeller
    buyer: ReceiptBuyer
    itemData: List[SingleItemData]
    totalSales: float
    # totalCommercialDiscount: float
    # totalItemsDiscount: float
    # extraReceiptDiscountData: List[SingleExtraReceiptDiscountData]
    netAmount: float
    # feesAmount: float
    totalAmount: float
    taxTotals: List[SingleTaxTotal]
    paymentMethod: str
    # adjustment: float
    contractor: Contractor
    beneficiary: Beneficiary


class SingleSignature(BaseModel):
    signatureType: str = Field(default="T", description="Signature Type Codes.")
    value: str = Field(default="ANY", description="Signature value.")


class ReceiptsResponse(BaseModel):
    receipts: List[Receipt]
    # signatures: List[SingleSignature]


class ItemWiseTaxDetails(BaseModel):
    """
    `__root__` is used to indicate that the model's structure is a simple dictionary with no additional named fields.
    """

    data : Dict[str, List[float]]


@frappe.whitelist()
def build_erceipt_json(docname: str):
    """Entry point for creating the POS E-Receipt json."""

    # Set the global raw data: POS_INVOICE_RAW_DATA, COMPANY_DATA
    set_global_raw_data(docname)

    header: ReceiptHeader = get_pos_ereceipt_header()
    document_type: ReceiptDocumentType = ReceiptDocumentType()
    seller: ReceiptSeller = get_pos_receipt_seller()
    buyer: ReceiptBuyer = get_pos_receipt_buyer()
    item_data: List[SingleItemData] = get_pos_receipt_item_data()
    total_sales: float = sum([item.totalSale for item in item_data])
    net_amount: float = sum([item.netSale for item in item_data])
    total_amount: float = sum([item.total for item in item_data])
    payment_method: str = "C"
    adjustment: float = 0.0
    contractor: Contractor = Contractor()
    beneficiary: Beneficiary = Beneficiary()

    # total_commercial_discount: float = get_pos_receipt_total_commercial_discount()
    # total_items_discount: float = get_pos_receipt_total_items_discount()
    # extra_receipt_discount_data: List[SingleExtraReceiptDiscountData] = get_extra_receipt_discount_data()
    # fees_amount: float = get_pos_receipt_fees_amount()
    
	# List comprehension to extract taxableItems
    taxable_items_list = [item.taxableItems for item in item_data]
    taxable_items_list = [taxable_item for sublist in taxable_items_list for taxable_item in sublist]
    tax_totals: List[SingleTaxTotal] = get_pos_receipt_tax_totals(taxable_items_list)
    receipts: List[Receipt] = []
    receipt = Receipt(
            header=header,
            documentType=document_type,
            seller=seller,
            buyer=buyer,
            itemData=item_data,
            totalSales=total_sales,
            # totalCommercialDiscount=total_commercial_discount,
            # totalItemsDiscount=total_items_discount,
            # extraReceiptDiscountData=extra_receipt_discount_data,
            netAmount=net_amount,
            # feesAmount=fees_amount,
            totalAmount=total_amount,
            taxTotals=tax_totals,
            paymentMethod=payment_method,
            adjustment=adjustment,
            contractor=contractor,
            beneficiary=beneficiary,
        )
    
    seconds = POS_INVOICE_RAW_DATA.get("posting_time").seconds
    date_formated = eta_datetime_issued_format(POS_INVOICE_RAW_DATA.get("posting_date"), seconds)
    receipt.header.dateTimeIssued = date_formated
    uuid = validate_and_generate_uuid(receipt.dict())
    receipt.header.uuid = uuid
    receipts.append(receipt)
    # signatures: List[SingleSignature] = [SingleSignature()]
    receipts_response: ReceiptsResponse = ReceiptsResponse(receipts=receipts)

    receipts_response: str = receipts_response
    # submit_ereceipt(receipts_response_json)
    return receipts_response

@frappe.whitelist()
def download_ereceipt_json(docname):
    file_content = build_erceipt_json(docname)
    ereceipt_as_json = file_content.model_dump_json()
    return download_eta_ereceipt_json(docname, ereceipt_as_json)
    
def download_eta_ereceipt_json(docname, file_content):
	frappe.local.response.filename = f"eReceipt-{docname}.json"
	frappe.local.response.filecontent = file_content
	frappe.local.response.type = "download"

@frappe.whitelist()
def submit_ereceipt(docname, pos_profile) -> None:
    """Submit the POS E-Receipt to the API."""
    ereceipt = build_erceipt_json(docname)
    connector = frappe.get_doc("ETA POS Connector", pos_profile)
    if connector:
    	connector.submit_erecipt(ereceipt.model_dump())
        
@frappe.whitelist()      
def fetch_ereceipt_status(docname):
    pos_profile = frappe.db.get_value("POS Invoice", docname, "pos_profile")
    connector = frappe.get_doc("ETA POS Connector", pos_profile)
    if connector:
        connector.update_ereceipt_docstatus(docname)

def _pos_total_qty():
    """Add _total_qty to the POS Invoice Item."""
    total = collections.defaultdict(int)
    for item in POS_INVOICE_RAW_DATA.get("items"):
        total[item.get("item_code")] += item.get("qty")
    POS_INVOICE_RAW_DATA["_total_qty"] = total


def set_global_raw_data(docname: str) -> None:
    """Get the raw POS data from the database."""
    global POS_INVOICE_RAW_DATA
    global COMPANY_DATA

    # Set the global POS data
    POS_INVOICE_RAW_DATA = frappe.get_doc("POS Invoice", docname).as_dict()
    _pos_total_qty()

    # Set the global company data
    COMPANY_DATA = frappe.get_doc("Company", POS_INVOICE_RAW_DATA.get("company")).as_dict()


def get_pos_ereceipt_header() -> ReceiptHeader:
    """Get the POS E-Receipt header."""
    header = ReceiptHeader(
        dateTimeIssued=POS_INVOICE_RAW_DATA.get("posting_date"),
        receiptNumber=POS_INVOICE_RAW_DATA.get("name"),
        currency=POS_INVOICE_RAW_DATA.get("currency"),
        uuid=""
    )
    return header


def get_pos_receipt_seller() -> ReceiptSeller:
    """Get the POS E-Receipt Seller."""
    branch = frappe.get_doc("Branch", COMPANY_DATA.get("eta_default_branch")).as_dict()
    branch_address = frappe.get_doc("Address", branch.get("eta_branch_address")).as_dict()
    country_code = frappe.db.get_value("Country", branch_address.country, "code")
    seller = ReceiptSeller(
        rin=COMPANY_DATA.get("eta_tax_id"),
        companyTradeName=COMPANY_DATA.get("eta_issuer_name"),
        branchCode=branch.get("eta_branch_id"),
        # deviceSerialNumber=company.get("company"),
        # syndicateLicenseNumber=company.get("company"),
        activityCode=COMPANY_DATA.get("eta_default_activity_code"),
        branchAddress=BranchAddress(
            country=country_code,
            governate=branch_address.get("state"),
            regionCity=branch_address.get("city"),
            street=branch_address.get("address_line1"),
            buildingNumber=branch_address.get("building_number"),
            # postalCode=company.get("company"),
            # floor=company.get("company"),
            # room=company.get("company"),
            # landmark=company.get("company"),
            # additionalInformation=company.get("company"),
        ),
    )
    return seller


def get_pos_receipt_buyer() -> ReceiptBuyer:
    """Get the POS E-Receipt Buyer."""
    customer = frappe.get_doc("Customer", POS_INVOICE_RAW_DATA.get("customer")).as_dict()
    buyer = ReceiptBuyer(
        type=customer.get("eta_receiver_type"),
        # id=COMPANY_DATA.get("eta_tax_id"),
        name=COMPANY_DATA.get("eta_issuer_name"),
    )
    return buyer


def _calculate_item_total(_item: dict, _net_sale: float, _taxable_items: List[SingleTaxableItems]) -> float:
    """Get the item total."""
    calculation_parts = [_net_sale]
    calculation_parts.extend([tax.amount for tax in _taxable_items])
    _item_total = sum(calculation_parts)
    return _eta_round(_item_total)


def _get_tax_amount(item_tax_detail: float, net_rate: float, qty: float, _exchange_rate: float) -> float:
    return _eta_round(item_tax_detail * net_rate * qty * _exchange_rate)


def _get_taxable_items(_item: dict) -> List[SingleTaxableItems]:
    """Get the item tax data."""
    taxable_items = []
    if POS_INVOICE_RAW_DATA.get("taxes"):
        for tax in POS_INVOICE_RAW_DATA.get("taxes"):
            # TODO: Hardcoded, Type: T1, SubType: V009, amount=_get_tax_amount()
            item_wise_tax_detail_asjson = json.loads(tax.item_wise_tax_detail)
            items_tax_detail_list = ItemWiseTaxDetails(data=item_wise_tax_detail_asjson)

            item_tax_detail = items_tax_detail_list.data.get(_item.get("item_code"))
            amount = _get_tax_amount(
                (item_tax_detail[0] / 100),
                _item.get("net_rate"),
                _item.get("qty"),
                _item.get("_exchange_rate") or 1,
            )
            taxable_items.append(
                SingleTaxableItems(
                    taxType="T1",
                    subType="V001",
                    amount=amount,
                    rate=item_tax_detail[0],
                )
            )

    return taxable_items


def _eta_round(_value: float, decimal: int = 2) -> float:
    """
    Round unit price to the specified number of decimal places, with a maximum of 5 decimal places.
    If the precision is not provided, it is fetched from the precision settings for "Sales Invoice Item net_rate".
    """
    if not decimal:
        decimal = frappe.get_precision("Sales Invoice Item", "net_rate") or 2

    precision = min(decimal, 5)  # Ensure decimal places is not more than 5
    return round(_value, precision)


def _get_unit_price(_item: dict) -> float:
    """Get the unit price of an item."""
    unit_price = _item.get("net_rate") * (_item.get("_exchange_rate") or 1)
    return _eta_round(unit_price)


def _get_item_metrics(_item: dict) -> Dict:
    unit_price = _get_unit_price(_item)
    exchange_rate = _item.get("_exchange_rate") or 1

    net_sale = _item.get("net_amount")
    total_sale = net_sale + _item.get("discount_amount")

    # TODO: Hardcoded
    tax_rate = (_item.get("tax_rate") or 14) / 100
    item_tax_amount = net_sale * tax_rate
    item_total = _eta_round(net_sale + item_tax_amount)

    taxable_items = _get_taxable_items(_item)

    item_unit_type = frappe.get_value("UOM", _item.get("uom"), "eta_uom") or frappe.get_value(
        "ETA Settings", "ETA Settings", "eta_uom"
    )
    item_code = (
        _item.get("eta_item_code")
        or frappe.get_value("ETA Settings", "ETA Settings", "eta_item_code")
        or _item.get("item_code")
    )
    return {
        "unit_price": unit_price,
        "exchange_rate": exchange_rate,
        "net_sale": net_sale,
        "taxable_items": taxable_items,
        "item_total": item_total,
        "item_unit_type": item_unit_type,
        "item_code": item_code,
        "total_sale": total_sale,
    }


def get_pos_receipt_item_data() -> List[SingleItemData]:
    """Get the POS E-Receipt ItemData."""
    item_data = []
    for item in POS_INVOICE_RAW_DATA.get("items"):
        item_metrics = _get_item_metrics(item)
        item_data.append(
            SingleItemData(
                internalCode=item.get("item_code"),
                description=item.get("item_name"),
                itemType=item.get("eta_code_type", "GS1"),
                quantity=item.get("qty"),
                itemCode=item_metrics.get("item_code"),
                unitType=item_metrics.get("item_unit_type"),
                unitPrice=item_metrics.get("unit_price"),
                # TODO: Semi-validated, Hardcoded
                netSale=item_metrics.get("net_sale"),
                totalSale=item_metrics.get("total_sale"),
                taxableItems=item_metrics.get("taxable_items"),
                total=item_metrics.get("item_total"),
                # commercialDiscountData=[],
                # valueDifference=0,
                # itemDiscountData=[],
            )
        )
    return item_data

def get_pos_receipt_tax_totals(taxableItems):
    total = collections.defaultdict(int)
    for item in taxableItems:
        total[item.taxType] += frappe.utils.flt(item.amount, 5)

    tax_totals = []
    for tax_type, amount in total.items():
        tax_totals.append(SingleTaxTotal(
            taxType=tax_type,
            amount=amount
        )) 
    return tax_totals