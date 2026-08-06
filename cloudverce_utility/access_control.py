import frappe
from frappe import _
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def add_bootinfo(bootinfo):
	context = get_list_settings_context(frappe.session.user)
	bootinfo.cloudverce_is_list_settings_admin = context["is_admin"]
	bootinfo.cloudverce_admin_group = context["group_name"]
	bootinfo.cloudverce_list_settings_doctypes = context["doctypes"]
	bootinfo.cloudverce_enable_session_timer = _session_timer_enabled()


def _session_timer_enabled():
	"""Whether the auto-logout session timer widget should run (default on)."""
	try:
		if frappe.db.exists("DocType", "Cloudverce Utility Settings"):
			value = frappe.db.get_single_value("Cloudverce Utility Settings", "enable_session_timer")
			return 0 if value in (0, "0") else 1
	except Exception:
		pass
	return 1


def get_list_settings_context(user=None):
	user = user or frappe.session.user
	group = _get_admin_group_for_user(user)
	doctypes = _get_allowed_list_settings_doctypes(user) if group else []

	return {
		"is_admin": bool(group),
		"group_name": group,
		"doctypes": doctypes,
	}


def _get_admin_group_for_user(user):
	if not user or user == "Guest":
		return None

	if "System Manager" in frappe.get_roles(user):
		return None

	group_names = _get_user_group_candidates(user)
	if not group_names:
		return None

	for group_name in group_names:
		group = frappe.db.get_value(
			"Cloudverce User Group",
			{"name": group_name},
			["name", "is_admin", "is_active"],
			as_dict=True,
		)
		if group and group.is_admin and group.is_active:
			return group.name

	return None


def _get_user_group_candidates(user):
	candidates = []
	seen = set()

	for profile_ref in _get_user_role_profile_refs(user):
		if profile_ref and profile_ref not in seen:
			candidates.append(profile_ref)
			seen.add(profile_ref)

		role_name = frappe.db.get_value("Role Profile", profile_ref, "role_profile")
		if role_name and role_name not in seen:
			candidates.append(role_name)
			seen.add(role_name)

	return [
		name for name in candidates
		if frappe.db.exists("Cloudverce User Group", {"name": name})
	]


def _get_user_role_profile_refs(user):
	refs = []
	seen = set()

	for profile in frappe.get_all(
		"User Role Profile",
		filters={"parent": user, "parenttype": "User"},
		pluck="role_profile",
	):
		profile = (profile or "").strip()
		if profile and profile not in seen:
			refs.append(profile)
			seen.add(profile)

	profile_name = (frappe.db.get_value("User", user, "role_profile_name") or "").strip()
	if profile_name and profile_name not in seen:
		refs.append(profile_name)

	return refs


def _get_allowed_list_settings_doctypes(user):
	from cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group import _get_managed_doctypes

	allowed = []
	for doctype in _get_managed_doctypes():
		meta = frappe.get_meta(doctype)
		if meta.istable or meta.issingle:
			continue
		if not frappe.has_permission(doctype=doctype, ptype="read", user=user):
			continue
		allowed.append(doctype)

	return allowed


def save_listview_settings(doctype, listview_settings, removed_listview_fields):
	_validate_list_settings_access(doctype)

	listview_settings = frappe.parse_json(listview_settings) or {}
	removed_listview_fields = frappe.parse_json(removed_listview_fields) or []

	doc = _upsert_list_view_settings(doctype, listview_settings)
	_set_listview_fields(doctype, listview_settings.get("fields"), removed_listview_fields)

	frappe.clear_cache(doctype=doctype)
	return {"meta": frappe.get_meta(doctype, cached=False), "listview_settings": doc}


def _validate_list_settings_access(doctype):
	if not doctype:
		frappe.throw(_("DocType is required"))

	if frappe.session.user == "Guest":
		raise frappe.PermissionError

	if "System Manager" in frappe.get_roles():
		return

	context = get_list_settings_context(frappe.session.user)
	if not context["is_admin"]:
		raise frappe.PermissionError

	if doctype not in context["doctypes"]:
		frappe.throw(
			_("List Settings are not allowed for {0}").format(frappe.bold(doctype)),
			exc=frappe.PermissionError,
		)

	if not frappe.has_permission(doctype=doctype, ptype="read"):
		raise frappe.PermissionError


def _upsert_list_view_settings(doctype, values):
	if frappe.db.exists("List View Settings", doctype):
		doc = frappe.get_doc("List View Settings", doctype)
		doc.update(values)
		doc.save(ignore_permissions=True)
		return doc

	doc = frappe.new_doc("List View Settings")
	doc.name = doctype
	doc.update(values)
	doc.insert(ignore_permissions=True)
	return doc


def _set_listview_fields(doctype, listview_fields, removed_listview_fields):
	meta = frappe.get_meta(doctype)
	listview_fields = [
		field.get("fieldname")
		for field in frappe.parse_json(listview_fields or [])
		if field.get("fieldname")
	]

	for fieldname in removed_listview_fields:
		_set_in_list_view_property(doctype, meta.get_field(fieldname), "0")

	for fieldname in listview_fields:
		_set_in_list_view_property(doctype, meta.get_field(fieldname), "1")


def _set_in_list_view_property(doctype, field, value):
	if not field or field.fieldname == "status_field":
		return

	property_setter = frappe.db.get_value(
		"Property Setter",
		{"doc_type": doctype, "field_name": field.fieldname, "property": "in_list_view"},
	)
	if property_setter:
		doc = frappe.get_doc("Property Setter", property_setter)
		doc.value = value
		doc.save(ignore_permissions=True)
		return

	make_property_setter(
		doctype,
		field.fieldname,
		"in_list_view",
		value,
		"Check",
		validate_fields_for_doctype=False,
	)


def on_user_update_clear_bootinfo(doc, method=None):
	clear_bootinfo_for_user(doc.name)


def invalidate_group_bootinfo(group_name):
	for user in _get_users_assigned_to_group(group_name):
		clear_bootinfo_for_user(user)


def clear_bootinfo_for_user(user):
	if user:
		frappe.cache.hdel("bootinfo", user)


def _get_users_assigned_to_group(group_name):
	if not group_name:
		return set()

	users = set()
	profile_candidates = {group_name}

	role_profile_name = frappe.db.get_value("Role Profile", {"role_profile": group_name}, "name")
	if role_profile_name:
		profile_candidates.add(role_profile_name)

	for profile_name in profile_candidates:
		for user in frappe.get_all(
			"User Role Profile",
			filters={"role_profile": profile_name, "parenttype": "User"},
			pluck="parent",
		):
			users.add(user)

		for user in frappe.get_all(
			"User",
			filters={"role_profile_name": profile_name},
			pluck="name",
		):
			users.add(user)

	return users


@frappe.whitelist()
def save_listview_settings_api(doctype, listview_settings, removed_listview_fields):
	return save_listview_settings(doctype, listview_settings, removed_listview_fields)
