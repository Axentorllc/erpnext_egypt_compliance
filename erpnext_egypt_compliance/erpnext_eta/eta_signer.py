# Copyright (c) 2022, Axentor LLC
# For license information, please see license.txt

import frappe
import json
from datetime import datetime
from erpnext_egypt_compliance.erpnext_eta.utils import (
    get_company_eta_connector,
)

# from erpnext_eta.erpnext_eta.utils import get_eta_invoice
from erpnext_egypt_compliance.erpnext_eta.einvoice_schema import get_invoice_asjson
import base64

@frappe.whitelist()
def get_invoice_names_to_sign(company):
    connector = get_company_eta_connector(company)
    docstatus = ["1"]
    if connector.get("all_docstatus"):
        docstatus = ["0", "1"]
    invoice_names = frappe.get_list(
        "Sales Invoice",
        filters=[
            ["docstatus", "in", docstatus],
            ["company", "=", company],
            ["posting_date", ">=", connector.signature_start_date],
            ["eta_signature", "=", ""],
        ],
        order_by="posting_date",
    )
    return invoice_names if invoice_names else []


@frappe.whitelist()
def get_eta_invoice_for_signer(docname):
    try:
        frappe.set_value("Sales Invoice", docname, "eta_signature_date", datetime.today())
        frappe.set_value("Sales Invoice", docname, "eta_signature_time", datetime.now())
        frappe.db.commit()

        inv = get_invoice_asjson(docname, as_dict=True)
        inv.pop("signatures")
        inv["documentTypeVersion"] = "1.0"
        return inv
    except Exception as e:
        trace = frappe.get_traceback()
        frappe.log_error(
            title=f"Failed to get ETA Invoice for signer {docname}",
            message=trace,
        )
        return {"error": f"Failed to get ETA Invoice {str(e)}"}


@frappe.whitelist()
def set_invoice_signature(docname, signature, doctype="Sales Invoice"):
    is_valid_base64(signature)
    frappe.set_value(doctype, docname, "eta_signature", signature)
    
    company = frappe.get_value("Sales Invoice", docname, "company")
    connector = get_company_eta_connector(company)
    if connector and connector.submission_mode=='Live':
        enqueue_invoice_live_submission(docname ,connector)
    
    return "Signature Received"


def enqueue_invoice_live_submission(docname , connector):
    """Enqueue invoice for background submission after signature is set"""
    try:
        
            # Use Frappe's background job system
        frappe.enqueue(
            method="erpnext_egypt_compliance.erpnext_eta.main.autosubmit_eta_live_submission",
            queue="short",
            docname=docname,
            connector=connector,
            job_name=f"eta_submission_{docname}"
        )
        frappe.log_error(f"Invoice {docname} queued for ETA submission")
            
    except Exception as e:
        frappe.log_error(f"Failed to enqueue invoice {docname} for submission: {str(e)}")



def is_valid_base64(signature):
  base64.b64decode(signature, validate=True)
