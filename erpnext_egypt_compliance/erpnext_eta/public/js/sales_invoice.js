frappe.ui.form.on('Sales Invoice', {
	onload(frm) {
		frm.trigger('set_query_for_eta_sub_type');
		let eta_wrapper = $('.title-area').append('<div id="eta-status"></div>')

		// your code here
		frm.trigger('eta_add_download_button');
		frm.trigger('eta_add_submit_button');
		frm.trigger('eta_fetch_status_button');
		frm.trigger('eta_add_status_indicator');
		frm.trigger('eta_add_download_e_receipt_button')
		frm.trigger('eta_submit_ereceipt')
		frm.trigger('eta_add_download_pdf_button');
		
	},
	refresh(frm) {
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
	eta_add_download_button(frm) {
		frm.add_custom_button('Download ETA Json', () => {

			var url = frappe.urllib.get_base_url() + '/api/method/erpnext_egypt_compliance.erpnext_eta.main.download_eta_inv_json?docname=' + encodeURIComponent(frm.doc.name)
			$.ajax({
				url: url,
				type: 'GET',
				success: function (result) {
					if (jQuery.isEmptyObject(result)) {
						frappe.msgprint('Failed to load ETA Invoice format.');
					}
					else {
						window.location = url;
					}
					// if (result.exc){
					// 	console.log(exc)
					// }
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

		}, "ETA")
	},
	fetch_eta_status(frm) {
		frappe.call({
			method: 'erpnext_egypt_compliance.erpnext_eta.main.fetch_eta_status',
			args: {	docname: frm.doc.name },
			callback: function(r) {
				if (r.message) {
					frappe.show_alert('ETA Status Updated');
					cur_frm.reload_doc();
				}
			}
		})

	},
	eta_add_submit_button(frm) {
		frm.add_custom_button('Submit to ETA', () => {
			frappe.call({
				method: 'erpnext_egypt_compliance.erpnext_eta.main.submit_eta_invoice',
				args: {	docname: frm.doc.name },
				callback: function(r) {
					if (r.message) {
						console.log(r.message)
						frappe.show_alert(r.message)
						frm.trigger('fetch_eta_status')
						// cur_frm.reload_doc();
					}
				}
			})

		}, "ETA")
	},
	eta_fetch_status_button(frm) {
		frm.add_custom_button('Fetch ETA Status', () => {
			frm.trigger('fetch_eta_status')
		}, "ETA")
	},
	eta_add_status_indicator(frm) {
		let eta_status_str = "ETA N/A"
		let eta_status_class = "red"
		if (frm.doc.eta_status == "" && frm.doc.eta_signature) {
			eta_status_str = "Signed"
			eta_status_class = "green"
		} else if (frm.doc.eta_status) {
			eta_status_str = "ETA " + frm.doc.eta_status
			if (frm.doc.eta_status == "Valid" || frm.doc.eta_status == "Submitted") {
				eta_status_class = "green"
			}
		}
		 $('#eta-status').html('<span class="eta-pill indicator-pill whitespace-nowrap ' + eta_status_class +' ">' + eta_status_str + '</span>')
	},
	eta_add_download_e_receipt_button(frm) {
		frm.add_custom_button('Download e-Receipt Json', () => {

		var url = frappe.urllib.get_base_url() + '/api/method/erpnext_egypt_compliance.erpnext_eta.ereceipt_schema.download_ereceipt_json?docname=' + encodeURIComponent(frm.doc.name) + "&doctype=" +  encodeURIComponent(frm.doc.doctype)
			$.ajax({
				url: url,
				type: 'GET',
				success: function (result) {
					if (jQuery.isEmptyObject(result)) {
						frappe.msgprint('Failed to load e-Receipt Invoice format.');
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
						doctype: frm.doc.doctype,
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
	eta_add_download_pdf_button(frm) {
		// Create button with proper name as suggested
		frm.add_custom_button('Download ETA PDF', () => {
			if (!frm.doc.eta_uuid) {
				frappe.msgprint('Sales Invoice must have a UUID to get ETA PDF.');
				return;
			}
			var url = frappe.urllib.get_base_url() + '/api/method/erpnext_egypt_compliance.erpnext_eta.main.get_eta_pdf?docname=' + encodeURIComponent(frm.doc.name);
			$.ajax({
				url: url,
				type: 'GET',
				success: function (result) {
					if (jQuery.isEmptyObject(result)) {
						frappe.msgprint('Failed to load ETA PDF document.');
					} else {
						window.location = url;
					}
					
				},
				error: (r) => {
					console.log(r)
					if (r.responseJSON && r.responseJSON._server_messages && r.responseJSON._server_messages.length > 0) {
						console.log(r.responseJSON._server_messages)
						var server_massage = JSON.parse(r.responseText);
						frappe.throw({ message: `<pre> ${server_massage.exc}<pre>`, title: server_massage.exc_type, indicator: "red" });
					}
				}
			});
		},"ETA");

	},
})
