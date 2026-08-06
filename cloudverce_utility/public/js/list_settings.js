window.TMS = window.TMS || {};

(function () {
	class TMSListSettings {
		constructor({ listview, doctype, meta, settings }) {
			if (!doctype) {
				frappe.throw("DocType required");
			}

			this.listview = listview;
			this.doctype = doctype;
			this.meta = meta;
			this.settings = settings || {};
			this.dialog = null;
			this.fields =
				this.settings && this.settings.fields ? JSON.parse(this.settings.fields) : [];
			this.subject_field = null;
			this.max_number_of_fields = 50;

			frappe.model.with_doctype("List View Settings", () => {
				this.make();
				this.get_listview_fields(meta);
				this.setup_fields();
				this.setup_remove_fields();
				this.add_new_fields();
				this.show_dialog();
			});
		}

		make() {
			const list_view_settings = frappe.get_meta("List View Settings");

			this.dialog = new frappe.ui.Dialog({
				title: __("{0} List View Settings", [__(this.doctype)]),
				fields: list_view_settings.fields,
			});
			this.dialog.set_values(this.settings);
			this.dialog.set_primary_action(__("Save"), () => {
				const values = this.dialog.get_values();

				frappe.show_alert({
					message: __("Saving"),
					indicator: "green",
				});

				frappe.call({
					method: "cloudverce_utility.access_control.save_listview_settings_api",
					args: {
						doctype: this.doctype,
						listview_settings: values,
						removed_listview_fields: this.removed_fields || [],
					},
					callback: (r) => {
						this.listview.refresh_columns(r.message.meta, r.message.listview_settings);
						this.dialog.hide();
					},
				});
			});
		}

		refresh() {
			this.setup_fields();
			this.add_new_fields();
			this.setup_remove_fields();
		}

		show_dialog() {
			if (!this.settings.fields) {
				this.update_fields();
			}

			if (!this.dialog.get_value("total_fields")) {
				let field_count = this.settings.total_fields;

				if (!field_count) {
					field_count = this.fields.length;
					if (field_count < 4) {
						field_count = 4;
					} else if (field_count > 10) {
						field_count = 10;
					}
				}

				this.dialog.set_value("total_fields", field_count);
			}

			this.dialog.show();
		}

		setup_fields() {
			const fields_html = this.dialog.get_field("fields_html");
			const wrapper = fields_html.$wrapper[0];
			let fields = "";

			for (const idx in this.fields) {
				if (Number(idx) === this.max_number_of_fields) {
					break;
				}
				const is_sortable = idx === "0" ? "" : "sortable";
				const show_sortable_handle = idx === "0" ? "hide" : "";
				const can_remove =
					idx === "0" || this._is_status_field(this.fields[idx]) ? "hide" : "d-flex";

				fields += `
					<div class="control-input form-control fields_order ${is_sortable} flex"
	 				style="margin-bottom: 5px; padding-bottom: 1.5px;"
	 				data-fieldname="${this.fields[idx].fieldname}"
	 				data-label="${this.fields[idx].label}"
	 				data-type="${this.fields[idx].type}">
						<div class="row flex-fill align-items-center">
							<div class="col-1 d-flex align-items-center justify-content-center px-1">
								${frappe.utils.icon("drag", "xs", "", "", "sortable-handle " + show_sortable_handle)}
							</div>
							<div class="col d-flex align-items-center px-0">
								${__(this.fields[idx].label, null, this.doctype)}
							</div>
							<div class="col-1 d-flex align-items-center justify-content-center px-0">
								<a class="text-muted remove-field align-items-center ${can_remove}"
								   data-fieldname="${this.fields[idx].fieldname}">
									${frappe.utils.icon("x", "xs")}
								</a>
							</div>
						</div>
					</div>`;
			}

			fields_html.html(`
				<div class="form-group">
					<div class="clearfix">
						<label class="control-label" style="padding-right: 0px;">${__("Fields")}</label>
						<label class="text-extra-muted float-right">
							<a class="add-new-fields text-muted">
								${__("+ Add / Remove Fields")}
							</a>
						</label>
					</div>
					<div class="control-input-wrapper">
					${fields}
					</div>
				</div>
			`);

			new Sortable(wrapper.getElementsByClassName("control-input-wrapper")[0], {
				handle: ".sortable-handle",
				draggable: ".sortable",
				onUpdate: () => {
					this.update_fields();
					this.refresh();
				},
			});
		}

		add_new_fields() {
			const fields_html = this.dialog.get_field("fields_html");
			const add_new_fields = fields_html.$wrapper[0].getElementsByClassName("add-new-fields")[0];
			add_new_fields.onclick = () => this.column_selector();
		}

		setup_remove_fields() {
			const fields_html = this.dialog.get_field("fields_html");
			const remove_fields = fields_html.$wrapper[0].getElementsByClassName("remove-field");

			for (let idx = 0; idx < remove_fields.length; idx++) {
				remove_fields.item(idx).onclick = () =>
					this.remove_fields(remove_fields.item(idx).getAttribute("data-fieldname"));
			}
		}

		remove_fields(fieldname) {
			const existing_fields = this.fields.map((f) => f.fieldname);

			for (const idx in this.fields) {
				const field = this.fields[idx];
				if (field.fieldname === fieldname) {
					this.fields.splice(idx, 1);
					break;
				}
			}
			this.set_removed_fields(
				this.get_removed_listview_fields(
					this.fields.map((f) => f.fieldname),
					existing_fields
				)
			);
			this.refresh();
			this.update_fields();
		}

		update_fields() {
			const fields_html = this.dialog.get_field("fields_html");
			const wrapper = fields_html.$wrapper[0];
			const fields_order = wrapper.getElementsByClassName("fields_order");
			this.fields = [];

			for (let idx = 0; idx < fields_order.length; idx++) {
				this.fields.push({
					fieldname: fields_order.item(idx).getAttribute("data-fieldname"),
					label: __(fields_order.item(idx).getAttribute("data-label")),
				});
			}

			this.dialog.set_value("fields", JSON.stringify(this.fields));
			this.dialog.get_value("fields");
		}

		column_selector() {
			const d = new frappe.ui.Dialog({
				title: __("{0} Fields", [__(this.doctype)]),
				fields: [
					{
						label: __("Reset Fields"),
						fieldtype: "Button",
						fieldname: "reset_fields",
						click: () => this.reset_listview_fields(d),
					},
					{
						label: __("Select Fields (Up to {0})", [this.max_number_of_fields]),
						fieldtype: "MultiCheck",
						fieldname: "fields",
						options: this.get_doctype_fields(
							this.meta,
							this.fields.map((f) => f.fieldname)
						),
						columns: 2,
					},
				],
			});
			d.set_primary_action(__("Save"), () => {
				const values = d.get_values().fields;

				this.set_removed_fields(
					this.get_removed_listview_fields(
						values,
						this.fields.map((f) => f.fieldname)
					)
				);

				this.fields = [];
				this.set_subject_field(this.meta);
				this.set_status_field();

				for (const idx in values) {
					const value = values[idx];

					if (this.fields.length === this.max_number_of_fields) {
						break;
					} else if (value !== this.subject_field.fieldname) {
						const field = frappe.meta.get_docfield(this.doctype, value);
						if (field) {
							this.fields.push({
								label: __(field.label, null, this.doctype),
								fieldname: field.fieldname,
							});
						}
					}
				}

				this.refresh();
				this.dialog.set_value("fields", JSON.stringify(this.fields));
				d.hide();
			});
			d.show();
		}

		reset_listview_fields(dialog) {
			frappe
				.xcall("frappe.desk.doctype.list_view_settings.list_view_settings.get_default_listview_fields", {
					doctype: this.doctype,
				})
				.then((fields) => {
					const field = dialog.get_field("fields");
					field.df.options = this.get_doctype_fields(this.meta, fields);
					dialog.refresh();
				});
		}

		get_listview_fields(meta) {
			if (!this.settings.fields) {
				this.set_list_view_fields(meta);
			} else {
				this.fields = JSON.parse(this.settings.fields);
			}

			this.fields = this.fields.filter(
				(field, index, array) => index === array.findIndex((entry) => entry.fieldname === field.fieldname)
			);
		}

		set_list_view_fields(meta) {
			this.set_subject_field(meta);
			this.set_status_field();

			meta.fields.forEach((field) => {
				if (
					field.in_list_view &&
					!frappe.model.no_value_type.includes(field.fieldtype) &&
					this.subject_field.fieldname !== field.fieldname
				) {
					this.fields.push({
						label: __(field.label, null, this.doctype),
						fieldname: field.fieldname,
					});
				}
			});
		}

		set_subject_field(meta) {
			this.subject_field = {
				label: __("ID"),
				fieldname: "name",
			};

			if (meta.title_field) {
				const field = frappe.meta.get_docfield(this.doctype, meta.title_field.trim());
				this.subject_field = {
					label: __(field.label, null, this.doctype),
					fieldname: field.fieldname,
				};
			}

			this.fields.push(this.subject_field);
		}

		set_status_field() {
			if (frappe.has_indicator(this.doctype)) {
				this.fields.push({
					type: "Status",
					label: __("Status"),
					fieldname: "status_field",
				});
			}
		}

		get_doctype_fields(meta, fields) {
			const multiselect_fields = [];

			meta.fields.forEach((field) => {
				if (!frappe.model.no_value_type.includes(field.fieldtype)) {
					multiselect_fields.push({
						label: __(field.label, null, field.doctype),
						value: field.fieldname,
						checked: fields.includes(field.fieldname),
					});
				}
			});

			return multiselect_fields;
		}

		get_removed_listview_fields(new_fields, existing_fields) {
			const removed_fields = [];
			const next_fields = [...new_fields];

			if (frappe.has_indicator(this.doctype)) {
				next_fields.push("status_field");
			}

			existing_fields.forEach((column) => {
				if (!next_fields.includes(column)) {
					removed_fields.push(column);
				}
			});

			return removed_fields;
		}

		set_removed_fields(fields) {
			if (this.removed_fields) {
				this.removed_fields = this.removed_fields.concat(fields);
			} else {
				this.removed_fields = fields;
			}
		}

		_is_status_field(field) {
			return field.fieldname === "status_field";
		}
	}

	function can_show_tms_list_settings(listview) {
		const boot = frappe.boot || {};
		if (frappe.user.has_role("System Manager")) {
			return false;
		}
		if (!boot.cloudverce_is_list_settings_admin) {
			return false;
		}
		return Array.isArray(boot.cloudverce_list_settings_doctypes)
			&& boot.cloudverce_list_settings_doctypes.includes(listview.doctype);
	}

	function patch_list_view() {
		const ListView = frappe.views && frappe.views.ListView;
		if (!ListView || ListView.prototype._tms_list_settings_patched) {
			return Boolean(ListView);
		}

		const original_get_menu_items = ListView.prototype.get_menu_items;
		const original_show_list_settings = ListView.prototype.show_list_settings;

		ListView.prototype.get_menu_items = function () {
			const items = original_get_menu_items.call(this) || [];
			if (!can_show_tms_list_settings(this)) {
				return items;
			}

			const has_list_settings = items.some((item) => item.label === __("List Settings", null, "Button in list view menu"));
			if (!has_list_settings) {
				items.push(this.get_view_settings());
			}
			return items;
		};

		ListView.prototype.show_list_settings = function () {
			if (!can_show_tms_list_settings(this)) {
				return original_show_list_settings.call(this);
			}

			frappe.model.with_doctype(this.doctype, () => {
				new TMSListSettings({
					listview: this,
					doctype: this.doctype,
					settings: this.list_view_settings,
					meta: frappe.get_meta(this.doctype),
				});
			});
		};

		ListView.prototype._tms_list_settings_patched = true;
		return true;
	}

	TMS.patch_list_view_for_tms_list_settings = patch_list_view;

	if (!patch_list_view()) {
		const patch_timer = window.setInterval(() => {
			if (patch_list_view()) {
				window.clearInterval(patch_timer);
			}
		}, 200);
	}
})();
