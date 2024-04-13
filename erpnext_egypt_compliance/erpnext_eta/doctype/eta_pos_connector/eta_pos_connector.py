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
			"content-type": "application/json; charset=utf-8",
			"Authorization": f"Bearer " + self.get_access_token(),
		}
		
		url = self.ETA_BASE + "/receiptsubmissions"

		data = json.dumps(erecipe, ensure_ascii=False).encode("utf8")
		eta_response = make_request(method="POST", url=url, data=data, headers=headers)
		eta_response = frappe._dict(eta_response)
		if eta_response.get("acceptedDocuments"):
			for doc in eta_response.get("acceptedDocuments"):
				if doc.get("internalId"):
					_id = doc.get("internalId")
					fields = {
						"custom_eta_uuid": doc.get("uuid"),
						"eta_hash_key": doc.get("hashKey"),
						"custom_eta_long_id" : doc.get("longId"),
						"custom_eta_status": "Submitted",
					}
					frappe.db.set_value("POS Invoice", _id, field=fields)
					frappe.db.commit()
		return eta_response