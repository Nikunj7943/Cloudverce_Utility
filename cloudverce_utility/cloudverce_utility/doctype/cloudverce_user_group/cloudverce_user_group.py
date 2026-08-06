import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.model.document import Document
from frappe import _
from cloudverce_utility.role_profile_sync import (
	FRAPPE_SYSTEM_ROLES,
	_save_unlocking_if_needed,
	enqueue_role_profile_sync,
)

# Fieldtypes excluded from the field-permission popup's "currently visible fields"
# list: pure layout/UI (never real data fields) and child tables (a Grid isn't
# meaningfully toggled Hidden/Read-Only the same way a single-value field is — it
# always shows as-is, same as today, for every group).
LAYOUT_FIELDTYPES = {
	"Section Break", "Column Break", "Tab Break", "HTML", "Button",
	"Table", "Table MultiSelect",
}

# System fields that are never candidates for group-level field permission — their
# value is managed entirely by Frappe's own document lifecycle (e.g. amended_from is
# auto-set only when a cancelled submittable doc is amended), not business data a
# group's Hidden/Read-Only choice should apply to.
EXCLUDED_SYSTEM_FIELDNAMES = {"amended_from", "naming_series"}


class CloudverceUserGroup(Document):
	# ── Lifecycle ──────────────────────────────────────────────────────────

	def validate(self):
		if not self.group_name:
			frappe.throw(_("Group Name is mandatory"))
		self.group_name = self.group_name.strip()
		if self.group_name in FRAPPE_SYSTEM_ROLES:
			frappe.throw(
				_("'{0}' is a Frappe system role and cannot be managed as a Cloudverce User Group.").format(
					self.group_name
				)
			)
		self._normalize_permissions()
		self._lock_navigation_visibility_to_db()

	def _lock_navigation_visibility_to_db(self):
		"""CAPA FIX: navigation_visibility_json is written EXCLUSIVELY by the dedicated
		set_navigation_visibility() whitelisted endpoint, called immediately on every toggle
		click. The normal document Save (this validate/save cycle) must never be able to write
		this field, no matter what value the client payload carries — whether it's a stale
		snapshot, a mid-toggle DOM state, or anything else. This makes the field fully
		server-owned: any client-side timing issue in the main form's save flow becomes
		structurally unable to revert a toggle, because this method always discards whatever
		the client sent and re-pulls the current DB value right before the row is written.

		For a brand-new (unsaved) document there is no DB row yet, so the client-supplied
		default is kept as-is.
		"""
		if self.is_new():
			if not self.navigation_visibility_json:
				self.navigation_visibility_json = frappe.as_json({"hidden_labels": []})
			return

		# CAPA FIX: use SELECT ... FOR UPDATE, not a plain read. A plain read-then-write here
		# can lose a concurrent set_navigation_visibility() write: if the user toggles and then
		# immediately clicks Save, both requests hit the DB in quick succession. Whichever
		# transaction's WRITE commits last always wins -- so if THIS save's read landed before
		# the toggle's write committed, this save would silently re-persist the pre-toggle value
		# and overwrite the correct one. FOR UPDATE takes a row lock, forcing this transaction to
		# wait for any in-flight set_navigation_visibility() write to commit first, so the value
		# read here is always genuinely the latest one.
		row = frappe.db.sql(
			"SELECT navigation_visibility_json FROM `tabCloudverce User Group` WHERE name=%s FOR UPDATE",
			self.name,
		)
		self.navigation_visibility_json = (row and row[0][0]) or frappe.as_json({"hidden_labels": []})

	def _normalize_permissions(self):
		"""Drop empty / missing-doctype permission rows so a stale matrix entry
		(e.g. Fuel Urea Expenses after TMS was uninstalled or never installed on
		this site) cannot crash form open/save with 'DocType ... not found'.
		"""
		cleaned_rows = []
		for row in self.permissions or []:
			document_type = (row.get("document_type") or "").strip()
			if not document_type:
				continue
			if not frappe.db.exists("DocType", document_type):
				continue

			module = (row.get("module") or "").strip()
			if not module:
				module = frappe.db.get_value("DocType", document_type, "module") or ""
				if not module:
					continue
				row.module = module

			row.document_type = document_type
			cleaned_rows.append(row)

		if len(cleaned_rows) != len(self.permissions or []):
			self.set("permissions", cleaned_rows)

	# Superseded by _lock_navigation_visibility_to_db(), which now owns this field exclusively.
	# Kept for reference, not called.
	# def _normalize_navigation_visibility(self):
	# 	"""Keep the navigation visibility JSON valid and stable across saves."""
	# 	config = frappe.parse_json(self.navigation_visibility_json) or {}
	# 	hidden_labels = config.get("hidden_labels") or config.get("hidden") or []
	# 	if isinstance(hidden_labels, str):
	# 		hidden_labels = [hidden_labels]
	#
	# 	cleaned_hidden = []
	# 	seen = set()
	# 	for label in hidden_labels:
	# 		label = (label or "").strip()
	# 		if label and label not in seen:
	# 			cleaned_hidden.append(label)
	# 			seen.add(label)
	#
	# 	self.navigation_visibility_json = frappe.as_json({"hidden_labels": cleaned_hidden})

	def before_save(self):
		self._rename_target = None
		if not self.is_new() and self.group_name != self.name:
			self._rename_target = self.group_name
			self.group_name = self.name

	def on_update(self):
		if getattr(self, "_rename_target", None):
			frappe.rename_doc(
				"Cloudverce User Group",
				self.name,
				self._rename_target,
				force=True,
			)
			frappe.clear_cache()
			return

		_purge_orphaned_custom_docperms()
		_purge_orphaned_field_permlevel_property_setters()
		self._sync_role()
		self._sync_custom_docperms()
		self._sync_baseline_permissions()
		self._sync_field_permission_docperms()
		self._enqueue_role_profile_sync()
		self._invalidate_bootinfo()
		frappe.clear_cache()

	def on_trash(self):
		if self.group_name in FRAPPE_SYSTEM_ROLES:
			frappe.throw(
				_("System role '{0}' cannot be deleted from Cloudverce User Group.").format(self.group_name)
			)
		self._invalidate_bootinfo()
		self._validate_no_assigned_users()
		self._delete_linked_role_profile()
		self._delete_linked_role()

	def after_rename(self, old_name, new_name, merge=False):
		frappe.db.set_value("Cloudverce User Group", new_name, "group_name", new_name, update_modified=False)

		# Sync Role: rename existing or create fresh if it never existed
		if frappe.db.exists("Role", old_name):
			frappe.rename_doc("Role", old_name, new_name, force=True)
		elif not frappe.db.exists("Role", new_name):
			is_active = frappe.db.get_value("Cloudverce User Group", new_name, "is_active")
			frappe.get_doc({
				"doctype": "Role",
				"role_name": new_name,
				"desk_access": 1,
				"disabled": 0 if is_active else 1,
			}).insert(ignore_permissions=True)

		# Custom DocPerm rows still reference the old role name after Role rename.
		# Update them so permissions continue to work immediately.
		frappe.db.sql(
			"UPDATE `tabCustom DocPerm` SET role=%s WHERE role=%s",
			(new_name, old_name),
		)
		frappe.clear_cache(doctype="Custom DocPerm")

		# Sync Role Profile: rename by doc name first, then by role_profile field
		if frappe.db.exists("Role Profile", old_name):
			frappe.rename_doc("Role Profile", old_name, new_name, force=True)
			role_profile = frappe.get_doc("Role Profile", new_name)
			role_profile.role_profile = new_name
			for row in role_profile.roles or []:
				if row.role == old_name:
					row.role = new_name
			_save_unlocking_if_needed(role_profile)
		else:
			old_profile_name = frappe.db.get_value("Role Profile", {"role_profile": old_name}, "name")
			if old_profile_name:
				role_profile = frappe.get_doc("Role Profile", old_profile_name)
				role_profile.role_profile = new_name
				for row in role_profile.roles or []:
					if row.role == old_name:
						row.role = new_name
				_save_unlocking_if_needed(role_profile)
		self._invalidate_bootinfo()

	# ── Internal sync helpers ───────────────────────────────────────────────

	def _sync_role(self):
		role_name = self.group_name
		if not frappe.db.exists("Role", role_name):
			frappe.get_doc({
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": 1,
				"disabled": 0 if self.is_active else 1,
			}).insert(ignore_permissions=True)
		else:
			frappe.db.set_value("Role", role_name, "disabled",
				0 if self.is_active else 1)

		if not self.is_active:
			# frappe.get_roles() reads Has Role rows directly — Role.disabled alone does NOT
			# block access. We must delete the Has Role rows to revoke access immediately.
			# role_profiles child table is kept intact so reactivation can restore access.
			frappe.db.sql(
				"DELETE FROM `tabHas Role` WHERE role=%s AND parenttype='User'",
				role_name,
			)
		else:
			# Reactivation: restore Has Role rows for all users who still have this
			# group's profile assigned (role_profiles child table or deprecated field).
			_restore_has_role_for_profile(role_name)

	def _enqueue_role_profile_sync(self):
		try:
			enqueue_role_profile_sync(self.group_name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Failed to enqueue role profile sync for {self.group_name}")

	def _invalidate_bootinfo(self):
		from cloudverce_utility.access_control import invalidate_group_bootinfo

		invalidate_group_bootinfo(self.group_name)

	def _sync_custom_docperms(self):
		if self.flags.get("skip_custom_docperm_sync"):
			return

		role = self.group_name
		if frappe.db.get_value("Role", role, "disabled"):
			return

		# is_admin=1 → grant all permissions on all managed doctypes regardless of
		# what is stored in the permissions child table (which is disabled in the UI).
		_bulk_sync_custom_docperms(role, self.permissions, force_all=bool(self.is_admin))
		_ensure_protected_role_permissions()

	def _sync_baseline_permissions(self):
		if self.flags.get("skip_custom_docperm_sync"):
			return
		if frappe.db.get_value("Role", self.group_name, "disabled"):
			return
		_ensure_baseline_group_permissions([self.group_name])
		_ensure_protected_role_permissions(BASELINE_ALWAYS_GRANTED_DOCTYPES)

	def _sync_field_permission_docperms(self):
		"""Push this group's field_permissions (per-field Hidden/Read Only, real
		permlevel-based) into Custom DocPerm. Skipped for is_admin groups — they keep
		full access via the backfill grant every field already gets when it's first
		assigned a permlevel, exactly like the doctype-level matrix's force_all=True.
		"""
		if self.flags.get("skip_custom_docperm_sync"):
			return
		if self.is_admin:
			return
		role = self.group_name
		if frappe.db.get_value("Role", role, "disabled"):
			return
		# A group created/reactivated AFTER a field's permlevel was already assigned (and
		# backfilled for every group active at that time) would otherwise have NO grant
		# at that permlevel at all -- missing row = deny, so it would silently lose
		# access to a field every other group can already see. Backfill this group up to
		# the same default-visible baseline before applying its own customizations.
		_ensure_field_permlevel_baseline_for_role(role)
		_sync_field_permlevel_custom_docperms(role, self.field_permissions)

	# ── Validation & deletion helpers ──────────────────────────────────────

	def _validate_no_assigned_users(self):
		role_name = self.group_name
		profile_name = frappe.db.get_value("Role Profile", {"role_profile": role_name}, "name")

		# Direct role assignment (Has Role table)
		users_with_role = set(frappe.get_all(
			"Has Role",
			filters={"role": role_name, "parenttype": "User"},
			pluck="parent",
		))

		# Profile assignment — new way (Frappe v15 role_profiles child table)
		users_with_profile = set()
		if profile_name:
			users_with_profile = set(frappe.get_all(
				"User Role Profile",
				filters={"role_profile": profile_name, "parenttype": "User"},
				pluck="parent",
			))
			# Deprecated role_profile_name field (still used in some v15 installs)
			users_with_profile |= set(frappe.get_all(
				"User",
				filters={"role_profile_name": profile_name},
				pluck="name",
			))

		affected = sorted(users_with_role | users_with_profile)
		if affected:
			frappe.throw(
				_(
					"Cannot delete User Group <b>{0}</b>. It is assigned to {1} user(s): {2}.<br>"
					"Please unassign users first."
				).format(role_name, len(affected), ", ".join(affected))
			)

	def _delete_linked_role_profile(self):
		candidates = set()
		p = frappe.db.get_value("Role Profile", {"role_profile": self.group_name}, "name")
		if p:
			candidates.add(p)
		if frappe.db.exists("Role Profile", self.group_name):
			candidates.add(self.group_name)

		for profile_name in candidates:
			# Clear from Frappe v15 role_profiles child table
			frappe.db.sql(
				"DELETE FROM `tabUser Role Profile` WHERE role_profile=%s AND parenttype='User'",
				profile_name,
			)
			# Clear deprecated role_profile_name field
			frappe.db.sql(
				"UPDATE `tabUser` SET role_profile_name=NULL WHERE role_profile_name=%s",
				profile_name,
			)
			frappe.delete_doc("Role Profile", profile_name, ignore_permissions=True, force=True)

	def _delete_linked_role(self):
		role_name = self.group_name
		if not frappe.db.exists("Role", role_name):
			return

		# Remove all Custom DocPerm rows for this role on managed doctypes, plus the
		# always-on baseline doctypes (BASELINE_ALWAYS_GRANTED_DOCTYPES).
		managed = list(_get_managed_doctypes()) + list(BASELINE_ALWAYS_GRANTED_DOCTYPES)
		if managed:
			placeholders = ",".join(["%s"] * len(managed))
			frappe.db.sql(
				f"DELETE FROM `tabCustom DocPerm` WHERE role=%s AND parent IN ({placeholders})",
				[role_name] + managed,
			)

		# Remove Has Role assignments for this role from all users
		frappe.db.sql(
			"DELETE FROM `tabHas Role` WHERE role=%s",
			role_name,
		)

		frappe.delete_doc("Role", role_name, ignore_permissions=True, force=True)

	@frappe.whitelist()
	def sync_managed_doctypes(self):
		"""Housekeeping sync against managed doctypes for this Cloudverce User Group.

		Managed doctypes are auto-detected from every installed custom (non-core) app
		(see _get_managed_doctypes / _get_managed_modules). Removes permission rows for
		doctypes no longer managed. Does NOT add rows for newly-detected doctypes — a
		missing row is already an explicit deny.
		"""
		try:
			managed = set(_get_managed_doctypes())
			existing_permissions = {row.document_type: row for row in (self.permissions or [])}
			changed = False

			# CAPA FIX (v2): do NOT add rows for missing managed doctypes at all. A missing
			# row is already an explicit deny in _bulk_sync_custom_docperms, so auto-adding
			# all-zero rows (or worse, pre-filled rows) here would silently grant access on
			# every form open. This sync now ONLY REMOVES rows for doctypes no longer managed.
			# (Old behavior: pre-filled rows with perm_read/write/create/delete/print/report/
			# import/export/select all =1, granting near-full access silently on every refresh.)
			# for doctype in managed:
			# 	if doctype not in existing_permissions:
			# 		module = frappe.db.get_value("DocType", doctype, "module") or ""
			# 		self.append("permissions", {
			# 			"module": module,
			# 			"document_type": doctype,
			# 			"perm_read": 1,
			# 			"perm_write": 1,
			# 			"perm_create": 1,
			# 			"perm_delete": 1,
			# 			"perm_print": 1,
			# 			"perm_report": 1,
			# 			"perm_import": 1,
			# 			"perm_export": 1,
			# 			"perm_select": 1,
			# 		})
			# 		changed = True

			# Remove doctypes no longer managed
			rows_to_remove = []
			for doctype, row in existing_permissions.items():
				if doctype not in managed:
					rows_to_remove.append(row)
					changed = True

			for row in rows_to_remove:
				self.permissions.remove(row)

			if changed:
				# CAPA FIX (preventive): this method is invoked from the client with `doc: frm.doc`,
				# so `self` is built from the browser payload. Its only job is to sync managed
				# doctypes into the permissions table — it must never persist a stale/empty
				# navigation_visibility_json and wipe the group's dashboard/page visibility.
				# Re-load the persisted value from DB before saving.
				self.navigation_visibility_json = frappe.db.get_value(
					"Cloudverce User Group", self.name, "navigation_visibility_json"
				)
				self.flags.ignore_permissions = True
				self.flags.skip_custom_docperm_sync = False
				self.save(ignore_permissions=True)
				# This server-side save bumps `modified` behind the open form's back. The
				# form still holds the older timestamp, so the user's very next Save (e.g.
				# ticking Is Admin right after opening) raised a false TimestampMismatchError.
				# Return the fresh timestamp so the client can update frm.doc.modified (same
				# pattern as set_navigation_visibility).
				return {"changed": True, "modified": str(self.modified)}

			return {"changed": False}

		except Exception:
			frappe.log_error(frappe.get_traceback(), "Failed to sync managed doctypes")
			return {"changed": False}


# ── Module-level helpers ────────────────────────────────────────────────────


def _restore_has_role_for_profile(role_name):
	"""Re-add Has Role rows for users who still have this role's profile assigned.

	Called when a group is reactivated (is_active 0 → 1). Deactivation only removes
	Has Role rows; the role_profiles assignment is kept intact so we can restore here.
	Uses a single bulk INSERT IGNORE instead of a per-user loop.
	"""
	profile_name = frappe.db.get_value("Role Profile", {"role_profile": role_name}, "name")
	if not profile_name:
		return

	# Collect users from both Frappe v16 role_profiles table and deprecated field
	users_new = set(frappe.get_all(
		"User Role Profile",
		filters={"role_profile": profile_name, "parenttype": "User"},
		pluck="parent",
	))
	users_old = set(frappe.get_all(
		"User",
		filters={"role_profile_name": profile_name},
		pluck="name",
	))
	all_users = users_new | users_old
	if not all_users:
		return

	# Exclude users who already have the Has Role row
	existing = set(frappe.get_all(
		"Has Role",
		filters={"role": role_name, "parenttype": "User", "parent": ["in", list(all_users)]},
		pluck="parent",
	))
	to_restore = all_users - existing
	if not to_restore:
		return

	now = frappe.utils.now()
	admin = frappe.session.user or "Administrator"
	col_list = "name, creation, modified, modified_by, owner, parent, parenttype, parentfield, role"
	row_tpl = "(%s, %s, %s, %s, %s, %s, 'User', 'roles', %s)"
	placeholders = ", ".join([row_tpl] * len(to_restore))
	values = []
	for user in to_restore:
		values += [frappe.generate_hash(10), now, now, admin, admin, user, role_name]
	frappe.db.sql(
		f"INSERT IGNORE INTO `tabHas Role` ({col_list}) VALUES {placeholders}",
		values,
	)


def _ensure_protected_role_permissions(doctypes=None):
	"""Ensure admin access remains intact on managed doctypes.

	Cloudverce User Group sync writes Custom DocPerm rows for business roles. Once any
	Custom DocPerm exists on a doctype, Frappe resolves permissions from that
	table first. To keep admin access stable across sites after migrate/sync, we
	explicitly grant full Custom DocPerm access to Administrator and System
	Manager on every managed doctype. For other protected roles, we only mirror
	file-based DocPerm rows when they exist.
	"""
	managed = list(doctypes or _get_managed_doctypes())
	if not managed:
		return

	full_admin_roles = ("Administrator", "System Manager")
	# Do not mirror broad default roles. "All" applies to every user and would
	# bypass Cloudverce User Group grants; "Desk User" applies to most system users.
	mirror_roles = sorted(FRAPPE_SYSTEM_ROLES - {"Administrator", "System Manager", "All", "Guest", "Desk User"})
	protected_roles = sorted(set(full_admin_roles) | set(mirror_roles))
	native_rows = frappe.get_all(
		"DocPerm",
		filters={
			"parent": ["in", managed],
			"permlevel": 0,
			"role": ["in", mirror_roles],
		},
		fields=["parent", "role"] + list(PERM_MAP.keys()),
	)

	native_map = {
		(row.parent, row.role): {col: int(bool(row.get(col))) for col in PERM_MAP}
		for row in native_rows
	}

	existing_map = {
		(row.parent, row.role): row
		for row in frappe.get_all(
			"Custom DocPerm",
			filters={
				"parent": ["in", managed],
				"permlevel": 0,
				"role": ["in", protected_roles],
			},
			fields=["name", "parent", "role"] + list(PERM_MAP.keys()),
		)
	}

	stale_zero_rows = []
	for key, row in existing_map.items():
		native_perm = native_map.get(key) or {}
		if not native_perm or not any(native_perm.values()):
			continue
		if any(int(bool(row.get(col))) for col in PERM_MAP):
			continue
		stale_zero_rows.append(row.name)

	if stale_zero_rows:
		frappe.db.sql(
			f"DELETE FROM `tabCustom DocPerm` WHERE name IN ({','.join(['%s'] * len(stale_zero_rows))})",
			stale_zero_rows,
		)
		existing_map = {
			key: row for key, row in existing_map.items() if row.name not in set(stale_zero_rows)
		}

	now = frappe.utils.now()
	user = frappe.session.user or "Administrator"
	perm_cols = list(PERM_MAP.keys())
	to_insert = []
	to_update = []

	full_admin_set = set(full_admin_roles)
	full_perm_map = {col: 1 for col in perm_cols}

	for doctype in managed:
		for role in full_admin_roles:
			existing_row = existing_map.get((doctype, role))
			if existing_row:
				current_perm_map = {col: int(bool(existing_row.get(col))) for col in perm_cols}
				if current_perm_map != full_perm_map:
					to_update.append((existing_row.name, full_perm_map))
			else:
				to_insert.append((doctype, role, [1] * len(perm_cols)))

	for row in native_rows:
		if row.role in full_admin_set:
			continue
		if existing_map.get((row.parent, row.role)):
			continue
		perm_vals = [int(bool(row.get(col))) for col in perm_cols]
		to_insert.append((row.parent, row.role, perm_vals))

	if to_update:
		set_clause = ", ".join(f"`{col}` = %s" for col in perm_cols)
		update_sql = (
			f"UPDATE `tabCustom DocPerm` SET {set_clause}, modified=%s, modified_by=%s WHERE name=%s"
		)
		for name, perm_map in to_update:
			frappe.db.sql(update_sql, [perm_map[col] for col in perm_cols] + [now, user, name])

	if not to_insert and not to_update:
		return

	col_list = (
		"name, creation, modified, modified_by, owner, docstatus, idx, "
		"parent, role, permlevel, if_owner, "
		+ ", ".join(f"`{c}`" for c in perm_cols)
	)
	if to_insert:
		row_tpl = f"(%s, %s, %s, %s, %s, 0, 0, %s, %s, 0, 0, {', '.join(['%s'] * len(perm_cols))})"
		placeholders = ", ".join([row_tpl] * len(to_insert))
		values = []

		for doctype, role, perm_vals in to_insert:
			values += [frappe.generate_hash(length=10), now, now, user, user, doctype, role] + perm_vals

		frappe.db.sql(
			f"INSERT IGNORE INTO `tabCustom DocPerm` ({col_list}) VALUES {placeholders}",
			values,
		)
	frappe.clear_cache(doctype="Custom DocPerm")


def _purge_orphaned_custom_docperms():
	"""Delete Custom DocPerm rows whose parent doctype no longer exists.

	Other apps can be installed/uninstalled independently of cloudverce_utility;
	Frappe's uninstaller only cleans up records the uninstalled app itself
	created, so Custom DocPerm rows we wrote for that app's doctypes are left
	behind pointing at nothing. Frappe core's own permission loading
	(frappe.permissions.get_valid_perms) queries Custom DocPerm by role with
	no existence check, so a single orphaned row crashes every save/boot for
	any role that has it. This keeps the table self-healing on any bench.
	"""
	orphaned = frappe.db.sql(
		"""
		SELECT cdp.name FROM `tabCustom DocPerm` cdp
		LEFT JOIN `tabDocType` dt ON dt.name = cdp.parent
		WHERE dt.name IS NULL
		""",
		as_dict=True,
	)
	if not orphaned:
		return

	names = [r.name for r in orphaned]
	frappe.db.sql(
		f"DELETE FROM `tabCustom DocPerm` WHERE name IN ({','.join(['%s'] * len(names))})",
		names,
	)
	frappe.clear_cache(doctype="Custom DocPerm")


def _purge_orphaned_field_permlevel_property_setters():
	"""Delete field-permlevel Property Setter rows (and any Custom DocPerm /
	field_permissions rows built on top of them) whose doc_type no longer exists.

	Mirrors _purge_orphaned_custom_docperms(): when another app is uninstalled after
	cloudverce_utility already assigned permlevels to its fields (via _assign_permlevel_for_field),
	Frappe's uninstaller only cleans up records that app itself created -- the Property
	Setter rows we wrote are left behind pointing at nothing. Without this, every
	Cloudverce User Group save calls frappe.get_meta() on the orphaned doc_type inside
	_ensure_field_permlevel_baseline_for_role() and crashes with "DocType ... not found"
	for every group, not just ones referencing that doctype. This keeps the table
	self-healing on any bench, same as the Custom DocPerm purge.
	"""
	orphaned = frappe.db.sql(
		"""
		SELECT ps.name, ps.doc_type FROM `tabProperty Setter` ps
		LEFT JOIN `tabDocType` dt ON dt.name = ps.doc_type
		WHERE ps.doctype_or_field='DocField' AND ps.property='permlevel' AND dt.name IS NULL
		""",
		as_dict=True,
	)
	if not orphaned:
		return

	ps_names = [r.name for r in orphaned]
	orphaned_doctypes = sorted({r.doc_type for r in orphaned})

	frappe.db.sql(
		f"DELETE FROM `tabProperty Setter` WHERE name IN ({','.join(['%s'] * len(ps_names))})",
		ps_names,
	)

	placeholders = ",".join(["%s"] * len(orphaned_doctypes))
	frappe.db.sql(
		f"DELETE FROM `tabCustom DocPerm` WHERE permlevel > 0 AND parent IN ({placeholders})",
		orphaned_doctypes,
	)
	frappe.db.sql(
		f"DELETE FROM `tabCloudverce User Group Field Permission` WHERE document_type IN ({placeholders})",
		orphaned_doctypes,
	)

	frappe.clear_cache()


def _describe_workspace_shortcuts(workspace_name):
	"""Human-readable summary of the DocType Link items actually in a real Desk sidebar
	("Workspace Sidebar") right now, e.g. "Work Order Fabro, Sales Invoice" -- or "" if it
	has none. Used to populate Cloudverce Utility Included Workspace's read-only "Sidebar
	Shortcuts" column so an admin can see what's really in a sidebar directly from
	Settings, without opening the Workspace Editor or a Cloudverce User Group form.
	"""
	try:
		sidebar = frappe.get_doc("Workspace Sidebar", workspace_name)
	except Exception:
		return ""
	labels = [
		(i.label or i.link_to or "").strip()
		for i in (sidebar.items or [])
		if (getattr(i, "type", "") or "").strip() == "Link"
		and (getattr(i, "link_type", "") or "").strip() == "DocType"
		and (i.link_to or "").strip()
	]
	return ", ".join(labels)


@frappe.whitelist()
def refresh_workspace_sidebar_preview():
	"""On-demand refresh of every Included Workspace row's "Sidebar Shortcuts" column,
	for the Settings form's "Refresh Sidebar Preview" button -- so an admin sees current
	shortcuts immediately after adding/removing one, without waiting for the next
	`bench migrate` (which is when _sync_included_scope_tables() would otherwise refresh it).
	"""
	if not frappe.has_permission("Cloudverce Utility Settings", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	settings = frappe.get_single("Cloudverce Utility Settings")
	changed = False
	for row in (settings.included_workspaces or []):
		fresh = _describe_workspace_shortcuts(row.workspace_name)
		if fresh != (row.sidebar_shortcuts or ""):
			row.sidebar_shortcuts = fresh
			changed = True

	if changed:
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)
		frappe.db.commit()

	return {"refreshed": changed}


def _bootstrap_missing_workspace_sidebars():
	"""Portability safeguard: on a fresh bench, a custom app may have a "Workspace"
	(the older, universal Frappe feature) but no "Workspace Sidebar" yet (the newer,
	real Desk left-nav that everything in this file is built on) -- e.g. the app was
	never opened in a v16-era Desk session, or the sidebar was simply never generated.
	Without this, _get_shortcut_referenced_doctypes() / get_eligible_sidebar_workspaces()
	would find nothing for that app: the Permission Matrix stays silently empty AND the
	"+ Add DocType" dialog's sidebar dropdown has nowhere to add to either -- no way to
	bootstrap out of it from the UI.

	Reuses Frappe's own `create_workspace_sidebar_for_workspaces()` (same one `bench`
	exposes for this exact purpose) rather than reimplementing it: idempotent, skips any
	workspace that already has a sidebar, and copies each remaining workspace's own
	shortcuts into a new standard Workspace Sidebar. Safe to call on every migrate.
	"""
	try:
		from frappe.desk.doctype.workspace_sidebar.workspace_sidebar import (
			create_workspace_sidebar_for_workspaces,
		)

		create_workspace_sidebar_for_workspaces()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Failed to bootstrap missing Workspace Sidebars")


def _sync_included_scope_tables():
	"""Additive-only sync of Cloudverce Utility Settings' Included Apps/Modules/Workspaces
	checkbox tables against what's actually installed. Called from install.py's
	after_migrate, mirroring the orphan-cleanup pattern already used above for Custom
	DocPerm / Property Setter rows: adds a checked row for anything new (never touches
	an existing row's checked state -- preserves an admin's prior choice across every
	future migrate), and removes rows for anything no longer installed, so an
	uninstalled app/module/workspace doesn't leave a permanently-stuck checkbox behind.
	Also refreshes every Included Workspace row's "Sidebar Shortcuts" preview column
	(see _describe_workspace_shortcuts()) so it stays current on every migrate too.
	"""
	if not frappe.db.exists("DocType", "Cloudverce Utility Settings"):
		return

	settings = frappe.get_single("Cloudverce Utility Settings")
	changed = False

	installed_apps = [a for a in frappe.get_installed_apps() if a not in CORE_APPS]

	existing_app_rows = {row.app_name: row for row in (settings.included_apps or [])}
	for app_name in installed_apps:
		if app_name not in existing_app_rows:
			settings.append("included_apps", {"app_name": app_name, "included": 1})
			changed = True
	for name, row in list(existing_app_rows.items()):
		if name not in installed_apps:
			settings.included_apps.remove(row)
			changed = True

	# Every module belonging to any non-core installed app, regardless of whether that
	# app is currently checked -- unchecking an app must not hide its modules from ever
	# being individually re-included later.
	modules = frappe.get_all(
		"Module Def", filters={"app_name": ["in", installed_apps]}, fields=["name", "app_name"]
	) if installed_apps else []
	module_names = {m.name for m in modules}

	existing_module_rows = {row.module_name: row for row in (settings.included_modules or [])}
	for m in modules:
		if m.name not in existing_module_rows:
			settings.append(
				"included_modules", {"module_name": m.name, "app_name": m.app_name, "included": 1}
			)
			changed = True
	for name, row in list(existing_module_rows.items()):
		if name not in module_names:
			settings.included_modules.remove(row)
			changed = True

	_bootstrap_missing_workspace_sidebars()

	# Every standard (app-wide, not per-user) Workspace Sidebar belonging to any of the
	# modules above -- the real Desk left-nav, not the older Workspace doctype's own
	# shortcuts/links -- same additive rule.
	workspaces = frappe.get_all(
		"Workspace Sidebar",
		filters={"module": ["in", list(module_names)], "standard": 1},
		fields=["name", "module", "for_user"],
	) if module_names else []
	workspaces = [w for w in workspaces if not w.for_user]
	workspace_names = {w.name for w in workspaces}

	existing_ws_rows = {row.workspace_name: row for row in (settings.included_workspaces or [])}
	for w in workspaces:
		if w.name not in existing_ws_rows:
			settings.append(
				"included_workspaces",
				{
					"workspace_name": w.name,
					"module_name": w.module,
					"included": 1,
					"sidebar_shortcuts": _describe_workspace_shortcuts(w.name),
				},
			)
			changed = True
	for name, row in list(existing_ws_rows.items()):
		if name not in workspace_names:
			settings.included_workspaces.remove(row)
			changed = True

	# Refresh the "Sidebar Shortcuts" preview on every row (new or pre-existing) so it
	# never goes stale between migrates -- shortcuts get added/removed far more often
	# (via "+ Add DocType" on any Cloudverce User Group form) than a migrate typically runs.
	for row in (settings.included_workspaces or []):
		fresh = _describe_workspace_shortcuts(row.workspace_name)
		if fresh != (row.sidebar_shortcuts or ""):
			row.sidebar_shortcuts = fresh
			changed = True

	if changed:
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)
		frappe.db.commit()


