// Copyright (c) 2026, Cloudverce and contributors
// For license information, please see license.txt

frappe.ui.form.on("Cloudverce Utility Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Refresh Sidebar Preview"), () => {
			frappe.call({
				method: "cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group.refresh_workspace_sidebar_preview",
				freeze: true,
				callback: () => {
					frappe.show_alert({ message: __("Sidebar preview refreshed"), indicator: "green" });
					frm.reload_doc();
				},
			});
		});
	},
});
