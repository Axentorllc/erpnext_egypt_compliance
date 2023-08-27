// Copyright (c) 2022, Axentor, LLC and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["ETA Sales Invoices Status"] = {
	"filters": [
		{
			"label": "From Date",
			"fieldname" : "from_date",
			"fieldtype" : "Date",
			"reqd" : 1,
		},
		{
			"label": "To Date",
			"fieldname" : "to_date",
			"fieldtype" : "Date",
			"reqd" : 1,
			"default" : frappe.datetime.get_today()
		},
		{
			"label": "Company",
			"fieldname" : "company",
			"fieldtype" : "Link",
			"options" : "Company",
			"reqd" : 1,
			"default" : frappe.defaults.get_user_default("Company"),
		}


	],
	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		let format_fields = ["invs_count", "inv_status"];

		if (in_list(format_fields, column.fieldname) && data && data[column.fieldname] == "Submitted") {
			value = "<span class= 'indicator-pill whitespace-nowrap green'>" + value + "</span>";
		}
		if (in_list(format_fields, column.fieldname) && data && data[column.fieldname] == "Invalid") {
			value = "<span class= 'indicator-pill whitespace-nowrap yellow'>" + value + "</span>";
		
		}
		if (in_list(format_fields, column.fieldname) && data && data[column.fieldname] == "Valid") {
			value = "<span class= 'indicator-pill whitespace-nowrap blue'>" + value + "</span>";
		
		}
		if (in_list(format_fields, column.fieldname) && data && data[column.fieldname] == "Cancelled") {
			value = "<span class= 'indicator-pill whitespace-nowrap red'>" + value + "</span>";
		
		}
		if (in_list(format_fields, column.fieldname) && data && data[column.fieldname] == "Signed Not Submitted") {
			value = "<span class= 'indicator-pill whitespace-nowrap gray'>" + value + "</span>";
		
		}
		if (in_list(format_fields, column.fieldname) && data && data[column.fieldname] == "Rejected") {
			value = "<span class= 'indicator-pill whitespace-nowrap orange'>" + value + "</span>";
		
		}
		if (in_list(format_fields, column.fieldname) && data && data[column.fieldname] == "Not Signed") {
			value = "<span class= 'indicator-pill whitespace-nowrap gray'>" + value + "</span>";
		
		}

		
		if (column.fieldname == "invs_count" && data && data.invs_count > 0 && data.inv_status == "Invalid") {
			value = "<span style='color:black'>"  + value + "</span>";
		}
		if (column.fieldname == "invs_count" && data && data.invs_count > 0 && data.inv_status == "Submitted") {
			value = "<span style='color:green'>" + value + "</span>";
		}
		if (column.fieldname == "invs_count" && data && data.invs_count > 0 && data.inv_status == "Submitted") {
			value = "<span style='color:green'>" + value + "</span>";
		}
		if (column.fieldname == "invs_count" && data && data.invs_count > 0 && data.inv_status == "Valid") {
			value = "<span style='color:blue'>" + value + "</span>";
		}
		if (column.fieldname == "invs_count" && data && data.invs_count > 0 && data.inv_status == "Cancelled") {
			value = "<span style='color:red'>" + value + "</span>";
		}
		if (column.fieldname == "invs_count" && data && data.invs_count > 0 && data.inv_status == "Rejected") {
			value = "<span style='color:orange'>" + value + "</span>";
		}


		return value;
	},
	"tree": true,
	"name_field": "child",
	"parent_field": "inv_status",
	"initial_depth": 3,

};