def _bulk_sync_custom_docperms(role, permission_rows, force_all=False):
	"""Bulk-sync Cloudverce User Group permissions → Custom DocPerm table.

	force_all=True is used for is_admin=1 groups: all permissions are set to 1
	regardless of what the permissions child table contains.
	"""
	if role in FRAPPE_SYSTEM_ROLES:
		return

	managed_doctypes = list(_get_managed_doctypes())
	if not managed_doctypes:
		return

	granted = {row.document_type: row for row in (permission_rows or [])}

	existing_map = {
		r.parent: r.name
		for r in frappe.db.get_all(
			"Custom DocPerm",
			filters={"role": role, "parent": ["in", managed_doctypes], "permlevel": 0},
			fields=["name", "parent"],
		)
	}

	perm_cols = list(PERM_MAP.keys())
	now = frappe.utils.now()
	user = frappe.session.user or "Administrator"

	to_insert = []
	to_update = []
	deny_to_delete = []

	# Pass 1: identify stale explicit-deny rows to delete (only when not force_all)
	if not force_all:
		for doctype in managed_doctypes:
			if doctype in _NO_EXPLICIT_DENY and granted.get(doctype) is None:
				existing_name = existing_map.get(doctype)
				if existing_name:
					deny_to_delete.append(existing_name)

	if deny_to_delete:
		frappe.db.sql(
			f"DELETE FROM `tabCustom DocPerm` WHERE name IN ({','.join(['%s']*len(deny_to_delete))})",
			deny_to_delete,
		)

	# Pass 2: build insert / update lists
	for doctype in managed_doctypes:
		row = granted.get(doctype)

		if not force_all and doctype in _NO_EXPLICIT_DENY and row is None:
			continue

		if force_all:
			perm_vals = {ff: 1 for ff in PERM_MAP}
		elif row is not None:
			perm_vals = {ff: int(bool(getattr(row, cf, 0))) for ff, cf in PERM_MAP.items()}
		else:
			perm_vals = {ff: 0 for ff in PERM_MAP}

		existing_name = existing_map.get(doctype)
		if existing_name:
			to_update.append((existing_name, perm_vals))
		else:
			to_insert.append((doctype, perm_vals))

	if to_update:
		set_clause = ", ".join(f"`{col}` = %s" for col in perm_cols)
		update_sql = (
			f"UPDATE `tabCustom DocPerm` SET {set_clause}, modified=%s, modified_by=%s WHERE name=%s"
		)
		for name, pv in to_update:
			frappe.db.sql(update_sql, [pv[col] for col in perm_cols] + [now, user, name])

	if to_insert:
		col_list = (
			"name, creation, modified, modified_by, owner, docstatus, idx, "
			"parent, role, permlevel, if_owner, "
			+ ", ".join(f"`{c}`" for c in perm_cols)
		)
		row_tpl = f"(%s, %s, %s, %s, %s, 0, 0, %s, %s, 0, 0, {', '.join(['%s']*len(perm_cols))})"
		placeholders = ", ".join([row_tpl] * len(to_insert))
		values = []
		for doctype, pv in to_insert:
			row_name = frappe.generate_hash(length=10)
			values += [row_name, now, now, user, user, doctype, role] + [pv[c] for c in perm_cols]
		frappe.db.sql(
			f"INSERT IGNORE INTO `tabCustom DocPerm` ({col_list}) VALUES {placeholders}",
			values,
		)

	frappe.clear_cache(doctype="Custom DocPerm")


