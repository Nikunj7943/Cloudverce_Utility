import frappe
from frappe.model.document import Document


class CloudverceUtilitySettings(Document):
	def on_update(self):
		# Scope changed → drop the per-request caches so the next request re-detects
		# managed modules/doctypes. Also clear bootinfo so users pick up new visibility.
		for attr in (
			"_cloudverce_managed_modules_cache",
			"_cloudverce_managed_doctypes_cache",
			"_cloudverce_shortcut_doctypes_cache",
		):
			if hasattr(frappe.local, attr):
				delattr(frappe.local, attr)
		frappe.clear_cache()
