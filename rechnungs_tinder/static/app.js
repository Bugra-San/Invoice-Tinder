"use strict";

/* ====================================================================
   Rechnungs-Tinder – Oberfläche
   ==================================================================== */

const $ = (id) => document.getElementById(id);

const S = {
  token: null,         // Zugangsschlüssel für die API
  network: false,      // Server läuft im Netzwerk-Modus (Anmeldung mit PIN)
  status: null,        // Status des geöffneten Ordners (vom Server)
  recent: [],
  nativeDialog: false,
  deciding: false,
  browsePath: null,
  detail: null,        // { name, info, version, zoom, mode, loaded[] }
  annots: {},          // Dateiname -> [{seite, xref}] (für "Notiz löschen")
};

/* ------------------------------------------------------------ Speicher */

// Im privaten Modus (z. B. Safari) kann der Speicher fehlen – dann eben ohne.
const store = {
  get(key) { try { return localStorage.getItem(key); } catch (e) { return null; } },
  set(key, value) {
    try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch (e) { /* egal */ }
  },
};

/* ---------------------------------------------------------------- Server */

class AuthNeeded extends Error {}

async function api(path, data) {
  const opts = { headers: {} };
  if (S.token) opts.headers.Authorization = "Bearer " + S.token;
  if (data !== undefined) {
    opts.method = "POST";
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(data);
  }
  let res;
  try {
    res = await fetch("/api/v1/" + path, opts);
  } catch (e) {
    throw new Error(S.network
      ? "Keine Verbindung zum Computer. Ist das WLAN an und läuft das Programm noch?"
      : "Keine Verbindung zum Programm. Läuft das Programm-Fenster noch?");
  }
  let json = null;
  try { json = await res.json(); } catch (e) { /* keine JSON-Antwort */ }
  if (res.status === 401 && json && json.code === "anmeldung") {
    setToken(null);
    showLogin();
    throw new AuthNeeded(json.fehler);
  }
  if (!res.ok) throw new Error((json && json.fehler) || "Es ist ein Fehler aufgetreten.");
  return json;
}

function setToken(token) {
  S.token = token;
  if (S.network) store.set("token", token);
}

function folderPath() { return S.status ? S.status.ordner : null; }

function pageUrl(name, page, width, version) {
  const q = new URLSearchParams({ ordner: folderPath(), name, seite: page, breite: width, v: version, t: S.token });
  return "/api/v1/seite?" + q.toString();
}

function applyStatus(payload) {
  if ("status" in payload) {
    S.status = payload.status;
    store.set("ordner", S.status ? S.status.ordner : null);
  }
  if (payload.letzte_ordner) S.recent = payload.letzte_ordner;
}

async function withBusy(fn) {
  const timer = setTimeout(() => { $("busy").hidden = false; }, 250);
  try {
    return await fn();
  } catch (e) {
    if (!(e instanceof AuthNeeded)) toast(e.message, "error", 5000);
  } finally {
    clearTimeout(timer);
    $("busy").hidden = true;
  }
}

let toastTimer = null;
function toast(text, kind = "", ms = 1800) {
  const el = $("toast");
  el.textContent = text;
  el.className = "toast " + kind;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, ms);
}

/* --------------------------------------------------------------- Ansichten */

function show(id) {
  document.querySelectorAll(".screen").forEach((s) => { s.hidden = s.id !== id; });
}

function invoices() { return S.status ? S.status.rechnungen : []; }
function openInvoices() { return invoices().filter((r) => !r.entscheidung); }
function currentInvoice() { return openInvoices()[0] || null; }

function route(justOpened = false) {
  if (!S.status) return showStart();
  const all = invoices();
  if (all.length === 0) {
    showStart();
    if (justOpened) toast(`Im Ordner „${S.status.ordnername}“ liegen keine PDF-Rechnungen.`, "error", 5000);
    return;
  }
  if (openInvoices().length > 0) return showSwipe();
  showDone();
}

