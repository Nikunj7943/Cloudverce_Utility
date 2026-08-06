import frappe


@frappe.whitelist()
def get_session_expiry():
	"""Return the site's session TTL in seconds (used by the session-timer widget)."""
	if frappe.session.user == "Guest":
		frappe.throw("Not logged in")
	expiry_str = frappe.db.get_single_value("System Settings", "session_expiry") or "170:00"
	parts = expiry_str.split(":")
	hours = int(parts[0]) if len(parts) > 0 and parts[0] else 170
	minutes = int(parts[1]) if len(parts) > 1 and parts[1] else 0
	seconds = int(parts[2]) if len(parts) > 2 and parts[2] else 0
	return {"expiry_seconds": (hours * 3600) + (minutes * 60) + seconds}
