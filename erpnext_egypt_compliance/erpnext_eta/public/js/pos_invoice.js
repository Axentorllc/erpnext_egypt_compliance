frappe.ui.form.on('POS Invoice', {
  onload(frm) {
    console.log("onload");

    frm.trigger("eta_add_download_ereceipt_button");
  },
  eta_add_download_ereceipt_button(frm) {
	  frm.add_custom_button('Download eReceipt Json', () => {
		var url = frappe.urllib.get_base_url() + '/api/method/erpnext_egypt_compliance.erpnext_eta.ereceipt_schema.build_erceipt_json?docname=' + encodeURIComponent(frm.doc.name)
      
			$.ajax({
				url: url,
				type: 'GET',
				success: function (result) {
					if (jQuery.isEmptyObject(result)) {
						frappe.msgprint('Failed to load e-Receipt format.');
					}
					else {
						window.location = url;
					}
					if (result.exc){
						console.log(exc)
					}
				},
				error:(r) => {
					if (r.responseJSON.exc_type) {
						console.log(r)
						var server_massages =  jQuery.parseJSON(r.responseJSON._server_messages)
						var object = JSON.parse(server_massages)
						frappe.throw({message: object.message , title: object.title})

					}
				}
			})
		}, "eReceipt")
  }

});