/* ------------------------------------------------------------- Anmelden */

function showLogin() {
  show("screen-login");
  $("pin").value = "";
  setTimeout(() => $("pin").focus(), 50);
}

async function login(e) {
  e.preventDefault();
  const pin = $("pin").value.trim();
  if (!pin) return;
  await withBusy(async () => {
    const res = await api("anmelden", { pin });
    $("toast").hidden = true;
    setToken(res.token);
    await start();
  });
}

/* -------------------------------------------------------------- Startseite */

function showStart() {
  show("screen-start");
  const list = $("recent-list");
  list.innerHTML = "";
  S.recent.forEach((path) => {
    const b = document.createElement("button");
    b.className = "btn btn-grey recent-btn";
    const name = path.split(/[\\/]/).filter(Boolean).pop() || path;
    b.innerHTML = '<span class="recent-name"></span><span class="recent-path"></span>';
    b.querySelector(".recent-name").textContent = "📁 " + name;
    b.querySelector(".recent-path").textContent = path;
    b.onclick = () => openFolder(path);
    list.appendChild(b);
  });
  $("recent").hidden = S.recent.length === 0;
  $("btn-browse").hidden = !S.nativeDialog;
}

async function pickFolder() {
  if (!S.nativeDialog) return openBrowse(null);
  await withBusy(async () => {
    const res = await api("systemdialog", {});
    if (res.pfad) await openFolder(res.pfad);
  });
}

async function openFolder(path) {
  await withBusy(async () => {
    applyStatus(await api("ordner", { pfad: path }));
    route(true);
  });
}

/* ----------------------------------------------------------- Ordner-Browser */

async function openBrowse(path) {
  await withBusy(async () => {
    const q = path ? "?pfad=" + encodeURIComponent(path) : "";
    const res = await api("durchsuchen" + q);
    S.browsePath = res.pfad;
    show("screen-browse");
    $("browse-path").textContent = res.pfad ? "📂 " + res.pfad : "Wo liegen die Rechnungen?";
    $("browse-up").hidden = !res.pfad;
    $("browse-up").onclick = () => openBrowse(res.oben || null);
    const list = $("browse-list");
    list.innerHTML = "";
    res.ordner.forEach((d) => {
      const b = document.createElement("button");
      b.className = "btn btn-grey";
      b.textContent = "📁 " + d.name;
      b.onclick = () => openBrowse(d.pfad);
      list.appendChild(b);
    });
    if (res.pfad && res.ordner.length === 0) {
      list.innerHTML = '<p class="lead">Keine weiteren Unterordner.</p>';
    }
    $("browse-choose").disabled = !res.pfad;
    $("browse-count").textContent = !res.pfad
      ? "Bitte tippen Sie auf einen Ordner."
      : res.pdfs === 1 ? "In diesem Ordner liegt 1 Rechnung."
      : res.pdfs > 1 ? `In diesem Ordner liegen ${res.pdfs} Rechnungen.`
      : "In diesem Ordner liegen keine PDF-Rechnungen.";
    document.querySelector(".browse-body").scrollTop = 0;
  });
}

/* --------------------------------------------------------------- Wischen */

function cardRenderWidth() {
  const w = $("card").clientWidth || 600;
  return Math.min(3500, Math.ceil((w * (window.devicePixelRatio || 1)) / 100) * 100);
}

function showSwipe() {
  show("screen-swipe");
  const all = invoices();
  const open = openInvoices();
  const done = all.length - open.length;
  $("progress-text").textContent = `Rechnung ${done + 1} von ${all.length}`;
  $("progress-bar").style.width = (100 * done) / all.length + "%";
  $("btn-undo").disabled = done === 0;

  const inv = open[0];
  const card = $("card");
  card.classList.remove("animate");
  card.style.transform = "";
  card.style.opacity = "";
  setStamps(0);
  $("card-name").textContent = inv.name;
  $("card-img").src = pageUrl(inv.name, 0, cardRenderWidth(), inv.version);
  card.setAttribute("aria-label", `Rechnung ${inv.name}. Tippen zum Vergrößern.`);
  document.querySelector(".card-behind").hidden = open.length < 2;
  // Nächste Rechnung schon vorladen, damit es flüssig weitergeht.
  if (open[1]) new Image().src = pageUrl(open[1].name, 0, cardRenderWidth(), open[1].version);
}

