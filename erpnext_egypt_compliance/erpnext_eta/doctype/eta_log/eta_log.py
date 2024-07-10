# Copyright (c) 2024, Axentor, LLC and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from erpnext_egypt_compliance.erpnext_eta.utils import (
	parse_error_details
)


class ETALog(Document):

	def process_documents(self, eta_response, doctype, log_name):
		for doc in eta_response.get("acceptedDocuments", []):
			if doc.get("receiptNumber"):
				docname = doc.get("receiptNumber")
				self.update_eta_fields(doctype, docname, doc, eta_response.get("submissionId"))
				fields = {"uuid": doc.get("uuid"), "long_id": doc.get("longId"), "accepted": True}
				child_docname = frappe.db.get_value("ETA Log Documents", {"parent": log_name.get("name"), "reference_doctype": doctype ,"reference_document": docname}, as_dict=True)
				frappe.db.set_value("ETA Log Documents", child_docname.get("name"), fields)

		
		for doc in eta_response.get("rejectedDocuments", []):
			if doc.get("receiptNumber"):
				docname = doc.get("receiptNumber")
				self.update_eta_fields(doctype, docname, doc, eta_response.get("submissionId"))
				fields = {"uuid": doc.get("uuid"), "error": parse_error_details(doc.get("error", {})), "accepted": False}
				frappe.db.set_value(dt="ETA Log Documents", dn={"parent": log_name.get("name"), "reference_doctype": doctype ,"reference_document": docname}, field=fields)
	
	def update_eta_fields(self, doctype, docname, eta_response, submissionId):
		if doctype == "Sales Invoice":
			fields = {
				"eta_uuid": eta_response.get("uuid"),
				"eta_hash_key": eta_response.get("hashKey"),
				"eta_long_key": eta_response.get("longId"),
				"eta_submission_id": submissionId,
				"eta_status": "Submitted",
			}
		else:
			fields = {
				"custom_eta_uuid": eta_response.get("uuid"),
				"custom_eta_hash_key": eta_response.get("hashKey"),
				"custom_eta_long_id": eta_response.get("longId"),
				"custom_eta_submission_id": submissionId,
				"custom_eta_status": "Submitted",
			}
		frappe.db.set_value(doctype, docname, fields)