def _ensure_baseline_group_permissions(roles=None):
	"""Grant Custom DocPerm access on BASELINE_ALWAYS_GRANTED_DOCTYPES to every
	Cloudverce User Group role. Unlike the permissions matrix, this set is not exposed
	in the UI and can't be toggled off.

	Full access for all of them, EXCEPT doctypes listed in
	BASELINE_RESTRICTED_FOR_NON_ADMIN (currently just "User"): non-admin (is_admin=0)
	groups get only that doctype's reduced column set there — combined with the
	get_permission_query_conditions_user/has_permission_user hooks (see
	navigation_visibility.py, wired in hooks.py), this means a normal user can see
	and edit only their own User record (e.g. change their own password), never anyone
	else's. is_admin=1 groups keep full access, same as before.

	roles=None syncs every active Cloudverce User Group (used from install.after_migrate
	so existing groups converge on every migrate, without a one-time patch). Passing
	an explicit role list is used from on_update() for a single group.
	"""
	baseline = [dt for dt in BASELINE_ALWAYS_GRANTED_DOCTYPES if frappe.db.exists("DocType", dt)]
	if not baseline:
		return

	if roles is None:
		roles = frappe.get_all("Cloudverce User Group", filters={"is_active": 1}, pluck="group_name")
	roles = [r for r in roles if r and r not in FRAPPE_SYSTEM_ROLES]
	if not roles:
		return

	role_is_admin = {
		r.group_name: bool(r.is_admin)
		for r in frappe.get_all(
			"Cloudverce User Group", filters={"group_name": ["in", roles]}, fields=["group_name", "is_admin"]
		)
	}

	existing_map = {
		(r.parent, r.role): r
		for r in frappe.get_all(
			"Custom DocPerm",
			filters={"role": ["in", roles], "parent": ["in", baseline], "permlevel": 0},
			fields=["name", "parent", "role"] + BASELINE_PERM_COLUMNS,
		)
	}

	now = frappe.utils.now()
	user = frappe.session.user or "Administrator"
	full_perm_map = {col: 1 for col in BASELINE_PERM_COLUMNS}

	def _target_perm_map(doctype, role):
		restricted_cols = BASELINE_RESTRICTED_FOR_NON_ADMIN.get(doctype)
		if restricted_cols is not None and not role_is_admin.get(role):
			return {col: (1 if col in restricted_cols else 0) for col in BASELINE_PERM_COLUMNS}
		return full_perm_map

	to_insert = []
	to_update = []

	for role in roles:
		for doctype in baseline:
			target = _target_perm_map(doctype, role)
			existing_row = existing_map.get((doctype, role))
			if existing_row:
				current = {col: int(bool(existing_row.get(col))) for col in BASELINE_PERM_COLUMNS}
				if current != target:
					to_update.append((existing_row.name, target))
			else:
				to_insert.append((doctype, role, target))

	if to_update:
		for name, target in to_update:
			set_clause = ", ".join(f"`{col}` = %s" for col in BASELINE_PERM_COLUMNS)
			frappe.db.sql(
				f"UPDATE `tabCustom DocPerm` SET {set_clause}, modified=%s, modified_by=%s WHERE name=%s",
				[target[col] for col in BASELINE_PERM_COLUMNS] + [now, user, name],
			)

	if to_insert:
		col_list = (
			"name, creation, modified, modified_by, owner, docstatus, idx, "
			"parent, role, permlevel, if_owner, "
			+ ", ".join(f"`{c}`" for c in BASELINE_PERM_COLUMNS)
		)
		row_tpl = f"(%s, %s, %s, %s, %s, 0, 0, %s, %s, 0, 0, {', '.join(['%s']*len(BASELINE_PERM_COLUMNS))})"
		placeholders = ", ".join([row_tpl] * len(to_insert))
		values = []
		for doctype, role, target in to_insert:
			row_name = frappe.generate_hash(length=10)
			values += [row_name, now, now, user, user, doctype, role]
			values += [target[col] for col in BASELINE_PERM_COLUMNS]
		frappe.db.sql(
			f"INSERT IGNORE INTO `tabCustom DocPerm` ({col_list}) VALUES {placeholders}",
			values,
		)

	if to_insert or to_update:
		frappe.clear_cache(doctype="Custom DocPerm")


