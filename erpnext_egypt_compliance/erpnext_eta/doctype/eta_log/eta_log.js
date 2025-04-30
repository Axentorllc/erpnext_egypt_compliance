// Copyright (c) 2024, Axentor, LLC and contributors
// For license information, please see license.txt

frappe.ui.form.on("ETA Log", {
	refresh(frm) {
		const { submission_id, pos_profile } = frm.doc;
		
		// Buttons related to eReceipt		
		if (submission_id && pos_profile) {
			frm.add_custom_button("Get Receipts Submission Status", () => { 
				frm.trigger("get_receipt_submission");
			}, "ETA Actions");

			frm.add_custom_button("Update Receipts Status", () => { 
				frm.trigger("update_receipts_status");
			}, "ETA Actions")
		}

		// Buttons related to eInvoice
		if (submission_id && !pos_profile) { 
			frm.add_custom_button("Get Invoices Submission Status", () => { 
				frm.trigger("update_invoices_status");
			}, "ETA Actions");
		}
	},
	async get_receipt_submission(frm) {
		try {
			await frm.call({
				doc: frm.doc,
				method: "get_submission_status",
				freeze: true,
				freeze_message: __("Getting Receipts Submission Details")
				}).then((r) => {
					if (!r.exc) {
						frm.reload_doc();
						frappe.show_alert({ message: __("Getting submission details done"), indicator: "green" });
					}
				});
			} catch(e) {
				console.log(e);
				frappe.show_alert({ 
					message: __("Failed to get submission details"), 
					indicator: "red" 
				});
		}
	},
	async update_receipts_status(frm) {
			try {
				await frm.call({
					doc: frm.doc,
					method: "update_receipts_status",
					freeze: true,
					freeze_message: __("Updating Receipts Status")
					}).then((r) => {
						if (!r.exc) {
							frm.reload_doc();
							frappe.show_alert({ message: __("Updating receipts status done"), indicator: "green" });
						}
					});
				} catch(e) {
				console.log(e);
				frappe.show_alert({ 
					message: __("Failed to update receipts status"), 
					indicator: "red" 
				});
			}
	},
	async update_invoices_status(frm) {
			try {
				await frm.call({
					doc: frm.doc,
					method: "update_documents_status",
					freeze: true,
					freeze_message: __("Updating Invoices Status")
				}).then((r) => {
					if (!r.exc) {
						frm.reload_doc();
						frappe.show_alert({ 
							message: __("Documents status updated successfully"), 
							indicator: "green" 
						});
					}
				});
			} catch(e) {
				console.error(e);
				frappe.show_alert({ 
					message: __("Failed to update documents status"), 
					indicator: "red" 
				});
			}
	},
});
