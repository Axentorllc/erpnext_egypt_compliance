import json

import frappe
from frappe import _
from erpnext_egypt_compliance.erpnext_eta.einvoice_schema import get_invoice_asjson
# from erpnext_egypt_compliance.erpnext_eta.legacy_einvoice import (
#     fetch_eta_status as fetch_eta_status_legacy,
# )
from erpnext_egypt_compliance.erpnext_eta.legacy_einvoice import (
    get_eta_invoice as get_eta_invoice_legacy, get_eta_inv_datetime_diff
)
# from erpnext_egypt_compliance.erpnext_eta.legacy_einvoice import (
#     submit_eta_invoice as submit_eta_invoice_legacy,
# )
from erpnext_egypt_compliance.erpnext_eta.utils import (
    download_eta_invoice_json, update_eta_docstatus
)
from erpnext_egypt_compliance.erpnext_eta.doctype.eta_log.einvoice_logging_utils import submit_einvoice_using_logger, submit_einvoice_background_logger
from erpnext_egypt_compliance.erpnext_eta.utils import get_company_eta_connector
from erpnext_egypt_compliance.erpnext_eta.einvoice_submitter import EInvoiceSubmitter

@frappe.whitelist()
def download_eta_inv_json(docname):
    # is_pydantic_builder_enabled = frappe.db.get_single_value("ETA Settings", "pydantic_builder")
    try:
        # if is_pydantic_builder_enabled:
        file_content = get_invoice_asjson(docname)
        # else:
        #     invoice_doc = get_eta_invoice_legacy(docname)
        #     file_content = json.dumps(invoice_doc, indent=4, ensure_ascii=False).encode("utf8")

        return download_eta_invoice_json(docname, file_content)
    except Exception as e:
        frappe.throw(_("{0}").format(e), title=_("ETA Validation"))

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
    
    company = frappe.get_value("Sales Invoice", docname, "company")
    connector = get_company_eta_connector(company)
    return update_eta_docstatus(connector, docname)
    

def get_auto_submit_invoices(company):
    try:
        connector = get_company_eta_connector(company)
        if connector.enable_auto_submission_batch:
            batch_size=connector.eta_batch_size or 10
            docs = frappe.get_all(
                    "Sales Invoice",
                    filters=[
                        ["eta_signature", "!=", ""],
                        ["docstatus", "=", 1],
                        ["eta_status", "=", ""],
                        ["eta_submission_id", "=", ""],
                    ],
                    pluck="name",
                    limit=batch_size
                )
            for docname in docs:
                submit_inv = True
                if get_eta_inv_datetime_diff(docname) < connector.delay_in_hours:
                    submit_inv = False
                if connector.enable_eta_grace_period_validation and (
                    get_eta_inv_datetime_diff(docname) > connector.einvoice_submission_grace_period
                ):
                    submit_inv = False

                if submit_inv:
                    inv = get_invoice_asjson(docname, as_dict=True)
                    submit_einvoice_background_logger(inv, company=company)
               
                 
    except Exception as e:
        frappe.log_error("Auto Submission Error", f"Failed to submit e-invoice  {0}").format(str(e))
        

def autosubmit_eta_process():
    companies = frappe.get_all("Company", pluck="name")

    for company in companies:
        try:
            connectors = frappe.get_list(
            "ETA Connector",
            filters={'company':company,"is_default": 1},
            pluck="name",
            limit=1
            )
            get_auto_submit_invoices(company)
        except:
            print("An exception occurred")


@frappe.whitelist()
def submit_eta_invoice(docname):
    try:
       
        company = frappe.get_value("Sales Invoice", docname, "company")
        inv = get_invoice_asjson(docname, as_dict=True)
        submit_einvoice_using_logger(inv, company)

    except Exception as e:
        frappe.throw(_("Error submitting ETA invoice: {0}").format(str(e)), title=_("ETA Validation"))


def submit_eta_invoice_background(docname):
    """Background job function for submitting ETA invoice"""
    try:
        # Check if invoice still has signature and is eligible for submission
        invoice_data = frappe.get_value("Sales Invoice", docname, 
                                      ["eta_signature", "docstatus", "company", "eta_status"], 
                                      as_dict=True)
        
        if not invoice_data:
            frappe.log_error(f"Invoice {docname} not found")
            return
            
        # Submit the invoice
        company = invoice_data.company
        inv = get_invoice_asjson(docname, as_dict=True)
        submit_einvoice_background_logger(inv, company)
        
        # Update status to completed
        # frappe.set_value("Sales Invoice", docname, "eta_submission_status", "Submitted")
        # frappe.db.commit()
        
    except Exception as e:
        frappe.log_error(f"Background ETA submission failed for {docname}: {str(e)}")


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
