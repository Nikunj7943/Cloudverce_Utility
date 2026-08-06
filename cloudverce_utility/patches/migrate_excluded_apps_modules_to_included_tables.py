import frappe


def execute():
	"""One-time migration: the old free-text `excluded_apps` / `excluded_modules` Small
	Text fields on Cloudverce Utility Settings are being replaced by checkbox tables
	(`included_apps` / `included_modules` / `included_workspaces`). Anything already
	excluded there must carry forward as an unchecked row -- not silently re-included --
	so an existing site's RBAC scope doesn't change out from under it on upgrade.

	Runs post_model_sync, i.e. after the new Table fields already exist in the DB but
	the old Small Text fields no longer do -- so the old values are read directly from
	`tabSingles` (Frappe's generic single-doctype key/value store) instead of via the
	ORM, which would no longer know about them.
	"""
	if not frappe.db.exists("DocType", "Cloudverce Utility Settings"):
		return

	old_values = dict(
		frappe.db.sql(
			"""
			SELECT field, value FROM `tabSingles`
			WHERE doctype='Cloudverce Utility Settings' AND field IN ('excluded_apps', 'excluded_modules')
			"""
		)
	)
	excluded_apps = _parse_lines(old_values.get("excluded_apps"))
	excluded_modules = _parse_lines(old_values.get("excluded_modules"))
	if not excluded_apps and not excluded_modules:
		return

	settings = frappe.get_single("Cloudverce Utility Settings")
	changed = False

	existing_app_rows = {row.app_name: row for row in (settings.included_apps or [])}
	for app_name in excluded_apps:
		if app_name in existing_app_rows:
			existing_app_rows[app_name].included = 0
		else:
			settings.append("included_apps", {"app_name": app_name, "included": 0})
		changed = True

	existing_module_rows = {row.module_name: row for row in (settings.included_modules or [])}
	for module_name in excluded_modules:
		app_name = frappe.db.get_value("Module Def", module_name, "app_name") or ""
		if module_name in existing_module_rows:
			existing_module_rows[module_name].included = 0
		else:
			settings.append(
				"included_modules", {"module_name": module_name, "app_name": app_name, "included": 0}
			)
		changed = True

	if changed:
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)
		frappe.db.commit()

	frappe.db.sql(
		"""
		DELETE FROM `tabSingles`
		WHERE doctype='Cloudverce Utility Settings' AND field IN ('excluded_apps', 'excluded_modules')
		"""
	)


def _parse_lines(value):
	if not value:
		return set()
	tokens = set()
	for chunk in str(value).replace(",", "\n").splitlines():
		chunk = chunk.strip()
		if chunk:
			tokens.add(chunk)
	return tokens