function setStamps(dx) {
  const p = Math.min(1, Math.abs(dx) / 120);
  document.querySelector(".stamp-yes").style.opacity = dx > 0 ? p : 0;
  document.querySelector(".stamp-no").style.opacity = dx < 0 ? p : 0;
}

function initSwipe() {
  const card = $("card");
  let start = null;

  card.addEventListener("pointerdown", (e) => {
    if (S.deciding || e.button > 0) return;
    start = { x: e.clientX, y: e.clientY, id: e.pointerId };
    card.setPointerCapture(e.pointerId);
    card.classList.remove("animate");
    card.classList.add("dragging");
  });

  card.addEventListener("pointermove", (e) => {
    if (!start || e.pointerId !== start.id) return;
    const dx = e.clientX - start.x;
    const dy = e.clientY - start.y;
    card.style.transform = `translate(${dx}px, ${dy * 0.3}px) rotate(${dx / 18}deg)`;
    setStamps(dx);
  });

  const end = (e) => {
    if (!start || e.pointerId !== start.id) return;
    const dx = e.clientX - start.x;
    const dy = e.clientY - start.y;
    start = null;
    card.classList.remove("dragging");
    const threshold = Math.min(140, card.clientWidth * 0.3);
    if (e.type === "pointerup" && Math.abs(dx) < 10 && Math.abs(dy) < 10) {
      card.style.transform = "";
      setStamps(0);
      openDetail();
    } else if (e.type === "pointerup" && Math.abs(dx) > threshold) {
      decide(dx > 0 ? "bewilligt" : "abgelehnt");
    } else {
      card.classList.add("animate");
      card.style.transform = "";
      setStamps(0);
    }
  };
  card.addEventListener("pointerup", end);
  card.addEventListener("pointercancel", end);
  card.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDetail(); }
  });
}

async function decide(decision) {
  const inv = currentInvoice();
  if (!inv || S.deciding) return;
  S.deciding = true;
  const yes = decision === "bewilligt";
  const card = $("card");
  card.classList.add("animate");
  setStamps(yes ? 200 : -200);
  const out = (window.innerWidth + card.clientWidth) * (yes ? 1 : -1);
  card.style.transform = `translate(${out}px, 40px) rotate(${yes ? 30 : -30}deg)`;
  card.style.opacity = "0";
  try {
    const [res] = await Promise.all([
      api("entscheiden", { ordner: folderPath(), name: inv.name, entscheidung: decision }),
      new Promise((r) => setTimeout(r, 300)),
    ]);
    applyStatus(res);
    toast(yes ? "✓ Bewilligt" : "✗ Abgelehnt", yes ? "ok" : "no", 1200);
  } catch (e) {
    toast(e.message, "error", 5000);
    try { await reloadFolder(); } catch (e2) { /* bleibt beim alten Stand */ }
  } finally {
    S.deciding = false;
    route();
  }
}

async function undoDecision() {
  await withBusy(async () => {
    const res = await api("rueckgaengig", { ordner: folderPath() });
    applyStatus(res);
    if (res.name) toast(`„${res.name}“ ist wieder offen.`, "", 2500);
    route();
  });
}

/* ------------------------------------------------- Detailansicht / Zoom */

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 6;

