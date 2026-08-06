// Combined endpoint replacing 4 separate frappe.call()s (matrix, nav matrix, role
// permissions, nav visibility config) that used to run as parallel requests competing
// for the browser's per-origin connection limit alongside sync_managed_doctypes.
// Same data, one round-trip. See get_form_bundle() in cloudverce_user_group.py.
const _FORM_BUNDLE_API = "cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group.get_form_bundle";

const PERM_COLS = [
	{ key: "perm_select", label: "Select", group: "core"     },
	{ key: "perm_read",   label: "Read",   group: "core"     },
	{ key: "perm_write",  label: "Write",  group: "core"     },
	{ key: "perm_create", label: "Create", group: "core"     },
	{ key: "perm_delete", label: "Delete", group: "core"     },
	{ key: "perm_submit", label: "Submit", group: "workflow" },
	{ key: "perm_cancel", label: "Cancel", group: "workflow" },
	{ key: "perm_amend",  label: "Amend",  group: "workflow" },
	{ key: "perm_print",  label: "Print",  group: "extras"   },
	{ key: "perm_email",  label: "Email",  group: "extras"   },
	{ key: "perm_report", label: "Report", group: "extras"   },
	{ key: "perm_import", label: "Import", group: "extras"   },
	{ key: "perm_export", label: "Export", group: "extras"   },
];

const GROUP_META = {
	core:     { label: "Core Access",  bg: "#4338CA", span: 5 },
	workflow: { label: "Workflow",     bg: "#B45309", span: 3 },
	extras:   { label: "Data & Extras",bg: "#0F766E", span: 5 },
};

const S = {
	wrap:     "overflow-x:auto;-webkit-overflow-scrolling:touch;width:100%;max-width:100%;border-radius:14px;border:2px solid #4338CA;box-shadow:0 14px 32px rgba(37, 45, 122, .16), 0 2px 8px rgba(67,56,202,.10);margin-top:12px;background:linear-gradient(180deg,#F8FAFF 0%,#FFFFFF 100%);padding:0;",
	table:    "width:100%;min-width:1120px;border-collapse:separate;border-spacing:0;font-size:13px;font-family:inherit;",
	corner:   "background:#1E1B4B;color:#fff;font-weight:700;font-size:12px;padding:10px 14px;white-space:nowrap;vertical-align:middle;border-right:1px solid rgba(255,255,255,.15);border-bottom:1px solid #A5B4FC;",
	cornerFirst:"border-top-left-radius:12px;",
	cornerLast: "border-top-right-radius:12px;",
	grpTh:    "color:#fff;font-weight:800;font-size:11px;text-transform:uppercase;letter-spacing:.07em;text-align:center;padding:8px 4px;border:1px solid rgba(255,255,255,.2);",
	colTh:    "background:#EEF2FF;color:#3730A3;font-weight:700;font-size:11px;text-transform:uppercase;text-align:center;padding:7px 4px;white-space:nowrap;border-right:1px solid #C7D2FE;border-bottom:1px solid #C7D2FE;width:52px;",
	colThSep: "border-left:2px solid #A5B4FC;",
	modCell:  "vertical-align:middle;padding:8px;border-right:1px solid #D6DAF5;border-bottom:1px solid #E5E7EB;background:#F8FAFC;text-align:center;",
	modInner: "min-height:100%;display:flex;align-items:center;justify-content:center;",
	secCell:  "vertical-align:middle;padding:8px;border-right:1px solid #D6DAF5;border-bottom:1px solid #E5E7EB;background:#FBFBFF;text-align:center;",
	secInner: "min-height:100%;display:flex;align-items:center;justify-content:center;",
	nameCell: "padding:7px 12px;white-space:nowrap;font-size:13px;color:#111827;border-right:2px solid #A5B4FC;border-bottom:1px solid #E5E7EB;",
	chkCell:  "text-align:center;padding:5px 2px;border-right:1px solid #E5E7EB;border-bottom:1px solid #E5E7EB;",
	chkSep:   "border-left:2px solid #C7D2FE;",
	groupTop: "border-top:3px solid #818CF8 !important;",
	groupRow: "box-shadow:inset 0 1px 0 #E0E7FF;",
	even:     "background:#FAFAFF;",
	odd:      "background:#FFFFFF;",
	badge:    "display:inline-flex;align-items:center;justify-content:center;min-width:92px;padding:7px 14px;border-radius:999px;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;white-space:nowrap;background:#E0E7FF;color:#3730A3;line-height:1.1;box-shadow:inset 0 0 0 1px rgba(67,56,202,.08),0 4px 10px rgba(67,56,202,.08);",
};

const NAV = {
	wrap: "margin-top:20px;padding-top:14px;border-top:2px solid #E0E7FF;",
	title: "font-size:15px;font-weight:800;color:#1E1B4B;margin:0 0 4px 0;",
	subtitle: "font-size:12px;color:#6B7280;margin:0 0 16px 0;",
	grid: "display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px;margin-bottom:16px;",
	sectionLabel: "font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:#6366F1;margin:0 0 6px 0;padding:0 2px;",
	card: "background:#fff;border:1.5px solid #E0E7FF;border-radius:10px;padding:9px 12px;display:flex;align-items:center;justify-content:space-between;gap:8px;transition:box-shadow .15s,border-color .15s;cursor:default;min-width:0;",
	cardHover: "border-color:#818CF8;box-shadow:0 2px 10px rgba(99,102,241,.12);",
	cardLabel: "font-size:13px;color:#1E1B4B;font-weight:500;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
	toggle: "position:relative;display:inline-flex;width:38px;height:22px;flex-shrink:0;",
	toggleInput: "opacity:0;width:0;height:0;position:absolute;",
	toggleSlider: "position:absolute;inset:0;border-radius:999px;transition:.2s;cursor:pointer;",
	sectionWrap: "margin-bottom:20px;",
};

// Whether the CURRENT logged-in user can actually save changes to this specific
// Cloudverce User Group document (server-side already enforces this via has_permission --
// this only mirrors it in the UI so a read-only viewer's controls are visibly disabled
// rather than appearing editable and failing silently on Save).
function _group_is_read_only_for_viewer(frm) {
	return !(frm.perm && frm.perm[0] && frm.perm[0].write);
}

