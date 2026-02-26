import frappe
from frappe import _
from pydantic import ValidationError
from erpnext_egypt_compliance.erpnext_eta.einvoice_schema import get_invoice_asjson
from frappe.utils import getdate, nowdate
from erpnext_egypt_compliance.erpnext_eta.utils import get_company_eta_connector

def validate_eta_before_submit(doc, method=None):
    """
    Pre-validate Sales Invoice using the same Pydantic validation that ETA submission uses.
    This prevents users from submitting invoices with incomplete Master Data.
    For POS invoices, runs e-receipt validation instead of e-invoice validation.

    Detection logic:
    - POS Invoice doctype → always POS
    - Sales Invoice + pos_profile → POS from POSAwesome
    """
    is_pos = bool(doc.get("pos_profile"))
    company = frappe.get_value("Sales Invoice", doc.name, "company")
    enable_ereceipt = frappe.get_value("Company", company, "custom_enable_ereceipt")

    if enable_ereceipt and is_pos:
        pos_profile = doc.get("pos_profile")
        # Check if ETA POS Connector is configured for this POS Profile
        pos_connector = _get_eta_pos_connector_for_profile(pos_profile, throw_if_missing=False)

        if not pos_connector:
            # E-Receipt enabled but no connector configured for this POS Profile → warn and allow local submission
            frappe.msgprint(
                _("E-Receipt is enabled for company {0}, but no ETA POS Connector is configured for POS Profile '{1}'. "
                  "Receipt will be submitted locally only.").format(company, pos_profile),
                alert=True,
                indicator="orange"
            )
            return

        # Connector exists → validate e-receipt format
        _validate_ereceipt_before_submit(doc)
        return

    # === E-INVOICE PATH (Regular Sales Invoice without POS) ===
    connector = get_company_eta_connector(company)

    if not connector:
        return

    # Skip if signature start date not reached
    if connector.signature_start_date and getdate(doc.posting_date) < getdate(connector.signature_start_date):
        return

    try:
        get_invoice_asjson(doc.name,as_dict=True)

    except ValidationError as e:
        error_messages = parse_pydantic_errors(e)
        frappe.throw(
            _("Invoice cannot be submitted due to incomplete ETA Master Data:<br><br>{0}").format(
                "<br>".join(error_messages)
            ),
            title=_("ETA Validation Failed")
        )


def parse_pydantic_errors(validation_error):
    """
    Parse Pydantic ValidationError and convert to user-friendly messages.
    """
    error_messages = []
    
    for error in validation_error.errors():
        field_path = " → ".join(str(loc) for loc in error["loc"])
        error_type = error["type"]
        error_msg = error["msg"]
        
        # Create user-friendly field names
        friendly_field_name = get_friendly_field_name(field_path)
        
        if error_type == "value_error.missing":
            error_messages.append(_("Required field '{0}' is missing").format(friendly_field_name))
        elif error_type == "value_error.str.regex":
            error_messages.append(_("Field '{0}' has invalid format: {1}").format(friendly_field_name, error_msg))
        elif "required" in error_type:
            error_messages.append(_("Required field '{0}' is missing or empty").format(friendly_field_name))
        else:
            error_messages.append(_("Field '{0}': {1}").format(friendly_field_name, error_msg))
    
    return error_messages


def get_friendly_field_name(field_path):
    """
    Convert technical field paths to user-friendly names.
    """
    field_mapping = {
        "issuer.id": "Company ETA Tax ID",
        "issuer.name": "Company ETA Issuer Name", 
        "issuer.address.branchId": "Branch ETA ID",
        "issuer.address.country": "Branch Country",
        "issuer.address.governate": "Branch Governate/State",
        "issuer.address.regionCity": "Branch City",
        "issuer.address.street": "Branch Street",
        "issuer.address.buildingNumber": "Branch Building Number",
        "taxpayerActivityCode": "Company ETA Activity Code",
        "receiver.name": "Customer Name",
        "receiver.address": "Customer Address",
        "invoiceLines": "Invoice Items",
        "taxTotals": "Tax Information",
    }
    
    # Check for exact matches first
    if field_path in field_mapping:
        return field_mapping[field_path]
    
    # Check for partial matches
    for key, value in field_mapping.items():
        if key in field_path:
            return value
    
    # Return the original field path if no mapping found
    return field_path


def validate_eta_invoice_data(docname):
    """
    Whitelist method to validate ETA invoice data from client-side.
    This can be called before submission to show validation errors.
    """
    try:
        doc = frappe.get_doc("Sales Invoice", docname)
        validate_eta_before_submit(doc)
        return {"status": "success", "message": _("ETA validation passed successfully")}

    except Exception as e:
        return {"status": "error", "message": str(e)}


def _get_eta_pos_connector_for_profile(pos_profile, throw_if_missing=False):
    """
    Get the ETA POS Connector linked to a specific POS Profile.

    Args:
        pos_profile (str): POS Profile name/docname
        throw_if_missing (bool): If True, throw error if connector not found

    Returns:
        Document: ETAPOSConnector document or None
    """
    if not pos_profile:
        return None

    try:
        # ETA POS Connector is directly linked to POS Profile (unique 1:1 relationship)
        connector_name = frappe.get_value(
            "ETA POS Connector",
            filters={"pos_profile": pos_profile, "disabled": 0},
            fieldname="name"
        )

        if not connector_name:
            if throw_if_missing:
                frappe.throw(
                    _("No active ETA POS Connector found for POS Profile '{0}'. "
                      "Please configure ETA POS Connector to submit e-receipts.").format(pos_profile),
                    title=_("ETA POS Connector Not Found")
                )
            return None

        return frappe.get_doc("ETA POS Connector", connector_name)

    except Exception as e:
        frappe.log_error(f"Error fetching ETA POS Connector for POS Profile '{pos_profile}': {str(e)}")
        if throw_if_missing:
            raise
        return None


def _validate_ereceipt_before_submit(doc):
    """
    Run e-receipt Pydantic validation (mirrors e-invoice validation but for receipts).
    Raises a user-friendly error if validation fails.
    """
    from erpnext_egypt_compliance.erpnext_eta.ereceipt_schema import build_erceipt_json

    try:
        build_erceipt_json(doc.name, doctype=doc.doctype)
    except ValidationError as e:
        error_messages = parse_pydantic_errors(e)
        frappe.throw(
            _("Receipt cannot be submitted due to incomplete ETA Master Data:<br><br>{0}").format(
                "<br>".join(error_messages)
            ),
            title=_("ETA E-Receipt Validation Failed")
        )