async function openDetail() {
  const inv = currentInvoice();
  if (!inv) return;
  await withBusy(async () => {
    const q = new URLSearchParams({ ordner: folderPath(), name: inv.name });
    const info = await api("rechnung?" + q.toString());
    S.detail = { name: inv.name, info, version: info.version, zoom: 1, mode: null, loaded: [] };
    S.annots[inv.name] = S.annots[inv.name] || [];
    show("screen-detail");
    $("detail-name").textContent = inv.name;
    buildPages();
    setMode(null);
    updateAnnotUndo();
    $("pages").scrollTo(0, 0);
  });
}

function closeDetail() {
  S.detail = null;
  $("pages").innerHTML = "";
  route();
}

function baseWidth() {
  const box = $("pages");
  const cs = getComputedStyle(box);
  const inner = box.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  return Math.max(150, Math.min(inner, 1100));
}

function buildPages() {
  const box = $("pages");
  box.innerHTML = "";
  S.detail.info.seiten.forEach((p, i) => {
    const div = document.createElement("div");
    div.className = "page";
    div.dataset.page = i;
    const img = document.createElement("img");
    img.alt = `Seite ${i + 1}`;
    img.draggable = false;
    const canvas = document.createElement("canvas");
    div.append(img, canvas);
    if (S.detail.info.seiten.length > 1) {
      const label = document.createElement("div");
      label.className = "page-label";
      label.textContent = `Seite ${i + 1} von ${S.detail.info.seiten.length}`;
      div.appendChild(label);
    }
    div.addEventListener("click", (e) => onPageClick(e, i, div));
    initDrawing(canvas, i);
    box.appendChild(div);
  });
  layoutPages();
}

function layoutPages() {
  const d = S.detail;
  const w = baseWidth() * d.zoom;
  const dpr = window.devicePixelRatio || 1;
  document.querySelectorAll("#pages .page").forEach((div, i) => {
    const p = d.info.seiten[i];
    const h = (w * p.hoehe) / p.breite;
    div.style.width = w + "px";
    div.style.height = h + "px";
    div.style.marginTop = i > 0 ? "28px" : "0";
    const canvas = div.querySelector("canvas");
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  });
  $("zoom-label").textContent = Math.round(d.zoom * 100) + " %";
  $("zoom-out").disabled = d.zoom <= ZOOM_MIN + 1e-6;
  $("zoom-in").disabled = d.zoom >= ZOOM_MAX - 1e-6;
  scheduleImageLoad();
}

let loadTimer = null;
function scheduleImageLoad() {
  clearTimeout(loadTimer);
  loadTimer = setTimeout(loadImages, 150);
}

function loadImages(force = false) {
  const d = S.detail;
  if (!d) return;
  const want = Math.min(3500, Math.ceil((baseWidth() * d.zoom * (window.devicePixelRatio || 1)) / 200) * 200);
  document.querySelectorAll("#pages .page").forEach((div, i) => loadPageImage(div, i, want, force));
}

function loadPageImage(div, i, width, force) {
  const d = S.detail;
  const loaded = d.loaded[i];
  // Nur nachladen, wenn wir ein schärferes Bild brauchen oder sich die Datei geändert hat.
  if (!force && loaded && loaded.width >= width && loaded.version === d.version) return;
  width = Math.max(width, loaded && loaded.version === d.version ? loaded.width : 0);
  const url = pageUrl(d.name, i, width, d.version);
  const pre = new Image();
  pre.onload = () => {
    if (S.detail !== d) return;
    div.querySelector("img").src = url;
    const c = div.querySelector("canvas");
    c.getContext("2d").clearRect(0, 0, c.width, c.height);
  };
  pre.src = url;
  d.loaded[i] = { width, version: d.version };
}

function setZoom(z, clientX, clientY) {
  const d = S.detail;
  z = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));
  if (Math.abs(z - d.zoom) < 1e-4) return;
  const box = $("pages");
  const rect = box.getBoundingClientRect();
  if (clientX === undefined) { clientX = rect.left + rect.width / 2; clientY = rect.top + rect.height / 2; }
  const vx = clientX - rect.left;
  const vy = clientY - rect.top;
  const contentX = box.scrollLeft + vx;
  const contentY = box.scrollTop + vy;
  const ratio = z / d.zoom;
  d.zoom = z;
  layoutPages();
  box.scrollLeft = contentX * ratio - vx;
  box.scrollTop = contentY * ratio - vy;
}

