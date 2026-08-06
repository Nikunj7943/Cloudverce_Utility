import time

import frappe

# Role Profile's own on_update (Frappe core) locks the doc via queue_action()
# and only releases the lock once a "long" queue worker runs update_all_users.
# Benches that don't run a long-queue consumer leave that lock stuck forever,
# so a plain single retry isn't enough — retry a few times, then give up
# quietly rather than surfacing frappe.DocumentLockedError to the user.
ROLE_PROFILE_SAVE_RETRIES = 3
ROLE_PROFILE_SAVE_RETRY_DELAY = 0.3


FRAPPE_SYSTEM_ROLES = {
	"Administrator",
	"All",
	"Auditor",
	"Blogger",
	"Dashboard Manager",
	"Desk User",
	"Guest",
	"Newsletter Manager",
	"Script Manager",
	"System Manager",
	"Translator",
	"Workspace Manager",
}


def is_syncable_role(role_name):
	return bool(role_name and role_name not in FRAPPE_SYSTEM_ROLES)


def get_syncable_roles():
	roles = frappe.get_all(
		"Role",
		filters={"desk_access": 1},
		pluck="name",
		order_by="name asc",
	)
	return [role_name for role_name in roles if is_syncable_role(role_name)]


def ensure_role_profile_for_role(role_name):
	if not is_syncable_role(role_name):
		return None

	if not frappe.db.exists("Role", role_name):
		return None

	# Skip if no Cloudverce User Group owns this role — prevents queued sync jobs from
	# resurrecting Role Profiles after their Cloudverce User Group was deleted.
	if not frappe.db.exists("Cloudverce User Group", role_name):
		return None

	role_profile_name = frappe.db.get_value(
		"Role Profile",
		{"role_profile": role_name},
		"name",
	)

	if role_profile_name:
		role_profile = frappe.get_doc("Role Profile", role_profile_name)
		if role_name not in {row.role for row in (role_profile.roles or [])}:
			role_profile.append("roles", {"role": role_name})
			_save_unlocking_if_needed(role_profile)
		return role_profile.name

	role_profile = frappe.new_doc("Role Profile")
	role_profile.role_profile = role_name
	role_profile.append("roles", {"role": role_name})
	try:
		role_profile.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		# Race condition: inserted by a concurrent job between our exists() check and insert
		return frappe.db.get_value("Role Profile", {"role_profile": role_name}, "name")
	return role_profile.name


def ensure_role_profiles_for_existing_roles():
	created_or_updated = []
	for role_name in get_syncable_roles():
		role_profile_name = ensure_role_profile_for_role(role_name)
		if role_profile_name:
			created_or_updated.append(role_profile_name)
	return created_or_updated


def _save_unlocking_if_needed(doc):
	"""Save doc; if a stale file-lock blocks it, unlock and retry a few times.

	Role Profile saves are never user-facing critical actions on their own —
	they're background housekeeping triggered from Cloudverce User Group syncs.
	If the lock keeps coming back (e.g. the site has no worker consuming the
	"long" queue, so queue_action() locks never get released), skip silently
	and log rather than raising DocumentLockedError up into the caller's
	request/response cycle.
	"""
	for attempt in range(ROLE_PROFILE_SAVE_RETRIES):
		try:
			doc.save(ignore_permissions=True)
			return
		except frappe.DocumentLockedError:
			doc.unlock()
			if attempt < ROLE_PROFILE_SAVE_RETRIES - 1:
				time.sleep(ROLE_PROFILE_SAVE_RETRY_DELAY)

	frappe.log_error(
		title="Role Profile sync skipped: document locked",
		message=(
			f"Role Profile {doc.name} stayed locked after {ROLE_PROFILE_SAVE_RETRIES} attempts "
			"(likely no worker is consuming the 'long' queue on this site) — skipped this sync."
		),
	)


def enqueue_role_profile_sync(role_name):
	if not is_syncable_role(role_name):
		return

	frappe.enqueue(
		"cloudverce_utility.role_profile_sync.ensure_role_profile_for_role",
		queue="short",
		job_name=f"ensure-role-profile::{role_name}",
		enqueue_after_commit=True,
		role_name=role_name,
	)
