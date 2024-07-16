// Copyright (c) 2024, Axentor, LLC and contributors
// For license information, please see license.txt

frappe.ui.form.on("ETA Log", {
	refresh(frm) {
		if (frm.doc.submission_id) {
			frm.trigger("get_submission_status");
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
					args: {
						submission_id: frm.doc.submission_id,
						pos_profile: frm.doc.pos_profile,
					},
					freeze: true,
					freeze_message: __("Getting Submission Details")
					}).then((r) => {
						if (!r.exc) {
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
					args: {
						pos_profile: frm.doc.pos_profile,
					},
					freeze: true,
					freeze_message: __("Updating Receipts Status")
					}).then((r) => {
						if (!r.exc) {
							frappe.show_alert({ message: __("Updating receipts status done"), indicator: "green" });
						}
					});
				} catch(e) {
					console.log(e);
			}
		}, "ETA Portal")
	}
});