function initZoomGestures() {
  const box = $("pages");
  box.addEventListener("wheel", (e) => {
    if (!S.detail || !(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    setZoom(S.detail.zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1), e.clientX, e.clientY);
  }, { passive: false });

  // Mit zwei Fingern zoomen (Tablet / Touchscreen).
  let pinch = null;
  const dist = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
  const mid = (t) => [(t[0].clientX + t[1].clientX) / 2, (t[0].clientY + t[1].clientY) / 2];
  box.addEventListener("touchstart", (e) => {
    if (S.detail && e.touches.length === 2) pinch = { d: dist(e.touches), z: S.detail.zoom };
  }, { passive: true });
  box.addEventListener("touchmove", (e) => {
    if (!pinch || e.touches.length !== 2) return;
    e.preventDefault();
    const [x, y] = mid(e.touches);
    setZoom(pinch.z * (dist(e.touches) / pinch.d), x, y);
  }, { passive: false });
  box.addEventListener("touchend", (e) => {
    if (e.touches.length < 2) pinch = null;
  });

  // Doppelt tippen: vergrößern bzw. wieder auf Bildschirmbreite.
  let lastTap = null;
  box.addEventListener("pointerup", (e) => {
    if (!S.detail || S.detail.mode || e.pointerType !== "touch") return;
    const now = Date.now();
    if (lastTap && now - lastTap.t < 320 && Math.hypot(e.clientX - lastTap.x, e.clientY - lastTap.y) < 40) {
      setZoom(S.detail.zoom < 1.5 ? 2.5 : 1, e.clientX, e.clientY);
      lastTap = null;
    } else {
      lastTap = { t: now, x: e.clientX, y: e.clientY };
    }
  });

  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (S.detail) layoutPages();
      else if (!$("screen-swipe").hidden && currentInvoice()) showSwipe(); // z. B. Handy gedreht
    }, 200);
  });
}

/* ------------------------------------------------------------ Anmerkungen */

function setMode(mode) {
  if (!S.detail) return;
  S.detail.mode = S.detail.mode === mode ? null : mode;
  const m = S.detail.mode;
  $("tool-note").classList.toggle("active", m === "note");
  $("tool-draw").classList.toggle("active", m === "draw");
  const box = $("pages");
  box.classList.toggle("mode-note", m === "note");
  box.classList.toggle("mode-draw", m === "draw");
  const hint = $("tool-hint");
  hint.hidden = !m;
  if (m === "note") hint.textContent = "👆 Tippen Sie auf die Stelle in der Rechnung, an die die Notiz soll.";
  if (m === "draw") hint.textContent = "🖊 Zeichnen Sie mit dem Finger oder der Maus. Zum Beenden nochmals auf „Zeichnen“ tippen.";
}

function relativePoint(e, el) {
  const r = el.getBoundingClientRect();
  return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height];
}

function onPageClick(e, page, div) {
  if (!S.detail || S.detail.mode !== "note") return;
  const [x, y] = relativePoint(e, div);
  const dialog = $("note-dialog");
  const text = $("note-text");
  text.value = "";
  dialog.returnValue = "";
  dialog.onclose = async () => {
    if (dialog.returnValue !== "ok" || !text.value.trim()) return;
    const d = S.detail;
    await withBusy(async () => {
      const res = await api("notiz", { ordner: folderPath(), name: d.name, seite: page, x, y, text: text.value });
      rememberAnnot(d, page, res);
      setMode(null);
      toast("✔ Notiz gespeichert", "ok");
    });
  };
  dialog.showModal();
  text.focus();
}

