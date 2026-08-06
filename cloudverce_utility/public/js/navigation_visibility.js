(function () {
	function getHiddenLabels() {
		return frappe.boot?.cloudverce_navigation_visibility?.hidden_labels || [];
	}

	// Map sidebar label → route patterns to block (url-type items have no link_to)
	// We match by page title or route segment
	function getBlockedRoutes(hidden) {
		const routes = new Set();
		hidden.forEach(label => {
			// Convert label to likely route: "Alert Center" → "alert-center"
			const slug = label.trim().toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");
			routes.add(slug);
			// Also store original label for dashboard/report name matching
			routes.add(label.trim());
		});
		return routes;
	}

	function isRouteBlocked(route, hidden, blockedRoutes) {
		if (!hidden.size) return false;
		// route like "alert-center", "fleet-dashboard", "salary-advance-report"
		const routeLower = (route || "").toLowerCase();
		// Check slug match
		for (const label of hidden) {
			const slug = label.trim().toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");
			if (routeLower === slug) return true;
		}
		return false;
	}

	function checkAndBlockCurrentRoute() {
		const hidden = new Set(getHiddenLabels().map(l => (l || "").trim()).filter(Boolean));
		if (!hidden.size) return;

		const route = frappe.get_route();
		if (!route || !route.length) return;

		const routeType = route[0];

		if (isRouteBlocked(routeType, hidden)) {
			frappe.show_alert({
				message: __("You do not have permission to access this page."),
				indicator: "red"
			}, 5);
			frappe.set_route("");
		}
	}

	// Block direct URL access via server-side check on page load
	function serverSideRouteCheck() {
		const route = frappe.get_route();
		if (!route || !route.length) return;
		const routeType = route[0];
		if (!routeType) return;

		frappe.call({
			method: "cloudverce_utility.navigation_visibility.check_route_access",
			args: { route: routeType },
			callback: function(r) {
				if (r.message && r.message.blocked) {
					frappe.show_alert({
						message: __("You do not have permission to access this page."),
						indicator: "red"
					}, 5);
					frappe.set_route("");
				}
			}
		});
	}

	function applyNavigationVisibility() {
		const hidden = new Set(getHiddenLabels().map((label) => (label || "").trim()).filter(Boolean));
		if (!hidden.size) return;

		const $sidebar = $(".body-sidebar");
		if (!$sidebar.length) return;

		$sidebar.find(".sidebar-item-container").each(function () {
			const $item = $(this);
			const label = ($item.attr("item-name") || "").trim();
			if (label && hidden.has(label)) {
				$item.addClass("tms-nav-hidden").hide();
			}
		});

		$sidebar.find(".section-item").each(function () {
			const $section = $(this);
			const hasVisibleChild = $section.find(".nested-container .sidebar-item-container:visible").length > 0;
			if (!hasVisibleChild) {
				$section.addClass("tms-nav-hidden").hide();
			}
		});
	}

	$(document).on("sidebar_setup page-change", function () {
		window.setTimeout(applyNavigationVisibility, 0);
		window.setTimeout(checkAndBlockCurrentRoute, 50);
		window.setTimeout(serverSideRouteCheck, 100);
	});

	$(function () {
		window.setTimeout(applyNavigationVisibility, 0);
		window.setTimeout(checkAndBlockCurrentRoute, 100);
		window.setTimeout(serverSideRouteCheck, 200);
	});

	// ── Access-denied dialog + redirect ─────────────────────────────────────
	//
	// CAPA FIX: direct-URL access to a hidden Dashboard/Report/Page is now blocked
	// server-side (Page.roles / Report.roles / Dashboard permission override -- see
	// cloudverce_user_group.py and cloudverce_navigation_visibility.py). That raises a PermissionError
	// with a message like "You don't have access to Dashboard: Fleet Dashboard.". This
	// intercepts exactly those TMS messages and shows a clear dialog; dismissing it
	// (any way -- OK button, X, clicking outside) sends the user back to Home instead of
	// leaving them stuck on a half-loaded/broken page.

	const HOME_URL = "/app";

	// Two different Frappe code paths can raise the block, each with its own wording:
	//  1. Report/Page's own is_permitted() (Report.roles / Page.roles) -> custom message
	//     ("You don't have access to Report: X.", "No read permission for Page X").
	//  2. The standard doc.check_permission() chain (which our has_permission_* hooks
	//     also feed into) -> Frappe's generic message ("You need the 'read' permission
	//     on Report X to perform this action."). This is the one actually seen in
	//     practice for direct-URL access, since the report/page view loads the
	//     Report/Page document itself before ever reaching is_permitted().
	// Both patterns are matched and normalized to one friendly message below.
	const PATTERNS = [
		{ re: /You don't have access to (Dashboard|Report):\s*([^.]+)\.?/i, type: 1, name: 2 },
		{ re: /No read permission for Page\s+(.+)/i, type: null, name: 1 },
		{ re: /You need the '[\w ]+' permission on (Dashboard|Report|Page)\s+(.+?)\s+to perform this action/i, type: 1, name: 2 },
	];

	function extractMessageText(raw) {
		if (typeof raw !== "string") return raw;
		try {
			const parsed = JSON.parse(raw);
			return parsed && parsed.message ? parsed.message : raw;
		} catch (e) {
			return raw;
		}
	}

	function matchTmsAccessDenied(text) {
		text = (text || "").toString();
		for (const p of PATTERNS) {
			const m = text.match(p.re);
			if (m) {
				const type = p.type ? m[p.type] : "Page";
				const name = (m[p.name] || "").trim();
				return { type, name };
			}
		}
		return null;
	}

	let accessDeniedShown = false;
	$(document).on("page-change", function () {
		accessDeniedShown = false;
	});

	function showAccessDeniedDialog(type, name) {
		if (accessDeniedShown) return;
		accessDeniedShown = true;

		const message = __(
			"You don't have permission to access this {0}: {1}. Please contact your System Administrator.",
			[type, name]
		);

		const dialog = new frappe.ui.Dialog({
			title: __("Access Denied"),
			indicator: "red",
			primary_action_label: __("OK"),
			primary_action() {
				dialog.hide();
			},
		});
		dialog.$body.html(`<p style="font-size:14px;">${frappe.utils.escape_html(message)}</p>`);
		dialog.onhide = function () {
			window.location.href = HOME_URL;
		};
		dialog.show();
	}

	frappe.provide("frappe.request.error_handlers");
	frappe.request.error_handlers["PermissionError"] = frappe.request.error_handlers["PermissionError"] || [];
	frappe.request.error_handlers["PermissionError"].push(function (r) {
		let raw = [];
		try {
			raw = r._server_messages ? JSON.parse(r._server_messages) : (r.messages || []);
		} catch (e) {
			raw = [];
		}
		if (!Array.isArray(raw)) raw = [raw];

		let matched = null;
		for (const m of raw) {
			const text = extractMessageText(m);
			matched = matchTmsAccessDenied(text);
			if (matched) break;
		}

		if (!matched) {
			// Not one of ours -- restore Frappe's default message rendering.
			frappe.hide_msgprint();
			frappe.msgprint(raw);
			return;
		}

		showAccessDeniedDialog(matched.type, matched.name);
	});

	// Defense-in-depth: some page-load error paths (e.g. the initial Report/Page
	// document fetch that happens before a view is even constructed) may not always
	// route through frappe.request.cleanup's error_handlers above. As a fallback, watch
	// for ANY dialog Frappe shows and inspect its own rendered text -- this works
	// regardless of which internal code path produced the error.
	$(document).on("shown.bs.modal", ".modal", function () {
		const $modal = $(this);
		if ($modal.data("tms-access-checked")) return;
		$modal.data("tms-access-checked", true);

		const bodyText = $modal.find(".modal-body").text();
		const matched = matchTmsAccessDenied(bodyText);
		if (!matched) return;

		// Close Frappe's own dialog immediately and show ours instead.
		$modal.modal("hide");
		showAccessDeniedDialog(matched.type, matched.name);
	});
})();
