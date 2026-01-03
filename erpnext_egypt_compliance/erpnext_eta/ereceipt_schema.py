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
from frappe import _
from erpnext_egypt_compliance.erpnext_eta.ereceipt_submitter import EReceiptSubmitter

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
                serialized_string += '"' + list_key.upper() + '"'
                for item in value:
                    serialized_string += '"' + name.upper() + '"'
                    serialized_string += serialize(item)

            else:
                serialized_string += '"' + name.upper() + '"'
                serialized_string += serialize(value)
        return serialized_string
    else:
         return '"' + str(document_structure) + '"'


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

    @validator("amount")
    def round_float_values(cls, value):
        return frappe.utils.flt(value, 5)


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
    id: str = Field(default="", description="Buyer ID.")
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
        if values.get("type") == "P":
            value = frappe.db.get_value("Customer", POS_INVOICE_RAW_DATA.get("customer"), "tax_id")

        return value

    @validator("name")
    def get_default_name(cls, value, values):
        value = POS_INVOICE_RAW_DATA.get("customer_name") or "Walk-in Customer"
        return value


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
    deviceSerialNumber: str = Field(default="", description="This is the POS serial number.")
    syndicateLicenseNumber: str = Field(default="", description="This is the syndicate license number.")
    activityCode: str = Field(..., description="Activity types define the allowed activities for the company.")
    branchAddress: BranchAddress = Field(..., description="Structure representing the branchAddress information.")


class ReceiptDocumentType(BaseModel):
    receiptType: str = Field(default="s", description="Receipt Type Codes. s: Sale Receipt, r: Return Receipt")
    typeVersion: str = Field(default="1.2", description="SDK Version")


