import frappe
from erpnext_egypt_compliance.hooks import app_title


def after_uninstall():
	"""Remove all custom fields created by this app"""
	# Frappe automatically removes custom fields by module, this is a safety check
	custom_fields = frappe.get_all("Custom Field", filters={"module": app_title}, pluck="name")

	if not custom_fields:
		return

	# Delete remaining custom fields
	for field_name in custom_fields:
		frappe.delete_doc("Custom Field", field_name, force=True, ignore_missing=True)

	frappe.db.commit()
	print(f"Cleaned up {len(custom_fields)} remaining custom fields")
