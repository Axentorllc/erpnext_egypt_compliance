
import frappe
from erpnext_egypt_compliance.erpnext_eta.ereceipt_schema import submit_ereceipt

def submit_bulk_ereceipts(doctype: str, filters: dict):
	args = frappe._dict(filters)
	douments = frappe.db.get_all(
		doctype,
		filters=args,
		fields=["name", "pos_profile"]
	)
	for doc in douments:
		print(f"Proccess {doc.name}")
		submit_ereceipt(doc.name, doc.get("pos_profile"), doctype, False)
	print("Done :)")