function initDrawing(canvas, page) {
  let stroke = null;
  const ctx = canvas.getContext("2d");
  canvas.addEventListener("pointerdown", (e) => {
    if (!S.detail || S.detail.mode !== "draw") return;
    e.preventDefault();
    canvas.setPointerCapture(e.pointerId);
    stroke = [relativePoint(e, canvas)];
    ctx.strokeStyle = "#d90000";
    ctx.lineWidth = Math.max(2, canvas.width / 250);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(stroke[0][0] * canvas.width, stroke[0][1] * canvas.height);
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!stroke) return;
    const p = relativePoint(e, canvas);
    stroke.push(p);
    ctx.lineTo(p[0] * canvas.width, p[1] * canvas.height);
    ctx.stroke();
  });
  const finish = async () => {
    if (!stroke) return;
    const pts = stroke;
    stroke = null;
    const d = S.detail;
    try {
      const res = await api("zeichnung", { ordner: folderPath(), name: d.name, seite: page, striche: [pts] });
      rememberAnnot(d, page, res);
    } catch (err) {
      toast(err.message, "error", 5000);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
  };
  canvas.addEventListener("pointerup", finish);
  canvas.addEventListener("pointercancel", finish);
}

function rememberAnnot(d, page, res) {
  S.annots[d.name].push({ seite: page, xref: res.xref });
  fileChanged(d, page, res.version);
}

function fileChanged(d, page, version) {
  d.version = version;
  const inv = invoices().find((r) => r.name === d.name);
  if (inv) inv.version = version;
  if (S.detail !== d) return;
  // Die geänderte Seite sofort neu laden, die übrigen bei Bedarf.
  const div = document.querySelector(`#pages .page[data-page="${page}"]`);
  const want = d.loaded[page] ? d.loaded[page].width : 1000;
  d.loaded = d.loaded.map((l) => (l ? { ...l, version: -1 } : l));
  if (div) loadPageImage(div, page, want, true);
  loadImages();
  updateAnnotUndo();
}

function updateAnnotUndo() {
  const list = S.detail ? S.annots[S.detail.name] : [];
  $("annot-undo").disabled = !list || list.length === 0;
}

async function undoAnnot() {
  const d = S.detail;
  const list = S.annots[d.name];
  if (!list.length) return;
  const last = list[list.length - 1];
  await withBusy(async () => {
    const res = await api("anmerkung-loeschen", { ordner: folderPath(), name: d.name, seite: last.seite, xref: last.xref });
    list.pop();
    fileChanged(d, last.seite, res.version);
    toast("Letzte Notiz gelöscht");
  });
  updateAnnotUndo();
}

/* ---------------------------------------------------------- Zusammenfassung */

function showDone() {
  show("screen-done");
  $("done-title").textContent = "Alle Rechnungen geprüft ✓";
  $("done-summary").hidden = false;
  $("done-result").hidden = true;
  const all = invoices();
  const fill = (listId, countId, decision) => {
    const names = all.filter((r) => r.entscheidung === decision).map((r) => r.name);
    $(countId).textContent = names.length;
    const ul = $(listId);
    ul.innerHTML = "";
    names.forEach((n) => { const li = document.createElement("li"); li.textContent = n; ul.appendChild(li); });
    if (!names.length) ul.innerHTML = "<li>–</li>";
  };
  fill("list-yes", "count-yes", "bewilligt");
  fill("list-no", "count-no", "abgelehnt");
  $("targets").textContent =
    `Bewilligte kommen nach: ${S.status.ziele.bewilligt} · Abgelehnte nach: ${S.status.ziele.abgelehnt}`;
}

