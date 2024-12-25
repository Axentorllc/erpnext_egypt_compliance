import json

import frappe

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
    if is_pydantic_builder_enabled:
        inv = get_invoice_asjson(docname, as_dict=True)
        return submit_eta_invoice_legacy(docname, inv) if not enable_eta_log else submit_einvoice_using_logger(inv, company)
    else:
        return submit_eta_invoice_legacy(docname) if not enable_eta_log else submit_einvoice_using_logger(docname, company)
