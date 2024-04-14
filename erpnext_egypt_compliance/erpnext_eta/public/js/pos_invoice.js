frappe.ui.form.on('POS Invoice', {
  onload(frm) {
    console.log("onload");
		frm.trigger("eta_add_download_ereceipt_button");
		frm.trigger("eta_submit_ereceipt")
		frm.trigger("add_fetch_status_button")
  },
  eta_add_download_ereceipt_button(frm) {
	  frm.add_custom_button('Download eReceipt Json', () => {
		var url = frappe.urllib.get_base_url() + '/api/method/erpnext_egypt_compliance.erpnext_eta.ereceipt_schema.download_ereceipt_json?docname=' + encodeURIComponent(frm.doc.name)
      
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
	},
	eta_submit_ereceipt(frm) {
		frm.add_custom_button("Submit eReceipt", () => {
			frappe.call(
				{
					method: "erpnext_egypt_compliance.erpnext_eta.ereceipt_schema.submit_ereceipt",
					args: {
						docname: frm.docname,
						pos_profile: frm.doc.pos_profile,
					},
					freeze: true,
					freeze_message: __("Submitting ..."),
					callback: function (r) {
						if (!r.exc) {
							console.log(r)
						}
					},


				}
			)
		}, "eReceipt")
	},
	add_fetch_status_button(frm) {
		frm.add_custom_button("Fetch eReceipt Status", () => {
			frm.trigger("fetch_eta_status")
		}, "eReceipt")
	},
	fetch_eta_status(frm) {
		frappe.call({
			method: "erpnext_egypt_compliance.erpnext_eta.ereceipt_schema.fetch_ereceipt_status",
			args: { docname: frm.doc.name },
			freeze: true,
			freeze_message: __("Fetch Status..."),
			callback: function (r) {
				console.log(r.message)
				if (!r.exc) {
					frappe.show_alert("E-Receipt Status Updated");
					cur_frm.reload_doc();
				}
			}
		})

	},

});
