import frappe
from typing import Union, Dict, List
from erpnext_egypt_compliance.erpnext_eta.utils import get_company_eta_connector
from erpnext_egypt_compliance.erpnext_eta.utils import create_eta_log
from erpnext_egypt_compliance.erpnext_eta.einvoice_submitter import EInvoiceSubmitter


def submit_einvoice_using_logger(einvoices: Union[Dict, List[Dict]], company: str):
	"""
	Submits an e-invoice using the logger.
	Args:
		einvoice (Union[Dict, List[Dict]]): The e-invoice data to be submitted. Can be a single dictionary or a list of dictionaries.
		company (str): The name of the company for which the e-invoice is being submitted.
	Returns:
		dict: The response from the ETA after submitting the e-invoice.
	"""
	try:
		if isinstance(einvoices, dict):
			einvoices = [einvoices]  # convert to list

		connector = get_company_eta_connector(company)
		# create eta log
		documents = get_eta_documents(einvoices)
		eta_log = create_eta_log(documents=documents, from_doctype="Sales Invoice")
		# submit einvoice
		submitter = EInvoiceSubmitter(connector)
		eta_response = submitter.submit_documents(einvoices)
		# process eta response
		eta_log._process_response(eta_response)
		frappe.msgprint("ETA Log created successfully", indicator="blue", alert=True)
		return eta_response
	except Exception as e:
		frappe.log_error("E-Invoice Submission Error", f"Failed to submit e-invoice:\n {str(e)}",)
		frappe.msgprint("An error occurred while submitting the e-invoice.", indicator="red", alert=True)

def get_eta_documents(invoices: list) -> list:
	return [
		frappe._dict({"reference_doctype": "Sales Invoice", "reference_document": i.get("internalID", None)})
		for i in invoices
	]
