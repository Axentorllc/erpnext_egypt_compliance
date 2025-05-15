import json

import frappe
from frappe import _
from erpnext_egypt_compliance.erpnext_eta.einvoice_schema import get_invoice_asjson
from erpnext_egypt_compliance.erpnext_eta.legacy_einvoice import (
    fetch_eta_status as fetch_eta_status_legacy,
)
from erpnext_egypt_compliance.erpnext_eta.legacy_einvoice import (
    get_eta_invoice as get_eta_invoice_legacy,
)
from erpnext_egypt_compliance.erpnext_eta.legacy_einvoice import (
    submit_eta_invoice as submit_eta_invoice_legacy,
)
from erpnext_egypt_compliance.erpnext_eta.utils import (
    download_eta_invoice_json,
)
from erpnext_egypt_compliance.erpnext_eta.doctype.eta_log.einvoice_logging_utils import submit_einvoice_using_logger
from erpnext_egypt_compliance.erpnext_eta.utils import get_company_eta_connector
from erpnext_egypt_compliance.erpnext_eta.einvoice_submitter import EInvoiceSubmitter


@frappe.whitelist()
def download_eta_inv_json(docname):
    is_pydantic_builder_enabled = frappe.db.get_single_value("ETA Settings", "pydantic_builder")
    if is_pydantic_builder_enabled:
        file_content = get_invoice_asjson(docname)
    else:
        invoice_doc = get_eta_invoice_legacy(docname)
        file_content = json.dumps(invoice_doc, indent=4, ensure_ascii=False).encode("utf8")

    return download_eta_invoice_json(docname, file_content)

@frappe.whitelist()
def get_eta_pdf(docname):
    try:
        sinv_doc_company = frappe.get_value("Sales Invoice", docname, "company")
        if not sinv_doc_company:
            frappe.throw(_("Company not found for the Sales Invoice"))

        connector = get_company_eta_connector(sinv_doc_company)
        if not connector:
            frappe.throw(_("ETA Connector not found for company {0}").format(sinv_doc_company))

        einvoice_submitter = EInvoiceSubmitter(connector)
        return einvoice_submitter.download_eta_pdf(docname)

    except Exception as e:
        frappe.log_error(f"ETA PDF Download Error for invoice {docname}: {str(e)}")
        frappe.throw(f"Error downloading PDF: {str(e)}")

@frappe.whitelist()
def fetch_eta_status(docname):
    is_pydantic_builder_enabled = frappe.db.get_single_value("ETA Settings", "pydantic_builder")
    if is_pydantic_builder_enabled:
        return fetch_eta_status_legacy(docname)
    else:
        return fetch_eta_status_legacy(docname)


@frappe.whitelist()
def submit_eta_invoice(docname):
    is_pydantic_builder_enabled = frappe.db.get_single_value("ETA Settings", "pydantic_builder")
    enable_eta_log = frappe.db.get_single_value("ETA Settings", "enable_eta_log")
    company = frappe.get_value("Sales Invoice", docname, "company")
    inv = get_invoice_asjson(docname, as_dict=True)
    if is_pydantic_builder_enabled:
        return submit_eta_invoice_legacy(docname, inv) if not enable_eta_log else submit_einvoice_using_logger(inv, company)
    else:
        return submit_eta_invoice_legacy(docname, inv) if not enable_eta_log else submit_einvoice_using_logger(inv, company)

@frappe.whitelist()
def cancel_eta_invoice(docname, reason):
    try:
        doc = frappe.get_doc("Sales Invoice", docname)
        connector = get_company_eta_connector(doc.company)
        if not connector:
            frappe.throw(_("ETA Connector not found for company {0}").format(doc.company))
            
        einvoice_submitter = EInvoiceSubmitter(connector)
        response = einvoice_submitter.cancel_document(doc.eta_uuid, reason)
        
        if response.get("status_code") == 200:
            doc.eta_status = "Cancelled"
            doc.eta_cancellation_reason = reason
            doc.save()
            return {"status": "success"}
        
        # Handle error responses
        error_message = "An unknown error occurred"
        
        if isinstance(response, dict):
            if response.get("error"):
                error = response.get("error")
                if isinstance(error, dict) and error.get("details"):
                    details = error.get("details")
                    if isinstance(details, list) and details and isinstance(details[0], dict):
                        error_message = details[0].get("message") or error_message
                elif isinstance(error, dict) and error.get("message"):
                    error_message = error.get("message")
                elif isinstance(error, str):
                    error_message = error
            elif response.get("message"):
                error_message = response.get("message")
        
        frappe.log_error(f"ETA Cancellation Error: {str(response)}", "ETA Cancellation Error")
        return {"status": "error", "message": error_message}
        
    except Exception as e:
        frappe.log_error(f"ETA Invoice Cancellation Error: {str(e)}")
        return {"status": "error", "message": str(e)}
