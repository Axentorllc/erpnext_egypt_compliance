from datetime import datetime
import pytz

import frappe
import requests
import json



def download_eta_invoice_json(docname, file_content):
	is_pydantic_builder = frappe.db.get_single_value("ETA Settings",  "pydantic_builder")
	frappe.local.response.filename = f"{'PydanticBuilder-' if is_pydantic_builder else ''}ETA-{docname}.json"
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


def eta_round(_value: float, decimal: int = 5) -> float:
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
		update_eta_docstatus(connector,docname)
	frappe.db.commit()

def update_eta_docstatus(connector, docname):
        headers = connector.get_headers()
        uuid = frappe.get_value("Sales Invoice", docname, "eta_uuid")
        UUID_PATH = connector.ETA_BASE + f"/documents/{uuid}/raw"
        eta_response = connector.session.get(UUID_PATH, headers=headers)
        if eta_response.ok:
            eta_response = eta_response.json()
            frappe.db.set_value(
                "Sales Invoice", eta_response.get("internalId"), "eta_status", eta_response.get("status")
            )
            return eta_response.get("status")
        return "Didn't update Status"


def autofetch_eta_status_process():
	companies = frappe.get_all("Company", pluck="name")
	for company in companies:
		try:
			autofetch_eta_status(company)
		except:
			print("An exception occurred")  # TODO handle error properly.


def create_eta_log(
	posting_date: datetime = None,
	from_doctype: str = None,
	documents: list = None,
	status_code: str = None,
	submission_summary: str = "",
	submission_status: str = "Started",
	pos_profile: str = None
):
	doc = frappe.get_doc({
		"doctype": "ETA Log", 
		"from_doctype": from_doctype,
		"posting_date": posting_date or frappe.utils.now(),
		"status_code": status_code,
		"documents": documents or [],
		"submission_status": submission_status,
		"submission_summary": submission_summary,
		"pos_profile": pos_profile

	}).insert()
	return doc

def parse_error_details(error_object):
	error_object = frappe.parse_json(error_object)

	# Extract error message and target
	error_message = error_object.get("message", "No error message provided")
	error_target = error_object.get("target", "N/A")

	error_msg = f"Error Message: {error_message}\n"
	error_msg += f"Target: {error_target}\n"

	# Process error details
	error_details = error_object.get("details", [])
	for detail in error_details:
		code = detail.get("code", "N/A")
		message = detail.get("message", "No message provided")
		target = detail.get("target", "N/A")
		property_path = detail.get("propertyPath", "N/A")
		
		error_msg += f"\nDetail:\n"
		error_msg += f"  Code: {code}\n"
		error_msg += f"  Message: {message}\n"
		error_msg += f"  Target: {target}\n"
		error_msg += f"  Property Path: {property_path}\n"

	return error_msg


