frappe.ui.form.on('Item', {
	refresh(frm) {
	},
	validate(frm) {
		if(frm.doc.eta_inherit_brand && frm.doc.eta_inherit_item_group && frm.doc.is_sales_item) {
			frappe.throw(__('Sales Item Cannot inherit ETA details from <b>Brand</b> and <b>Item Group</b>. <br/> Please Update your selection.'))
		}
	},
	eta_inherit_brand(frm){
		if (frm.doc.is_sales_item) {
			if (frm.doc.eta_inherit_brand) {
				// cur_frm.toggle_display('eta_details',false)
				cur_frm.toggle_reqd('eta_code_type', false)
				cur_frm.toggle_reqd('eta_item_code', false)
				cur_frm.toggle_reqd('gpc', false)


			} else {
				// cur_frm.toggle_display('eta_details', true)

				cur_frm.toggle_reqd('eta_code_type', true)
				cur_frm.toggle_reqd('eta_item_code', true)
				cur_frm.toggle_reqd('gpc', true)

			}
		}
	},
	eta_inherit_item_group(frm){
		if (frm.doc.is_sales_item) {
			if (frm.doc.eta_inherit_item_group) {
				// cur_frm.toggle_display('eta_details',false)

				cur_frm.toggle_reqd('eta_code_type', false)
				cur_frm.toggle_reqd('eta_item_code', false)
				cur_frm.toggle_reqd('gpc', false)


			} else {
				// cur_frm.toggle_display('eta_details', true)

				cur_frm.toggle_reqd('eta_code_type', true)
				cur_frm.toggle_reqd('eta_item_code', true)
				cur_frm.toggle_reqd('gpc', true)

			}
		}
	}
	
})