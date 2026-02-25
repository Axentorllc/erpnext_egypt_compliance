# Copyright (c) 2024, Axentor, LLC and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import requests
from frappe.utils import now, get_datetime
from frappe.integrations.utils import make_request
import json
from erpnext_egypt_compliance.erpnext_eta.utils import create_eta_log, parse_error_details

from requests.adapters import HTTPAdapter
import ssl
import urllib3

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
		# Add 3-minute buffer before expiry (matches B2B connector behavior)
		expiry_with_buffer = frappe.utils.add_to_date(get_datetime(now()), minutes=3)
		return (
			access_token
			if (access_token and expiry_with_buffer < get_datetime(self.expires_in))
			else self.refresh_eta_token()
		)

	@frappe.whitelist()
	def refresh_eta_token(self):
		eta_session = ETASession().get_session()

		headers = {
			"content-type": "application/x-www-form-urlencoded",
			"posserial": self.serial_number,
			"pososversion": self.pos_os_version,
		}
		response = eta_session.post(
			self.ID_URL,
			data={
				"grant_type": "client_credentials",
				"client_id": self.client_id,
				"client_secret": self.get_password(fieldname="client_secret", raise_exception=False),
			},
			headers=headers
		)

		# Handle non-200 responses explicitly
		if response.status_code != 200:
			error_detail = ""
			try:
				error_detail = response.json()
			except Exception:
				error_detail = response.text
			frappe.log_error(
				title="ETA POS Token Refresh Failed",
				message=f"HTTP {response.status_code}: {error_detail}",
			)
			frappe.throw(
				frappe._("Failed to refresh ETA POS access token (HTTP {0}): {1}").format(
					response.status_code, str(error_detail)[:200]
				),
				title=frappe._("ETA Authentication Error"),
			)

		# Check for access token in response
		eta_response = response.json()
		if not eta_response.get("access_token"):
			frappe.log_error(
				title="ETA POS Token Refresh Failed",
				message=f"ETA returned 200 but no access_token. Response: {eta_response}",
			)
			frappe.throw(
				frappe._("ETA identity server returned success but no access token was received."),
				title=frappe._("ETA Authentication Error"),
			)

		# Token refresh successful
		self.access_token = eta_response.get("access_token")
		self.expires_in = frappe.utils.add_to_date(now(), seconds=eta_response.get("expires_in"))
		self.save(ignore_permissions=True)
		frappe.db.commit()
		return eta_response.get("access_token")
			
  
class ETASession:
	def __init__(self):
		# Create a SSLContext object with TLSv1.2
		ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
		# ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
		# ssl_context.options |= ssl.OP_NO_RENEGOTIATION
		ssl_context.options |= 0x4
		# Create a new Requests Session
		self.session = requests.Session()

		# Create an adapter with the SSL context
		adapter = HTTPAdapter(
			pool_connections=100,
			pool_maxsize=100,
			max_retries=3,
			pool_block=True
		)
		adapter.poolmanager = urllib3.PoolManager(
			num_pools= adapter._pool_connections,
			maxsize= adapter._pool_maxsize,
			block= adapter._pool_block,
			ssl_context=ssl_context
		)

		# Mount the adapter to the session
		self.session.mount('https://', adapter)


	def get_session(self):
		return self.session