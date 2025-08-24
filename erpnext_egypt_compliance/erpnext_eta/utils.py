from datetime import datetime, timedelta
import pytz

import frappe
import requests
import json



def download_eta_invoice_json(docname, file_content):
	frappe.local.response.filename = f"{''}ETA-{docname}.json"
	frappe.local.response.filecontent = file_content
	frappe.local.response.type = "download"


def eta_datetime_issued_format(posting_date, seconds):
	date_time: datetime = datetime.strptime(
		frappe.utils.add_to_date(
			posting_date,
			seconds=seconds,
		).strftime("%Y-%m-%d %H:%M:%S"),
		"%Y-%m-%d %H:%M:%S",
	)
	date_utc_with_z_suffix: str = (
		pytz.timezone("Africa/Cairo")
		.localize(date_time, is_dst=None)
		.astimezone(pytz.utc)
		.strftime("%Y-%m-%dT%H:%M:%SZ")
	)
	return date_utc_with_z_suffix


def validate_allowed_values(value, allowed_values):
	if value not in allowed_values:
		raise ValueError(f"Value must be one of {allowed_values}")
	return value


def eta_round(_value: float, decimal: int = 5) -> float:
	"""
	Round value to the specified number of decimal places, with a maximum of 5 decimal places.
	If the precision is not provided, it is fetched from the precision settings for "Sales Invoice Item net_rate".
	"""
	if not decimal:
		decimal = frappe.get_precision("Sales Invoice Item", "net_rate") or 2

	# Ensure decimal places is not more than 5
	precision = min(decimal, 5)
	return round(_value, precision)


# --- eta_helper.py ---
def get_company_eta_connector(company, throw_if_no_connector=True):
	connector = frappe.get_list(
		"ETA Connector",
		filters={"company": company, "is_default": 1},
		fields=["name"],
		limit=1,
	)
	if connector:
		return frappe.get_doc("ETA Connector", connector[0].name)
	elif throw_if_no_connector:
		frappe.throw("No Default Connector Set.")
	connectors = frappe.get_list("ETA Connector", filters={"company": company, "is_default": 1})
	if connectors:
		connector = frappe.get_doc("ETA Connector", connectors[0]["name"])
		return connector
	elif throw_if_no_connector:
		frappe.throw("No Default Connecter Set.")


def autofetch_eta_status(company):
	connector = get_company_eta_connector(company)
	# get list of submitted invoices:
	docs = frappe.get_all("Sales Invoice", filters=[["eta_status", "=", "Submitted"]], pluck="name")
	for docname in docs:
		update_eta_docstatus(connector,docname)
	frappe.db.commit()

def update_eta_docstatus(connector, docname):
        headers = connector.get_headers()
        uuid = frappe.get_value("Sales Invoice", docname, "eta_uuid")
        UUID_PATH = connector.ETA_BASE + f"/documents/{uuid}/raw"
        eta_response = connector.session.get(UUID_PATH, headers=headers)
        if eta_response.ok:
            eta_response = eta_response.json()
            frappe.db.set_value(
                "Sales Invoice", eta_response.get("internalId"), "eta_status", eta_response.get("status")
            )
            return eta_response.get("status")
        return "Didn't update Status"


def autofetch_eta_status_process():
	companies = frappe.get_all("Company", pluck="name")
	for company in companies:
		try:
			autofetch_eta_status(company)
		except:
			print("An exception occurred")  # TODO handle error properly.


def create_eta_log(
	posting_date: datetime = None,
	from_doctype: str = None,
	documents: list = None,
	status_code: str = None,
	submission_summary: str = "",
	submission_status: str = "Started",
	pos_profile: str = None
):
	doc = frappe.get_doc({
		"doctype": "ETA Log", 
		"from_doctype": from_doctype,
		"posting_date": posting_date or frappe.utils.now(),
		"status_code": status_code,
		"documents": documents or [],
		"submission_status": submission_status,
		"submission_summary": submission_summary,
		"pos_profile": pos_profile

	}).insert()
	return doc

def parse_error_details(error_object):
	error_object = frappe.parse_json(error_object)

	# Extract error message and target
	error_message = error_object.get("message", "No error message provided")
	error_target = error_object.get("target", "N/A")

	error_msg = f"Error Message: {error_message}\n"
	error_msg += f"Target: {error_target}\n"

	# Process error details
	error_details = error_object.get("details", [])
	for detail in error_details:
		code = detail.get("code", "N/A")
		message = detail.get("message", "No message provided")
		target = detail.get("target", "N/A")
		property_path = detail.get("propertyPath", "N/A")
		
		error_msg += f"\nDetail:\n"
		error_msg += f"  Code: {code}\n"
		error_msg += f"  Message: {message}\n"
		error_msg += f"  Target: {target}\n"
		error_msg += f"  Property Path: {property_path}\n"

	return error_msg