# ── Field-level permission (per-field Hidden / Read Only via real permlevel) ────


def _assign_permlevel_for_field(doctype, fieldname):
	"""Ensure `fieldname` on `doctype` has its own unique, never-reused permlevel (>0),
	assigning one via Property Setter on first use and backfilling full access for every
	currently-active group + admin roles so the field's visibility never changes for
	anyone until a group explicitly restricts it via the field-permission popup. Returns
	the field's permlevel (existing or newly assigned).
	"""
	if not doctype or not fieldname or not frappe.db.exists("DocType", doctype):
		return 0

	existing = frappe.db.get_value(
		"Property Setter",
		{"doc_type": doctype, "field_name": fieldname, "property": "permlevel"},
		"value",
	)
	if existing:
		return frappe.utils.cint(existing)

	max_level = frappe.db.sql(
		"SELECT MAX(CAST(value AS UNSIGNED)) FROM `tabProperty Setter` "
		"WHERE doctype_or_field='DocField' AND property='permlevel'"
	)[0][0]
	new_level = frappe.utils.cint(max_level or 0) + 1

	make_property_setter(doctype, fieldname, "permlevel", new_level, "Int")

	df = frappe.get_meta(doctype).get_field(fieldname)
	_backfill_field_permlevel_grants(doctype, new_level, read_only=bool(df and df.read_only))

	return new_level


def _backfill_field_permlevel_grants(doctype, permlevel, read_only=False):
	"""Grant every currently-active Cloudverce User Group + Administrator + System Manager
	access at `permlevel` for `doctype`, so a field's first-ever permlevel assignment
	never hides it from anyone who could already see it. `read_only=True` grants
	read-only (for fields that were already structurally read_only=1); otherwise full
	read+write. Only a group's own explicit Hidden/Read Only choice in the field
	permission popup (synced via _sync_field_permlevel_custom_docperms) changes this
	afterwards.
	"""
	roles = frappe.get_all("Cloudverce User Group", filters={"is_active": 1}, pluck="group_name")
	roles = [r for r in roles if r not in FRAPPE_SYSTEM_ROLES]
	roles += ["Administrator", "System Manager"]
	if not roles:
		return

	existing_roles = set(frappe.get_all(
		"Custom DocPerm",
		filters={"parent": doctype, "permlevel": permlevel, "role": ["in", roles]},
		pluck="role",
	))
	to_insert = [r for r in roles if r not in existing_roles]
	if not to_insert:
		return

	now = frappe.utils.now()
	user = frappe.session.user or "Administrator"
	write_val = 0 if read_only else 1
	col_list = (
		"name, creation, modified, modified_by, owner, docstatus, idx, "
		"parent, role, permlevel, if_owner, `read`, `write`"
	)
	row_tpl = "(%s, %s, %s, %s, %s, 0, 0, %s, %s, %s, 0, 1, %s)"
	placeholders = ", ".join([row_tpl] * len(to_insert))
	values = []
	for role in to_insert:
		values += [frappe.generate_hash(length=10), now, now, user, user, doctype, role, permlevel, write_val]
	frappe.db.sql(
		f"INSERT IGNORE INTO `tabCustom DocPerm` ({col_list}) VALUES {placeholders}",
		values,
	)
	frappe.clear_cache(doctype="Custom DocPerm")


def _ensure_field_permlevel_baseline_for_role(role):
	"""Backfill full access (or read-only, for structurally-read-only fields) at every
	field-permlevel already assigned SO FAR, for any permlevel this role has no
	explicit Custom DocPerm row at yet.

	_backfill_field_permlevel_grants() only runs once, at the moment a field FIRST
	gets its permlevel, and only covers groups active at that instant. A group
	created (or reactivated) afterwards would otherwise have NO row at all for that
	permlevel — missing row = deny — silently losing access to a field every other
	group can already see. This makes every group converge on the same default-visible
	baseline before its own explicit Hidden/Read Only customizations are applied.
	"""
	assignments = frappe.get_all(
		"Property Setter",
		filters={"doctype_or_field": "DocField", "property": "permlevel"},
		fields=["doc_type", "field_name", "value"],
	)
	if not assignments:
		return

	existing = {
		(r.parent, r.permlevel)
		for r in frappe.get_all(
			"Custom DocPerm",
			filters={"role": role, "permlevel": [">", 0]},
			fields=["parent", "permlevel"],
		)
	}

	now = frappe.utils.now()
	user = frappe.session.user or "Administrator"
	to_insert = []
	for row in assignments:
		permlevel = frappe.utils.cint(row.value)
		key = (row.doc_type, permlevel)
		if not permlevel or key in existing:
			continue
		if not frappe.db.exists("DocType", row.doc_type):
			continue
		df = frappe.get_meta(row.doc_type).get_field(row.field_name)
		write_val = 0 if (df and df.read_only) else 1
		to_insert.append((row.doc_type, permlevel, write_val))

	if not to_insert:
		return

	col_list = (
		"name, creation, modified, modified_by, owner, docstatus, idx, "
		"parent, role, permlevel, if_owner, `read`, `write`"
	)
	row_tpl = "(%s, %s, %s, %s, %s, 0, 0, %s, %s, %s, 0, 1, %s)"
	placeholders = ", ".join([row_tpl] * len(to_insert))
	values = []
	for doctype, permlevel, write_val in to_insert:
		values += [frappe.generate_hash(length=10), now, now, user, user, doctype, role, permlevel, write_val]
	frappe.db.sql(
		f"INSERT IGNORE INTO `tabCustom DocPerm` ({col_list}) VALUES {placeholders}",
		values,
	)
	frappe.clear_cache(doctype="Custom DocPerm")


