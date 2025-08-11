import frappe
from typing import Union, Dict, List
from erpnext_egypt_compliance.erpnext_eta.utils import get_company_eta_connector
from erpnext_egypt_compliance.erpnext_eta.utils import create_eta_log
from erpnext_egypt_compliance.erpnext_eta.einvoice_submitter import EInvoiceSubmitter



def get_eta_documents(invoices: list) -> list:
	return [
		frappe._dict({"reference_doctype": "Sales Invoice", "reference_document": i.get("internalID", None)})
		for i in invoices
	]


def _submit_einvoice(einvoices: Union[Dict, List[Dict]], connector ,show_msg=False):
	"""
	Submits an e-invoice using the logger.
	Args:
		einvoice (Union[Dict, List[Dict]]): The e-invoice data to be submitted. Can be a single dictionary or a list of dictionaries.
		company (str): The name of the company for which the e-invoice is being submitted.
	Returns:
		dict: The response from the ETA after submitting the e-invoice.
	"""
	try:
		# Always ensure einvoices is a list
		if isinstance(einvoices, dict):
			einvoices = [einvoices]

		# Fetch ETA connector for the company
		# connector = get_company_eta_connector(company)

		# Prepare ETA log
		documents = get_eta_documents(einvoices)
		eta_log = create_eta_log(documents=documents, from_doctype="Sales Invoice")

		# Submit documents
		submitter = EInvoiceSubmitter(connector)
		eta_response = submitter.submit_documents(einvoices)

		# Process response
		eta_log._process_response(eta_response)

		# User feedback (only in manual case)
		if show_msg:
			frappe.msgprint(f" ETA Log created successfully", indicator="blue", alert=True)

		return eta_response

	except Exception as e:
		error_msg = f" Failed to submit e-invoice for company ': {str(e)}"
		frappe.log_error(title=f" E-Invoice Submission Error", message=error_msg)
		if show_msg:
			frappe.msgprint("An error occurred while submitting the e-invoice.", indicator="red", alert=True)
		raise


# public wrappers for the submit functions
def submit_einvoice_feedback_logger(einvoices: Union[Dict, List[Dict]], connector):
	return _submit_einvoice(einvoices, connector ,show_msg=True)


def submit_einvoice_background_logger(einvoices: Union[Dict, List[Dict]], connector):
	return _submit_einvoice(einvoices, connector, show_msg=False)