def check_unsigned_invoices_and_notify():
	"""
	Check for submitted invoices that haven't been signed and send email notifications
	based on ETA Connector notification settings
	"""
	companies = frappe.get_all("Company", pluck="name")
	for company in companies:
		try:
			connector = get_company_eta_connector(company)
			
			if not connector:
				continue
				
			# Check if any notification is enabled
			if not (connector.notify_unsigned_invoices_every_hour or connector.notify_unsigned_invoices_at_time):
				continue
			
			# Check if we should send notification based on settings
			should_notify = False
			
			# Check hourly notification setting
			if connector.notify_unsigned_invoices_every_hour:
				should_notify = True
			
			# Check time-based notification setting
			if connector.notify_unsigned_invoices_at_time and not should_notify:
				current_time = datetime.now().strftime("%H:%M")
				notification_time = connector.notify_unsigned_invoices_at_time.strftime("%H:%M")

				if current_time == notification_time:
					should_notify = True
				

			if should_notify:
				# Calculate the cutoff time (2 hours ago)
				cutoff_time = datetime.now() - timedelta(hours=2)
				
				# Get all submitted invoices without signatures that are older than 2 hours for this company
				unsigned_invoices = frappe.get_all(
					"Sales Invoice",
					filters=[
						["docstatus", "=", 1],  # Submitted
						["eta_signature", "in", ["", None]],  # No signature
						["modified", "<=", cutoff_time],  # Older than 2 hours
						["company", "=", company],  # Filter by company
					],
					fields=["name", "customer", "company", "posting_date", "grand_total", "modified"]
				)
				
				# Only send notification if there are unsigned invoices
				if unsigned_invoices:
					try:
						frappe.enqueue(
							method=send_unsigned_invoice_notification,
							queue="long",
							invoices=unsigned_invoices,
							company=company,
							notification_type="hourly" if connector.notify_unsigned_invoices_every_hour else "daily",
							job_name=f"unsigned_invoice_notification_{company}",
						)
						
					except Exception as e:
						frappe.log_error(f"Failed to send notification for invoices in company {company}: {str(e)}")
				
		except Exception as e:
			frappe.log_error(f"Error in check_unsigned_invoices_and_notify for company {company}: {str(e)}")


def check_not_submitted_invoices_and_notify():
	"""
	Check for submitted invoices that haven't been submitted to ETA and send email notifications
	based on ETA Connector notification settings
	"""
	companies = frappe.get_all("Company", pluck="name")
	for company in companies:
		try:
			connector = get_company_eta_connector(company)
			
			if not connector:
				continue
				
			# Only proceed if submission mode is Manual
			if connector.submission_mode != "Manual":
				continue
				
			# Check if any notification is enabled
			if not (connector.notify_not_submitted_every_hour or connector.notify_not_submitted_at_time):
				continue
			
			# Check if we should send notification based on settings
			should_notify = False
			
			# Check hourly notification setting
			if connector.notify_not_submitted_every_hour:
				should_notify = True
			
			# Check time-based notification setting
			if connector.notify_not_submitted_at_time and not should_notify:
				current_time = datetime.now().strftime("%H:%M")
				notification_time = connector.notify_not_submitted_at_time.strftime("%H:%M")

				if current_time == notification_time:
					should_notify = True
				

			if should_notify:
				# Calculate the cutoff time (2 hours ago)
				cutoff_time = datetime.now() - timedelta(hours=2)
				
				# Get all submitted invoices not submitted to ETA that are older than 2 hours for this company
				not_submitted_invoices = frappe.get_all(
					"Sales Invoice",
					filters=[
						["docstatus", "=", 1],  # Submitted
						["eta_signature", "not in", ["", None]], # Signed
						["eta_uuid", "in", ["", None]],  # Not submitted to ETA
						["modified", "<=", cutoff_time],  # Older than 2 hours
						["company", "=", company],  # Filter by company
					],
					fields=["name", "customer", "company", "posting_date", "grand_total", "modified"]
				)
				
				# Only send notification if there are not submitted invoices
				if not_submitted_invoices:
					try:
						frappe.enqueue(
							method=send_not_submitted_invoice_notification,
							queue="long",
							invoices=not_submitted_invoices,
							company=company,
							notification_type="hourly" if connector.notify_not_submitted_every_hour else "daily",
							job_name=f"not_submitted_invoice_notification_{company}",
						)
						
					except Exception as e:
						frappe.log_error(f"Failed to send notification for not submitted invoices in company {company}: {str(e)}")
				
		except Exception as e:
			frappe.log_error(f"Error in check_not_submitted_invoices_and_notify for company {company}: {str(e)}")


