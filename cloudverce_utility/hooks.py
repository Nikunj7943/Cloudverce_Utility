app_name = "cloudverce_utility"
app_title = "Cloudverce Utility"
app_publisher = "Nikunj Parmar"
app_description = "Cloudverce Utility"
app_email = "nikunj7943@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "cloudverce_utility",
# 		"logo": "/assets/cloudverce_utility/logo.png",
# 		"title": "Cloudverce Utility",
# 		"route": "/cloudverce_utility",
# 		"has_permission": "cloudverce_utility.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/cloudverce_utility/css/cloudverce_utility.css"
# app_include_js = "/assets/cloudverce_utility/js/cloudverce_utility.js"

# include js, css files in header of web template
# web_include_css = "/assets/cloudverce_utility/css/cloudverce_utility.css"
# web_include_js = "/assets/cloudverce_utility/js/cloudverce_utility.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "cloudverce_utility/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "cloudverce_utility/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "cloudverce_utility.utils.jinja_methods",
# 	"filters": "cloudverce_utility.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "cloudverce_utility.install.before_install"
# after_install = "cloudverce_utility.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "cloudverce_utility.uninstall.before_uninstall"
# after_uninstall = "cloudverce_utility.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "cloudverce_utility.utils.before_app_install"
# after_app_install = "cloudverce_utility.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "cloudverce_utility.utils.before_app_uninstall"
# after_app_uninstall = "cloudverce_utility.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "cloudverce_utility.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "cloudverce_utility.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"cloudverce_utility.tasks.all"
# 	],
# 	"daily": [
# 		"cloudverce_utility.tasks.daily"
# 	],
# 	"hourly": [
# 		"cloudverce_utility.tasks.hourly"
# 	],
# 	"weekly": [
# 		"cloudverce_utility.tasks.weekly"
# 	],
# 	"monthly": [
# 		"cloudverce_utility.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "cloudverce_utility.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "cloudverce_utility.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "cloudverce_utility.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "cloudverce_utility.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["cloudverce_utility.utils.before_request"]
# after_request = ["cloudverce_utility.utils.after_request"]

# Job Events
# ----------
# before_job = ["cloudverce_utility.utils.before_job"]
# after_job = ["cloudverce_utility.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"cloudverce_utility.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []


# ══════════════════════════════════════════════════════════════════════════════
#  Cloudverce Utility — RBAC (Cloudverce User Group) + navigation visibility + session timer
# ══════════════════════════════════════════════════════════════════════════════

app_include_js = [
	"/assets/cloudverce_utility/js/session_timer.js",
	"/assets/cloudverce_utility/js/navigation_visibility.js",
	"/assets/cloudverce_utility/js/list_settings.js",
]

boot_session = [
	"cloudverce_utility.access_control.add_bootinfo",
	"cloudverce_utility.navigation_visibility.add_navigation_visibility_bootinfo",
]

doc_events = {
	"User": {
		"on_update": "cloudverce_utility.access_control.on_user_update_clear_bootinfo",
	},
	"Role": {
		"on_update": "cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group.sync_role_disabled_to_user_group",
	},
	"Custom DocPerm": {
		"on_update": "cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group.sync_custom_docperm_to_user_group",
		"on_trash": "cloudverce_utility.cloudverce_utility.doctype.cloudverce_user_group.cloudverce_user_group.sync_custom_docperm_to_user_group",
	},
}

# Row-level "own record only" restriction for non-admin groups on User and on the
# Cloudverce User Group doctype itself (which action columns are allowed at all is
# controlled separately by BASELINE_RESTRICTED_FOR_NON_ADMIN in cloudverce_user_group.py).
permission_query_conditions = {
	"User": "cloudverce_utility.navigation_visibility.get_permission_query_conditions_user",
	"Cloudverce User Group": "cloudverce_utility.navigation_visibility.get_permission_query_conditions_cloudverce_user_group",
}

# Block direct access to hidden Pages/Reports/Dashboards per group.
has_permission = {
	"Page": "cloudverce_utility.navigation_visibility.has_permission_page",
	"Dashboard": "cloudverce_utility.navigation_visibility.has_permission_dashboard",
	"Report": "cloudverce_utility.navigation_visibility.has_permission_report",
	"User": "cloudverce_utility.navigation_visibility.has_permission_user",
	"Cloudverce User Group": "cloudverce_utility.navigation_visibility.has_permission_cloudverce_user_group",
}

# Dashboard view loads charts/cards without checking Dashboard-level permission —
# these overrides add the missing check.
override_whitelisted_methods = {
	"frappe.desk.doctype.dashboard.dashboard.get_permitted_charts": "cloudverce_utility.navigation_visibility.get_permitted_charts",
	"frappe.desk.doctype.dashboard.dashboard.get_permitted_cards": "cloudverce_utility.navigation_visibility.get_permitted_cards",
}

fixtures = [
	{"dt": "Server Script", "filters": [["module", "=", "Cloudverce Utility"]]},
]

after_install = "cloudverce_utility.install.after_install"
after_migrate = "cloudverce_utility.install.after_migrate"

