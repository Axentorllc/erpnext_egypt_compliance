// Copyright (c) 2024, Axentor, LLC and contributors
// For license information, please see license.txt

frappe.ui.form.on("ETA POS Connector", {
	refresh(frm) {
		frm.add_custom_button(__("Get Access Token"), () => {
			frm.trigger("get_access_token")
		}).addClass("btn btn-primary")
	},
	get_access_token: function (frm) {
		try {
			frm.call({
				method: "refresh_eta_token",
				doc: frm.doc,
				freeze: true,
				freeze_message: __("Getting Access Token ...")
			}).then((r) => {
				if (!r.exc) {
					frappe.show_alert({ message: __("Access Token Updated"), indicator: "green" });
				}
			});
		} catch(e) {
			console.log(e);
		}
	}
});