def send_not_submitted_invoice_notification(invoices, company=None, notification_type="hourly"):
	"""
	Send email notification for invoices not submitted to ETA
	"""
	try:
		
		eta_managers=get_eta_mangers()
		
		if not eta_managers:
			frappe.log_error(f"No email found for ETA Managers")
			return
		
		# Prepare email content
		notification_frequency = "Hourly" if notification_type == "hourly" else "Daily"
		subject = f"[{notification_frequency}] ETA Alert: Invoices Not Submitted to ETA Portal"
		
		# Build the invoice table
		invoice_rows = ""
		for invoice in invoices:
			invoice_rows += f"""
			<tr>
				<td><a href="{frappe.utils.get_url()}/app/sales-invoice/{invoice.name}">{invoice.name}</a></td>
				<td>{invoice.customer}</td>
				<td>{invoice.company}</td>
				<td>{invoice.posting_date}</td>
				<td>{invoice.grand_total}</td>
			</tr>
			"""
		
		message = f"""
		<p>Dear ETA Manager,</p>
		
		<p>This is a {notification_frequency.lower()} reminder that the following {len(invoices)} invoice(s) have been submitted but not yet submitted to the ETA Portal for over 2 hours:</p>
		
		<table border="1" style="border-collapse: collapse; margin: 10px 0; width: 100%;">
			<thead style="background-color: #ffc107;">
				<tr>
					<th style="padding: 8px; text-align: left;">Invoice Number</th>
					<th style="padding: 8px; text-align: left;">Customer</th>
					<th style="padding: 8px; text-align: left;">Company</th>
					<th style="padding: 8px; text-align: left;">Posting Date</th>
					<th style="padding: 8px; text-align: left;">Amount</th>
				</tr>
			</thead>
			<tbody>
				{invoice_rows}
			</tbody>
		</table>
		
		<p><strong style="color: orange;">Action Required:</strong> Please submit these invoices to the ETA Portal immediately to comply with ETA requirements.</p>
		
		<p>You can click on any invoice number in the table above to access it directly.</p>
		
		<p>Best regards,<br>ETA Compliance System</p>
		"""
		
		# Send the email
		frappe.sendmail(
			recipients=eta_managers,
			subject=subject,
			message=message,
			header=["ETA Submission Reminder", "orange"]
		)
		
		frappe.log_error(f"Notification sent to {eta_managers} for invoices needing ETA submission.")
		
	except Exception as e:
		frappe.log_error(f"Failed to send email for not submitted invoices: {str(e)}")
		raise


def send_unsigned_invoice_notification(invoices):
	"""
	Send email notification for unsigned invoice
	"""
	try:
		
		eta_managers=get_eta_mangers()
		
		if not eta_managers:
			frappe.log_error(f"No email found for user {eta_managers}")
			return
		
		# Prepare email content
		subject = f"Urgent: Invoices requires ETA signature"
		
		# Build the invoice table
		invoice_rows = ""
		for invoice in invoices:
			invoice_rows += f"""
			<tr>
				<td><a href="{frappe.utils.get_url()}/app/sales-invoice/{invoice.name}">{invoice.name}</a></td>
				<td>{invoice.customer}</td>
				<td>{invoice.company}</td>
				<td>{invoice.posting_date}</td>
				<td>{invoice.grand_total}</td>
			</tr>
			"""
		
		message = f"""
		<p>Dear User,</p>
		
		<p>This is a reminder that the following  invoice/s been submitted but not signed for over 2 hours:</p>
		
		<table border="1" style="border-collapse: collapse; margin: 10px 0; width: 100%;">
			<thead style="background-color: #f8f9fa;">
				<tr>
					<th style="padding: 8px; text-align: left;">Invoice Number</th>
					<th style="padding: 8px; text-align: left;">Customer</th>
					<th style="padding: 8px; text-align: left;">Company</th>
					<th style="padding: 8px; text-align: left;">Posting Date</th>
					<th style="padding: 8px; text-align: left;">Amount</th>
				</tr>
			</thead>
			<tbody>
				{invoice_rows}
			</tbody>
		</table>
		
		<p><strong style="color: red;">Action Required:</strong> Please sign 'these invoice/s immediately to comply with ETA requirements.</p>
		
		<p>You can click on any invoice number in the table above to access it directly.</p>
		
		<p>Best regards,<br>ETA Compliance System</p>
		"""
		
		# Send the email
		frappe.sendmail(
			recipients=eta_managers,
			subject=subject,
			message=message,
			header=["ETA Signature Reminder", "orange"]
		)
		
		frappe.log_error(f"Notification sent to {eta_managers} for invoices needing signature.")
		
	except Exception as e:
		frappe.log_error(f"Failed to send email for invoices: {str(e)}")
		raise


def get_eta_mangers() -> list	:
	"""Fetches the email addresses of users with the 'ETA Manager' role."""

	eta_manager_users = frappe.get_all(
		"Has Role",
		filters={"role": "ETA Manager"},
		fields=["parent"],  # parent = user id
		pluck="parent"
	)

	eta_managers = frappe.get_all(
			"User",
			filters={"name": ["in", eta_manager_users]},
			fields=["email"],
			pluck="email"
	)

	return eta_managers
