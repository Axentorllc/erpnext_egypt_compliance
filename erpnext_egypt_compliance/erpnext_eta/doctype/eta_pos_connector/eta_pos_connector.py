# Copyright (c) 2024, Axentor, LLC and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import requests
from frappe.utils import now, get_datetime
from frappe.integrations.utils import make_request
import json


class ETAPOSConnector(Document):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.PREPROD_URL = "https://api.preprod.invoicing.eta.gov.eg/api/v1"
		self.PREPROD_ID_URL = "https://id.preprod.eta.gov.eg/connect/token"
		self.PROD_URL = "https://api.invoicing.eta.gov.eg/api/v1"
		self.PROD_ID_URL = "https://id.eta.gov.eg/connect/token"

		self.ETA_BASE = self.PREPROD_URL
		self.ID_URL = self.PREPROD_ID_URL

		if self.environment == "Production":
			self.ETA_BASE = self.PROD_URL
			self.ID_URL = self.PROD_ID_URL

	def get_access_token(self):
		if self.access_token:
			access_token = self.get_password(fieldname="access_token", raise_exception=False)
		else:
			access_token = self.refresh_eta_token()
		return (
			access_token
			if (access_token and get_datetime(now()) < get_datetime(self.expires_in))
			else self.refresh_eta_token()
		)

	@frappe.whitelist()
	def refresh_eta_token(self):
		headers = {
			"content-type": "application/x-www-form-urlencoded",
			"posserial": self.serial_number,
			"pososversion": "os",
		}
		response = requests.post(
			self.ID_URL,
			data={
				"grant_type": "client_credentials",
				"client_id": self.client_id,
				"client_secret": self.get_password(fieldname="client_secret", raise_exception=False),
			},
			headers=headers,
		)

		if response.status_code == 200:
			eta_response = response.json()
			if eta_response.get("access_token"):
				self.access_token = eta_response.get("access_token")
				self.expires_in = frappe.utils.add_to_date(now(), seconds=eta_response.get("expires_in"))
				self.save(ignore_permissions=True)
				frappe.db.commit()
				return eta_response.get("access_token")
			
	def submit_erecipt(self, erecipe):	
		headers = {
			"Content-Type": "application/json; charset=utf-8",
			"Authorization": f"Bearer " + self.get_access_token(),
		}

		url = self.ETA_BASE + "/receiptsubmissions"

		data = json.dumps(erecipe, ensure_ascii=False).encode("utf8")
		try:
			eta_response = requests.post(url, headers=headers, data=data)
			eta_response = frappe._dict(eta_response.json())
			if eta_response.get("acceptedDocuments"):
				for doc in eta_response.get("acceptedDocuments"):
					if doc.get("receiptNumber"):
						_id = doc.get("receiptNumber")
						fields = {
							"custom_eta_uuid": doc.get("uuid"),
							"custom_eta_hash_key": doc.get("hashKey"),
							"custom_eta_long_id" : doc.get("longId"),
							"custom_eta_submission_id": eta_response.get("submissionId"),
							"custom_eta_status": "Submitted",
						}
						frappe.db.set_value("POS Invoice", _id, fields)
						frappe.db.commit()
			if eta_response.get("error"):
				frappe.log_error("Submit E-Receipt", message=eta_response.get("error"), reference_doctype="POS Invoice")

		except Exception as e:
			traceback = frappe.get_traceback()
			frappe.log_error("Submit E-Receipt", message=traceback)
		return eta_response
	
	def update_ereceipt_docstatus(self, docname):
		# Get access token
		access_token = self.get_access_token()
		
		if not access_token:
			return "Failed to get access token"
		
		headers = {
			"content-type": "application/json;charset=utf-8",
			"Authorization": "Bearer " + access_token
		}
		
		# Get UUID from POS Invoice
		uuid = frappe.get_value("POS Invoice", docname, "custom_eta_uuid")
		
		if not uuid:
			return "UUID not found for document: {}".format(docname)
		
		UUID_PATH = self.ETA_BASE + f"/receipts/{uuid}/details"

		# Send request to ETA service
		try:
			eta_response = requests.get(UUID_PATH, headers=headers)
			eta_response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes
		except requests.RequestException as e:
			frappe.log_error(title="Error fetching ETA details", message=e, reference_doctype="POS Invoice", reference_name=docname)
			return "Error fetching ETA details: {}".format(str(e))
		
		# Process ETA response
		if eta_response.ok:
			eta_data = eta_response.json()
			receipt_number = eta_data["receipt"]["receiptNumber"]
			
			if receipt_number:
				frappe.db.set_value("POS Invoice", docname, "custom_eta_status", eta_data["receipt"]["status"])
				return eta_data["receipt"]["status"]
		
		return "Failed to update status for document: {}".format(docname)
	
	def get_receipt_submission(self, docname):
		access_token = self.get_access_token()
		
		headers = {
			"content-type": "application/json;charset=utf-8",
			"Authorization": "Bearer " + access_token
		}
		
		submission_id = frappe.get_value("POS Invoice", docname, "custom_eta_submission_id")
		
		if not submission_id:
			return "UUID not found for document: {}".format(docname)
		
		url = self.ETA_BASE + f"/receiptsubmissions/{submission_id}/details?ReceiptNumber={docname}&PageNo=1&PageSize=10"
		# Send request to ETA service
		try:
			eta_response = requests.get(url, headers=headers)
			eta_response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes
		except requests.RequestException as e:
			frappe.log_error(title="Error fetching ETA details", message=e, reference_doctype="POS Invoice", reference_name=docname)
			return "Error fetching ETA details: {}".format(str(e))
		
		# Process ETA response
		if eta_response.ok:
			eta_data = eta_response.json()
			status = eta_data["status"]
			frappe.db.set_value("POS Invoice", docname, "custom_eta_status", status)
			result = frappe._dict({"status": status, "errors": []})
			for r in eta_data["receipts"]:
				if r.get("errors"):
					result["errors"].extend([error for error in r.get("errors")])
			return result
		
		return "Failed to update status for document: {}".format(docname)