class ReceiptHeader(BaseModel):
    dateTimeIssued: datetime = Field(..., description="Date and time of the receipt issue")
    receiptNumber: str = Field(..., description="Receipt Number. Unique per branch within the same submission")
    uuid: str = Field(default_factory="", description="Unique ID for the receipt")
    previousUUID: str = Field(default="", description="Mandatory, SHA256 format, Reference to previous receipt, empty string value is accepted only if this is the first receipt issued from this POS")
    referenceUUID: Optional[str] = Field(
        default=None,
        description="Mandatory for return receipts, Reference to The Sale Receipt. Not included for normal receipts.",
    )
    referenceOldUUID: str = Field(
        default="",
        description="Optional, This is not validated and is used for the resent return receipt case in case of validation failure and requirement to change something in the return receipt and resend it with a different UUID.",
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
    # Exclude uuid and also exclude referenceUUID if it's None (for normal receipts)
    document_structure = {}
    for key, value in ereceipt.items():
        if key == "uuid":
            continue
        # Exclude referenceUUID if it's None (for normal receipts) to match what will be sent
        if key == "header" and isinstance(value, dict):
            header_copy = value.copy()
            # Remove referenceUUID if None (normal receipts)
            if header_copy.get("referenceUUID") is None:
                header_copy.pop("referenceUUID", None)
            document_structure[key] = header_copy
        else:
            document_structure[key] = value
    
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
def build_erceipt_json(docname: str, doctype: str):
    """Entry point for creating the POS E-Receipt json."""

    # Set the global raw data: POS_INVOICE_RAW_DATA, COMPANY_DATA
    set_global_raw_data(docname, doctype)

    header: ReceiptHeader = get_pos_ereceipt_header()
    
    # Set receipt type to "r" for return receipts, "s" for normal receipts
    is_return = POS_INVOICE_RAW_DATA.get("is_return", 0)
    receipt_type = "r" if is_return else "s"
    document_type: ReceiptDocumentType = ReceiptDocumentType(receiptType=receipt_type)
    
    seller: ReceiptSeller = get_pos_receipt_seller()
    buyer: ReceiptBuyer = get_pos_receipt_buyer()
    item_data: List[SingleItemData] = get_pos_receipt_item_data()
    
    # For return receipts, convert negative totals to positive
    total_sales: float = frappe.utils.flt(sum([item.totalSale for item in item_data]), 5)
    net_amount: float = frappe.utils.flt(sum([item.netSale for item in item_data]), 5)
    total_amount: float = sum([item.total for item in item_data])
    
    if is_return:
        total_sales = abs(total_sales)
        net_amount = abs(net_amount)
        total_amount = abs(total_amount)
    # TODO make payment method dynamic
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
    
    # Generate UUID from the receipt structure
    # First, get the dict representation
    receipt_dict = receipt.model_dump()
    
    # Clean it (remove referenceUUID if None for normal receipts) before generating UUID
    # This ensures UUID matches what will actually be sent
    cleaned_receipt = receipt_dict.copy()
    if "header" in cleaned_receipt and isinstance(cleaned_receipt["header"], dict):
        is_return = cleaned_receipt.get("documentType", {}).get("receiptType") == "r"
        ref_uuid = cleaned_receipt["header"].get("referenceUUID")
        if not is_return and (ref_uuid is None or ref_uuid == ""):
            cleaned_receipt["header"].pop("referenceUUID", None)
    
    # Generate UUID from the cleaned structure (what will actually be sent)
    uuid = validate_and_generate_uuid(cleaned_receipt)
    receipt.header.uuid = uuid
    receipts.append(receipt)
    # signatures: List[SingleSignature] = [SingleSignature()]
    receipts_response: ReceiptsResponse = ReceiptsResponse(receipts=receipts)

    receipts_response: str = receipts_response
    
    return receipts_response

def _clean_receipt_dict(receipt_dict: dict) -> dict:
    """Remove referenceUUID from normal receipts (when None or empty) but keep it for return receipts."""
    if isinstance(receipt_dict, dict):
        if "receipts" in receipt_dict:
            for receipt in receipt_dict["receipts"]:
                if "header" in receipt and isinstance(receipt["header"], dict):
                    # Check if it's a return receipt by looking at documentType
                    is_return = receipt.get("documentType", {}).get("receiptType") == "r"
                    # If not a return receipt and referenceUUID is None or empty, remove it
                    ref_uuid = receipt["header"].get("referenceUUID")
                    if not is_return and (ref_uuid is None or ref_uuid == ""):
                        receipt["header"].pop("referenceUUID", None)
                        # Log for debugging
                        receipt_num = receipt["header"].get("receiptNumber", "Unknown")
                        frappe.log_error(
                            title="E-Receipt - Removed referenceUUID",
                            message=f"Removed referenceUUID from normal receipt: {receipt_num}"
                        )
    return receipt_dict

@frappe.whitelist()
def download_ereceipt_json(docname, doctype):
    try:
        file_content = build_erceipt_json(docname, doctype)
        receipt_dict = file_content.model_dump()
        cleaned_dict = _clean_receipt_dict(receipt_dict)
        ereceipt_as_json = json.dumps(cleaned_dict, indent=4, ensure_ascii=False)
        return download_eta_ereceipt_json(docname, ereceipt_as_json)
    except ValueError as e:
        frappe.log_error(title="Download E-Receipt", message=e, reference_doctype="POS Invoice", reference_name=docname)
        frappe.throw(
                _(str(e)),
                title=_("Download e-Receipt Failed"),
            )
    
def download_eta_ereceipt_json(docname, file_content):
    frappe.local.response.filename = f"eReceipt-{docname}.json"
    frappe.local.response.filecontent = file_content
    frappe.local.response.type = "download"


@frappe.whitelist()
def submit_ereceipt(docname, pos_profile, doctype="POS Invoice", raise_throw=True):
    """Submit the POS E-Receipt to the API."""
    try:
        ereceipt = build_erceipt_json(docname, doctype)
        receipt_dict = ereceipt.model_dump()
        
        # Determine if this is a return receipt
        is_return = False
        receipt_type_display = "Receipt"
        if receipt_dict.get("receipts"):
            first_receipt = receipt_dict["receipts"][0]
            receipt_type = first_receipt.get("documentType", {}).get("receiptType", "s")
            is_return = (receipt_type == "r")
            receipt_type_display = "Return Receipt" if is_return else "Receipt"
            receipt_num = first_receipt.get("header", {}).get("receiptNumber", "unknown")
            ref_uuid_before = first_receipt.get("header", {}).get("referenceUUID")
            
            frappe.log_error(
                title="E-Receipt - Before Cleaning",
                message=f"Receipt: {receipt_num}, Type: {receipt_type}, referenceUUID before: {ref_uuid_before}",
                reference_doctype=doctype,
                reference_name=docname
            )
        
        cleaned_dict = _clean_receipt_dict(receipt_dict)
        
        # Log receipt details after cleaning
        if cleaned_dict.get("receipts"):
            first_receipt = cleaned_dict["receipts"][0]
            receipt_num = first_receipt.get("header", {}).get("receiptNumber", "unknown")
            ref_uuid_after = first_receipt.get("header", {}).get("referenceUUID")
            frappe.log_error(
                title="E-Receipt - After Cleaning",
                message=f"Receipt: {receipt_num}, referenceUUID after: {ref_uuid_after}",
                reference_doctype=doctype,
                reference_name=docname
            )
        
        connector = frappe.get_doc("ETA POS Connector", pos_profile)
        if connector:
            eta_submitter = EReceiptSubmitter(connector)
            processed_docs = eta_submitter.submit_ereceipt(cleaned_dict, doctype)
            
            # Show success message
            if raise_throw:
                success_message = f"E-{receipt_type_display} submitted successfully for {docname}"
                frappe.msgprint(
                    msg=_(success_message),
                    title=_("Success"),
                    indicator="green"
                )
            
            return {
                "status": "success",
                "message": f"E-{receipt_type_display} submitted successfully",
                "docname": docname,
                "is_return": is_return
            }
            
    except Exception as e:
        error_traceback = frappe.get_traceback()
        frappe.log_error(
            title="Submit E-Receipt - Exception",
            message=f"Error: {str(e)}\n\nTraceback:\n{error_traceback}",
            reference_doctype=doctype,
            reference_name=docname
        )
        if raise_throw:
            # Determine receipt type for error message
            receipt_type_display = "Receipt"
            try:
                is_return = frappe.db.get_value(doctype, docname, "is_return")
                receipt_type_display = "Return Receipt" if is_return else "Receipt"
            except:
                pass
            
            frappe.throw(
                _(str(e)),
                title=_(f"Submitting E-{receipt_type_display} Failed"),
            )
        
        return {
            "status": "error",
            "message": str(e),
            "docname": docname
        }
        
@frappe.whitelist()      
def fetch_ereceipt_status(docname, raise_throw=True):
    try:
        pos_profile = frappe.db.get_value("POS Invoice", docname, "pos_profile")
        connector = frappe.get_doc("ETA POS Connector", pos_profile)
        if connector:
            result = connector.get_receipt_submission(docname)
            if raise_throw:
                frappe.msgprint(_(str(result)))
    except Exception as e:
        frappe.log_error(title="Fetch e-Receipt Status", message=e, reference_doctype="POS Invoice", reference_name=docname)
        if raise_throw:
            frappe.throw(
                    _(e),
                    title=_("Fetch e-Receipt Failed"),)


def _pos_total_qty():
    """Add _total_qty to the POS Invoice Item."""
    total = collections.defaultdict(int)
    for item in POS_INVOICE_RAW_DATA.get("items"):
        total[item.get("item_code")] += item.get("qty")
    POS_INVOICE_RAW_DATA["_total_qty"] = total


def set_global_raw_data(docname: str, doctype: str) -> None:
    """Get the raw POS data from the database."""
    global POS_INVOICE_RAW_DATA
    global COMPANY_DATA

    # Set the global POS data
    POS_INVOICE_RAW_DATA = frappe.get_doc(doctype, docname).as_dict()
    _pos_total_qty()

    # Set the global company data
    COMPANY_DATA = frappe.get_doc("Company", POS_INVOICE_RAW_DATA.get("company")).as_dict()


def get_original_receipt_uuid() -> str:
    """Get the original receipt UUID for return receipts."""
    return_against = POS_INVOICE_RAW_DATA.get("return_against")
    current_doctype = POS_INVOICE_RAW_DATA.get("doctype") or "POS Invoice"
    
    if not return_against:
        frappe.log_error(f"No return_against found for document", "Get Original Receipt UUID")
        return ""
    
    # Determine the doctype of the original document
    original_doctype = None
    if frappe.db.exists("Sales Invoice", return_against):
        original_doctype = "Sales Invoice"
    elif frappe.db.exists("POS Invoice", return_against):
        original_doctype = "POS Invoice"
    
    if not original_doctype:
        frappe.log_error(f"Original document {return_against} not found", "Get Original Receipt UUID")
        return ""
    
    # Try to get UUID from ETA Log Documents (works for both POS Invoice and Sales Invoice)
    # This is the most reliable way as it stores the UUID after submission
    try:
        # First try with exact doctype match
        original_uuid = frappe.db.sql("""
            SELECT uuid 
            FROM `tabETA Log Documents`
            WHERE reference_document = %s
            AND reference_doctype = %s
            AND uuid IS NOT NULL
            AND uuid != ''
            ORDER BY creation DESC
            LIMIT 1
        """, (return_against, original_doctype), as_dict=False)
        
        if original_uuid and len(original_uuid) > 0 and original_uuid[0] and original_uuid[0][0]:
            uuid_value = original_uuid[0][0]
            frappe.log_error(f"Found UUID from ETA Log Documents: {uuid_value[:20]}... for {return_against}", "Get Original Receipt UUID - Success")
            return uuid_value
        
        # If not found, try without doctype filter (in case of mismatch)
        original_uuid = frappe.db.sql("""
            SELECT uuid 
            FROM `tabETA Log Documents`
            WHERE reference_document = %s
            AND uuid IS NOT NULL
            AND uuid != ''
            ORDER BY creation DESC
            LIMIT 1
        """, (return_against,), as_dict=False)
        
        if original_uuid and len(original_uuid) > 0 and original_uuid[0] and original_uuid[0][0]:
            uuid_value = original_uuid[0][0]
            frappe.log_error(f"Found UUID from ETA Log Documents (no doctype): {uuid_value[:20]}... for {return_against}", "Get Original Receipt UUID - Success")
            return uuid_value
        
        # Also try querying through parent ETA Log table
        original_uuid = frappe.db.sql("""
            SELECT d.uuid 
            FROM `tabETA Log Documents` d
            INNER JOIN `tabETA Log` l ON d.parent = l.name
            WHERE d.reference_document = %s
            AND l.from_doctype = %s
            AND d.uuid IS NOT NULL
            AND d.uuid != ''
            ORDER BY d.creation DESC
            LIMIT 1
        """, (return_against, original_doctype), as_dict=False)
        
        if original_uuid and len(original_uuid) > 0 and original_uuid[0] and original_uuid[0][0]:
            uuid_value = original_uuid[0][0]
            frappe.log_error(f"Found UUID from ETA Log (via parent): {uuid_value[:20]}... for {return_against}", "Get Original Receipt UUID - Success")
            return uuid_value
        
        # If UUID is None in ETA Log Documents, try to extract it from parent ETA Log's response
        # This happens when the UUID hasn't been populated in the child table yet
        try:
            parent_logs = frappe.db.sql("""
                SELECT l.name, l.eta_response, l.submission_id, l.pos_profile, d.reference_document
                FROM `tabETA Log Documents` d
                INNER JOIN `tabETA Log` l ON d.parent = l.name
                WHERE d.reference_document = %s
                AND l.from_doctype = %s
                ORDER BY d.creation DESC
                LIMIT 1
            """, (return_against, original_doctype), as_dict=True)
            
            if parent_logs and len(parent_logs) > 0:
                parent_log = parent_logs[0]
                eta_response_str = parent_log.get("eta_response")
                
                if eta_response_str:
                    try:
                        # Handle both string and dict formats
                        if isinstance(eta_response_str, str):
                            eta_response = json.loads(eta_response_str)
                        else:
                            eta_response = eta_response_str
                        
                        # Try to find UUID in acceptedDocuments
                        internal_id_key = "internalId" if original_doctype == "Sales Invoice" else "receiptNumber"
                        
                        # Check acceptedDocuments
                        for doc in eta_response.get("acceptedDocuments", []):
                            doc_id = doc.get(internal_id_key)
                            if doc_id == return_against and doc.get("uuid"):
                                uuid_value = doc.get("uuid")
                                frappe.log_error(f"Found UUID from ETA Log response: {uuid_value[:20]}... for {return_against}", "Get Original Receipt UUID - Success")
                                return uuid_value
                        
                        # Also check rejectedDocuments (sometimes UUID is there even if rejected)
                        for doc in eta_response.get("rejectedDocuments", []):
                            doc_id = doc.get(internal_id_key)
                            if doc_id == return_against and doc.get("uuid"):
                                uuid_value = doc.get("uuid")
                                frappe.log_error(f"Found UUID from ETA Log response (rejected): {uuid_value[:20]}... for {return_against}", "Get Original Receipt UUID - Success")
                                return uuid_value
                        
                        # Debug: log what we found
                        accepted_count = len(eta_response.get("acceptedDocuments", []))
                        rejected_count = len(eta_response.get("rejectedDocuments", []))
                        frappe.log_error(f"ETA Log response has {accepted_count} accepted, {rejected_count} rejected docs. Looking for {return_against} with key {internal_id_key}", "Get Original Receipt UUID - Debug")
                    except json.JSONDecodeError as e:
                        frappe.log_error(f"JSON decode error: {str(e)[:100]}", "Get Original Receipt UUID")
                    except Exception as e:
                        frappe.log_error(f"Error parsing ETA Log response: {str(e)[:100]}", "Get Original Receipt UUID")
                else:
                    # If no eta_response, try to get UUID from ETA API using submission_id
                    submission_id = parent_log.get("submission_id")
                    pos_profile = parent_log.get("pos_profile")
                    if submission_id and pos_profile:
                        try:
                            from erpnext_egypt_compliance.erpnext_eta.ereceipt_submitter import EReceiptSubmitter
                            connector = frappe.get_doc("ETA POS Connector", pos_profile)
                            submitter = EReceiptSubmitter(connector)
                            submission_data = submitter.get_receipt_submission(submission_id)
                            
                            if isinstance(submission_data, dict):
                                # Look for the receipt in the submission data
                                internal_id_key = "receiptNumber"  # For receipts, it's always receiptNumber
                                receipts = submission_data.get("receipts", [])
                                for receipt in receipts:
                                    if receipt.get(internal_id_key) == return_against and receipt.get("uuid"):
                                        uuid_value = receipt.get("uuid")
                                        frappe.log_error(f"Found UUID from ETA API: {uuid_value[:20]}... for {return_against}", "Get Original Receipt UUID - Success")
                                        return uuid_value
                        except Exception as e:
                            frappe.log_error(f"Error getting UUID from ETA API: {str(e)[:100]}", "Get Original Receipt UUID")
                    else:
                        frappe.log_error(f"ETA Log {parent_log.get('name')} has no eta_response, submission_id: {submission_id}, pos_profile: {pos_profile}", "Get Original Receipt UUID - Debug")
        except Exception as e:
            frappe.log_error(f"Error querying parent ETA Log: {str(e)[:100]}", "Get Original Receipt UUID")
        
        # Debug: Check what's actually in ETA Log Documents
        debug_info = frappe.db.sql("""
            SELECT reference_document, reference_doctype, uuid, parent
            FROM `tabETA Log Documents`
            WHERE reference_document = %s
            LIMIT 5
        """, (return_against,), as_dict=True)
        if debug_info:
            frappe.log_error(f"Debug ETA Log Documents for {return_against}: {str(debug_info)}", "Get Original Receipt UUID - Debug")
    except Exception as e:
        frappe.log_error(f"Error getting UUID from ETA Log Documents: {str(e)}", "Get Original Receipt UUID")
    
    # For Sales Invoice: Check if original was submitted as e-invoice (eta_uuid) or e-receipt (custom_eta_uuid)
    if original_doctype == "Sales Invoice":
        try:
            # First check custom_eta_uuid (for e-receipts)
            try:
                original_uuid = frappe.db.get_value("Sales Invoice", return_against, "custom_eta_uuid")
                if original_uuid:
                    frappe.log_error(f"Found UUID from Sales Invoice custom_eta_uuid: {original_uuid} for {return_against}", "Get Original Receipt UUID - Success")
                    return original_uuid
            except Exception:
                pass  # Field might not exist, continue to next check
            
            # Then check eta_uuid (for e-invoices)
            original_uuid = frappe.db.get_value("Sales Invoice", return_against, "eta_uuid")
            if original_uuid:
                frappe.log_error(f"Found UUID from Sales Invoice eta_uuid: {original_uuid} for {return_against}", "Get Original Receipt UUID - Success")
                return original_uuid
        except Exception as e:
            frappe.log_error(f"Error getting UUID from Sales Invoice: {str(e)}", "Get Original Receipt UUID")
    
    # For POS Invoice: Check custom field if it exists
    if original_doctype == "POS Invoice":
        try:
            # Try custom_eta_uuid first (if it exists)
            original_uuid = frappe.db.get_value("POS Invoice", return_against, "custom_eta_uuid")
            if original_uuid:
                frappe.log_error(f"Found UUID from POS Invoice custom_eta_uuid: {original_uuid} for {return_against}", "Get Original Receipt UUID - Success")
                return original_uuid
            # Try custom_eta_ereceipt_uuid as fallback
            original_uuid = frappe.db.get_value("POS Invoice", return_against, "custom_eta_ereceipt_uuid")
            if original_uuid:
                frappe.log_error(f"Found UUID from POS Invoice custom_eta_ereceipt_uuid: {original_uuid} for {return_against}", "Get Original Receipt UUID - Success")
                return original_uuid
        except Exception as e:
            frappe.log_error(f"Error getting custom UUID from POS Invoice: {str(e)}", "Get Original Receipt UUID")
    
    # Log warning if UUID not found with more details
    # Check if the original document exists and what fields it has
    try:
        if original_doctype == "Sales Invoice":
            doc_exists = frappe.db.exists("Sales Invoice", return_against)
            if doc_exists:
                eta_uuid_value = frappe.db.get_value("Sales Invoice", return_against, "eta_uuid")
                custom_eta_uuid_value = None
                try:
                    custom_eta_uuid_value = frappe.db.get_value("Sales Invoice", return_against, "custom_eta_uuid")
                except:
                    pass
                frappe.log_error(
                    f"UUID not found for {return_against}. eta_uuid: {eta_uuid_value or 'None'}, custom_eta_uuid: {custom_eta_uuid_value or 'None'}",
                    "Get Original Receipt UUID - UUID Not Found"
                )
            else:
                frappe.log_error(
                    f"Original Sales Invoice {return_against} does not exist",
                    "Get Original Receipt UUID - Document Not Found"
                )
        elif original_doctype == "POS Invoice":
            doc_exists = frappe.db.exists("POS Invoice", return_against)
            if doc_exists:
                custom_uuid = frappe.db.get_value("POS Invoice", return_against, "custom_eta_uuid")
                frappe.log_error(
                    f"UUID not found for {return_against}. custom_eta_uuid: {custom_uuid or 'None'}",
                    "Get Original Receipt UUID - UUID Not Found"
                )
            else:
                frappe.log_error(
                    f"Original POS Invoice {return_against} does not exist",
                    "Get Original Receipt UUID - Document Not Found"
                )
    except Exception as e:
        frappe.log_error(
            f"Error checking document: {str(e)[:100]}. Doc: {return_against}",
            "Get Original Receipt UUID - Error"
        )
    
    return ""


def get_pos_ereceipt_header() -> ReceiptHeader:
    """Get the POS E-Receipt header."""
    header = ReceiptHeader(
        dateTimeIssued=POS_INVOICE_RAW_DATA.get("posting_date"),
        receiptNumber=POS_INVOICE_RAW_DATA.get("name"),
        currency=POS_INVOICE_RAW_DATA.get("currency"),
        uuid=""
    )
    
    # Handle return receipts - populate previousUUID and referenceUUID
    # For return receipts:
    # - previousUUID: Reference to previous receipt (mandatory)
    # - referenceUUID: Reference to The Sale Receipt (mandatory for return receipts)
    is_return = POS_INVOICE_RAW_DATA.get("is_return", 0)
    if is_return:
        original_receipt_uuid = get_original_receipt_uuid()
        if original_receipt_uuid:
            header.previousUUID = original_receipt_uuid
            header.referenceUUID = original_receipt_uuid  # Mandatory for return receipts according to ETA SDK
    
    return header


def get_pos_receipt_seller() -> ReceiptSeller:
    """Get the POS E-Receipt Seller."""
    branch = frappe.get_doc("Branch", COMPANY_DATA.get("eta_default_branch")).as_dict()
    branch_address = frappe.get_doc("Address", branch.get("eta_branch_address")).as_dict()
    country_code = frappe.db.get_value("Country", branch_address.country, "code")
    device_serial = str(frappe.db.get_value("ETA POS Connector", POS_INVOICE_RAW_DATA.get("pos_profile"), "serial_number"))
    seller = ReceiptSeller(
        rin=COMPANY_DATA.get("eta_tax_id"),
        companyTradeName=COMPANY_DATA.get("eta_issuer_name"),
        branchCode=branch.get("eta_branch_id"),
        deviceSerialNumber=device_serial,
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
        id=customer.get("tax_id"),
        name=customer.get("customer_name") or "Walk-in Customer"
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
    total_sale = _eta_round(_item.get("qty") * _item.get("net_rate"))

    taxable_items = _get_taxable_items(_item)

    total_tax_amount = sum(tax.amount for tax in taxable_items)

    item_total = _eta_round(net_sale + total_tax_amount)

    item_unit_type = frappe.get_value("UOM", _item.get("uom"), "eta_uom") or frappe.get_value(
        "ETA Settings", "ETA Settings", "eta_uom"
    )

    item_code = (
        _item.get("eta_item_code")
        or frappe.get_value("ETA Settings", "ETA Settings", "eta_item_code")
        or _item.get("item_code")
    )
    
    # For return receipts, convert negative values to positive
    is_return = POS_INVOICE_RAW_DATA.get("is_return", 0)
    if is_return:
        net_sale = abs(net_sale)
        total_sale = abs(total_sale)
        item_total = abs(item_total)
        # Convert tax amounts to positive
        for tax_item in taxable_items:
            tax_item.amount = abs(tax_item.amount)

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
    is_return = POS_INVOICE_RAW_DATA.get("is_return", 0)
    
    for item in POS_INVOICE_RAW_DATA.get("items"):
        item_metrics = _get_item_metrics(item)
        # For return receipts, convert negative quantity to positive
        quantity = abs(item.get("qty")) if is_return else item.get("qty")
        
        item_data.append(
            SingleItemData(
                internalCode=item.get("item_code"),
                description=item.get("item_name"),
                itemType=item.get("eta_code_type", "EGS"),
                quantity=quantity,
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
    is_return = POS_INVOICE_RAW_DATA.get("is_return", 0)
    
    for item in taxableItems:
        amount = abs(frappe.utils.flt(item.amount, 5)) if is_return else frappe.utils.flt(item.amount, 5)
        total[item.taxType] += amount

    tax_totals = []
    for tax_type, amount in total.items():
        tax_totals.append(SingleTaxTotal(
            taxType=tax_type,
            amount=amount
        )) 
    return tax_totals