// Shared by both the permission matrix's Module column and the Dashboard & Page
// Permissions grid below it, so the same section name (e.g. "Manufacturing") always
// gets the same color everywhere on the form.
const SECTION_COLORS = [
	{ bg: "#EEF2FF", border: "#C7D2FE", text: "#4338CA", dot: "#6366F1" },
	{ bg: "#F0FDF4", border: "#BBF7D0", text: "#15803D", dot: "#22C55E" },
	{ bg: "#FFF7ED", border: "#FED7AA", text: "#C2410C", dot: "#F97316" },
	{ bg: "#F5F3FF", border: "#DDD6FE", text: "#7C3AED", dot: "#A855F7" },
	{ bg: "#FFF1F2", border: "#FECDD3", text: "#BE123C", dot: "#F43F5E" },
	{ bg: "#F0F9FF", border: "#BAE6FD", text: "#0369A1", dot: "#0EA5E9" },
];

// Stable color per section name (same name -> same color on every render), rather than
// a color keyed to row/column position, so "Manufacturing" looks the same whether it's
// the 1st or 4th section encountered for a given module.
function _sectionColor(sectionName) {
	let hash = 0;
	const s = sectionName || "";
	for (let i = 0; i < s.length; i++) {
		hash = (hash * 31 + s.charCodeAt(i)) | 0;
	}
	return SECTION_COLORS[Math.abs(hash) % SECTION_COLORS.length];
}

function moduleBadge(module) {
	return `<span style="${S.badge}">${frappe.utils.escape_html(module)}</span>`;
}

function sectionBadge(section) {
	const clr = _sectionColor(section);
	return `<span style="display:inline-flex;align-items:center;gap:5px;padding:6px 12px;border-radius:999px;
	             background:${clr.bg};border:1.5px solid ${clr.border};color:${clr.text};
	             font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;white-space:nowrap;">
		<span style="width:6px;height:6px;border-radius:50%;background:${clr.dot};flex-shrink:0;"></span>
		${frappe.utils.escape_html(section)}
	</span>`;
}

