from datetime import datetime
import pytz

import frappe


def download_eta_invoice_json(docname, file_content):
    frappe.local.response.filename = f"ETA-{docname}.json"
    frappe.local.response.filecontent = file_content
    frappe.local.response.type = "download"


def eta_datetime_issued_format(posting_date, seconds):
    date_time: datetime = datetime.strptime(
        frappe.utils.add_to_date(
            posting_date,
            seconds=seconds,
        ).strftime("%Y-%m-%d %H:%M:%S"),
        "%Y-%m-%d %H:%M:%S",
    )
    date_utc_with_z_suffix: str = (
        pytz.timezone("Africa/Cairo")
        .localize(date_time, is_dst=None)
        .astimezone(pytz.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    return date_utc_with_z_suffix


def validate_allowed_values(value, allowed_values):
    if value not in allowed_values:
        raise ValueError(f"Value must be one of {allowed_values}")
    return value


def eta_round(_value: float, decimal: int = 2) -> float:
    """
    Round value to the specified number of decimal places, with a maximum of 5 decimal places.
    If the precision is not provided, it is fetched from the precision settings for "Sales Invoice Item net_rate".
    """
    if not decimal:
        decimal = frappe.get_precision("Sales Invoice Item", "net_rate") or 2

    # Ensure decimal places is not more than 5
    precision = min(decimal, 5)
    return round(_value, precision)


# --- eta_helper.py ---
def get_company_eta_connector(company, throw_if_no_connector=True):
    connector = frappe.get_list(
        "ETA Connector",
        filters={"company": company, "is_default": 1},
        fields=["name"],
        limit=1,
    )
    if connector:
        return frappe.get_doc("ETA Connector", connector[0].name)
    elif throw_if_no_connector:
        frappe.throw("No Default Connector Set.")
    connectors = frappe.get_list("ETA Connector", filters={"company": company, "is_default": 1})
    if connectors:
        connector = frappe.get_doc("ETA Connector", connectors[0]["name"])
        return connector
    elif throw_if_no_connector:
        frappe.throw("No Default Connecter Set.")


def autofetch_eta_status(company):
    connector = get_company_eta_connector(company)
    # get list of submitted invoices:
    docs = frappe.get_all("Sales Invoice", filters=[["eta_status", "=", "Submitted"]], pluck="name")
    for docname in docs:
        connector.update_eta_docstatus(docname)
    frappe.db.commit()


def autosubmit_signed_documents(company):
    connector = get_company_eta_connector(company)
    connector.submit_signed_invoices()


def gracefully_autosubmit_signed_documents(company):
    connector = get_company_eta_connector(company)
    connector.gracefully_submit_signed_documents()


def gracefully_autofetch_eta_status(company):
    connector = get_company_eta_connector(company)
    connector.gracefully_autofetch_eta_status()


def autofetch_eta_status_process():
    companies = frappe.get_all("Company", pluck="name")
    for company in companies:
        try:
            gracefully_autofetch_eta_status(company)
        except:
            print("An exception occurred")  # TODO handle error properly.


def autosubmit_eta_process():
    companies = frappe.get_all("Company", pluck="name")
    for company in companies:
        try:
            gracefully_autosubmit_signed_documents(company)
        except:
            print("An exception occurred")  # TODO handle error properly.