def _sync_field_permlevel_custom_docperms(role, field_permission_rows):
	"""Turn a group's field_permissions rows into real Custom DocPerm grants, one row
	per (doctype, field's own unique permlevel). Each field has its own permlevel, so
	this is a straightforward per-field mapping — no bucket-sharing/cross-field effects.

	Every permlevel>0 Custom DocPerm row for a Cloudverce User Group role belongs
	exclusively to this field-permission feature (permlevel 0 is the separate
	doctype-level matrix; nothing else in this app uses permlevel). So ANY such row
	that is no longer referenced by a current field_permissions row (the admin
	removed it, i.e. set the field back to "Default") must be reconciled back to full
	access here — otherwise a field that was once Hidden/Read Only would stay stuck at
	that stale state forever after being reverted to Default in the UI.
	"""
	if role in FRAPPE_SYSTEM_ROLES:
		return

	targets = {
		(r.document_type, r.permlevel): r.field_state
		for r in (field_permission_rows or [])
		if r.permlevel and r.document_type and frappe.db.exists("DocType", r.document_type)
	}

	existing_map = {
		(r.parent, r.permlevel): r
		for r in frappe.get_all(
			"Custom DocPerm",
			filters={"role": role, "permlevel": [">", 0]},
			fields=["name", "parent", "permlevel", "read", "write"],
		)
	}

	now = frappe.utils.now()
	user = frappe.session.user or "Administrator"
	to_delete = []

	for key in set(existing_map) | set(targets):
		doctype, permlevel = key
		state = targets.get(key)  # None => row removed, i.e. back to Default
		existing_row = existing_map.get(key)
		want_read_write = (1, 0) if state == "Read Only" else (1, 1)  # Hidden handled below

		if state == "Hidden":
			if existing_row:
				to_delete.append(existing_row.name)
			continue

		if existing_row:
			if (existing_row.read, existing_row.write) != want_read_write:
				frappe.db.sql(
					"UPDATE `tabCustom DocPerm` SET `read`=%s, `write`=%s, modified=%s, modified_by=%s WHERE name=%s",
					(*want_read_write, now, user, existing_row.name),
				)
		else:
			frappe.db.sql(
				"INSERT IGNORE INTO `tabCustom DocPerm` "
				"(name, creation, modified, modified_by, owner, docstatus, idx, "
				" parent, role, permlevel, if_owner, `read`, `write`) "
				"VALUES (%s, %s, %s, %s, %s, 0, 0, %s, %s, %s, 0, %s, %s)",
				(frappe.generate_hash(length=10), now, now, user, user, doctype, role, permlevel, *want_read_write),
			)

	if to_delete:
		frappe.db.sql(
			f"DELETE FROM `tabCustom DocPerm` WHERE name IN ({','.join(['%s']*len(to_delete))})",
			to_delete,
		)

	frappe.clear_cache(doctype="Custom DocPerm")


# ── Whitelisted API endpoints ───────────────────────────────────────────────


@frappe.whitelist()
def get_permission_matrix():
	doctype_names = set(_get_managed_doctypes())
	return _group_doctypes_by_module(doctype_names)


@frappe.whitelist()
def get_eligible_sidebar_workspaces():
	"""Workspace Sidebars an admin may add a DocType to, via the Cloudverce User Group form's
	Add DocType dialog -- every STANDARD (app-wide) sidebar belonging to a managed module,
	minus any explicitly excluded in Included Workspaces. Powers that dialog's Sidebar
	dropdown so an admin can only ever pick a sidebar actually in RBAC scope, never a
	Frappe/ERPNext-internal one, a per-user customized copy, or one deliberately excluded.
	"""
	modules = _get_managed_modules()
	if not modules:
		return []
	excluded = _get_excluded_workspaces()
	return [
		{"name": w.name, "label": w.title or w.name}
		for w in frappe.get_all(
			"Workspace Sidebar",
			filters={"module": ["in", modules], "standard": 1},
			fields=["name", "title", "for_user"],
			order_by="title asc",
		)
		if w.name not in excluded and not w.for_user
	]


def _validate_sidebar_doctype(doctype):
	if not doctype:
		frappe.throw(_("DocType is required"))
	if doctype == "Cloudverce User Group":
		frappe.throw(_("Cloudverce User Group cannot be added to a sidebar shortcut"))
	meta_row = frappe.db.get_value("DocType", doctype, ["istable", "issingle"], as_dict=True)
	if not meta_row:
		frappe.throw(_("DocType {0} not found").format(doctype))
	if meta_row.istable or meta_row.issingle:
		frappe.throw(_("{0} is a child table or single DocType and cannot be added as a shortcut").format(doctype))


def _validate_sidebar_workspace(workspace):
	if not workspace:
		frappe.throw(_("Sidebar is required"))
	eligible = {w["name"] for w in get_eligible_sidebar_workspaces()}
	if workspace not in eligible:
		frappe.throw(
			_(
				"{0} is not an RBAC-eligible sidebar. Include its app/module (or the "
				"sidebar itself) in Cloudverce Utility Settings first."
			).format(workspace)
		)


def _clear_shortcut_caches():
	for attr in ("_cloudverce_managed_doctypes_cache", "_cloudverce_shortcut_doctypes_cache"):
		if hasattr(frappe.local, attr):
			delattr(frappe.local, attr)


def _refresh_sidebar_shortcuts_preview_for(workspace_name):
	"""Keep Cloudverce Utility Settings' "Sidebar Shortcuts" preview column live the moment a
	shortcut actually changes (add/remove from a Cloudverce User Group form), not just on the
	next migrate or manual "Refresh Sidebar Preview" click. No-op if that workspace has no
	row there yet (nothing to update).
	"""
	if not frappe.db.exists("DocType", "Cloudverce Utility Settings"):
		return
	settings = frappe.get_single("Cloudverce Utility Settings")
	row = next((r for r in (settings.included_workspaces or []) if r.workspace_name == workspace_name), None)
	if not row:
		return
	fresh = _describe_workspace_shortcuts(workspace_name)
	if fresh != (row.sidebar_shortcuts or ""):
		row.sidebar_shortcuts = fresh
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)
		frappe.db.commit()


