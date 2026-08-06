import frappe
from frappe import _

from cloudverce_utility.access_control import _get_user_group_candidates


def add_navigation_visibility_bootinfo(bootinfo):
	context = get_navigation_visibility_context(frappe.session.user)
	bootinfo.cloudverce_navigation_visibility = context


def get_navigation_visibility_context(user=None):
	user = user or frappe.session.user
	group_name = _get_user_group(user)

	if not group_name:
		return {"group_name": None, "hidden_labels": []}

	group = frappe.db.get_value(
		"Cloudverce User Group",
		group_name,
		["name", "is_active", "navigation_visibility_json"],
		as_dict=True,
	)
	if not group or not group.is_active:
		return {"group_name": None, "hidden_labels": []}

	config = frappe.parse_json(group.navigation_visibility_json) or {}
	hidden_labels = config.get("hidden_labels") or config.get("hidden") or []
	if isinstance(hidden_labels, str):
		hidden_labels = [hidden_labels]

	cleaned_hidden = []
	seen = set()
	for label in hidden_labels:
		label = (label or "").strip()
		if label and label not in seen:
			cleaned_hidden.append(label)
			seen.add(label)

	return {
		"group_name": group.name,
		"hidden_labels": cleaned_hidden,
	}


def _get_user_group(user):
	if not user or user == "Guest":
		return None

	if "System Manager" in frappe.get_roles(user):
		return None

	candidates = _get_user_group_candidates(user)
	for group_name in candidates:
		if frappe.db.exists("Cloudverce User Group", group_name):
			return group_name

	return None


def _get_hidden_labels_for_user(user=None):
	"""Return set of hidden labels for the current user's group. Empty set = no restriction."""
	user = user or frappe.session.user
	# System Manager and Administrator are never restricted
	if not user or user in ("Guest",):
		return set()
	if "System Manager" in frappe.get_roles(user) or "Administrator" in frappe.get_roles(user):
		return set()

	ctx = get_navigation_visibility_context(user)
	return set(ctx.get("hidden_labels") or [])


def _nav_label_for_page(doc):
	"""Return the sidebar label used for a Page — try title then name."""
	return (doc.get("title") or doc.get("name") or "").strip()


def _nav_label_for_dashboard(doc):
	return (doc.get("dashboard_name") or doc.get("name") or "").strip()


def _nav_label_for_report(doc):
	return (doc.get("report_name") or doc.get("name") or "").strip()


@frappe.whitelist()
def check_route_access(route):
	"""Check if current user can access a given route slug (e.g. 'alert-center')."""
	user = frappe.session.user
	hidden = _get_hidden_labels_for_user(user)
	if not hidden:
		return {"blocked": False}

	route = (route or "").strip().lower()
	for label in hidden:
		slug = label.strip().lower().replace(" ", "-")
		# Remove non-alphanumeric except hyphens
		slug = "".join(c for c in slug if c.isalnum() or c == "-")
		if route == slug:
			return {"blocked": True, "label": label}

	return {"blocked": False}


def has_permission_page(doc, user=None, permission_type=None):
	"""Block Page access when its label is in the user's hidden_labels."""
	hidden = _get_hidden_labels_for_user(user or frappe.session.user)
	if not hidden:
		return True
	label = _nav_label_for_page(doc)
	if label and label in hidden:
		return False
	return True


def has_permission_dashboard(doc, user=None, permission_type=None):
	"""Block Dashboard access when its label is in the user's hidden_labels."""
	hidden = _get_hidden_labels_for_user(user or frappe.session.user)
	if not hidden:
		return True
	label = _nav_label_for_dashboard(doc)
	if label and label in hidden:
		return False
	return True


def has_permission_report(doc, user=None, permission_type=None):
	"""Block Report access when its label is in the user's hidden_labels."""
	hidden = _get_hidden_labels_for_user(user or frappe.session.user)
	if not hidden:
		return True
	label = _nav_label_for_report(doc)
	if label and label in hidden:
		return False
	return True


