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
    frappe.set_value("Sales Invoice", docname, "eta_signature_date", datetime.today())
    frappe.set_value("Sales Invoice", docname, "eta_signature_time", datetime.now())
    frappe.db.commit()

    inv = get_invoice_asjson(docname, as_dict=True)
    inv.pop("signatures")
    inv.documentTypeVersion = "1.0"
    return inv


@frappe.whitelist()
def set_invoice_signature(docname, signature, doctype="Sales Invoice"):
    frappe.set_value(doctype, docname, "eta_signature", signature)
    return "Signature Received"
