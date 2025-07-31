import requests
import time
import frappe


def after_install():
    send_installation_event("Install")


def after_uninstall():
    send_installation_event("Uninstall")


def send_installation_event(event_type: str = None):
    # TODO - Add the URL for the event
    url = ""
    data = frappe._dict(
        {
            "app": "EG Compliance",
            "site_path": frappe.utils.get_url(),
            "event_type": event_type,
        }
    )
    headers = {"Content-Type": "application/json"}

    max_retries = 3
    retry_delay = 5

    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=data, headers=headers)
            response.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                frappe.log_error(f"Failed to send installation event: {e}")
