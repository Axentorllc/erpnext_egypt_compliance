frappe.ui.form.on('POS Invoice', {
  onload(frm) {
    console.log("onload");

    frm.trigger("eta_add_download_ereceipt_button");
  },
  eta_add_download_ereceipt_button(frm) {
    frm.add_custom_button('Download ETA Json', () => {
      frappe.call({
			method: 'erpnext_eta.erpnext_eta.ereceipt_schema.build_erceipt_json',
			args: {	docname: frm.doc.name },
			callback: function(r) {
				if (r.message) {
					console.log(r.message)
				}
			}
		})
		}, "ETA")
  }

});
