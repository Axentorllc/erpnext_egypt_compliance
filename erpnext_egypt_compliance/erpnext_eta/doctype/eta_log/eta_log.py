# Copyright (c) 2024, Axentor, LLC and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from erpnext_egypt_compliance.erpnext_eta.utils import parse_error_details
from erpnext_egypt_compliance.erpnext_eta.ereceipt_submitter import EReceiptSubmitter
import json


class ETALog(Document):
	def process_documents(self, eta_response, doctype, log_name):
		for doc in eta_response.get("acceptedDocuments", []):
			if doc.get("receiptNumber"):
				docname = doc.get("receiptNumber")
				self.update_eta_fields(doctype, docname, doc, eta_response.get("submissionId"))
				fields = {"uuid": doc.get("uuid"), "long_id": doc.get("longId"), "accepted": True}
				child_docname = frappe.db.get_value(
					"ETA Log Documents",
					{"parent": log_name.get("name"), "reference_doctype": doctype, "reference_document": docname},
					as_dict=True,
				)
				frappe.db.set_value("ETA Log Documents", child_docname.get("name"), fields)

		for doc in eta_response.get("rejectedDocuments", []):
			if doc.get("receiptNumber"):
				docname = doc.get("receiptNumber")
				self.update_eta_fields(doctype, docname, doc, eta_response.get("submissionId"))
				fields = {
					"uuid": doc.get("uuid"),
					"error": parse_error_details(doc.get("error", {})),
					"accepted": False,
				}
				frappe.db.set_value(
					dt="ETA Log Documents",
					dn={"parent": log_name.get("name"), "reference_doctype": doctype, "reference_document": docname},
					field=fields,
				)

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

	@frappe.whitelist()
	def get_submission_status(self):
		connector = frappe.get_doc("ETA POS Connector", self.pos_profile)
		submitter = EReceiptSubmitter(connector)
		eta_response = submitter.get_receipt_submission(self.submission_id)

		if eta_response.get("status") == "Invalid":
			# update submission status
			self.db_set("submission_status", "Partially Succeeded")

		if eta_response and isinstance(eta_response, dict):
			meg = f"receipts Count = {eta_response.get('receiptsCount')}\ninvalid Receipts Count = {eta_response.get('invalidReceiptsCount')}"
			self.db_set("submission_summary", meg)
			receipts = [
				{"receiptNumber": r.get("receiptNumber"), "uuid": r.get("uuid"), "errors": r.get("errors")}
				for r in eta_response.get("receipts", [])
				if r.get("errors")
			]

			for r in receipts:
				if r.get("errors"):
					# update errors on child table
					frappe.db.set_value(
						dt="ETA Log Documents",
						dn={"parent": self.name, "uuid": r["uuid"], "reference_document": r.get("receiptNumber")},
						field={
							"error": str(r.get("errors")),
							"accepted": False,
						},
					)
					r.pop("errors")

			eta_response["receipts"] = receipts
			self.db_set("eta_submission_status", eta_response.get("status"))
			self.db_set("eta_response", str(json.dumps(eta_response, indent=4)))

	@frappe.whitelist()
	def update_receipts_status(self):
		connector = frappe.get_doc("ETA POS Connector", self.pos_profile)
		submitter = EReceiptSubmitter(connector)
		for doc in self.documents:
			eta_response = submitter.get_receipt_status(doc.uuid)
			fieldname = "eta_status" if doc.reference_doctype == "Sales Invoice" else "custome_eta_status"
			if isinstance(eta_response, dict):
				if eta_response.get("receipt", {}).get("status"):
					receipt_status = eta_response["receipt"]["status"]
					frappe.db.set_value(doc.reference_doctype, doc.reference_document, fieldname, receipt_status)
					doc.db_set("eta_status", receipt_status)
