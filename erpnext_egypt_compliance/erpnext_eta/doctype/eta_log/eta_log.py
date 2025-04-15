# Copyright (c) 2024, Axentor, LLC and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe.model.document import Document
from erpnext_egypt_compliance.erpnext_eta.utils import parse_error_details
from erpnext_egypt_compliance.erpnext_eta.ereceipt_submitter import EReceiptSubmitter
import json
from erpnext_egypt_compliance.erpnext_eta.utils import get_company_eta_connector
from erpnext_egypt_compliance.erpnext_eta.einvoice_submitter import EInvoiceSubmitter


class ETALog(Document):

    def _process_response(self, eta_response):
        if eta_response.get("acceptedDocuments") or eta_response.get("rejectedDocuments"):
            self._handle_success_response(eta_response)

        if eta_response.get("error"):
            self._handle_error_response(eta_response)

        return eta_response

    def _handle_success_response(self, eta_response):

        summary_message = (
            f"Total No of Accepted: {len(eta_response.get('acceptedDocuments', []))}\n"
            f"Total No of Rejected: {len(eta_response.get('rejectedDocuments', []))}\n"
        ).strip()
        submission_status = (
			"Failed" if len(eta_response.get('acceptedDocuments', [])) == 0 
			else "Partially Succeeded" if (len(eta_response.get('acceptedDocuments', [])) < len(self.documents))
			else "Completed"
		)
        self.status_code = eta_response.get("status_code", None)
        self.submission_id = eta_response.get("submissionId")
        self.submission_summary = summary_message
        self.submission_status = submission_status
        self.process_documents(eta_response)
        self.save()

    def _handle_error_response(self, eta_response):
        self.status_code = eta_response.get("status_code", None)
        self.eta_response = str(eta_response.get("error"))
        self.submission_status = "Failed"
        self.save()

    def process_documents(self, eta_response):
        internal_id_key = "internalId" if self.from_doctype == "Sales Invoice" else "receiptNumber"
        child_rows = frappe._dict({row.reference_document: row for row in self.get("documents", default=[])})

        for doc in eta_response.get("acceptedDocuments", []):
            if doc.get(internal_id_key):
                docname = doc.get(internal_id_key)
                self.update_eta_fields(doc, docname, eta_response, eta_response.get("submissionId"), "Submitted")
                fields = {"uuid": doc.get("uuid"), "long_id": doc.get("longId"), "accepted": True}
                child_rows.get(docname, {}).update(fields)

        for doc in eta_response.get("rejectedDocuments", []):
            if doc.get(internal_id_key):
                docname = doc.get(internal_id_key)
                self.update_eta_fields(doc, docname, eta_response, eta_response.get("submissionId"))
                fields = {
                    "uuid": doc.get("uuid"),
                    "error": parse_error_details(doc.get("error", {})),
                    "accepted": False,
                }
                child_rows.get(docname, {}).update(fields)

    def update_eta_fields(self, doc, docname, eta_response, submission_id, eta_status=None):
        if self.from_doctype == "Sales Invoice":
            fields = {
                "eta_uuid": doc.get("uuid"),
                "eta_hash_key": doc.get("hashKey"),
                "eta_long_key": doc.get("longId"),
                "eta_submission_id": submission_id,
                "eta_status": eta_status,
            }
        else:
            fields = {
                "custom_eta_uuid": doc.get("uuid"),
                "custom_eta_hash_key": doc.get("hashKey"),
                "custom_eta_long_id": doc.get("longId"),
                "custom_eta_submission_id": submission_id,
                "custom_eta_status": eta_status,
            }
        frappe.db.set_value(self.from_doctype, docname, fields)

    @frappe.whitelist()
    def get_submission_status(self):
        # TODO: Need to Migrate to EReceiptSubmitter
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
        # TODO: Need to Migrate to EReceiptSubmitter
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


    @frappe.whitelist()
    def update_documents_status(self):
        try:
            # Check and update document statuses from ETA submission details
            if not self.submission_id:
                frappe.throw("Submission ID is required to check status")

            # Retrieve the connector from the first document in the child table
            sinv_doc_company = frappe.get_value("Sales Invoice", self.documents[0], "company")
            connector = get_company_eta_connector(sinv_doc_company)

            submission_response = self._get_submission_details(connector)
            
            if not submission_response:
                frappe.msgprint('No submission response')
                return
                
            self._update_documents_from_submission(submission_response)
            self.save()
                        
        except requests.RequestException as e:
            frappe.log_error(f"ETA API Request Failed: {str(e)}", "ETA API Error")
            frappe.throw(f"Failed to fetch submission details: {str(e)}")

    def _get_submission_details(self, connector):
        url = f"{connector.ETA_BASE}/documentSubmissions/{self.submission_id}"
		
        submitter = EInvoiceSubmitter(connector)
        page_no = len(self.documents)
        submission_response = submitter.get_submission_details(self.submission_id, page_no)
        return submission_response

    def _update_documents_from_submission(self, submission_response):
        # Map internal IDs to their document details
        document_map = {
            doc.get("internalId"): doc 
            for doc in submission_response.get("documentSummary", [])
        }
        
        # a dictionary to count document statuses
        status_counts = {
            "Submitted": 0,
            "Valid": 0,
            "Invalid": 0,
            "Rejected": 0,
            "Cancelled": 0
        }
        for doc_row in self.documents:
            eta_doc = document_map.get(doc_row.reference_document)
            if not eta_doc:
                continue
            
            # Update the status count
            status = eta_doc.get("status")
            if status in status_counts:
                status_counts[status] += 1
            
            doc_row.update({
                "uuid": eta_doc.get("uuid"),
                "eta_status": eta_doc.get("status"),
                "long_id": eta_doc.get("longId"), 
                "accepted": eta_doc.get("status") == "Valid",
                "custom_eta_public_url": eta_doc.get("publicUrl"),
                "error": eta_doc.get("documentStatusReason") if eta_doc.get("documentStatusReason") else ""
            })
            frappe.db.set_value("Sales Invoice", doc_row.reference_document, "eta_status", status)
        # Map ETA status to internal submission status
        self.submission_status = {
            "Valid": "Completed",
            "Partially Valid": "Partially Succeeded", 
            "In Progress": "Started",
            "Invalid": "Failed"
        }.get(submission_response.get("overallStatus"))
        
        metadata = submission_response.get("metadata", {})
        
        summary = [
            f"Total Documents: {metadata.get('totalCount', 0)}",
            f"Submitted: {status_counts['Submitted']}",
            f"Valid Documents: {status_counts['Valid']}",
            f"Invalid Documents: {status_counts['Invalid']}",
            f"Rejected: {status_counts['Rejected']}",
            f"Cancelled: {status_counts['Cancelled']}",
        ]
        
        self.submission_summary = "\n".join(summary)
        # Store full response
        self.eta_response = json.dumps(submission_response, indent=4)