async function moveAll() {
  await withBusy(async () => {
    const res = await api("verschieben", { ordner: folderPath() });
    applyStatus(res);
    const r = res.ergebnis;
    const yes = r.verschoben.bewilligt.length;
    const no = r.verschoben.abgelehnt.length;
    const word = (n) => (n === 1 ? "1 Rechnung" : `${n} Rechnungen`);
    $("done-title").textContent = r.fehler.length ? "Fast fertig" : "Fertig! ✓";
    $("result-text").textContent =
      `${word(yes)} in den Ordner „Bewilligt“ und ${word(no)} in den Ordner „Abgelehnt“ verschoben.`;
    const errors = $("result-errors");
    errors.innerHTML = "";
    if (r.fehler.length) {
      const p = document.createElement("p");
      p.textContent = "Diese Rechnungen konnten nicht verschoben werden (bitte die Datei schließen und nochmal versuchen):";
      errors.appendChild(p);
      r.fehler.forEach((f) => {
        const div = document.createElement("div");
        div.textContent = `• ${f.name}: ${f.fehler}`;
        errors.appendChild(div);
      });
    }
    $("done-summary").hidden = r.fehler.length === 0;
    $("done-result").hidden = false;
  });
}

/* ------------------------------------------------------------------ Start */

function init() {
  $("btn-pick").onclick = pickFolder;
  $("btn-browse").onclick = () => openBrowse(null);
  $("browse-back").onclick = showStart;
  $("browse-choose").onclick = () => S.browsePath && openFolder(S.browsePath);
  $("btn-change-folder").onclick = showStart;
  $("btn-undo").onclick = undoDecision;
  $("done-undo").onclick = undoDecision;
  $("btn-yes").onclick = () => decide("bewilligt");
  $("btn-no").onclick = () => decide("abgelehnt");
  $("btn-view").onclick = openDetail;
  $("detail-close").onclick = closeDetail;
  $("detail-yes").onclick = () => { closeDetail(); decide("bewilligt"); };
  $("detail-no").onclick = () => { closeDetail(); decide("abgelehnt"); };
  $("zoom-in").onclick = () => setZoom(S.detail.zoom * 1.25);
  $("zoom-out").onclick = () => setZoom(S.detail.zoom / 1.25);
  $("tool-note").onclick = () => setMode("note");
  $("tool-draw").onclick = () => setMode("draw");
  $("annot-undo").onclick = undoAnnot;
  $("btn-move").onclick = moveAll;
  $("btn-again").onclick = showStart;

  document.addEventListener("keydown", (e) => {
    if ($("note-dialog").open) return;
    if (!$("screen-swipe").hidden) {
      if (e.key === "ArrowRight") decide("bewilligt");
      if (e.key === "ArrowLeft") decide("abgelehnt");
    } else if (!$("screen-detail").hidden) {
      if (e.key === "Escape") closeDetail();
      if (e.key === "+" || e.key === "=") setZoom(S.detail.zoom * 1.25);
      if (e.key === "-") setZoom(S.detail.zoom / 1.25);
    }
  });

  $("login-form").onsubmit = login;

  initSwipe();
  initZoomGestures();
  withBusy(start);
}

async function reloadFolder() {
  const q = new URLSearchParams({ pfad: folderPath() });
  applyStatus(await api("ordner?" + q.toString()));
}

async function start() {
  const info = await api("info");
  S.network = info.netzwerk;
  if (!info.angemeldet) {
    // Lokal liefert die Startseite den Schlüssel mit, im Netzwerk ist er gespeichert.
    S.token = window.TOKEN && window.TOKEN !== "__TOKEN__" ? window.TOKEN : store.get("token");
    const again = S.token ? await api("info") : info;
    if (!again.angemeldet) return info.netzwerk ? showLogin() : toast("Bitte das Programm neu starten.", "error", 8000);
    Object.assign(info, again);
  }
  S.recent = info.letzte_ordner || [];
  S.nativeDialog = !!info.systemdialog;
  const saved = store.get("ordner");
  if (saved && !S.status) {
    try {
      const q = new URLSearchParams({ pfad: saved });
      applyStatus(await api("ordner?" + q.toString()));
    } catch (e) {
      if (e instanceof AuthNeeded) return;
      store.set("ordner", null);
    }
  }
  route();
}

init();
