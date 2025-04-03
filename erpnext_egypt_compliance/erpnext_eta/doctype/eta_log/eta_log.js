// Copyright (c) 2024, Axentor, LLC and contributors
// For license information, please see license.txt

frappe.ui.form.on("ETA Log", {
	refresh(frm) {
		if (frm.doc.submission_id) {
			frm.trigger("get_submission_status");
			frm.trigger("update_documents_status");
		}
		if (frm.doc.eta_submission_status === "Valid") {
			frm.trigger("update_receipts_status");
		}
	},
	get_submission_status(frm) {
		frm.add_custom_button("Get Submission Status", () => {
			try {
				frm.call({
					doc: frm.doc,
					method: "get_submission_status",
					freeze: true,
					freeze_message: __("Getting Submission Details")
					}).then((r) => {
						if (!r.exc) {
							frm.reload_doc();
							frappe.show_alert({ message: __("Getting submission details done"), indicator: "green" });
						}
					});
				} catch(e) {
					console.log(e);
			}
		}, "ETA Portal")
	},
	update_receipts_status(frm) {
		frm.add_custom_button("Get & Update receipts Status", () => {
			try {
				frm.call({
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
			}
		}, "ETA Portal")
	},
	update_documents_status(frm) {
		frm.add_custom_button("Update Documents Status", () => {
			try {
				frm.set_df_property("pos_profile", "read_only", 1);
				frm.call({
					doc: frm.doc,
					method: "update_documents_status",
					freeze: true,
					freeze_message: __("Updating Documents Status")
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
		}, "ETA Portal");
	},
});
