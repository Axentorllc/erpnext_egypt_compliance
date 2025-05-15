frappe.ui.form.on("Sales Taxes and Charges Template", {
	onload(frm) {
		frm.trigger("set_query_for_eta_sub_type");
	},
	refresh(frm) {
		// write your code here
	},
	set_query_for_eta_sub_type(frm) {
		frm.set_query("eta_tax_sub_type", "taxes", function (doc, cdt, cdn) {
			row = locals[cdt][cdn];
			return {
				filters: {
					parent_eta_tax_type: row.eta_tax_type,
					is_group: 0
				},
			};
		});
	},
})