frappe.ui.form.on("Cloudverce User Group", {

	refresh(frm) {
		// Key the synced flag by doc name — frm is REUSED across documents of the same
		// doctype, so a plain boolean meant only the FIRST group opened in a session ever
		// got synced; every next group silently skipped it.
		if (frm._sidebar_synced_for !== frm.doc.name) {
			frm.events.sync_managed_doctypes(frm);
		}
		frm.events.add_rename_button(frm);
		frm.events.add_internal_permission_button(frm);
		frm.events.load_matrix(frm);
	},

	before_save(frm) {
		frm.events.normalize_permission_rows(frm);
		// CAPA FIX: Do NOT rebuild navigation visibility from the DOM on save.
		// The nav matrix re-renders asynchronously (load_matrix runs on every refresh and
		// via sync_managed_doctypes callback). If an in-flight re-render flips an OFF toggle
		// back to ON in the DOM after the user toggled it, reading the DOM here overwrote the
		// correct frm.doc value with `hidden_labels: []` -> the toggle silently reverted ON.
		// frm.doc.navigation_visibility_json is already the source of truth: it is loaded from
		// DB on form open and kept in sync live by on_nav_checkbox_change -> set_navigation_config.
		// frm.events.sync_navigation_visibility_from_dom(frm);
	},

	sync_managed_doctypes(frm) {
		if (frm.is_new() || frm._sidebar_synced_for === frm.doc.name) return;

		frappe.call({
			method: "sync_managed_doctypes",
			doc: frm.doc,
			callback: (r) => {
				frm._sidebar_synced_for = frm.doc.name;
				// If the sync SAVED the doc server-side (missing rows were removed),
				// `modified` was bumped behind the form's back — the user's very next Save
				// (e.g. ticking Is Admin right after opening) raised a false
				// TimestampMismatchError. Reload the doc to pick up the fresh timestamp and
				// row changes; if the user already started editing, don't wipe their edits —
				// just accept the fresh timestamp so their Save doesn't conflict.
				const res = r.message;
				if (res && res.changed) {
					if (frm.is_dirty()) {
						// Monotonic patch — only move the timestamp FORWARD. Two async
						// callbacks patch frm.doc.modified (this one and the nav-toggle one);
						// out-of-order responses must not overwrite a newer timestamp with an
						// older one. Format "YYYY-MM-DD HH:MM:SS.ffffff" sorts lexicographically,
						// so string compare is safe.
						if (res.modified && (!frm.doc.modified || res.modified > frm.doc.modified)) {
							frm.doc.modified = res.modified;
						}
					} else {
						frm.reload_doc();
						return; // reload triggers refresh → load_matrix runs from there
					}
				}
				// Refresh matrix to show newly added DocTypes
				frm.events.load_matrix(frm);
			},
		});
	},
	is_admin(frm) { frm.events.load_matrix(frm); },

	add_rename_button(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Rename Group"), () => {
			frappe.prompt(
				{
					fieldtype: "Data",
					label: __("Group Name"),
					fieldname: "group_name",
					reqd: 1,
					default: frm.doc.group_name || frm.doc.name,
				},
				(values) => {
					const newName = (values.group_name || "").trim();
					if (!newName || newName === frm.doc.name) return;

					frappe.call({
						method: "frappe.rename_doc",
						freeze: true,
						freeze_message: __("Renaming group and syncing linked role/profile..."),
						args: {
							doctype: "Cloudverce User Group",
							old: frm.doc.name,
							new: newName,
							merge: false,
						},
						callback: (r) => {
							if (r.exc) return;
							const renamedTo = r.message || newName;
							frappe.show_alert({
								message: __("Group renamed to {0}", [renamedTo]),
								indicator: "green",
							});
							frappe.set_route("Form", "Cloudverce User Group", renamedTo);
						},
					});
				},
				__("Rename Group"),
				__("Rename")
			);
		});
	},

	add_internal_permission_button(frm) {
		// Static/informational for every group (admin or normal, new or saved) — the
		// answer never depends on frm.doc, so it's safe to show unconditionally.
		frm.add_custom_button(__("Internal Permission"), () => {
			frm.events.show_internal_permission_dialog(frm);
		});
	},

	// ── Add DocType to sidebar (no Workspace Editor needed) ─────────────────

	add_sidebar_doctype_button(frm) {
		if (_group_is_read_only_for_viewer(frm) || frm.doc.is_admin) return;
		frm.add_custom_button(__("+ Add DocType"), () => {
			frm.events.show_add_sidebar_doctype_dialog(frm);
		});
	},

	show_add_sidebar_doctype_dialog(frm) {
		frappe.call({
			method: "cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group.get_eligible_sidebar_workspaces",
			freeze: true,
			callback: (r) => {
				const workspaces = r.message || [];
				if (!workspaces.length) {
					frappe.msgprint(__(
						"No RBAC-eligible workspace found. Include an app, module, or workspace in Cloudverce Utility Settings first."
					));
					return;
				}

				const d = new frappe.ui.Dialog({
					title: __("Add DocType to Sidebar"),
					fields: [
						{
							fieldtype: "Link",
							fieldname: "doctype_name",
							label: __("DocType"),
							options: "DocType",
							reqd: 1,
							description: __("Any DocType — even one from an app like ERPNext that isn't otherwise governed here."),
							get_query: () => ({
								filters: { istable: 0, issingle: 0, name: ["!=", "Cloudverce User Group"] },
							}),
						},
						{
							fieldtype: "Select",
							fieldname: "workspace",
							label: __("Sidebar"),
							reqd: 1,
							options: workspaces.map(w => ({ label: w.label, value: w.name })),
							description: __("Which sidebar this DocType should appear under."),
						},
						{
							fieldtype: "Data",
							fieldname: "label",
							label: __("Label"),
							description: __("Optional — defaults to the DocType name."),
						},
					],
					primary_action_label: __("Add"),
					primary_action: (values) => {
						frappe.call({
							method: "cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group.add_doctype_to_sidebar",
							args: {
								doctype: values.doctype_name,
								workspace: values.workspace,
								label: values.label || "",
							},
							freeze: true,
							callback: () => {
								d.hide();
								frappe.show_alert({ message: __("{0} added", [values.doctype_name]), indicator: "green" });
								frm.events.load_matrix(frm);
							},
						});
					},
				});
				d.show();
			},
		});
	},

	remove_sidebar_doctype(frm, doctype, workspace) {
		frappe.confirm(
			__("Remove {0} from the {1} sidebar? It will no longer be manageable in this Permission Matrix unless re-added.", [doctype, workspace]),
			() => {
				frappe.call({
					method: "cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group.remove_doctype_from_sidebar",
					args: { doctype, workspace },
					freeze: true,
					callback: () => {
						frappe.show_alert({ message: __("{0} removed", [doctype]), indicator: "orange" });
						frm.events.load_matrix(frm);
					},
				});
			}
		);
	},

	show_internal_permission_dialog(frm) {
		frappe.call({
			method: "cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group.get_baseline_permission_matrix",
			args: { group_name: frm.doc.name },
			freeze: true,
			callback: (r) => {
				const data = r.message || {};
				const doctypes = data.doctypes || [];
				const columns = data.columns || [];
				const permMap = data.perm_map || {};

				const d = new frappe.ui.Dialog({
					title: __("Internal Permission"),
					size: "extra-large",
					fields: [
						{
							fieldtype: "HTML",
							fieldname: "internal_permission_html",
							options: frm.events.render_internal_permission_table(doctypes, columns, permMap),
						},
					],
				});
				d.show();
				// Dialog markup renders after show(); force the responsive wrapper to
				// re-measure so the horizontal-scroll table sizes correctly on first paint.
				d.$wrapper.find(".cloudverce-ip-scroll").each(function () { void this.offsetWidth; });
			},
		});
	},

	render_internal_permission_table(doctypes, columns, permMap) {
		const IP = {
			banner: "display:flex;align-items:flex-start;gap:10px;padding:10px 14px;margin-bottom:14px;background:#ECFDF5;border:1.5px solid #A7F3D0;border-radius:10px;",
			bannerText: "font-size:12.5px;line-height:1.5;color:#065F46;font-weight:600;",
			scroll: "overflow-x:auto;overflow-y:auto;max-height:60vh;-webkit-overflow-scrolling:touch;width:100%;max-width:100%;border-radius:14px;border:2px solid #059669;box-shadow:0 14px 32px rgba(5,150,105,.14);background:linear-gradient(180deg,#F0FDF4 0%,#FFFFFF 100%);",
			table: "width:100%;min-width:100%;border-collapse:separate;border-spacing:0;font-size:13px;",
			corner: "position:sticky;left:0;top:0;z-index:3;background:#064E3B;color:#fff;font-weight:700;font-size:12px;padding:10px 14px;white-space:nowrap;text-align:left;border-top-left-radius:12px;border-bottom:1px solid #A7F3D0;",
			colTh: "position:sticky;top:0;z-index:2;background:#ECFDF5;color:#065F46;font-weight:700;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;text-align:center;padding:8px 6px;white-space:nowrap;border-bottom:1px solid #A7F3D0;border-left:1px solid #D1FAE5;min-width:58px;",
			nameTd: "position:sticky;left:0;padding:8px 14px;white-space:nowrap;font-size:12.5px;color:#111827;font-weight:600;border-bottom:1px solid #ECFDF5;",
			chkTd: "text-align:center;padding:6px 4px;border-bottom:1px solid #ECFDF5;border-left:1px solid #ECFDF5;",
			badge: "display:inline-flex;align-items:center;justify-content:center;width:19px;height:19px;border-radius:50%;background:#059669;color:#fff;font-size:11px;font-weight:800;line-height:1;",
			dash: "color:#9CA3AF;font-size:13px;font-weight:700;",
		};

		let head = `<tr><th style="${IP.corner}">${__("Doc Name")}</th>`;
		columns.forEach((c) => {
			head += `<th style="${IP.colTh}">${frappe.utils.escape_html(c)}</th>`;
		});
		head += "</tr>";

		let body = "";
		doctypes.forEach((dt, idx) => {
			const rowBg = idx % 2 === 0 ? "background:#F9FFFB;" : "background:#FFFFFF;";
			const rowPerm = (permMap && permMap[dt]) || {};
			body += `<tr><td style="${IP.nameTd}${rowBg}">${frappe.utils.escape_html(dt)}</td>`;
			columns.forEach((c) => {
				const granted = rowPerm[c.toLowerCase()];
				const cell = granted
					? `<span style="${IP.badge}">&#10003;</span>`
					: `<span style="${IP.dash}">&#8212;</span>`;
				body += `<td style="${IP.chkTd}${rowBg}">${cell}</td>`;
			});
			body += "</tr>";
		});

		return `
			<div style="${IP.banner}">
				<span style="font-size:16px;line-height:1;">&#128274;</span>
				<span style="${IP.bannerText}">
					${__("These Doc Names are always granted access for every Cloudverce User Group. Most give full access to Admin and Normal groups alike; a few (like User) give Normal groups a reduced, own-record-only access, with full access reserved for Admin groups. This is locked and cannot be changed from here or from the permissions matrix above.")}
				</span>
			</div>
			<div class="cloudverce-ip-scroll" style="${IP.scroll}">
				<table style="${IP.table}">
					<thead>${head}</thead>
					<tbody>${body}</tbody>
				</table>
			</div>`;
	},

	// ── Field-level (per-field Hidden / Read Only) permission dialog ────────

	show_field_permission_dialog(frm, doctype) {
		if (frm.is_new()) {
			frappe.msgprint(__("Save the group first before managing field permissions."));
			return;
		}
		frappe.call({
			method: "cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group.get_doctype_field_permission_config",
			args: { doctype, group_name: frm.doc.name },
			freeze: true,
			callback: (r) => {
				const data = r.message || {};
				frm.events.open_field_permission_dialog(frm, doctype, data.fields || [], data.saved || {});
			},
		});
	},

	open_field_permission_dialog(frm, doctype, fields, saved) {
		const isAdmin = !!frm.doc.is_admin;
		const readOnlyView = isAdmin || _group_is_read_only_for_viewer(frm);

		const d = new frappe.ui.Dialog({
			title: __("Field Permissions — {0}", [doctype]),
			size: "extra-large",
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "field_perm_html",
					options: frm.events.render_field_permission_table(fields, saved, readOnlyView),
				},
			],
			primary_action_label: __("Save"),
			primary_action: () => {
				// is_admin groups always have full access (see _sync_field_permission_docperms),
				// and a read-only viewer can never save -- dialog is informational only for both.
				if (readOnlyView) { d.hide(); return; }

				frappe.call({
					method: "cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group.save_field_permissions",
					args: {
						group_name: frm.doc.name,
						doctype,
						rows: JSON.stringify(frm.events.collect_field_permission_rows(d)),
					},
					freeze: true,
					callback: (r) => {
						// This save bumps the server-side `modified` timestamp behind the open
						// form's back -- sync it so the form's own next Save doesn't raise a
						// false TimestampMismatchError (same pattern as set_navigation_visibility).
						if (r.message && r.message.modified) {
							frm.doc.modified = r.message.modified;
						}
						d.hide();
						frappe.show_alert({ message: __("Field permissions saved"), indicator: "green" }, 4);
					},
				});
			},
		});

		d.show();
		d.$wrapper.find(".cloudverce-fp-scroll").each(function () { void this.offsetWidth; });

		// "Default" is a 3rd, mutually-exclusive-with-the-other-two toggle -- purely
		// visual, so an admin can tell at a glance "this group has no override on this
		// field" instead of wrongly assuming they configured it. Checking Default clears
		// Hidden + Read Only (the field's own permanent structural Read Only badge, if
		// any, cannot be cleared -- it isn't a group override). Hidden and Read Only stay
		// free to combine with EACH OTHER as before -- only Default is exclusive of the
		// other two.
		d.$wrapper.off("change.cloudverce_fp").on("change.cloudverce_fp", ".cloudverce-fp-toggle", function () {
			const $cb = $(this);
			const $row = $cb.closest(".cloudverce-fp-row");
			if ($cb.data("state") === "Default") {
				if ($cb.is(":checked")) {
					$row.find('.cloudverce-fp-toggle[data-state="Hidden"]').prop("checked", false);
					$row.find('.cloudverce-fp-toggle[data-state="Read Only"]:not(:disabled)').prop("checked", false);
				}
				return;
			}
			if ($cb.is(":checked")) {
				$row.find('.cloudverce-fp-toggle[data-state="Default"]').prop("checked", false);
				return;
			}
			const hiddenOn = $row.find('.cloudverce-fp-toggle[data-state="Hidden"]').is(":checked");
			const readOnlyOn = $row.find('.cloudverce-fp-toggle[data-state="Read Only"]').is(":checked");
			if (!hiddenOn && !readOnlyOn) {
				$row.find('.cloudverce-fp-toggle[data-state="Default"]').prop("checked", true);
			}
		});
	},

	// No client-side reconciliation between the Hidden/Read Only toggles -- whatever
	// the admin clicks is sent to the server exactly as-is (both flags, per field),
	// and the server resolves any conflict (Hidden always wins over Read Only) when
	// saving. This keeps the UI a plain, literal reflection of what's checked, with
	// no toggles silently flipping each other while the admin is still working.
	// (Default, above, is the one exception -- see the change handler.)
	collect_field_permission_rows(d) {
		const rows = [];
		d.$wrapper.find(".cloudverce-fp-row").each(function () {
			const $row = $(this);
			const hidden = $row.find('.cloudverce-fp-toggle[data-state="Hidden"]').is(":checked");
			const readOnly = $row.find('.cloudverce-fp-toggle[data-state="Read Only"]').is(":checked");
			if (hidden || readOnly) {
				rows.push({ fieldname: $row.data("fieldname"), hidden, read_only: readOnly });
			}
		});
		return rows;
	},

	render_field_permission_table(fields, savedState, readOnlyView) {
		const FP = {
			scroll: "overflow-y:auto;max-height:55vh;-webkit-overflow-scrolling:touch;width:100%;border-radius:14px;border:2px solid #4338CA;box-shadow:0 14px 32px rgba(37,45,122,.16);background:linear-gradient(180deg,#F8FAFF 0%,#FFFFFF 100%);",
			row: "display:flex;align-items:center;justify-content:space-between;gap:16px;padding:9px 16px;border-bottom:1px solid #E5E7EB;",
			label: "font-size:13px;color:#111827;font-weight:600;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
			roBadge: "font-size:10px;color:#92400E;font-weight:700;text-transform:uppercase;letter-spacing:.04em;background:#FEF3C7;border:1px solid #FCD34D;border-radius:999px;padding:1px 8px;margin-left:8px;",
			mandBadge: "font-size:10px;color:#991B1B;font-weight:700;text-transform:uppercase;letter-spacing:.04em;background:#FEE2E2;border:1px solid #FCA5A5;border-radius:999px;padding:1px 8px;margin-left:8px;",
			toggleGroup: "display:flex;gap:16px;flex-shrink:0;",
			toggleWrap: "display:flex;align-items:center;gap:6px;cursor:pointer;",
			toggleLabel: "font-size:11.5px;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:.03em;",
		};

		let rows = "";
		(fields || []).forEach((f) => {
			// Read-only in practice for everyone, structurally (df.read_only) -- the Read
			// Only toggle is locked ON, and Default is computed from Hidden alone (never
			// from a saved Read Only row), since "Read Only" isn't a real choice for these
			// fields -- it's a foregone conclusion.
			const forcedReadOnly = !!f.is_read_only;
			const isMandatory = !!f.is_mandatory;
			const savedFor = (savedState || {})[f.fieldname] || "";
			const hiddenOn = savedFor === "Hidden";
			const explicitReadOnly = savedFor === "Read Only";
			const readOnlyOn = forcedReadOnly ? true : explicitReadOnly;
			// Default = this group has no Hidden/Read Only override on this field at all.
			// For a forced-read-only field, Read Only isn't a real override to weigh --
			// Default only tracks whether Hidden is set.
			const defaultOn = forcedReadOnly ? !hiddenOn : (!hiddenOn && !explicitReadOnly);
			const disabled = readOnlyView ? "disabled" : "";
			const roDisabled = (readOnlyView || forcedReadOnly) ? "disabled" : "";

			rows += `<div class="cloudverce-fp-row" data-fieldname="${frappe.utils.escape_html(f.fieldname)}"
			             data-forced-readonly="${forcedReadOnly ? 1 : 0}" style="${FP.row}">
				<span style="${FP.label}" title="${frappe.utils.escape_html(f.fieldname)}">
					${frappe.utils.escape_html(f.label)}
					${forcedReadOnly ? `<span style="${FP.roBadge}">${__("Read Only")}</span>` : ""}
					${isMandatory ? `<span style="${FP.mandBadge}">${__("Mandatory")}</span>` : ""}
				</span>
				<div style="${FP.toggleGroup}">
					<label style="${FP.toggleWrap}">
						<input type="checkbox" class="cloudverce-fp-toggle" data-state="Default" ${defaultOn ? "checked" : ""} ${disabled}>
						<span style="${FP.toggleLabel}">${__("Default")}</span>
					</label>
					<label style="${FP.toggleWrap}">
						<input type="checkbox" class="cloudverce-fp-toggle" data-state="Read Only" ${readOnlyOn ? "checked" : ""} ${roDisabled}>
						<span style="${FP.toggleLabel}">${__("Read Only")}</span>
					</label>
					<label style="${FP.toggleWrap}">
						<input type="checkbox" class="cloudverce-fp-toggle" data-state="Hidden" ${hiddenOn ? "checked" : ""} ${disabled}>
						<span style="${FP.toggleLabel}">${__("Hidden")}</span>
					</label>
				</div>
			</div>`;
		});

		return `<div class="cloudverce-fp-scroll" style="${FP.scroll}">${
			rows || `<div style="padding:24px;text-align:center;color:#6B7280;">${__("No fields")}</div>`
		}</div>`;
	},

	load_matrix(frm) {
		const requestId = (frm._tms_matrix_request_id || 0) + 1;
		frm._tms_matrix_request_id = requestId;

		frappe.call({
			method: _FORM_BUNDLE_API,
			args: {
				group_name: frm.doc.name || "",
				include_doc: 0,
			},
			callback: (res) => {
				// Ignore stale responses from earlier matrix refreshes.
				if (frm._tms_matrix_request_id !== requestId) {
					return;
				}

				const bundle = res.message || {};
				const matrix = bundle.matrix || [];
				const navMatrix = bundle.nav_matrix || [];
				const rp = bundle.role_permissions || {};
				const navJson = bundle.navigation_visibility_json || frm.doc.navigation_visibility_json || "";

				// CAPA FIX: navigation_visibility_json is now written EXCLUSIVELY by
				// set_navigation_visibility() (immediate save on toggle) and is locked server-side
				// against being overwritten by the normal doc Save (see
				// _lock_navigation_visibility_to_db in cloudverce_user_group.py). That makes the DEDICATED
				// fresh fetch (navJson, from get_navigation_visibility_config) the one value that is
				// ALWAYS correct and current. frm.doc.navigation_visibility_json, by contrast, is a
				// point-in-time snapshot that can go stale on ANY re-render triggered outside a user
				// toggle -- e.g. Frappe's own realtime "doc_update" listener calls
				// frm.debounced_reload_doc() a moment after every Save, and that reload's render can
				// land using an older frm.doc snapshot. So: always trust the fresh server fetch, and
				// only fall back to frm.doc if that fetch is unavailable (e.g. brand-new/unsaved doc).
				const sourceJson = (frm._tms_nav_visibility_json !== undefined && frm._tms_nav_visibility_json !== null)
					? frm._tms_nav_visibility_json
					: ((navJson !== undefined && navJson !== null)
						? navJson
						: (frm.doc.navigation_visibility_json || ""));
				frm.doc.navigation_visibility_json = sourceJson;
				frm._tms_nav_visibility_json = sourceJson;
				let navConfig;
				try {
					// CAPA FIX: frappe.parse_json is not a real function -- only frappe.utils.parse_json
					// exists (verified against frappe core, which never calls the bare form). Every
					// call here was throwing a silent TypeError, caught below, defaulting to an EMPTY
					// Set on every single render. That made every dashboard/report/page toggle always
					// evaluate as "not hidden" (visible) right after any re-render -- this was the true
					// root cause of the toggle reverting to ON after Save.
					const parsed = frappe.utils.parse_json(sourceJson) || {};
					const hiddenArr = parsed.hidden_labels || parsed.hidden || [];
					navConfig = new Set((hiddenArr).map(l => (l || "").trim()).filter(Boolean));
				} catch(e) {
					navConfig = new Set();
				}
				frm.events.render_matrix(frm, matrix, rp, navMatrix, navConfig);
			},
		});
	},

	render_matrix(frm, matrix, rolePerms, navMatrix, navConfig) {
		rolePerms = rolePerms || {};
		const lookup = {};
		(frm.doc.permissions || []).forEach(row => { lookup[row.document_type] = row; });
		frm._tms_doc_module_map = {};
		matrix.forEach(group => {
			(group.items || []).forEach(item => {
				if (item.doctype) {
					frm._tms_doc_module_map[item.doctype] = group.module || "";
				}
			});
		});
		const isAdmin = !!frm.doc.is_admin;
		// Use passed navConfig (fresh from DB); fall back to frm.doc parse only if not provided
		if (!navConfig) navConfig = frm.events.get_navigation_config(frm);

		// ── row 1: group headers ────────────────────────────────────
		let grpRow = `<tr>
			<th rowspan="2" style="${S.corner}${S.cornerFirst}width:105px;">Module</th>
			<th rowspan="2" style="${S.corner}width:120px;">Section</th>
			<th rowspan="2" style="${S.corner}width:160px;min-width:160px;">Screen</th>`;

		["core","workflow","extras"].forEach(g => {
			const m = GROUP_META[g];
			const isLast = g === "extras";
			grpRow += `<th colspan="${m.span}" style="${S.grpTh}background:${m.bg};${isLast ? S.cornerLast : ""}">${m.label}</th>`;
		});
		grpRow += "</tr>";

		// ── row 2: column labels ────────────────────────────────────
		let colRow = "<tr>";
		PERM_COLS.forEach((c, i) => {
			const isFirst = i === 0 || PERM_COLS[i-1].group !== c.group;
			colRow += `<th style="${S.colTh}${isFirst ? S.colThSep : ""}">${c.label}</th>`;
		});
		colRow += "</tr>";

		// ── body ────────────────────────────────────────────────────
		let body = "";
		matrix.forEach(group => {
			const cnt = group.items.length;

			// Section runs are contiguous within a group (backend sorts items by section),
			// so a single forward pass can compute each run's start index and length for
			// the rowspan'd Section badge below (nested inside the Module badge, which
			// rowspans the whole group).
			const sectionRunLen = new Array(cnt);
			for (let i = 0; i < cnt; ) {
				let j = i + 1;
				while (j < cnt && group.items[j].section === group.items[i].section) j++;
				sectionRunLen[i] = j - i;
				for (let k = i + 1; k < j; k++) sectionRunLen[k] = 0;
				i = j;
			}

			group.items.forEach((item, idx) => {
				const perms = lookup[item.doctype] || rolePerms[item.doctype] || {};
				const rowS  = idx % 2 === 0 ? S.even : S.odd;
				const isGroupStart = idx === 0;
				const isSectionStart = sectionRunLen[idx] > 0;
				const rowStyle = `${rowS}${isGroupStart ? S.groupRow : ""}`;

				let modTd = "";
				if (isGroupStart) {
					modTd = `<td rowspan="${cnt}" style="${S.modCell}${S.groupTop}"><div style="${S.modInner}">${moduleBadge(group.module)}</div></td>`;
				}

				let secTd = "";
				if (isSectionStart) {
					secTd = `<td rowspan="${sectionRunLen[idx]}" style="${S.secCell}${isGroupStart ? S.groupTop : ""}"><div style="${S.secInner}">${sectionBadge(item.section)}</div></td>`;
				}

				let chkTds = "";
				PERM_COLS.forEach((c, i) => {
					const isFirst  = i === 0 || PERM_COLS[i-1].group !== c.group;
					const checked  = isAdmin || perms[c.key] ? "checked" : "";
					const disabled = isAdmin ? "disabled" : "";
					chkTds += `<td style="${S.chkCell}${isFirst ? S.chkSep : ""}${rowS}${isGroupStart ? S.groupTop : ""}">
						<input type="checkbox" class="tms-perm-cb" data-perm="${c.key}" ${checked} ${disabled}
						       style="width:15px;height:15px;cursor:pointer;accent-color:#4338CA;display:block;margin:0 auto;">
					</td>`;
				});

				body += `<tr style="${rowStyle}" data-doctype="${frappe.utils.escape_html(item.doctype)}" data-module="${frappe.utils.escape_html(group.module)}" data-section="${frappe.utils.escape_html(item.section)}">
					${modTd}
					${secTd}
					<td style="${S.nameCell}${rowS}${isGroupStart ? S.groupTop : ""}">
						<a href="#" class="cloudverce-field-perm-link" data-doctype="${frappe.utils.escape_html(item.doctype)}"
						   title="${__("Manage field-level Hidden / Read Only permissions")}"
						   style="color:#4338CA;font-weight:600;text-decoration:underline;cursor:pointer;">${frappe.utils.escape_html(item.display)}</a>
					</td>
					${chkTds}
				</tr>`;
			});
		});

		const html = `<div style="${S.wrap}">
			<table style="${S.table}">
				<thead>${grpRow}${colRow}</thead>
				<tbody>${body}</tbody>
			</table>
		</div>`;

		const wrapper = frm.get_field("permissions_html").$wrapper;
		wrapper.html(html);

		wrapper.off("change.tms_perm").on("change.tms_perm", ".tms-perm-cb", function() {
			frm.events.on_checkbox_change(frm, $(this));
		});
		wrapper.off("click.cloudverce_field_perm").on("click.cloudverce_field_perm", ".cloudverce-field-perm-link", function(e) {
			e.preventDefault();
			frm.events.show_field_permission_dialog(frm, $(this).data("doctype"));
		});
		const navWrapper = frm.get_field("navigation_visibility_html").$wrapper;
		navWrapper.html(frm.events.render_navigation_matrix(frm, navMatrix, navConfig));
		navWrapper.off("change.tms_nav").on("change.tms_nav", ".tms-nav-visible-cb", function() {
			frm.events.on_nav_checkbox_change(frm, $(this));
		});
	},

	get_navigation_config(frm) {
		try {
			// CAPA FIX: frappe.parse_json does not exist -- frappe.utils.parse_json is correct.
			const config = frappe.utils.parse_json(frm.doc.navigation_visibility_json) || {};
			const hiddenLabels = config.hidden_labels || config.hidden || [];
			const hidden = new Set();
			(hiddenLabels || []).forEach((label) => {
				if (label) hidden.add(String(label).trim());
			});
			return hidden;
		} catch (e) {
			return new Set();
		}
	},

	set_navigation_config(frm, hiddenLabels) {
		const deduped = [];
		const seen = new Set();
		(hiddenLabels || []).forEach((label) => {
			label = (label || "").trim();
			if (label && !seen.has(label)) {
				seen.add(label);
				deduped.push(label);
			}
		});
		const value = JSON.stringify({ hidden_labels: deduped });
		// Set directly on frm.doc so get_navigation_config and sync_navigation_visibility_from_dom
		// both read the correct value immediately. We intentionally avoid frappe.model.set_value
		// here because it can trigger extra refresh churn on this HTML-heavy form.
		frm.doc.navigation_visibility_json = value;
		frm._tms_nav_visibility_json = value;
	},

	render_navigation_matrix(frm, matrix, hiddenLabels) {
		if (!matrix || matrix.length === 0) return "";

		// is_admin group → every nav item is always visible and the toggles are locked
		// (disabled), mirroring the permission matrix's is_admin behavior. Nobody can hide
		// anything from an admin group via the UI.
		const isAdmin = !!frm.doc.is_admin;

		// SECTION_COLORS is now defined once at module scope (shared with the permission
		// matrix's Section column) so the same section name gets the same color everywhere.

		const onBg  = "#4F46E5";
		const offBg = "#D1D5DB";

		function makeToggle(safeLabel, visible) {
			const title = isAdmin
				? "Admin group — always visible, cannot be changed"
				: (visible ? "Visible — click to hide" : "Hidden — click to show");
			return `<label style="${NAV.toggle}${isAdmin ? "opacity:.55;cursor:not-allowed;" : ""}" title="${title}">
				<input type="checkbox" class="tms-nav-visible-cb"
				       data-nav-label="${safeLabel}"
				       ${visible ? "checked" : ""}
				       ${isAdmin ? "disabled" : ""}
				       style="${NAV.toggleInput}"
				       onchange="
				           const sl = this.nextElementSibling;
				           sl.style.background = this.checked ? '${onBg}' : '${offBg}';
				           sl.querySelector('span').style.transform = this.checked ? 'translateX(16px)' : 'translateX(2px)';
				       ">
				<span style="${NAV.toggleSlider}background:${visible ? onBg : offBg};">
					<span style="position:absolute;top:3px;width:16px;height:16px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.2);transition:.2s;transform:${visible ? "translateX(16px)" : "translateX(2px)"};display:block;"></span>
				</span>
			</label>`;
		}

		// Build one column per section
		let colHeaders = "";
		let colItems   = "";

		matrix.forEach((group, gIdx) => {
			const clr = SECTION_COLORS[gIdx % SECTION_COLORS.length];
			const sectionName = frappe.utils.escape_html(group.module);

			// Header cell
			colHeaders += `<th style="padding:0 8px 10px;vertical-align:bottom;white-space:nowrap;border:none;background:transparent;">
				<span style="display:inline-flex;align-items:center;gap:5px;padding:5px 12px;border-radius:999px;
				             background:${clr.bg};border:1.5px solid ${clr.border};color:${clr.text};
				             font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.07em;">
					<span style="width:7px;height:7px;border-radius:50%;background:${clr.dot};flex-shrink:0;"></span>
					${sectionName}
				</span>
			</th>`;

			// Find max rows across all sections for proper row alignment
			const items = group.items || [];
			colItems += `<td style="padding:0 8px;vertical-align:top;border:none;background:transparent;">
				<div style="display:flex;flex-direction:column;gap:6px;">`;

			items.forEach((item) => {
				const label     = item.label || item.display || item.link_to || item.url;
				const display   = frappe.utils.escape_html(item.display || label);
				const safeLabel = frappe.utils.escape_html(label);
				const visible   = isAdmin || !hiddenLabels.has(label);

				colItems += `
				<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;
				            background:#fff;border:1.5px solid #E0E7FF;border-radius:8px;
				            padding:7px 10px;min-width:140px;
				            transition:border-color .15s,box-shadow .15s;"
				     onmouseover="this.style.borderColor='${clr.border}';this.style.boxShadow='0 2px 8px rgba(0,0,0,.07)'"
				     onmouseout="this.style.borderColor='#E0E7FF';this.style.boxShadow='none'">
					<span style="font-size:12px;color:#1E1B4B;font-weight:500;
					             white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:120px;"
					      title="${safeLabel}">${display}</span>
					${makeToggle(safeLabel, visible)}
				</div>`;
			});

			colItems += `</div></td>`;
		});

		return `<div style="${NAV.wrap}">
			<div style="${NAV.title}">Dashboard &amp; Page Permissions</div>
			<div style="${NAV.subtitle}">Toggle items to show or hide them from the desk sidebar for this group.</div>
			<div style="overflow-x:auto;">
				<table style="border-collapse:separate;border-spacing:0;width:100%;background:transparent;">
					<thead>
						<tr>${colHeaders}</tr>
					</thead>
					<tbody>
						<tr style="vertical-align:top;">${colItems}</tr>
					</tbody>
				</table>
			</div>
		</div>`;
	},

	on_nav_checkbox_change(frm, $cb) {
		// Admin group toggles are disabled in the UI; guard here too so a programmatic/
		// DOM-forced change can never hide anything from an admin group.
		if (frm.doc.is_admin) return;

		const label = ($cb.data("nav-label") || "").toString().trim();
		if (!label) return;

		const currentHidden = Array.from(frm.events.get_navigation_config(frm));
		const nextHidden = currentHidden.filter((item) => item !== label);
		if (!$cb.is(":checked")) {
			nextHidden.push(label);
		}

		frm.events.set_navigation_config(frm, nextHidden);
		frm.dirty();

		// CAPA FIX: persist this toggle immediately, independent of the Save button /
		// before_save pipeline. A toggle must never be silently reverted by an unrelated
		// save-cycle race, so this field is no longer batched into the normal doc save.
		if (!frm.is_new()) {
			frappe.call({
				method: "cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group.set_navigation_visibility",
				args: { name: frm.doc.name, hidden_labels: JSON.stringify(nextHidden) },
				callback: (r) => {
					if (r.message) {
						frm.doc.navigation_visibility_json = r.message.navigation_visibility_json;
						frm._tms_nav_visibility_json = r.message.navigation_visibility_json;
						// This direct DB write bumps the server-side `modified` timestamp behind
						// the form's back. Sync frm.doc.modified too, otherwise the next click on
						// the Save button raises a false "modified after you opened it" conflict.
						if (r.message.modified) {
							frm.doc.modified = r.message.modified;
						}
					}
				},
			});
		}
	},

	sync_navigation_visibility_from_dom(frm) {
		const navWrapper = frm.get_field("navigation_visibility_html")?.$wrapper;
		if (!navWrapper || !navWrapper.length) return;

		const hiddenLabels = [];
		navWrapper.find(".tms-nav-visible-cb").each(function () {
			const $cb = $(this);
			if (!$cb.is(":checked")) {
				const label = ($cb.data("nav-label") || "").toString().trim();
				if (label) hiddenLabels.push(label);
			}
		});

		const deduped = [];
		const seen = new Set();
		hiddenLabels.forEach((label) => {
			if (!seen.has(label)) {
				seen.add(label);
				deduped.push(label);
			}
		});

		const value = JSON.stringify({ hidden_labels: deduped });
		frm.doc.navigation_visibility_json = value;
		if (frm.fields_dict?.navigation_visibility_json?.df) {
			frm.fields_dict.navigation_visibility_json.df.default = value;
		}
	},

	normalize_permission_rows(frm) {
		const moduleMap = frm._tms_doc_module_map || {};
		const cleanedRows = [];

		(frm.doc.permissions || []).forEach((row) => {
			const documentType = (row.document_type || "").trim();
			if (!documentType) {
				return;
			}

			const module = (row.module || moduleMap[documentType] || "").trim();
			if (!module) {
				return;
			}

			row.document_type = documentType;
			row.module = module;
			cleanedRows.push(row);
		});

		if (cleanedRows.length !== (frm.doc.permissions || []).length) {
			frm.doc.permissions = cleanedRows;
			frm.refresh_field("permissions");
		}
	},

	on_checkbox_change(frm, $cb) {
		const $row    = $cb.closest("tr[data-doctype]");
		const doctype = $row.data("doctype");
		const module  = $row.data("module");
		const changedPerm = $cb.data("perm");
		const isChecked   = $cb.is(":checked");

		// Cascade rules:
		// - Uncheck READ → uncheck SELECT + everything else (READ is required for any other perm)
		// - Uncheck SELECT → uncheck READ and everything else
		// - Check SELECT/WRITE/CREATE/DELETE/SUBMIT/CANCEL/AMEND/PRINT/EMAIL/REPORT/IMPORT/EXPORT → auto-check READ
		// - Check READ → auto-check SELECT (SELECT is needed for the doctype to appear in link fields)
		const READ_DEPS = ["perm_select","perm_write","perm_create","perm_delete","perm_submit","perm_cancel","perm_amend","perm_print","perm_email","perm_report","perm_import","perm_export"];

		if (!isChecked && changedPerm === "perm_read") {
			// Uncheck read → clear everything (including select)
			READ_DEPS.forEach(k => $row.find(`input[data-perm="${k}"]`).prop("checked", false));
		} else if (!isChecked && changedPerm === "perm_select") {
			// Uncheck select → clear read and everything
			$row.find(`input[data-perm="perm_read"]`).prop("checked", false);
			READ_DEPS.forEach(k => $row.find(`input[data-perm="${k}"]`).prop("checked", false));
		} else if (isChecked && READ_DEPS.includes(changedPerm)) {
			// Check any dep (including select) → auto-check read
			$row.find(`input[data-perm="perm_read"]`).prop("checked", true);
		} else if (isChecked && changedPerm === "perm_read") {
			// Check read → auto-check select (they go together)
			$row.find(`input[data-perm="perm_select"]`).prop("checked", true);
		}

		// Collect all 15 checkbox states from the DOM after cascade
		const state = {};
		PERM_COLS.forEach(c => {
			state[c.key] = $row.find(`input[data-perm="${c.key}"]`).is(":checked") ? 1 : 0;
		});

		const existingRow = (frm.doc.permissions || []).find(r => r.document_type === doctype);

		if (existingRow) {
			// Update every bit on the existing child row
			if (module && existingRow.module !== module) {
				frappe.model.set_value(existingRow.doctype, existingRow.name, "module", module);
			}
			if (doctype && existingRow.document_type !== doctype) {
				frappe.model.set_value(existingRow.doctype, existingRow.name, "document_type", doctype);
			}
			Object.keys(state).forEach(fieldname => {
				frappe.model.set_value(existingRow.doctype, existingRow.name, fieldname, state[fieldname]);
			});
		} else {
			// No child row yet — create one even if all zeros.
			// An all-zero child row is needed to explicitly override file-based DocPerm
			// permissions (tabDocPerm) so unchecking actually takes effect on Save.
			frm.add_child("permissions", {
				module:        module,
				document_type: doctype,
				display_name:  $row.find("td:nth-child(2)").text().trim(),
				...state,
			});
		}

		frm.dirty();
	},
});