# ── Dashboard access control ────────────────────────────────────────────────
#
# CAPA FIX: Dashboard has no native `roles` table (unlike Page/Report), and its view
# loads data via get_permitted_charts()/get_permitted_cards() -- both call
# frappe.get_doc("Dashboard", ...) WITHOUT ever calling check_permission(), so the
# has_permission_dashboard hook above is never actually invoked when a Dashboard view
# opens. These two functions override the originals (see hooks.py
# override_whitelisted_methods) to add the missing check, with a message matching
# Frappe's own dynamic Report/Page phrasing ("You don't have access to <Type>: <name>").


def _check_dashboard_access(dashboard_name):
	if not frappe.has_permission("Dashboard", doc=dashboard_name):
		frappe.throw(
			_("You don't have access to Dashboard: {0}. Please contact your System Administrator.").format(
				dashboard_name
			),
			frappe.PermissionError,
		)


@frappe.whitelist()
def get_permitted_charts(dashboard_name):
	_check_dashboard_access(dashboard_name)
	from frappe.desk.doctype.dashboard.dashboard import get_permitted_charts as _original

	return _original(dashboard_name)


@frappe.whitelist()
def get_permitted_cards(dashboard_name):
	_check_dashboard_access(dashboard_name)
	from frappe.desk.doctype.dashboard.dashboard import get_permitted_cards as _original

	return _original(dashboard_name)


# ── User doctype: non-admin groups restricted to their own record ──────────
#
# BASELINE_ALWAYS_GRANTED_DOCTYPES (cloudverce_user_group.py) grants every Cloudverce User
# Group role access to "User", but only with the reduced select/read/write columns for
# non-admin (is_admin=0) groups via BASELINE_RESTRICTED_FOR_NON_ADMIN. That controls
# which ACTIONS are allowed; these two hooks (wired in hooks.py) control WHICH ROWS —
# a non-admin user can only see/edit their own User record, never anyone else's.
# is_admin=1 groups, System Manager and Administrator are never restricted.


def _user_is_group_admin(user):
	if not user or user == "Guest":
		return False
	if "System Manager" in frappe.get_roles(user) or "Administrator" in frappe.get_roles(user):
		return True
	group_name = _get_user_group(user)
	if not group_name:
		return False
	return bool(frappe.db.get_value("Cloudverce User Group", group_name, "is_admin"))


def get_permission_query_conditions_user(user=None):
	user = user or frappe.session.user
	if _user_is_group_admin(user):
		return ""
	return f"`tabUser`.name = {frappe.db.escape(user)}"


def has_permission_user(doc, user=None, permission_type=None):
	user = user or frappe.session.user
	if _user_is_group_admin(user):
		return True
	return doc.name == user


# ── Cloudverce User Group: only group Admins manage every group; a normal group's own
# users can READ (never write) only their own group's record, never anyone else's. ──


def get_permission_query_conditions_cloudverce_user_group(user=None):
	user = user or frappe.session.user
	if _user_is_group_admin(user):
		return ""
	group_name = _get_user_group(user)
	if not group_name:
		return "1=0"
	return f"`tabCloudverce User Group`.name = {frappe.db.escape(group_name)}"


def has_permission_cloudverce_user_group(doc, user=None, permission_type=None):
	"""Only group Admins (is_admin=1 groups, System Manager, Administrator) may write,
	update, or create a Cloudverce User Group -- this governs BOTH the doctype-level
	permission matrix and the field-level Hidden/Read Only feature, since both save
	paths funnel through this same has_permission("Cloudverce User Group", "write", ...)
	check. A normal group's own users may only READ their own group's record (see
	what permissions apply to them), never write it, and never see/read any other
	group's record.
	"""
	user = user or frappe.session.user
	if _user_is_group_admin(user):
		return True

	if permission_type and permission_type != "read":
		return False

	group_name = _get_user_group(user)
	return bool(group_name) and doc.name == group_name
