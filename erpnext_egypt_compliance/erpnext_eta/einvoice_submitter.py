import frappe
import json
from erpnext_egypt_compliance.erpnext_eta.doctype.eta_connector.eta_connector import ETAConnector

class EInvoiceSubmitter:
    """
    A class to submit e-invoices to the ETA portal.

    Attributes:
        eta_connector: An instance of ETA connector the tokens.
    """

    def __init__(self, eta_connector: ETAConnector):
        self.eta_connector = eta_connector

    def submit_documents(self, invoices):		
        try:
            data = self._prepare_data(invoices)
            eta_response = self._send_submit_request(data)
            return eta_response

        except Exception as e:
            self._handle_exception(e)
            frappe.msgprint(alert=True, message="An error occurred while submitting the e-invoice.", indicator="red")
            return {"error": str(e)}
    
    def _prepare_data(self, einvoices):
        data = frappe._dict({"documents": einvoices})
        return json.dumps(data, ensure_ascii=False).encode("utf8")

    def _send_submit_request(self, data):
        url = self.eta_connector.DOCUMET_SUBMISSION
        headers = self.eta_connector.get_headers()
        response = self.eta_connector.session.post(url, headers=headers, data=data)
        _eta_response = frappe._dict(response.json())
        _eta_response["status_code"] = response.status_code or None
        return _eta_response

    def _handle_exception(self, exception):
        traceback = frappe.get_traceback()
        error_doc = frappe.log_error("Submit EInvoice", message=str(exception) + "\n" + str(traceback))

    def get_submission_details(self, submission_id, page_no=1):
        """
        Fetch document submission details from ETA API.
        """
        headers = self.eta_connector.get_headers()
        headers.update({
            "PageSize": "20",
            "PageNo": str(page_no)
        })
        url = f"{self.eta_connector.ETA_BASE}/documentSubmissions/{submission_id}"
        try:
            response = self.eta_connector.session.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            message = f"Failed to fetch submission details: {e}"
            if response is not None:
                try:
                    message += f"\nResponse: {response.text}"
                except Exception:
                    pass
            frappe.log_error(message)
            return frappe._dict()
