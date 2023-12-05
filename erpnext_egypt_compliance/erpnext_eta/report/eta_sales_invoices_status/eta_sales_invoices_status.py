# Copyright (c) 2022, Axentor, LLC and contributors
# For license information, pleASe see license.txt

import frappe
from erpnext_egypt_compliance.erpnext_eta.utils import get_company_eta_connector
from datetime import datetime


def execute(filters=None):
    columns, data = get_columns(filters=None), get_data(filters)
    get_signed_not_submitted_invs(filters, data)
    get_not_signed_invs(filters, data, get_company_eta_connector)
    get_total_no_submitted_invoices(filters, data)

    return columns, data


def get_data(filters):
    from_date, to_date, company = filters.get("from_date"), filters.get("to_date"), filters.get("company")

    eta_invoice_status = ["Submitted", "valid", "invalid", "Rejected", "Cancelled"]
    data = []

    for stat in eta_invoice_status:
        results = frappe.db.sql(
            f"""
			SELECT
				eta_status AS inv_status ,
				COUNT(name) AS invs_count,
				Sum(grand_total) AS total
			FROM `tabSales Invoice`
			WHERE eta_status = '{stat}'
			And docstatus = 1
			AND company = '{company}'
			AND posting_date >= '{from_date}' AND posting_date <= '{to_date}'
			Group By inv_status;""",
            filters,
            as_dict=1,
        )

        if len(results):
            data.append(results[0].update({"parent": stat, "indent": 1}))
            get_childs(filters, data, stat)

    return data


def get_signed_not_submitted_invs(filters, data):
    values = {
        "from_date": filters.get("from_date"),
        "to_date": filters.get("to_date"),
        "company": filters.get("company"),
    }

    singed_not_submitted_invs = frappe.db.sql(
        """
		SELECT
			REPLACE(name, name, "Signed Not Submitted") AS inv_status,
			count(name) AS invs_count,
			SUM(grand_total) AS total
		FROM `tabSales Invoice`
		WHERE
			(eta_status = "")
			AND eta_signature != "NULL"
			AND docstatus = 1
			AND (posting_date >= %(from_date)s and posting_date <= %(to_date)s)
			AND company = %(company)s
		GROUP BY inv_status
	""",
        values,
        as_dict=1,
    )

    if singed_not_submitted_invs:
        data.append(singed_not_submitted_invs[0].update({"parent": "Signed Not Submitted", "indent": 1}))
        get_childs_for_signed_not_submitted_invs(filters, data, values=values)


def get_not_signed_invs(filters, data, get_company_eta_connector):
    values = {
        "from_date": filters.get("from_date"),
        "to_date": filters.get("to_date"),
        "company": filters.get("company"),
    }

    eta_connector = get_company_eta_connector(values.get("company"))
    signature_start_date = eta_connector.get("signature_start_date")

    _from_date = datetime.strptime(filters.get("from_date"), "%Y-%m-%d").date()
    if _from_date < signature_start_date:
        values["from_date"] = signature_start_date

    not_signed_invs = frappe.db.sql(
        """
		SELECT
			REPLACE(name, name, "Not Signed") AS inv_status,
			count(name) AS invs_count,
			SUM(grand_total) AS total
		FROM `tabSales Invoice`
		WHERE
			eta_signature IS NULL
			AND docstatus = 1
			AND (posting_date > %(from_date)s and posting_date <= %(to_date)s)
			AND company = %(company)s
		GROUP BY inv_status
	""",
        values,
        as_dict=1,
    )

    if not_signed_invs:
        data.append(not_signed_invs[0].update({"parent": "Not Singed", "indent": 1}))
        get_childs_for_not_signed_invs(filters, data, values)


def get_childs(filters, data, stat):
    childrens = frappe.db.sql(
        """
		SELECT
			eta_status AS inv_status,
			COUNT(name) AS invs_count ,
			SUM(grand_total) AS total  ,
			posting_date
		FROM
			`tabSales Invoice`
		WHERE
			eta_status = '{stat}'
			AND company = '{company}'
			AND docstatus = 1
			AND posting_date >= '{from_date}' AND posting_date <= '{to_date}'
		GROUP BY
			posting_date
		ORDER BY
			posting_date ,
			total;""".format(
            stat=stat,
            company=filters.get("company"),
            from_date=filters.get("from_date"),
            to_date=filters.get("to_date"),
        ),
        as_dict=1,
    )

    for child in childrens:
        child.update({"parent": child.inv_status, "child": child.posting_date, "indent": 2})
        data.append(child)


def get_childs_for_signed_not_submitted_invs(filters, data, values):
    childrens = frappe.db.sql(
        """
		SELECT
			REPLACE(name, name, "Signed Not Submitted") AS inv_status,
			posting_date,
			count(posting_date) AS invs_count,
			grand_total AS total
		FROM
			`tabSales Invoice`
		WHERE
			(eta_status = "")
			AND eta_signature != "NULL"
			AND docstatus = 1
			AND (posting_date >= %(from_date)s
				and posting_date <= %(to_date)s)
			AND company = %(company)s
		Group by
			posting_date
		ORDER BY
			posting_date;""",
        values,
        as_dict=1,
    )

    for child in childrens:
        child.update({"parent": child.inv_status, "child": child.posting_date, "indent": 2})
        data.append(child)


def get_childs_for_not_signed_invs(filters, data, values):
    childrens = frappe.db.sql(
        """
		SELECT
			REPLACE(name, name, "Not Signed") AS inv_status,
			posting_date,
			count(posting_date) AS invs_count,
			sum(grand_total) AS total
		FROM
			`tabSales Invoice`
		WHERE
			eta_signature IS NULL
			AND docstatus = 1
			AND (posting_date >= %(from_date)s
				and posting_date <= %(to_date)s)
			AND company = %(company)s
		Group by
			posting_date
		ORDER BY
			posting_date;""",
        values,
        as_dict=1,
    )

    for child in childrens:
        child.update({"parent": child.inv_status, "child": child.posting_date, "indent": 2})
        data.append(child)


def get_total_no_submitted_invoices(filters, data):
    q = """
		SELECT
			count(name) As count,
			SUM(grand_total) AS total
		FROM
			`tabSales Invoice`
		WHERE
			(posting_date between %(from_date)s AND %(to_date)s)
			AND company = %(company)s AND docstatus = 1
	"""
    count = frappe.db.sql(q, filters, as_dict=1)
    data.append(
        {
            "inv_status": "<b> Total Submitted Invoices </b>",
            "invs_count": count[0].get("count"),
            "total": count[0].get("total"),
        }
    )


def get_columns(filters=None):
    columns = [
        {"fieldname": "inv_status", "label": "Status", "fieldtype": "Data", "width": 200},
        {"fieldname": "child", "label": "Date", "fieldtype": "Data", "width": 150},
        {"fieldname": "invs_count", "label": "Count", "fieldtype": "Int", "width": 150},
        {"fieldname": "total", "label": "Grand Total", "fieldtype": "Currency", "width": 150},
    ]
    return columns
