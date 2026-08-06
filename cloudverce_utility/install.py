import frappe

from cloudverce_utility.role_profile_sync import ensure_role_profiles_for_existing_roles


def after_install():
	_ensure_settings()


def after_migrate():
	"""Runs on every `bench migrate` — must stay idempotent."""
	_ensure_settings()
	_sync_included_scope_tables()
	_purge_orphaned_permissions()
	_ensure_role_profiles()
	_ensure_baseline_permissions()


def _ensure_settings():
	"""Create the Cloudverce Utility Settings single with defaults if it does not exist yet.

	Empty include tables → the RBAC auto-governs every non-core installed app immediately
	(rows are populated on migrate by _sync_included_scope_tables), so no admin action is
	required after install.
	"""
	if not frappe.db.exists("DocType", "Cloudverce Utility Settings"):
		return
	if frappe.db.exists("Cloudverce Utility Settings", "Cloudverce Utility Settings"):
		return
	try:
		doc = frappe.get_doc({
			"doctype": "Cloudverce Utility Settings",
			"enable_session_timer": 1,
		})
		doc.flags.ignore_permissions = True
		doc.insert(ignore_if_duplicate=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Failed to initialise Cloudverce Utility Settings")


def _sync_included_scope_tables():
	"""Keep Included Apps / Modules / Workspaces checkbox tables in sync with what is
	actually installed. Additive for new items; preserves existing checked state; purges
	rows for uninstalled apps/modules/workspaces. See
	cloudverce_user_group._sync_included_scope_tables for the full contract.
	"""
	try:
		from cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group import (
			_sync_included_scope_tables as _sync,
		)

		_sync()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Failed to sync included scope tables")


def _purge_orphaned_permissions():
	"""Sweep Custom DocPerm rows left behind by other apps that were uninstalled
	after cloudverce_utility already granted permissions on their doctypes — Frappe's
	uninstaller only cleans up records the uninstalled app itself created."""
	try:
		from cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group import (
			_purge_orphaned_custom_docperms,
		)

		_purge_orphaned_custom_docperms()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Failed to purge orphaned Custom DocPerm rows")

	try:
		from cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group import (
			_purge_orphaned_field_permlevel_property_setters,
		)

		_purge_orphaned_field_permlevel_property_setters()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Failed to purge orphaned field-permlevel Property Setter rows")


def _ensure_role_profiles():
	try:
		ensure_role_profiles_for_existing_roles()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Failed to ensure role profiles")


def _ensure_baseline_permissions():
	"""Converge every active Cloudverce User Group onto BASELINE_ALWAYS_GRANTED_DOCTYPES
	on every migrate — covers new sites and baseline doctypes that didn't exist yet
	at a group's last save, without needing a one-off patch."""
	try:
		from cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group import (
			_ensure_baseline_group_permissions,
		)

		_ensure_baseline_group_permissions()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Failed to ensure baseline group permissions")
