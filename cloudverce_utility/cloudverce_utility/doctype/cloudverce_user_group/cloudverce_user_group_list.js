frappe.listview_settings["Cloudverce User Group"] = {

	get_indicator(doc) {
		if (!doc.is_active) return [__("Inactive"), "red",  "is_active,=,0"];
		if (doc.is_admin)   return [__("Admin"),    "blue", "is_admin,=,1"];
		return [__("Active"), "green", "is_active,=,1"];
	},

	button: {
		show(doc)            { return true; },
		get_label()          { return __("Edit"); },
		get_description(doc) { return __("Edit {0}", [doc.group_name]); },
		action(doc)          { frappe.set_route("Form", "Cloudverce User Group", doc.name); },
	},
};
