import frappe
from erpnext_egypt_compliance.erpnext_eta.doctype.eta_pos_connector.eta_pos_connector import ETASession
import json
from erpnext_egypt_compliance.erpnext_eta.utils import create_eta_log
import requests

class EReceiptSubmitter:
    """
    A class to submit e-receipts to the ETA portal.

    Attributes:
        eta_connector: An instance of ETA connector to handle sessions and tokens.
    """

    def __init__(self, eta_connector):
        """
        Initialize the EReceiptSubmitter with an ETA connector.
        """
        self.eta_connector = eta_connector

    def submit_ereceipt(self, ereceipts, doctype):
        """
        Submit e-receipts to the ETA portal.

        Args:
            ereceipts (dict): A dictionary of e-receipts to be submitted.
            doctype (str): The document type of the receipts.

        Returns:
            dict: The response from the ETA portal.
        """
        headers = self._get_headers()
        url = self._get_submission_url()
        data = self._prepare_data(ereceipts)

        try:
            eta_response = self._send_submit_request(url, headers, data)
            processed_response = self._process_response(eta_response, ereceipts, doctype)
            frappe.db.commit()
            return processed_response
        except Exception as e:
            self._handle_exception(e)
            return {"error": str(e)}
    
    def get_receipt_submission(self, submission_id):
        """
        Get the submission details from the ETA portal.
        """
        try:
            access_token = self.eta_connector.get_access_token()
            headers = self._get_headers()

            url = f"{self.eta_connector.ETA_BASE}/receiptsubmissions/{submission_id}/details?PageNo=1&PageSize=100"
            eta_session = ETASession().get_session()
            eta_response = eta_session.get(url, headers=headers)
            eta_response.raise_for_status()
            eta_data = eta_response.json()

            return eta_data

        except requests.RequestException as e:
            frappe.log_error(title="Get e-receipt submission", message=str(e))
            return f"Error when Get e-receipt submission: {str(e)}"

        except Exception as e:
            frappe.log_error(title="Unexpected error in get_receipt_submission", message=str(e))
    
    def get_receipt_status(self, uuid):
        try:
            access_token = self.eta_connector.get_access_token()
            headers = self._get_headers()

            url = f"{self.eta_connector.ETA_BASE}/receipts/{uuid}/raw/"
            eta_session = ETASession().get_session()
            eta_response = eta_session.get(url, headers=headers)
            eta_response.raise_for_status()
            eta_data = eta_response.json()
            return eta_data

        except requests.RequestException as e:
            frappe.log_error(title="Get e-receipt Status", message=str(e))
            return f"Error when Get e-receipt status: {str(e)}"

    def _get_headers(self):
        """
        Get the headers required for the request.

        Returns:
            dict: A dictionary of headers.
        """
        return {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer " + self.eta_connector.get_access_token(),
        }

    def _get_submission_url(self):
        return self.eta_connector.ETA_BASE + "/receiptsubmissions"

    def _prepare_data(self, ereceipts):
        """
        Prepare the e-receipts data for submission.

        Args:
            ereceipts (dict): A dictionary of e-receipts.

        Returns:
            bytes: The JSON-encoded data.
        """
        return json.dumps(ereceipts, ensure_ascii=False).encode("utf8")

    def _send_submit_request(self, url, headers, data):
        """
        Send the request to the ETA portal.

        Args:
            url (str): The submission URL.
            headers (dict): The request headers.
            data (bytes): The JSON-encoded data.

        Returns:
            dict: The response from the ETA portal.
        """
        eta_session = ETASession().get_session()
        response = eta_session.post(url, headers=headers, data=data)
        
        # Log request details for debugging
        try:
            request_data = json.loads(data.decode('utf-8')) if isinstance(data, bytes) else data
            frappe.log_error(
                title="E-Receipt Submission - Request Details",
                message=f"Request URL: {url}\nStatus Code: {response.status_code}\nRequest Data (first receipt): {json.dumps(request_data.get('receipts', [{}])[0] if request_data.get('receipts') else {}, indent=2, ensure_ascii=False)}",
            )
        except Exception:
            pass  # Don't fail if logging fails
        
        try:
            _eta_response = frappe._dict(response.json())
        except json.JSONDecodeError:
            # If response is not JSON, log the raw response
            frappe.log_error(
                title="E-Receipt Submission - Invalid JSON Response",
                message=f"Status Code: {response.status_code}\nResponse Text: {response.text[:1000]}"
            )
            _eta_response = frappe._dict({"error": f"Invalid JSON response. Status: {response.status_code}", "status_code": response.status_code})
            return _eta_response
        
        _eta_response["status_code"] = response.status_code or None
        return _eta_response

    def _process_response(self, eta_response, ereceipts, doctype):
        """
        Process the response from the ETA portal.

        Args:
            eta_response (dict): The response from the ETA portal.
            ereceipts (dict): The submitted e-receipts.
            doctype (str): The document type of the receipts.

        Returns:
            dict: The processed response.
        """
        documents = [
            {"reference_doctype": doctype, "reference_document": d.get("header")["receiptNumber"]}
            for d in ereceipts.get("receipts", [])
        ]
        initial_eta_log = create_eta_log(
            from_doctype=doctype,
			pos_profile=self.eta_connector.pos_profile,
            documents=documents,
            submission_summary=f"Total no of receipts: {len(ereceipts.get('receipts'))}"
        )

        if eta_response.get("acceptedDocuments") or eta_response.get("rejectedDocuments"):
            self._handle_success_response(eta_response, ereceipts, initial_eta_log, doctype)

        if eta_response.get("error"):
            self._handle_error_response(eta_response, initial_eta_log)

        return eta_response

    def _handle_success_response(self, eta_response, ereceipts, eta_log, doctype):
        """
        Handle the successful response from the ETA portal.

        Args:
            eta_response (dict): The response from the ETA portal.
            ereceipts (dict): The submitted e-receipts.
            eta_log (Document): The ETA Log document.
        """
        from erpnext_egypt_compliance.erpnext_eta.utils import parse_error_details
        
        rejected_docs = eta_response.get('rejectedDocuments', [])
        accepted_docs = eta_response.get('acceptedDocuments', [])
        
        # Build detailed summary with rejection reasons
        summary_parts = [
            f"Total no of receipts: {len(ereceipts.get('receipts'))}",
            f"Total no of accepted: {len(accepted_docs)}",
            f"Total no of rejected: {len(rejected_docs)}"
        ]
        
        # Add detailed rejection information
        if rejected_docs:
            summary_parts.append("\n--- Rejected Receipts Details ---")
            for rejected_doc in rejected_docs:
                receipt_num = rejected_doc.get("receiptNumber") or rejected_doc.get("internalId", "Unknown")
                error_info = rejected_doc.get("error", {})
                error_msg = parse_error_details(error_info) if error_info else "No error details provided"
                summary_parts.append(f"\nReceipt: {receipt_num}")
                summary_parts.append(f"Error: {error_msg}")
                if rejected_doc.get("uuid"):
                    summary_parts.append(f"UUID: {rejected_doc.get('uuid')}")
        
        summary_message = "\n".join(summary_parts)
        
        submission_status = (
            "Partially Succeeded" if (len(accepted_docs) < len(ereceipts.get('receipts', [])))
            else "Completed"
        )
        eta_log.status_code = eta_response.get("status_code", None)
        eta_log.submission_id = eta_response.get("submissionId")
        eta_log.submission_summary = summary_message
        eta_log.submission_status = submission_status
        
        # Log detailed error information
        if rejected_docs:
            error_details = json.dumps({
                "rejected_documents": rejected_docs,
                "full_response": eta_response
            }, indent=2, ensure_ascii=False)
            frappe.log_error(
                title="E-Receipt Submission - Rejected Documents",
                message=f"Receipts were rejected during submission.\n\n{summary_message}\n\nFull Response:\n{error_details}",
                reference_doctype=doctype
            )
        
        eta_log.save()
        eta_log.process_documents(eta_response)

    def _handle_error_response(self, eta_response, initial_eta_log):
        """
        Handle the error response from the ETA portal.

        Args:
            eta_response (dict): The response from the ETA portal.
            initial_eta_log (Document): The initial log document.
        """
        error_details = eta_response.get("error", {})
        error_message = json.dumps(error_details, indent=2, ensure_ascii=False) if isinstance(error_details, dict) else str(error_details)
        
        initial_eta_log.status_code = eta_response.get("status_code", None)
        initial_eta_log.eta_response = error_message
        initial_eta_log.submission_status = "Failed"
        initial_eta_log.save()
        
        # Log detailed error information
        full_response = json.dumps(eta_response, indent=2, ensure_ascii=False)
        frappe.log_error(
            title="E-Receipt Submission - Error Response",
            message=f"ETA API returned an error response.\n\nError Details:\n{error_message}\n\nFull Response:\n{full_response}",
            reference_doctype=initial_eta_log.from_doctype
        )

    def _handle_exception(self, exception):
        """
        Handle exceptions that occur during the submission process.

        Args:
            exception (Exception): The caught exception.
        """
        traceback = frappe.get_traceback()
        frappe.log_error("Submit E-Receipt", message=traceback)