@frappe.whitelist()
def add_doctype_to_sidebar(doctype, workspace, label=None):
	"""Add a DocType Link item to a real Desk left-nav sidebar ("Workspace Sidebar") from
	inside the Cloudverce User Group form, so an admin never has to open Frappe's Workspace
	Editor just to make one extra doctype (e.g. "Sales Invoice", curated into a custom
	app's sidebar even though it technically lives in ERPNext) manageable in the
	Permission Matrix. Idempotent: adding an already-present item is a no-op, not a
	duplicate row.
	"""
	if not frappe.has_permission("Cloudverce User Group", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	_validate_sidebar_doctype(doctype)
	_validate_sidebar_workspace(workspace)

	sidebar = frappe.get_doc("Workspace Sidebar", workspace)
	if not any((i.type == "Link" and i.link_type == "DocType" and i.link_to == doctype) for i in (sidebar.items or [])):
		sidebar.append("items", {
			"type": "Link", "link_type": "DocType", "link_to": doctype, "label": (label or doctype).strip(),
		})
		sidebar.flags.ignore_links = True
		sidebar.save(ignore_permissions=True)
		frappe.db.commit()

	_clear_shortcut_caches()
	_refresh_sidebar_shortcuts_preview_for(workspace)
	return {"matrix": get_permission_matrix(), "nav_matrix": get_navigation_visibility_matrix()}


@frappe.whitelist()
def remove_doctype_from_sidebar(doctype, workspace):
	"""Reverse of add_doctype_to_sidebar() -- removes the matching DocType Link item, same
	no-Workspace-Editor-needed path. No-op if the item is already gone.
	"""
	if not frappe.has_permission("Cloudverce User Group", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not doctype or not workspace:
		frappe.throw(_("DocType and Sidebar are required"))

	sidebar = frappe.get_doc("Workspace Sidebar", workspace)
	remaining = [
		i for i in (sidebar.items or [])
		if not (i.type == "Link" and i.link_type == "DocType" and i.link_to == doctype)
	]
	if len(remaining) != len(sidebar.items or []):
		sidebar.items = remaining
		sidebar.flags.ignore_links = True
		sidebar.save(ignore_permissions=True)
		frappe.db.commit()

	_clear_shortcut_caches()
	_refresh_sidebar_shortcuts_preview_for(workspace)
	return {"matrix": get_permission_matrix(), "nav_matrix": get_navigation_visibility_matrix()}


@frappe.whitelist()
def get_navigation_visibility_matrix():
	return _group_navigation_items_by_workspace()


@frappe.whitelist()
def get_navigation_visibility_config(group_name):
	"""Return navigation_visibility_json for a Cloudverce User Group (hidden field, not accessible via get_value)."""
	if not group_name:
		return ""
	return frappe.db.get_value("Cloudverce User Group", group_name, "navigation_visibility_json") or ""


@frappe.whitelist()
def set_navigation_visibility(name, hidden_labels):
	"""CAPA FIX: persist a nav-visibility toggle immediately, independent of the full doc
	Save/before_save pipeline. Called directly from the toggle's onchange handler so a toggle
	can never be silently reverted by an unrelated client-side save-cycle race.
	"""
	if not name:
		frappe.throw(_("Group name is required"))
	if not frappe.has_permission("Cloudverce User Group", "write", doc=name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	# CAPA FIX (v2): is_admin group → toggles are locked; this endpoint is a NO-OP.
	# Return current DB values without writing anything. Prevents is_admin groups from
	# having their stored navigation_visibility_json accidentally overwritten if a client
	# sends stale/incorrect hidden_labels.
	if frappe.db.get_value("Cloudverce User Group", name, "is_admin"):
		return {
			"navigation_visibility_json": frappe.db.get_value(
				"Cloudverce User Group", name, "navigation_visibility_json"
			) or "",
			"modified": frappe.db.get_value("Cloudverce User Group", name, "modified"),
		}

	hidden_labels = frappe.parse_json(hidden_labels) or []
	if isinstance(hidden_labels, str):
		hidden_labels = [hidden_labels]

	cleaned = []
	seen = set()
	for label in hidden_labels:
		label = (label or "").strip()
		if label and label not in seen:
			cleaned.append(label)
			seen.add(label)

	value = frappe.as_json({"hidden_labels": cleaned})
	frappe.db.set_value("Cloudverce User Group", name, "navigation_visibility_json", value, update_modified=True)
	frappe.db.commit()

	from cloudverce_utility.access_control import invalidate_group_bootinfo

	invalidate_group_bootinfo(name)
	_sync_page_report_access_control()

	# CAPA FIX: this write bumps the doc's `modified` timestamp on the server, but the
	# already-open form still holds the OLDER timestamp from when it was loaded. Frappe's
	# next Save would then see DB.modified > frm.doc.modified and raise a false-positive
	# TimestampMismatchError ("modified after you opened it"). Return the fresh timestamp so
	# the client can update frm.doc.modified and keep the Save button's conflict check valid.
	new_modified = frappe.db.get_value("Cloudverce User Group", name, "modified")
	return {"navigation_visibility_json": value, "modified": new_modified}


def _resolve_nav_item_target(item):
	"""Return (target_doctype, target_name) for a Page/Report nav item, or None.

	Dashboard items are NOT handled here -- Dashboard has no native `roles` table, so it is
	blocked separately via an override on get_permitted_charts/get_permitted_cards.

	DocType items (Workspace shortcuts, e.g. "Sales Invoice") are also not handled here --
	DocType has no `roles` child table either, and unlike Dashboard it doesn't need one:
	real access is already fully governed by the separate doctype permission matrix (Custom
	DocPerm). Hiding a DocType shortcut via navigation_visibility_json is cosmetic only (hides
	the tile from that group's Workspace); returning None here is intentional so
	_sync_page_report_access_control() skips it rather than trying to restrict a doctype
	through a mechanism it doesn't have.
	"""
	link_type = (item.get("link_type") or "").strip()
	if link_type == "Report":
		return ("Report", (item.get("link_to") or "").strip())
	if link_type == "Page":
		return ("Page", (item.get("link_to") or "").strip())
	if link_type == "DocType":
		return None
	if link_type == "Workspace":
		# Not enforced here either (falls through to None below) -- no real sidebar item
		# currently uses this link type; revisit if/when one does.
		return None
	if link_type == "URL":
		# Sidebar URL items that route to /app/<page-name> are backed by a real Page record
		# (e.g. "Alert Center" -> /app/alert-center -> Page "alert-center").
		url = (item.get("url") or "").strip()
		if "/app/" in url:
			page_name = url.split("/app/", 1)[1].strip("/")
			if page_name and frappe.db.exists("Page", page_name):
				return ("Page", page_name)
	return None


def _sync_page_report_access_control():
	"""CAPA FIX: Page and Report bypass the has_permission hook chain entirely -- both use
	their own is_permitted() method that checks their native `roles` child table (Has Role)
	directly (see Page.is_permitted / Report.is_permitted in frappe core). Hiding an item
	from a Cloudverce User Group's sidebar therefore does NOTHING to actually restrict direct-URL
	access unless that group's Role is also removed from the target Page/Report's `roles`
	table. This function is the single source of truth that keeps those tables in sync with
	every Cloudverce User Group's navigation_visibility_json.

	Rule: if no group hides an item, its `roles` table is cleared (open access, matching
	default Frappe behavior -- an empty roles table means "everyone allowed"). If at least
	one group hides it, the table is set to exactly the roles of groups that still show it,
	plus Administrator/System Manager, so admin access is never accidentally locked out.
	"""
	matrix = _group_navigation_items_by_workspace()
	items_by_label = {}
	for group in matrix:
		for item in group.get("items", []):
			label = item.get("label")
			if label:
				items_by_label[label] = item
	if not items_by_label:
		return

	groups = frappe.get_all(
		"Cloudverce User Group",
		filters={"is_active": 1},
		fields=["name", "navigation_visibility_json"],
	)

	all_group_names = [g.name for g in groups]
	hidden_by_label = {label: [] for label in items_by_label}
	for g in groups:
		config = frappe.parse_json(g.navigation_visibility_json) or {}
		for label in config.get("hidden_labels") or []:
			if label in hidden_by_label:
				hidden_by_label[label].append(g.name)

	protected_roles = {"Administrator", "System Manager"}

	for label, item in items_by_label.items():
		target = _resolve_nav_item_target(item)
		if not target:
			continue
		target_doctype, target_name = target
		if not target_name or not frappe.db.exists(target_doctype, target_name):
			continue

		hiding_groups = set(hidden_by_label.get(label) or [])
		existing_roles = set(frappe.get_all(
			"Has Role",
			filters={"parent": target_name, "parenttype": target_doctype},
			pluck="role",
		))

		if not hiding_groups:
			# Nobody hides this item -- clear restrictions entirely (open access).
			if existing_roles:
				frappe.db.delete("Has Role", {"parent": target_name, "parenttype": target_doctype})
			continue

		allowed_roles = protected_roles | {g for g in all_group_names if g not in hiding_groups}
		to_add = allowed_roles - existing_roles
		to_remove = existing_roles - allowed_roles

		if to_remove:
			frappe.db.delete(
				"Has Role",
				{"parent": target_name, "parenttype": target_doctype, "role": ["in", list(to_remove)]},
			)
		for role in to_add:
			frappe.get_doc({
				"doctype": "Has Role",
				"parent": target_name,
				"parenttype": target_doctype,
				"parentfield": "roles",
				"role": role,
			}).insert(ignore_permissions=True)

	frappe.db.commit()


@frappe.whitelist()
def get_role_permissions(group_name):
	"""Return effective permissions for this role across all managed doctypes.

	Custom DocPerm takes precedence over file-based DocPerm, matching Frappe's own resolution.
	"""
	if not group_name:
		return {}

	managed_doctypes = _get_managed_doctypes()
	if not managed_doctypes:
		return {}

	result = {}

	for r in frappe.get_all(
		"DocPerm",
		filters={"role": group_name, "permlevel": 0, "parent": ["in", managed_doctypes]},
		fields=_PERM_FIELDS,
	):
		result[r.parent] = _row_to_perm_dict(r)

	for r in frappe.get_all(
		"Custom DocPerm",
		filters={"role": group_name, "permlevel": 0, "parent": ["in", managed_doctypes]},
		fields=_PERM_FIELDS,
	):
		result[r.parent] = _row_to_perm_dict(r)

	return result


@frappe.whitelist()
def get_baseline_permission_matrix(group_name=None):
	"""Read-only info for the form's "Internal Permission" button: the doctypes and
	columns every Cloudverce User Group role always has access to (BASELINE_ALWAYS_GRANTED_DOCTYPES).
	Informational only — never editable from the UI.

	Most of these give full access identically to every group. A few (see
	BASELINE_RESTRICTED_FOR_NON_ADMIN, e.g. "User") give non-admin groups only a
	reduced column set — group_name (the group currently open in the form) is used
	to reflect the real per-group state instead of always showing everything granted.
	"""
	is_admin = bool(frappe.db.get_value("Cloudverce User Group", group_name, "is_admin")) if group_name else True

	perm_map = {}
	for dt in BASELINE_ALWAYS_GRANTED_DOCTYPES:
		restricted_cols = BASELINE_RESTRICTED_FOR_NON_ADMIN.get(dt)
		if restricted_cols is not None and not is_admin:
			perm_map[dt] = {col: (col in restricted_cols) for col in BASELINE_PERM_COLUMNS}
		else:
			perm_map[dt] = dict.fromkeys(BASELINE_PERM_COLUMNS, True)

	return {
		"doctypes": list(BASELINE_ALWAYS_GRANTED_DOCTYPES),
		"columns": [c.capitalize() for c in BASELINE_PERM_COLUMNS],
		"perm_map": perm_map,
	}


@frappe.whitelist()
def get_form_bundle(group_name=None, include_doc=0):
	"""Combined endpoint for the Cloudverce User Group form's client JS.

	Bundles get_permission_matrix(), get_navigation_visibility_matrix(),
	get_role_permissions(), and get_navigation_visibility_config() into ONE round-trip
	instead of four separate frappe.call()s -- each of those competes for the browser's
	per-origin connection limit alongside sync_managed_doctypes(), stretching a group
	switch's wall-clock wait well past any single call's own server time. Optionally
	returns a fresh copy of the group doc itself (include_doc=1), equivalent to
	frappe.client.get, so a document switch never needs a second network wave to
	guarantee frm.doc is current.
	"""
	group_name = (group_name or "").strip()
	result = {
		"matrix": get_permission_matrix(),
		"nav_matrix": get_navigation_visibility_matrix(),
		"role_permissions": {},
		"navigation_visibility_json": "",
		"doc": None,
	}
	if group_name and frappe.db.exists("Cloudverce User Group", group_name):
		result["role_permissions"] = get_role_permissions(group_name)
		result["navigation_visibility_json"] = get_navigation_visibility_config(group_name)
		if frappe.utils.cint(include_doc):
			result["doc"] = frappe.get_doc("Cloudverce User Group", group_name).as_dict()
	return result


def get_effective_field_states(group_name, doctype):
	"""{fieldname: "Hidden"|"Read Only"} for this group's generic (permlevel-based)
	field permissions on `doctype`. Shared by the field-permission popup endpoint below
	and by doctype controllers that need to enforce Hidden/Read Only server-side.
	"""
	if not group_name or not frappe.db.exists("Cloudverce User Group", group_name):
		return {}
	group = frappe.get_doc("Cloudverce User Group", group_name)
	return {
		row.fieldname: row.field_state
		for row in (group.field_permissions or [])
		if row.document_type == doctype
	}


@frappe.whitelist()
def get_doctype_field_permission_config(doctype, group_name=None):
	"""Field list (currently visible, non-layout fields) for the field-permission popup,
	plus this group's already-saved Hidden/Read Only state per field.
	"""
	if not doctype or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("DocType {0} not found").format(doctype))
	if doctype not in set(_get_managed_doctypes()):
		frappe.throw(_("{0} is not a Cloudverce-managed doctype").format(doctype), frappe.PermissionError)

	meta = frappe.get_meta(doctype)
	fields = []
	for df in meta.fields:
		if df.fieldtype in LAYOUT_FIELDTYPES or df.fieldname in EXCLUDED_SYSTEM_FIELDNAMES or df.hidden:
			continue
		fields.append({
			"fieldname": df.fieldname,
			"label": df.label or df.fieldname,
			"fieldtype": df.fieldtype,
			"is_read_only": bool(df.read_only),
			"is_js_forced_read_only": False,
			# reqd=1 (always mandatory) OR mandatory_depends_on (conditionally mandatory) --
			# an admin hiding either kind can break saving for that group.
			"is_mandatory": bool(df.reqd) or bool(df.mandatory_depends_on),
		})

	return {"fields": fields, "saved": get_effective_field_states(group_name, doctype)}


@frappe.whitelist()
def save_field_permissions(group_name, doctype, rows):
	"""Save this group's per-field Hidden/Read Only choices for one doctype. Rows for
	OTHER doctypes on the same group are left untouched. Goes through a normal
	doc.save() (not a bypass-save) so changes land in the version/audit log, since this
	is a security-sensitive permission change.

	Each row carries BOTH raw toggle states (`hidden`, `read_only`) exactly as checked
	in the popup -- no client-side reconciliation between the two. Hidden always wins
	over Read Only when both are checked; this resolution happens here, server-side,
	not in the UI.
	"""
	if not frappe.has_permission("Cloudverce User Group", "write", doc=group_name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not doctype or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("DocType {0} not found").format(doctype))
	if doctype not in set(_get_managed_doctypes()):
		frappe.throw(_("{0} is not a Cloudverce-managed doctype").format(doctype), frappe.PermissionError)

	rows = frappe.parse_json(rows) or []
	meta = frappe.get_meta(doctype)
	group = frappe.get_doc("Cloudverce User Group", group_name)

	group.set("field_permissions", [r for r in (group.field_permissions or []) if r.document_type != doctype])

	for row in rows:
		fieldname = (row.get("fieldname") or "").strip()
		if not fieldname:
			continue
		# Hidden always wins over Read Only when both were checked in the popup.
		state = "Hidden" if row.get("hidden") else ("Read Only" if row.get("read_only") else "")
		if state not in ("Hidden", "Read Only"):
			continue

		df = meta.get_field(fieldname)
		if not df or df.fieldtype in LAYOUT_FIELDTYPES or fieldname in EXCLUDED_SYSTEM_FIELDNAMES:
			continue
		if state == "Read Only" and df.read_only:
			# Already read-only for everyone, structurally -- nothing to customize,
			# and no permlevel assignment either (only assigned when actually restricted).
			continue

		permlevel = _assign_permlevel_for_field(doctype, fieldname)
		group.append("field_permissions", {
			"document_type": doctype,
			"fieldname": fieldname,
			"label": df.label or fieldname,
			"fieldtype": df.fieldtype,
			"permlevel": permlevel,
			"field_state": state,
		})

	group.flags.ignore_permissions = True
	group.save(ignore_permissions=True)
	return {"modified": str(group.modified)}


@frappe.whitelist()
def import_existing_roles():
	frappe.throw(_("Import from Roles is no longer supported. Create Cloudverce User Group records manually."))


# ── Hook functions (called from hooks.py) ──────────────────────────────────


def sync_custom_docperm_to_user_group(doc, method=None):
	"""Hook: Custom DocPerm saved/deleted → mirror into Cloudverce User Group permissions table."""
	if doc.permlevel:
		# Field-level (permlevel > 0) rows are managed exclusively by the field-permission
		# sync (_sync_field_permlevel_custom_docperms) — mirroring them here would corrupt
		# the doctype-level `permissions` table, which only ever tracks permlevel-0 rows.
		return

	role = doc.role
	doctype = doc.parent

	if role in FRAPPE_SYSTEM_ROLES:
		return

	group_name = frappe.db.get_value("Cloudverce User Group", {"group_name": role}, "name")
	if not group_name:
		return

	if doctype not in set(_get_managed_doctypes()):
		return

	group = frappe.get_doc("Cloudverce User Group", group_name)

	existing_row = next((r for r in group.permissions if r.document_type == doctype), None)

	if method == "on_trash":
		if existing_row:
			group.permissions.remove(existing_row)
			group.flags.ignore_permissions = True
			group.flags.skip_custom_docperm_sync = True
			group.save(ignore_permissions=True)
	else:
		perm_vals = {
			child_field: int(bool(doc.get(frappe_field)))
			for frappe_field, child_field in PERM_MAP.items()
		}
		module = frappe.db.get_value("DocType", doctype, "module") or ""

		if existing_row:
			if not existing_row.get("module") and module:
				existing_row.set("module", module)
			for child_field, val in perm_vals.items():
				existing_row.set(child_field, val)
		else:
			if not module:
				return
			group.append("permissions", {"document_type": doctype, "module": module, **perm_vals})

		group.flags.ignore_permissions = True
		group.flags.skip_custom_docperm_sync = True
		group.save(ignore_permissions=True)

	_ensure_protected_role_permissions([doctype])


def sync_role_disabled_to_user_group(doc, method=None):
	"""Hook: Role disabled/enabled → mirror to Cloudverce User Group is_active."""
	if doc.name in FRAPPE_SYSTEM_ROLES:
		return
	group_name = frappe.db.get_value("Cloudverce User Group", {"group_name": doc.name}, "name")
	if not group_name:
		return
	is_active = 0 if doc.disabled else 1
	current = frappe.db.get_value("Cloudverce User Group", group_name, "is_active")
	if current != is_active:
		frappe.db.set_value("Cloudverce User Group", group_name, "is_active", is_active, update_modified=False)
		from cloudverce_utility.access_control import invalidate_group_bootinfo

		invalidate_group_bootinfo(group_name)


# ── Constants ───────────────────────────────────────────────────────────────


# Frappe framework doctypes are NEVER auto-governed by the RBAC -- they control the
# platform's own security/customization/code (DocType, Role, Custom DocPerm, Property
# Setter, Workflow, Server/Client Script, System Settings, etc.), and the matrix sync
# zeroes out anything not explicitly granted, so exposing these could brick a site.
# ERPNext IS governable like any other installed app -- it's business-domain doctypes
# (Sales Invoice, Item, Customer, ...), not framework internals.
CORE_APPS = {"frappe"}

_PERM_FIELDS = [
	"parent", "select", "read", "write", "create", "delete",
	"submit", "cancel", "amend", "print", "email", "report",
	"import", "export",
]

# Maps Frappe Custom DocPerm column → Cloudverce User Group Permission child fieldname
PERM_MAP = {
	"select": "perm_select",
	"read":   "perm_read",
	"write":  "perm_write",
	"create": "perm_create",
	"delete": "perm_delete",
	"submit": "perm_submit",
	"cancel": "perm_cancel",
	"amend":  "perm_amend",
	"print":  "perm_print",
	"email":  "perm_email",
	"report": "perm_report",
	"import": "perm_import",
	"export": "perm_export",
}

# Doctypes that should never receive an explicit-deny Custom DocPerm row.
# If ANY Custom DocPerm exists for a doctype, Frappe ignores ALL file-based DocPerms
# for that doctype across ALL roles — not just the one with the CDP row.
_NO_EXPLICIT_DENY: set = set()

# Doctypes every Cloudverce User Group role gets full access to, always, regardless of
# is_admin and regardless of what the group's own permissions matrix says. Not
# exposed in the permissions matrix UI (these are outside _get_managed_doctypes()) —
# there is nothing for an admin to toggle off. Entries are guarded by
# frappe.db.exists("DocType", dt) in _ensure_baseline_group_permissions, so any
# doctype not installed on a given site (e.g. HR-only doctypes) is silently skipped.
BASELINE_ALWAYS_GRANTED_DOCTYPES = [
	"Cloudverce User Group",
	"User",
	"File",
	"Salary Structure Assignment",
	"Department",
	"Designation",
	"Leave Type",
	"HR Settings",
	"Page",
	"Data Import",
	"Data Import Log",
	"Error Log",
	"Attendance",
	"Salary Structure",
	"Salary Component",
	"Account",
	"Buying Settings",
	"Stock Settings",
	"Contact",
	"Purchase Taxes and Charges Template",
	"Tax Category",
	"GL Entry",
	"Stock Ledger Entry",
]

# Custom DocPerm columns granted in full on BASELINE_ALWAYS_GRANTED_DOCTYPES.
# Distinct from PERM_MAP: adds share/mask (not used elsewhere in this file) and
# drops submit/cancel/amend (none of these doctypes are submittable).
BASELINE_PERM_COLUMNS = [
	"select", "read", "write", "create", "delete",
	"print", "email", "report", "import", "export", "share", "mask",
]

# Doctypes in BASELINE_ALWAYS_GRANTED_DOCTYPES that get a REDUCED column set instead
# of full access for non-admin (is_admin=0) groups — is_admin=1 groups still get full
# access as normal. Currently just "User": a normal user can view/edit their own
# profile (change their own password etc.) but not see or touch anyone else's User
# record. The row-level "own record only" restriction is enforced separately by
# get_permission_query_conditions_user/has_permission_user (navigation_visibility.py,
# wired in hooks.py) — this dict only controls which ACTIONS are allowed at all.
BASELINE_RESTRICTED_FOR_NON_ADMIN = {
	"User": {"select", "read", "write"},
	# Non-admin groups get READ only (never write/create/delete) at the role level --
	# and even that read is further narrowed to their OWN group's record only, by
	# get_permission_query_conditions_cloudverce_user_group / has_permission_cloudverce_user_group
	# (navigation_visibility.py, wired in hooks.py). Only group Admins (is_admin=1
	# groups) may write, update, or create a Cloudverce User Group.
	"Cloudverce User Group": {"select", "read"},
}


def _row_to_perm_dict(r):
	return {child: r.get(frappe_f) or 0 for frappe_f, child in PERM_MAP.items()}


# ── Managed module / doctype resolution ─────────────────────────────────────


def _included_names(rows, name_field):
	"""Return names that are EXPLICITLY unchecked in a checkbox child table.

	A row with `included=0` is excluded. A name with NO row at all defaults to
	included (safe fallback until the next migrate runs _sync_included_scope_tables).
	Despite the helper name, the return value is the excluded set so callers can
	keep the same membership checks as the old free-text excluded_apps/modules.
	"""
	from frappe.utils import cint

	excluded = set()
	for row in rows or []:
		name = (row.get(name_field) or "").strip()
		if name and not cint(row.get("included")):
			excluded.add(name)
	return excluded


def _get_managed_modules():
	"""Auto-detect the modules whose doctypes this RBAC governs.

	Governs every installed app except the core denylist (frappe) and any apps/modules
	unchecked in Cloudverce Utility Settings' Included Apps / Included Modules tables. An
	app/module with no row yet (not synced by the last migrate) defaults to governed,
	same as before. Cached per request.
	"""
	cached = getattr(frappe.local, "_cloudverce_managed_modules_cache", None)
	if cached is not None:
		return cached

	excluded_apps = set(CORE_APPS)
	excluded_modules = set()
	try:
		if frappe.db.exists("DocType", "Cloudverce Utility Settings"):
			settings = frappe.get_cached_doc("Cloudverce Utility Settings")
			excluded_apps |= _included_names(settings.get("included_apps"), "app_name")
			excluded_modules |= _included_names(settings.get("included_modules"), "module_name")
	except Exception:
		pass

	governed_apps = [a for a in frappe.get_installed_apps() if a not in excluded_apps]
	modules = []
	if governed_apps:
		modules = frappe.get_all(
			"Module Def",
			filters={"app_name": ["in", governed_apps]},
			pluck="name",
			order_by="name asc",
		)
	modules = [m for m in modules if m not in excluded_modules]

	frappe.local._cloudverce_managed_modules_cache = modules
	return modules


def _get_shortcut_referenced_doctypes():
	"""{doctype_name: {"name": sidebar_docname, "label": sidebar_title, "section":
	sidebar_section_label, "order": item_order}} for every DocType-type Link item in the
	real Desk left-nav sidebar ("Workspace Sidebar" -- NOT the older "Workspace" doctype's
	own shortcuts/links, which are just cards on a workspace's home page content and are a
	completely different, disconnected mechanism). Only STANDARD (app-wide, not
	per-user-customized) sidebars belonging to a managed module AND checked in Included
	Workspaces are considered. First sidebar found wins if the same doctype appears in
	more than one.

	These become permission-matrix-manageable (real Custom DocPerm read/write/create/
	delete via Cloudverce User Group) even when the doctype's OWN module/app isn't governed
	-- e.g. "Sales Invoice" already sits in the real Cloudverce Fabro sidebar (an ERPNext
	doctype curated into a custom app's navigation), so it becomes manageable there
	without governing all of ERPNext. Table/Single doctypes are skipped (matches the
	same filter _get_managed_doctypes() already applies to its module-based doctypes).

	Both the sidebar's real docname AND its display title are kept (not just the doctype
	set): the docname is what remove_doctype_from_sidebar() needs to actually find and
	edit the right Workspace Sidebar record; the title is what the permission-matrix
	display groups a doctype under, instead of its real DocType.module -- an admin who
	sees "Sales Invoice" in the Cloudverce Fabro sidebar has no reason to know or care that
	it technically lives in ERPNext's "Accounts" module; the matrix should speak in the
	same terms the sidebar does.

	"section" is the label of the nearest preceding "Section Break" item in the sidebar
	(e.g. "Manufacturing", "Buying", "Selling", "Master" in cloudverce_fabro's sidebar), empty
	string if the item sits before any Section Break. "order" is a running counter across
	the whole sidebar walk, used by _group_doctypes_by_module() to sort same-module
	doctypes so items sharing a section end up contiguous (needed for its rowspan display).
	Deliberately NOT persisted anywhere -- both are recomputed fresh from the live sidebar
	on every call, so a later Section Break rename/reorder is reflected immediately with no
	migration. Result is cached on frappe.local for the lifetime of the current request.
	"""
	cached = getattr(frappe.local, "_cloudverce_shortcut_doctypes_cache", None)
	if cached is not None:
		return cached

	modules = _get_managed_modules()
	if not modules:
		frappe.local._cloudverce_shortcut_doctypes_cache = {}
		return {}

	excluded_workspaces = _get_excluded_workspaces()
	result = {}
	order = 0
	for ws_row in frappe.get_all(
		"Workspace Sidebar",
		filters={"module": ["in", modules], "standard": 1},
		fields=["name", "module"],
	):
		if ws_row["name"] in excluded_workspaces:
			continue
		try:
			sidebar = frappe.get_doc("Workspace Sidebar", ws_row["name"])
		except Exception:
			continue
		if sidebar.for_user:
			continue  # a per-user customized copy, not the standard app-wide sidebar
		label = (sidebar.title or ws_row["name"]).strip()
		current_section = ""
		for item in (sidebar.items or []):
			item_type = (getattr(item, "type", "") or "").strip()
			if item_type == "Section Break":
				current_section = (item.label or "").strip()
				continue
			if item_type != "Link":
				continue
			if (getattr(item, "link_type", "") or "").strip() != "DocType":
				continue
			dt = (item.link_to or "").strip()
			if not dt or dt == "Cloudverce User Group" or dt in result:
				continue
			meta_row = frappe.db.get_value("DocType", dt, ["istable", "issingle"], as_dict=True)
			if meta_row and not meta_row.istable and not meta_row.issingle:
				order += 1
				result[dt] = {
					"name": ws_row["name"],
					"label": label,
					"section": current_section,
					"order": order,
				}

	frappe.local._cloudverce_shortcut_doctypes_cache = result
	return result


def _get_managed_doctypes():
	"""Return all DocTypes governed by the RBAC.

	Sidebar-driven, not module-driven: a doctype is only permission-matrix-manageable if
	it is actually reachable as a DocType-type Workspace shortcut in an included Workspace
	belonging to an included module (see _get_shortcut_referenced_doctypes()) -- the same
	thing a user would actually see and click in their Desk sidebar. Merely belonging to a
	governed module is NOT enough by itself; if a doctype has no shortcut anywhere, it does
	not appear here and cannot be configured from Cloudverce User Group. Use the "+Add DocType"
	button on the Cloudverce User Group form (add_doctype_to_sidebar()) to add one -- no need
	to open Frappe's Workspace Editor directly. Included Apps/Modules/Workspaces (Cloudverce
	Utility Settings) control which Workspaces are eligible SOURCES for shortcuts, not
	which doctypes are governed directly.

	Result is cached on frappe.local for the lifetime of the current request to avoid
	redundant DB queries when called multiple times in one save cycle.
	"""
	cached = getattr(frappe.local, "_cloudverce_managed_doctypes_cache", None)
	if cached is not None:
		return cached

	managed = set(_get_shortcut_referenced_doctypes().keys())

	# "Cloudverce User Group" manages its OWN access via BASELINE_ALWAYS_GRANTED_DOCTYPES +
	# BASELINE_RESTRICTED_FOR_NON_ADMIN (own-record-only read for non-admin groups,
	# full access for is_admin groups) -- see hooks.py's permission_query_conditions/
	# has_permission for "Cloudverce User Group". It must never be matrix-configurable --
	# that would let a normal group grant itself write access to every other group's
	# config via the ordinary permissions matrix.
	managed.discard("Cloudverce User Group")

	managed = sorted(managed)
	frappe.local._cloudverce_managed_doctypes_cache = managed
	return managed


# ── Display grouping helpers ─────────────────────────────────────────────────


def _group_doctypes_by_module(doctype_names):
	"""Group managed doctypes by their module for the permission-matrix display.

	A doctype that is ONLY reachable via a Workspace shortcut (not natively part of a
	managed module -- see _get_managed_doctypes()) is grouped under the WORKSPACE it was
	added from instead of its real DocType.module, so the matrix shows exactly what the
	user recognizes from the sidebar rather than an unfamiliar foreign module name (e.g.
	"Cloudverce Fabro" instead of ERPNext's "Accounts" for a "Sales Invoice" shortcut).
	A doctype that's natively managed always uses its real module, even if it also
	happens to be shortcut-referenced somewhere.

	Each item also carries "section" -- the label of the Section Break the doctype sits
	under in its source sidebar (e.g. "Manufacturing", "Buying"), or "General" if it has
	no shortcut source or sits before any Section Break. Within each module group, items
	are sorted by (section's first-appearance order in the sidebar, section label, doctype
	name) rather than plain alphabetical, so doctypes sharing a section end up contiguous
	-- the permission-matrix JS relies on that contiguity to render a single merged Section
	badge per run instead of one per row, mirroring the existing Module badge behavior.
	Doctypes with no section sort last within their module (large sentinel order).

	Returns [{"module": <module or workspace label>, "items": [{"doctype", "display",
	"section", ...}]}], modules ordered by first appearance while iterating doctypes
	alphabetically.
	"""
	managed_modules = set(_get_managed_modules())
	shortcut_sources = _get_shortcut_referenced_doctypes()
	NO_SECTION_ORDER = float("inf")

	groups = {}
	ordered = []
	for doctype in sorted(doctype_names):
		module = frappe.db.get_value("DocType", doctype, "module") or "Other"
		source = shortcut_sources.get(doctype)
		section = module if module in managed_modules else (source["label"] if source else module)
		if section not in groups:
			groups[section] = []
			ordered.append(section)
		item_section = (source.get("section") if source else "") or "General"
		groups[section].append({
			"doctype": doctype,
			"display": doctype,
			"is_shortcut": source is not None,
			"source_workspace": source["name"] if source else None,
			"section": item_section,
			"_section_order": source["order"] if source else NO_SECTION_ORDER,
		})

	result = []
	for m in ordered:
		items = groups.get(m)
		if not items:
			continue
		items.sort(key=lambda it: (it["_section_order"], it["section"], it["doctype"]))
		for it in items:
			it.pop("_section_order", None)
		result.append({"module": m, "items": items})
	return result


def _get_excluded_workspaces():
	"""Workspace Sidebar names unchecked in Cloudverce Utility Settings' Included Workspaces
	table (despite the generic "workspace_name" fieldname, this now stores "Workspace
	Sidebar" record names -- the real Desk left-nav sidebar, not the older "Workspace"
	doctype's own cards).

	Same no-row-defaults-to-included rule as _get_managed_modules()'s app/module handling.
	"""
	try:
		if frappe.db.exists("DocType", "Cloudverce Utility Settings"):
			settings = frappe.get_cached_doc("Cloudverce Utility Settings")
			return _included_names(settings.get("included_workspaces"), "workspace_name")
	except Exception:
		pass
	return set()


def _nav_enforcement_label(link_type, link_to):
	"""The identity that ACTUALLY gets enforced by has_permission_page/_report
	(navigation_visibility.py) for a given link -- which is NOT necessarily the sidebar's
	own display label. A Workspace Sidebar author can label an item however they like
	(e.g. "Reports" pointing at Report "Sales Analytics"), but those has_permission_*
	hooks check the TARGET record's own title/report_name (falling back to its name), not
	whatever text the sidebar happened to show. If the toggle stored the sidebar's display
	label instead, hiding it would update navigation_visibility_json but never actually
	match anything the enforcement hooks check -- the tile disappears from the sidebar,
	but the underlying Page/Report stays fully accessible by URL. This must mirror
	_nav_label_for_page/_report in navigation_visibility.py exactly, or hiding silently
	stops enforcing again.

	Dashboard is deliberately NOT resolved here (falls through to None below, so the
	toggle's key stays the sidebar's own display label) -- confirmed with the user that
	hiding a Dashboard nav item should be cosmetic-only (hide the tile), not a real access
	block, unlike Page/Report.
	"""
	if not link_to:
		return None
	if link_type == "Page":
		return (frappe.db.get_value("Page", link_to, "title") or link_to).strip()
	if link_type in {"Report", "Query Report"}:
		return (frappe.db.get_value("Report", link_to, "report_name") or link_to).strip()
	return None


def _group_navigation_items_by_workspace():
	"""Build the navigation-visibility matrix from the real Desk left-nav sidebar
	("Workspace Sidebar" items) of every managed, included sidebar. Grouped by sidebar title.

	This reads the actual sidebar an admin/user sees in the Desk -- NOT the older
	"Workspace" doctype's own shortcuts/links (cards on a workspace's home page content,
	a separate and disconnected mechanism from the real navigation tree).

	Scoped to Dashboard/Page/Report items only (confirmed with the user) -- DocType,
	Workspace and URL sidebar entries are deliberately excluded here. DocType visibility
	has no cosmetic show/hide control anywhere in this app anymore; its real access is
	still fully governed by the separate Permission Matrix (Custom DocPerm), unaffected
	by this scoping.

	Returns [{"module": <sidebar title>, "items": [{label, display, link_type, link_to, url}]}].
	"display" is the friendly text shown in the toggle UI (the sidebar's own label, e.g.
	"Home"); "label" is the key actually stored in hidden_labels and matched by
	has_permission_page/_report -- for Page/Report links this is the target's own
	title/report_name (see _nav_enforcement_label()), which can legitimately differ from
	"display". The two are equal for Dashboard links -- Dashboard hiding is deliberately
	cosmetic-only, not a real access block (see _nav_enforcement_label()'s docstring).
	"""
	modules = _get_managed_modules()
	if not modules:
		return []

	excluded_workspaces = _get_excluded_workspaces()
	groups = {}
	ordered = []

	for ws_row in frappe.get_all(
		"Workspace Sidebar",
		filters={"module": ["in", modules], "standard": 1},
		fields=["name", "module"],
		order_by="name asc",
	):
		if ws_row["name"] in excluded_workspaces:
			continue
		try:
			sidebar = frappe.get_doc("Workspace Sidebar", ws_row["name"])
		except Exception:
			continue
		if sidebar.for_user:
			continue

		section = (sidebar.title or ws_row["name"]).strip()
		items = []
		seen = set()

		for item in (sidebar.items or []):
			if (getattr(item, "type", "") or "").strip() != "Link":
				continue  # Section Break / Spacer / Sidebar Item Group are structural, not navigable
			link_type = (getattr(item, "link_type", "") or "").strip()
			display = (item.label or item.link_to or "").strip()
			if not display or display in seen:
				continue

			# Scoped to Dashboard/Page/Report only (confirmed with the user): DocType,
			# Workspace and URL items are deliberately excluded from this toggle -- DocType
			# visibility has no cosmetic control in this app at all anymore (real access is
			# still fully governed by the separate Permission Matrix regardless).
			if link_type not in {"Report", "Query Report", "Page", "Dashboard"}:
				continue

			link_to = (item.link_to or "").strip()
			if link_type in {"Report", "Query Report"}:
				if link_to and not frappe.db.exists("Report", link_to):
					continue
			elif link_type == "Page":
				if link_to and not frappe.db.exists("Page", link_to):
					continue
			elif link_type == "Dashboard":
				if link_to and not frappe.db.exists("Dashboard", link_to):
					continue

			# The toggle's stored/matched key must be whatever has_permission_page/_report
			# actually checks -- NOT the sidebar's own display text, which can legitimately
			# differ (see _nav_enforcement_label()). Falls back to the display label for
			# Dashboard (deliberately cosmetic-only, see _nav_enforcement_label()'s docstring).
			label = _nav_enforcement_label(link_type, link_to) or display
			if label != display and label in seen:
				continue
			seen.add(display)
			seen.add(label)
			items.append({
				"label": label,
				"display": display,
				"link_type": "Report" if link_type == "Query Report" else link_type,
				"link_to": link_to,
				"url": (getattr(item, "url", "") or "").strip(),
			})

		if items:
			if section not in groups:
				groups[section] = []
				ordered.append(section)
			groups[section].extend(items)

	return [{"module": s, "items": groups[s]} for s in ordered if groups.get(s)]
