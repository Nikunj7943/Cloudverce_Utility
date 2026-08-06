(function () {
	"use strict";

	// Color thresholds — recalculated dynamically in startWidget()
	var WARNING_THRESHOLD = 300;   // green→orange  (default for long sessions)
	var MODAL_AT          = 30;    // orange→red + modal  (default for long sessions)
	var AUDIO_SRC         = "https://freesound.org/data/previews/202/202029_2605156-lq.mp3";
	var WIDGET_POS_KEY    = "tms_session_widget_pos";

	var initialized       = false;
	var expirySeconds     = 0;
	var lastActivity      = Date.now();
	var timerInterval     = null;
	var syncInterval      = null;
	var expired           = false;
	var modalShown        = false;
	var userHasInteracted = false;
	var audioEl           = null;

	// Fix 1 — BroadcastChannel for cross-tab session sync
	var bc            = typeof BroadcastChannel !== "undefined"
	                      ? new BroadcastChannel("tms_session")
	                      : null;
	var lastBroadcast = 0; // ms timestamp — throttle activity broadcasts

	// ── Autoplay Policy: track first user gesture ─────────────────────────────

	function onFirstInteraction() {
		if (userHasInteracted) return;
		userHasInteracted = true;
		// Pre-load audio silently on first interaction so it's ready at 30s
		if (!audioEl) {
			audioEl = new Audio(AUDIO_SRC);
			audioEl.preload = "auto";
			audioEl.volume  = 0.8;
			audioEl.load();
		}
		["mousemove", "keydown", "click", "touchstart"].forEach(function (e) {
			document.removeEventListener(e, onFirstInteraction);
		});
	}

	["mousemove", "keydown", "click", "touchstart"].forEach(function (e) {
		document.addEventListener(e, onFirstInteraction, { passive: true, once: true });
	});

	// ── CSS ───────────────────────────────────────────────────────────────────

	function injectCSS() {
		if (document.getElementById("tms-session-style")) return;
		var s = document.createElement("style");
		s.id  = "tms-session-style";
		s.textContent = [
			/* ── Widget ── */
			"#tms-session-timer{",
			"  position:fixed;bottom:16px;left:16px;z-index:99998;",
			"  background:#fff;border-radius:10px;padding:10px 14px;",
			"  box-shadow:0 4px 16px rgba(0,0,0,.14);",
			"  display:flex;flex-direction:column;align-items:center;gap:4px;",
			"  font-family:inherit;min-width:148px;border:2px solid #12b76a;",
			"  transition:border-color .4s;",
			"  cursor:grab;user-select:none;",
			"}",
			"#tms-session-timer:active{cursor:grabbing;}",
			"#tms-session-timer .tms-t-label{font-size:10px;color:#667085;font-weight:500;letter-spacing:.5px;text-transform:uppercase;}",
			"#tms-session-timer .tms-t-count{font-size:22px;font-weight:700;color:#101828;letter-spacing:1px;line-height:1;}",
			"#tms-session-timer.tms-green {border-color:#12b76a;}",
			"#tms-session-timer.tms-orange{border-color:#f79009;animation:tms-pulse 1s ease-in-out infinite;}",
			"#tms-session-timer.tms-red   {border-color:#f04438;animation:tms-pulse .4s ease-in-out infinite;}",
			"@keyframes tms-pulse{",
			"  0%,100%{box-shadow:0 4px 16px rgba(0,0,0,.14);}",
			"  50%    {box-shadow:0 4px 24px rgba(240,68,56,.40);}",
			"}",
			/* ── Modal backdrop ── */
			"#tms-modal-backdrop{",
			"  position:fixed;inset:0;z-index:999999;",
			"  background:rgba(16,24,40,.55);",
			"  backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);",
			"  display:flex;align-items:center;justify-content:center;",
			"  opacity:0;transition:opacity .25s;",
			"}",
			"#tms-modal-backdrop.tms-visible{opacity:1;}",
			/* ── Modal card ── */
			"#tms-modal-card{",
			"  background:#fff;border-radius:16px;",
			"  padding:32px 28px 24px;",
			"  width:min(420px,92vw);",
			"  box-shadow:0 20px 60px rgba(16,24,40,.22);",
			"  text-align:center;",
			"  transform:translateY(18px) scale(.97);",
			"  transition:transform .25s;",
			"}",
			"#tms-modal-backdrop.tms-visible #tms-modal-card{transform:translateY(0) scale(1);}",
			/* ── Modal icon ── */
			"#tms-modal-icon{",
			"  width:56px;height:56px;border-radius:50%;",
			"  background:#fff3cd;border:8px solid #fef9c3;",
			"  display:inline-flex;align-items:center;justify-content:center;",
			"  margin-bottom:16px;",
			"  font-size:26px;line-height:1;",
			"}",
			/* ── Modal text ── */
			"#tms-modal-title{font-size:18px;font-weight:700;color:#101828;margin:0 0 6px;}",
			"#tms-modal-desc {font-size:14px;color:#475467;margin:0 0 6px;line-height:1.5;}",
			"#tms-modal-secs {",
			"  font-size:42px;font-weight:800;color:#f04438;",
			"  letter-spacing:2px;line-height:1;margin:12px 0 4px;",
			"  font-variant-numeric:tabular-nums;",
			"}",
			"#tms-modal-unit {font-size:12px;color:#667085;margin-bottom:24px;}",
			/* ── Modal buttons ── */
			"#tms-modal-actions{display:flex;gap:12px;justify-content:center;}",
			".tms-btn{",
			"  flex:1;max-width:160px;padding:10px 16px;",
			"  font-size:14px;font-weight:600;border-radius:8px;",
			"  cursor:pointer;border:none;transition:all .18s;",
			"}",
			".tms-btn-primary{background:#1570ef;color:#fff;}",
			".tms-btn-primary:hover{background:#175cd3;}",
			".tms-btn-danger {background:#fff;color:#b42318;border:1px solid #fda29b;}",
			".tms-btn-danger:hover {background:#fff5f5;}",
		].join("\n");
		document.head.appendChild(s);
	}

	// ── Snap positions (6 fixed anchors) ─────────────────────────────────────

	function makeDraggable(el) {
		var dragging = false;
		var ox = 0, oy = 0;
		var M = 16; // margin from screen edges

		function snapPoints() {
			var W  = window.innerWidth;
			var H  = window.innerHeight;
			var ew = el.offsetWidth;
			var eh = el.offsetHeight;
			return [
				{ name: "top-left",    left: M,            top: M },
				{ name: "top-center",  left: (W - ew) / 2, top: M },
				{ name: "top-right",   left: W - ew - M,   top: M },
				{ name: "bot-left",    left: M,            top: H - eh - M },
				{ name: "bot-center",  left: (W - ew) / 2, top: H - eh - M },
				{ name: "bot-right",   left: W - ew - M,   top: H - eh - M },
			];
		}

		function applyPos(left, top) {
			el.style.left   = left + "px";
			el.style.top    = top  + "px";
			el.style.right  = "auto";
			el.style.bottom = "auto";
		}

		function snapToNearest() {
			var r   = el.getBoundingClientRect();
			var cx  = r.left + r.width  / 2;
			var cy  = r.top  + r.height / 2;
			var pts = snapPoints();
			var best = pts[0];
			var minD = Infinity;
			pts.forEach(function (p) {
				var d = Math.hypot(
					cx - (p.left + el.offsetWidth  / 2),
					cy - (p.top  + el.offsetHeight / 2)
				);
				if (d < minD) { minD = d; best = p; }
			});
			// Smooth snap animation
			el.style.transition = "left .2s ease, top .2s ease";
			applyPos(best.left, best.top);
			setTimeout(function () { el.style.transition = "border-color .4s"; }, 250);
			// Save by name — stays correct on any screen size
			localStorage.setItem(WIDGET_POS_KEY, JSON.stringify({ name: best.name }));
		}

		function restoreSnap() {
			try {
				var s = localStorage.getItem(WIDGET_POS_KEY);
				var name = s ? JSON.parse(s).name : "bot-left";
				var pts  = snapPoints();
				pts.forEach(function (p) {
					if (p.name === name) applyPos(p.left, p.top);
				});
			} catch (e) {
				// fallback: bot-left
				var pts = snapPoints();
				pts.forEach(function (p) {
					if (p.name === "bot-left") applyPos(p.left, p.top);
				});
			}
		}

		restoreSnap(); // apply saved snap on load

		// ── Mouse ──
		el.addEventListener("mousedown", function (e) {
			if (e.button !== 0) return;
			var r = el.getBoundingClientRect();
			applyPos(r.left, r.top);
			ox = e.clientX - r.left;
			oy = e.clientY - r.top;
			dragging = true;
			el.style.transition = "border-color .4s";
			el.style.cursor = "grabbing";
			e.preventDefault();
		});

		document.addEventListener("mousemove", function (e) {
			if (!dragging) return;
			applyPos(e.clientX - ox, e.clientY - oy);
		});

		document.addEventListener("mouseup", function () {
			if (!dragging) return;
			dragging = false;
			el.style.cursor = "grab";
			snapToNearest();
		});

		// ── Touch ──
		el.addEventListener("touchstart", function (e) {
			if (e.touches.length !== 1) return;
			var t = e.touches[0];
			var r = el.getBoundingClientRect();
			applyPos(r.left, r.top);
			ox = t.clientX - r.left;
			oy = t.clientY - r.top;
			dragging = true;
			el.style.transition = "border-color .4s";
		}, { passive: true });

		el.addEventListener("touchmove", function (e) {
			if (!dragging || e.touches.length !== 1) return;
			var t = e.touches[0];
			applyPos(t.clientX - ox, t.clientY - oy);
			e.preventDefault();
		}, { passive: false });

		el.addEventListener("touchend", function () {
			if (!dragging) return;
			dragging = false;
			snapToNearest();
		});

		// Re-snap on window resize (e.g. tablet rotation)
		window.addEventListener("resize", function () {
			if (!dragging) snapToNearest();
		});
	}

	// ── Widget DOM ────────────────────────────────────────────────────────────

	function createWidget() {
		if (document.getElementById("tms-session-timer")) return;
		var wrap  = document.createElement("div");
		wrap.id   = "tms-session-timer";
		wrap.className = "tms-green";

		var label = document.createElement("div");
		label.className   = "tms-t-label";
		label.textContent = "Session Time Left";

		var count = document.createElement("div");
		count.className   = "tms-t-count";
		count.id          = "tms-t-count";
		count.textContent = "--:--";

		wrap.appendChild(label);
		wrap.appendChild(count);
		document.body.appendChild(wrap);
		makeDraggable(wrap);
	}

	// ── Modal DOM ─────────────────────────────────────────────────────────────

	function createModal() {
		if (document.getElementById("tms-modal-backdrop")) return;

		var backdrop     = document.createElement("div");
		backdrop.id      = "tms-modal-backdrop";

		var card         = document.createElement("div");
		card.id          = "tms-modal-card";

		var icon         = document.createElement("div");
		icon.id          = "tms-modal-icon";
		icon.textContent = "⏰";

		var title        = document.createElement("h3");
		title.id         = "tms-modal-title";
		title.textContent = "Session Expiring Soon";

		var desc         = document.createElement("p");
		desc.id          = "tms-modal-desc";
		desc.textContent = "Your session will expire in";

		var secs         = document.createElement("div");
		secs.id          = "tms-modal-secs";
		secs.textContent = "30";

		var unit         = document.createElement("div");
		unit.id          = "tms-modal-unit";
		unit.textContent = "seconds";

		var actions      = document.createElement("div");
		actions.id       = "tms-modal-actions";

		var btnStay      = document.createElement("button");
		btnStay.className  = "tms-btn tms-btn-primary";
		btnStay.textContent = "Stay Logged In";
		btnStay.addEventListener("click", stayLoggedIn);

		var btnOut       = document.createElement("button");
		btnOut.className   = "tms-btn tms-btn-danger";
		btnOut.textContent = "Logout";
		btnOut.addEventListener("click", doLogout);

		actions.appendChild(btnStay);
		actions.appendChild(btnOut);

		card.appendChild(icon);
		card.appendChild(title);
		card.appendChild(desc);
		card.appendChild(secs);
		card.appendChild(unit);
		card.appendChild(actions);
		backdrop.appendChild(card);
		document.body.appendChild(backdrop);

		// Show with animation on next frame
		requestAnimationFrame(function () {
			requestAnimationFrame(function () {
				backdrop.classList.add("tms-visible");
			});
		});
	}

	function updateModalSecs(remaining) {
		var el = document.getElementById("tms-modal-secs");
		if (el) el.textContent = Math.max(0, Math.ceil(remaining));
	}

	function destroyModal() {
		var el = document.getElementById("tms-modal-backdrop");
		if (!el) return;
		el.classList.remove("tms-visible");
		setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 280);
	}

	// ── Audio ─────────────────────────────────────────────────────────────────

	function playSound() {
		if (!userHasInteracted) return;
		if (!audioEl) {
			audioEl         = new Audio(AUDIO_SRC);
			audioEl.volume  = 0.8;
		}
		audioEl.currentTime = 0;
		var p = audioEl.play();
		if (p && p.catch) p.catch(function () { /* autoplay blocked */ });
	}

	function stopSound() {
		if (!audioEl) return;
		audioEl.pause();
		audioEl.currentTime = 0;
	}

	// ── Server session expired handler ────────────────────────────────────────

	function handleServerExpiry() {
		if (expired) return;
		expired = true;
		clearInterval(timerInterval);
		clearInterval(syncInterval);
		destroyModal();
		var wrap = document.getElementById("tms-session-timer");
		if (wrap) wrap.style.display = "none";
		playSound(); // Fix 7 — audio alert when server expires the session
		frappe.msgprint({
			title:     __("Session Expired"),
			message:   __("Your session has expired. Please login again."),
			indicator: "red",
		});
		setTimeout(function () {
			stopSound();
			localStorage.removeItem(WIDGET_POS_KEY);
			window.location.href = "/login?reason=timeout";
		}, 2000);
	}

	// ── Safe server ping — suppresses Frappe error popup ─────────────────────

	// Ping server to keep session alive — do NOT reset lastActivity here.
	// lastActivity is updated only by real user interaction (mousemove/keydown/click).
	function pingServer() {
		frappe.call({
			method:   "cloudverce_utility.api.get_session_expiry",
			freeze:   false,
			callback: function (r) {
				if (r && r.message) {
					if (bc) bc.postMessage({ type: "ping_ok", ts: lastActivity });
				}
			},
			error: function () { handleServerExpiry(); },
		});
	}

	// ── Actions ───────────────────────────────────────────────────────────────

	// Fix 4 — fromBroadcast flag prevents re-broadcasting when triggered by another tab
	function stayLoggedIn(fromBroadcast) {
		stopSound();
		destroyModal();
		modalShown   = false;
		lastActivity = Date.now();
		if (bc && !fromBroadcast) bc.postMessage({ type: "stay_logged_in" });
		pingServer();
	}

	// Fix 5 — broadcasts logout so other tabs redirect without calling server logout again
	function doLogout(fromBroadcast) {
		stopSound();
		destroyModal();
		localStorage.removeItem(WIDGET_POS_KEY);
		if (bc && !fromBroadcast) bc.postMessage({ type: "logout" });
		if (fromBroadcast) {
			// Another tab already invalidated the server session — just redirect
			window.location.href = "/login?reason=timeout";
			return;
		}
		frappe.call({
			method:   "logout",
			callback: function () { window.location.href = "/login?reason=timeout"; },
			error:    function () { window.location.href = "/login?reason=timeout"; },
		});
	}

	// ── Formatting ────────────────────────────────────────────────────────────

	function formatTime(secs) {
		secs = Math.max(0, Math.floor(secs));
		var h  = Math.floor(secs / 3600);
		var m  = Math.floor((secs % 3600) / 60);
		var sc = secs % 60;
		var mm = String(m).padStart(2, "0");
		var ss = String(sc).padStart(2, "0");
		return h > 0 ? String(h).padStart(2, "0") + ":" + mm + ":" + ss : mm + ":" + ss;
	}

	// ── Widget state ──────────────────────────────────────────────────────────

	function applyWidgetState(remaining) {
		var wrap  = document.getElementById("tms-session-timer");
		var count = document.getElementById("tms-t-count");
		if (!wrap || !count) return;
		count.textContent = formatTime(remaining);
		if (remaining > WARNING_THRESHOLD) {
			wrap.className = "tms-green";
		} else if (remaining > MODAL_AT) {
			wrap.className = "tms-orange";
		} else {
			wrap.className = "tms-red";
		}
	}

	// ── Tick ──────────────────────────────────────────────────────────────────

	function tick() {
		if (expired) return;
		var remaining = expirySeconds - ((Date.now() - lastActivity) / 1000);

		// Session expired — force logout (Fix 6: use doLogout so broadcast fires)
		if (remaining <= 0) {
			expired = true;
			clearInterval(timerInterval);
			clearInterval(syncInterval);
			var wrap = document.getElementById("tms-session-timer");
			if (wrap) wrap.style.display = "none";
			doLogout(false);
			return;
		}

		applyWidgetState(remaining);

		// Show modal + play sound once at 30 seconds
		if (remaining <= MODAL_AT && !modalShown) {
			modalShown = true;
			playSound();
			createModal();
		}

		// Reset modal if user activity pushed remaining back above 30
		if (remaining > MODAL_AT && modalShown) {
			modalShown = false;
			stopSound();
			destroyModal();
			pingServer(); // immediately reset server session
		}

		// Keep modal countdown in sync
		if (modalShown) updateModalSecs(remaining);
	}

	// ── Route guard ───────────────────────────────────────────────────────────

	function setupRouteGuard() {
		frappe.router.on("change", function () {
			var wrap = document.getElementById("tms-session-timer");
			if (!wrap) return;
			wrap.style.display = window.location.pathname.startsWith("/login") ? "none" : "flex";
		});
	}

	// ── Cross-tab BroadcastChannel handler ───────────────────────────────────

	// Fix 8 — listen for events from other tabs and sync state accordingly
	function setupBroadcast() {
		if (!bc) return;
		bc.onmessage = function (e) {
			var d = e.data;
			if (!d || !d.type) return;
			switch (d.type) {
				case "activity":
				case "ping_ok":
					// Another tab is active / server was pinged — keep our countdown alive too
					if (d.ts && d.ts > lastActivity) lastActivity = d.ts;
					break;
				case "stay_logged_in":
					// Another tab clicked "Stay Logged In" — dismiss our modal and reset timer
					if (!expired) stayLoggedIn(true);
					break;
				case "logout":
					// Another tab logged out on the server — redirect here without calling logout again
					if (!expired) { expired = true; doLogout(true); }
					break;
			}
		};
	}

	// ── Parse hh:mm[:ss] → seconds ───────────────────────────────────────────

	function parseExpiry(str) {
		var p = (str || "").split(":");
		return (parseInt(p[0]) || 0) * 3600 + (parseInt(p[1]) || 0) * 60 + (parseInt(p[2]) || 0);
	}

	// ── Start everything ──────────────────────────────────────────────────────

	function startWidget(seconds) {
		if (!seconds || seconds <= 0) return;
		expirySeconds = seconds;
		lastActivity  = Date.now();

		// Red + modal: ALWAYS last 30 seconds, regardless of session length
		// Orange:      last 1/3 of session, capped at 5 min, must be ≥ 2× MODAL_AT
		MODAL_AT          = 30;
		WARNING_THRESHOLD = Math.max(MODAL_AT * 2, Math.min(300, Math.floor(seconds / 3)));

		// Ping at 1/3 of session expiry, clamped between 30s and 2 min
		// e.g. 10 min session → ping every 3.3 min | 3 min session → ping every 1 min
		var syncMs = Math.max(30000, Math.min(Math.floor(seconds / 3) * 1000, 120000));

		injectCSS();
		createWidget();

		// Fix 3 — broadcast activity to other tabs (throttled: max once per 5s)
		["mousemove", "keydown", "click", "touchstart"].forEach(function (evt) {
			document.addEventListener(evt, function () {
				lastActivity = Date.now();
				if (bc && (lastActivity - lastBroadcast > 5000)) {
					lastBroadcast = lastActivity;
					bc.postMessage({ type: "activity", ts: lastActivity });
				}
			}, { passive: true });
		});

		setupRouteGuard();
		setupBroadcast(); // Fix 8 — start listening for cross-tab messages
		timerInterval = setInterval(tick, 1000);
		syncInterval  = setInterval(pingServer, syncMs);
	}

	// ── Init ──────────────────────────────────────────────────────────────────

	function init() {
		if (initialized) return;
		if (typeof frappe === "undefined") return;
		if (!frappe.session || !frappe.session.user) return;
		if (frappe.session.user === "Guest") return;
		if (window.location.pathname.startsWith("/login")) return;
		if (frappe.boot && frappe.boot.cloudverce_enable_session_timer === 0) return;
		if (document.getElementById("tms-session-timer")) return;

		initialized = true;

		// Layer 1: frappe.boot.sysdefaults (no API call)
		var bootExpiry = (
			frappe.boot &&
			frappe.boot.sysdefaults &&
			frappe.boot.sysdefaults.session_expiry
		) ? parseExpiry(frappe.boot.sysdefaults.session_expiry) : 0;

		if (bootExpiry > 0) { startWidget(bootExpiry); return; }

		// Layer 2: dedicated API fallback
		frappe.call({
			method:   "cloudverce_utility.api.get_session_expiry",
			freeze:   false,
			callback: function (r) {
				if (r && r.message && r.message.expiry_seconds) {
					startWidget(r.message.expiry_seconds);
				}
			},
		});
	}

	// ── Triggers ─────────────────────────────────────────────────────────────

	$(document).on("app_ready", init);
	$(document).on("page-change", init);
	setTimeout(init, 2500);

})();
