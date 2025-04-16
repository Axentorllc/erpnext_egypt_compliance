// Copyright (c) 2022, Axentor, LLC and contributors
// For license information, please see license.txt

frappe.ui.form.on('ETA Connector', {
	refresh: function(frm) {
		if (!frm.doc.client_secret_expiration_date) return;
		const helpLink = "https://preprod.invoicing.eta.gov.eg/content?path=userguide/regenerate%2Derp%2Dclient%2Dsecrets"
		const expirationDate = frappe.datetime.str_to_obj(frm.doc.client_secret_expiration_date);
		const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());

		const diffInDays = frappe.datetime.get_diff(expirationDate, today);
		if (diffInDays <= 0) {
			// Expired
			frm.dashboard.set_headline_alert(__('Client secret expired, please renew it from <a href={0}>ETA portal</a>', [helpLink]), 'red');
			frappe.msgprint({
				title: __('Alert'),
				indicator: 'red',
				message: __('The client secret has <b>expired</b>!')
			});
		} else if (diffInDays <= 60) {
			// Will expire in less than 2 months
			frm.dashboard.set_headline_alert(__('Client secret near expiration and it will expire in <b> {0} days</b>, please renew it from <a href={1}>ETA portal</a>', [diffInDays, helpLink]), 'orange');
			frappe.msgprint({
				title: __('Warning'),
				indicator: 'orange',
				message: __('The client secret will expire in <b>' + diffInDays + ' days</b>. Please update it soon.')
			});
		}
	}
		const helpLink = "https://preprod.invoicing.eta.gov.eg/content?path=userguide/regenerate%2Derp%2Dclient%2Dsecrets"
		const expirationDate = frappe.datetime.str_to_obj(frm.doc.client_secret_expiration_date);
		const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());

		const diffInDays = frappe.datetime.get_diff(expirationDate, today);
		if (diffInDays <= 0) {
			// Expired
			frm.dashboard.set_headline_alert(__('Client secret expired, please renew it from <a href={0}>ETA portal</a>', [helpLink]), 'red');
			frappe.msgprint({
				title: __('Alert'),
				indicator: 'red',
				message: __('The client secret has <b>expired</b>!')
			});
		} else if (diffInDays <= 60) {
			// Will expire in less than 2 months
			frm.dashboard.set_headline_alert(__('Client secret near expiration and it will expire in <b> {0} days</b>, please renew it from <a href={1}>ETA portal</a>', [diffInDays, helpLink]), 'orange');
			frappe.msgprint({
				title: __('Warning'),
				indicator: 'orange',
				message: __('The client secret will expire in <b>' + diffInDays + ' days</b>. Please update it soon.')
			});
		}
	}
});

// https://preprod.invoicing.eta.gov.eg/content?path=userguide/regenerate%2Derp%2Dclient%2Dsecrets
