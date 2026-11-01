/* ShrapMind console. No framework, no build step.
 *
 * One WebSocket in, one switch(kind) over AgentEvent, DOM out. Case history
 * is client-side only (localStorage) - the server keeps design runs in
 * Postgres but stores no transcript, so clearing your browser clears your
 * chat and nothing else.
 */
"use strict";

const STAGES = ["inspect", "characterize", "reaction", "retrieve", "generate",
                "predict", "simulate", "gate", "rank", "report"];

const chat = document.getElementById("chat");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const pauseBtn = document.getElementById("pause");
const stopBtn = document.getElementById("stop");
const modeSel = document.getElementById("mode");
const modeHint = document.getElementById("mode-hint");
const caseList = document.getElementById("case-list");

let ws = null;
let busy = false;
let paused = false;

/* ----------------------------------------------------------- utilities */

function el(cls, text) {
  const d = document.createElement("div");
  if (cls) d.className = cls;
  if (text !== undefined && text !== null) d.textContent = text;
  return d;
}

function esc(s) {
  return String(s === undefined || s === null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function num(v, digits) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!isFinite(n)) return "—";
  if (digits !== undefined) return n.toFixed(digits);
  if (Math.abs(n) >= 100) return n.toFixed(0);
  if (Math.abs(n) >= 1) return n.toFixed(2);
  if (Math.abs(n) > 0) return n.toExponential(1);
  return "0";
}

function append(node) {
  const intro = chat.querySelector(".intro");
  if (intro) intro.remove();
  chat.appendChild(node);
  chat.scrollTop = chat.scrollHeight;
  return node;
}

/* ----------------------------------------------------------- case history */

const K_CASES = "shrapmind-cases";
const K_ACTIVE = "shrapmind-active";

function loadCases() {
  try { return JSON.parse(localStorage.getItem(K_CASES) || "[]"); }
  catch (e) { return []; }
}
function saveCases(list) {
  try { localStorage.setItem(K_CASES, JSON.stringify(list.slice(0, 40))); }
  catch (e) { /* private mode, quota - the UI must still work */ }
}
let cases = loadCases();
let activeId = localStorage.getItem(K_ACTIVE) || null;

function getCase(id) { return cases.find((c) => c.id === id) || null; }

function createCase(title) {
  const c = { id: String(Date.now()), title: title || "New case", msgs: [] };
  cases.unshift(c);
  saveCases(cases);
  setActive(c.id);
  return c;
}

function ensureActive() {
  if (!getCase(activeId)) {
    if (cases.length) setActive(cases[0].id);
    else createCase("New case");
  }
}

function setActive(id) {
  activeId = id;
  try { localStorage.setItem(K_ACTIVE, id); } catch (e) { /* ignore */ }
  renderCaseList();
}

function saveMsg(msg) {
  const c = getCase(activeId);
  if (!c) return;
  // A full assay payload is large and we only need it to redraw the card.
  c.msgs.push(msg);
  if (c.msgs.length > 220) c.msgs = c.msgs.slice(-220);
  saveCases(cases);
}

function renderCaseList() {
  caseList.innerHTML = "";
  cases.forEach((c) => {
    const row = el("case-item" + (c.id === activeId ? " active" : ""));
    row.dataset.id = c.id;
    const t = el("case-title", c.title);
    const del = document.createElement("button");
    del.className = "del";
    del.dataset.del = c.id;
    del.textContent = "×";
    del.title = "Delete";
    row.appendChild(t);
    row.appendChild(del);
    caseList.appendChild(row);
  });
}

/* ----------------------------------------------------------- pipeline strip */

function resetPipeline() {
  document.querySelectorAll(".stage").forEach((s) => {
    s.classList.remove("active", "done", "blocked");
  });
}

function setStage(name) {
  const idx = STAGES.indexOf(name);
  if (idx < 0) return;
  document.querySelectorAll(".stage").forEach((s) => {
    const i = STAGES.indexOf(s.dataset.stage);
    s.classList.remove("active", "done");
    if (i < idx) s.classList.add("done");
    else if (i === idx) s.classList.add("active");
  });
}

function blockPipeline() {
  const a = document.querySelector(".stage.active");
  if (a) { a.classList.remove("active"); a.classList.add("blocked"); }
}

/* ----------------------------------------------------------- renderers */

function thoughtBubble(text, streaming) {
  const wrap = el("msg thought");
  if (streaming) {
    wrap.dataset.stream = "1";
    chat.querySelectorAll('.msg.thought[data-stream="1"]').forEach((n) => {
      if (n !== wrap) delete n.dataset.stream;
    });
  }
  wrap.appendChild(el("thought-body", text || ""));
  return wrap;
}

function toolRow(name, stage) {
  const row = el("msg tool");
  if (stage) row.appendChild(el("tool-stage", stage));
  row.appendChild(el(null, name));
  return row;
}

function obsRow(name, payload) {
  const row = el("msg obs");
  const full = typeof payload === "string" ? payload
    : JSON.stringify(payload, null, 2);
  row.dataset.full = full;
  row.textContent = name + " → " + summarize(name, payload);
  return row;
}

function summarize(name, p) {
  if (p === null || p === undefined) return "";
  if (typeof p !== "object") return String(p).slice(0, 180);
  if (p.passport) {
    return "material=" + p.passport.material_family +
           " confidence=" + p.passport.confidence +
           (p.no_go ? " NO-GO" : "");
  }
  if (p.reaction_spec) {
    return "mechanism=" + p.reaction_spec.mechanism +
           " forbidden=[" + (p.reaction_spec.forbidden_products || []).join(", ") + "]";
  }
  if (p.erosion_rate_um_per_day !== undefined) {
    const ci = p.erosion_rate_ci || [];
    return num(p.erosion_rate_um_per_day) + " um/day" +
           (ci.length === 2 ? " [" + num(ci[0]) + ", " + num(ci[1]) + "]" : "") +
           " captured=" + num(p.captured_fraction, 2);
  }
  if (p.gates) return p.summary || (p.passed ? "all gates passed" : "gates failed");
  if (p.candidates) return p.n + " candidates";
  if (p.families) return p.n + " families";
  if (p.ranking) {
    return p.ranking.slice(0, 3)
      .map((r) => r.candidate + "(" + num(r.score, 2) + ")").join(", ");
  }
  if (p.experiments) {
    return p.experiments.map((e) => e.candidate).join(" > ");
  }
  if (p.note) return String(p.note).slice(0, 160);
  if (p.error) return "ERROR " + p.error;
  const keys = Object.keys(p);
  return "{" + keys.slice(0, 6).join(", ") + (keys.length > 6 ? ", ..." : "") + "}";
}

/* Inline sparkline of the fragment pool over time. No chart library: it is
 * one path, and a dependency for one path is a bad trade. */
function sparkline(series) {
  if (!series || series.length < 2) return null;
  const W = 760, H = 76, pad = 4;
  const t = series.map((p) => Number(p.t_h) || 0);
  const tMax = Math.max.apply(null, t) || 1;
  const keys = [
    { k: "fragment", color: "var(--accent-2)" },
    { k: "captured", color: "var(--ok)" },
    { k: "free", color: "var(--warn)" }
  ];
  let vMax = 0;
  keys.forEach((s) => series.forEach((p) => {
    const v = Number(p[s.k]) || 0;
    if (v > vMax) vMax = v;
  }));
  if (vMax <= 0) vMax = 1;

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "spark");
  svg.setAttribute("viewBox", "0 0 " + W + " " + H);
  svg.setAttribute("preserveAspectRatio", "none");

  keys.forEach((s) => {
    const pts = series.map((p, i) => {
      const x = pad + (t[i] / tMax) * (W - 2 * pad);
      const y = H - pad - ((Number(p[s.k]) || 0) / vMax) * (H - 2 * pad);
      return (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
    }).join(" ");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", pts);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", s.color);
    path.setAttribute("stroke-width", "2");
    path.setAttribute("vector-effect", "non-scaling-stroke");
    svg.appendChild(path);
  });

  const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
  label.setAttribute("x", String(pad + 2));
  label.setAttribute("y", "13");
  label.setAttribute("font-size", "10");
  label.setAttribute("fill", "currentColor");
  label.setAttribute("opacity", "0.65");
  label.textContent = "fragment — captured — free   (0–" +
                      Math.round(tMax) + " h)";
  svg.appendChild(label);
  return svg;
}

function resultCard(p) {
  const ok = !!p.success;
  const card = el("card " + (ok ? "ok" : "bad"));

  const head = el("card-head");
  head.appendChild(el("card-title",
    ok ? "Design run complete" : (p.halted ? "Run halted" : "No supported conclusion")));
  const badge = el("badge " + (ok ? "ok" : "bad"),
    p.halted === "safety_gate" ? "gate failure"
      : p.halted === "clinical_output" ? "refused"
      : ok ? "hypothesis" : "no result");
  head.appendChild(badge);
  card.appendChild(head);

  const body = el("card-body");

  const assay = p.assay || null;

  /* Provenance first, above the numbers. If the kinetics came from a
   * chromogenic stand-in, that is the most important thing on the card and it
   * must not sit below a large bold erosion rate. */
  if (assay && assay.kinetics_provenance) {
    const prov = assay.kinetics_provenance;
    const good = prov === "polymer" || prov === "oligomer";
    const banner = el("prov " + (good ? "prov-ok" : "prov-bad"));
    const on = assay.measured_on || "an unrecorded substrate";
    banner.textContent = good
      ? "Kinetics measured on " + on + " \u2014 " + prov + "-level evidence."
      : "Kinetics measured on " + on + " \u2014 " + prov +
        "-level evidence, not on the fragment material. The rate below is an " +
        "extrapolation across substrates, not a prediction.";
    body.appendChild(banner);
  }
  if (assay && (assay.assumed_parameters || []).length) {
    const warn = el("prov prov-bad",
      "Assumed, not measured: " + assay.assumed_parameters.join(", ") +
      ". These fell back to generic defaults.");
    body.appendChild(warn);
  }
  if (assay) {
    const m = el("metrics");
    const ci = assay.erosion_rate_ci || [];
    const r1 = el("metric");
    r1.appendChild(el("k", "erosion rate"));
    r1.appendChild(el("v", num(assay.erosion_rate_um_per_day) + " µm/d"));
    if (ci.length === 2) {
      r1.appendChild(el("sub", "5–95%: " + num(ci[0]) + "–" + num(ci[1])));
    }
    m.appendChild(r1);

    const r2 = el("metric");
    r2.appendChild(el("k", "product captured"));
    r2.appendChild(el("v", (Number(assay.captured_fraction) * 100).toFixed(0) + "%"));
    r2.appendChild(el("sub", "free " +
      (Number(assay.free_fraction) * 100).toFixed(0) + "%"));
    m.appendChild(r2);

    const r3 = el("metric");
    r3.appendChild(el("k", "mass balance"));
    r3.appendChild(el("v", num(assay.mass_balance_residual)));
    r3.appendChild(el("sub", "residual"));
    m.appendChild(r3);

    const r4 = el("metric");
    r4.appendChild(el("k", "band width"));
    r4.appendChild(el("v", num(assay.uncertainty, 2)));
    r4.appendChild(el("sub", "n=" + (assay.n_samples || "?") + " samples"));
    m.appendChild(r4);
    body.appendChild(m);

    const spark = sparkline(assay.timeseries);
    if (spark) body.appendChild(spark);
  }

  if (p.gates && p.gates.length) {
    const g = el("gates");
    p.gates.forEach((x) => {
      const b = el("gate" + (x.passed ? "" : " bad"),
        (x.passed ? "✓ " : "✗ ") + x.name +
        (x.value !== null && x.value !== undefined ? " " + num(x.value) : ""));
      b.title = x.detail || "";
      g.appendChild(b);
    });
    body.appendChild(g);
  }

  body.appendChild(el("report", p.summary || ""));

  if (p.ranking && p.ranking.length) {
    const tbl = document.createElement("table");
    tbl.className = "rank";
    tbl.innerHTML =
      "<tr><th>#</th><th>candidate</th><th>µm/day</th><th>band</th>" +
      "<th>dev.</th><th>gates</th></tr>" +
      p.ranking.map((r) => {
        const ci = r.erosion_rate_ci || [];
        return "<tr><td>" + esc(r.rank) + "</td>" +
          "<td class='name'>" + esc(r.candidate) + "</td>" +
          "<td>" + num(r.erosion_rate_um_per_day) + "</td>" +
          "<td>" + (ci.length === 2 ? num(ci[0]) + "–" + num(ci[1]) : "—") + "</td>" +
          "<td>" + num(r.developability, 2) + "</td>" +
          "<td class='" + (r.gate_status === "fail" ? "fail" : "") + "'>" +
          (r.gate_status === "pass" ? "pass"
            : r.gate_status === "not_gated" ? "not gated"
            : esc((r.failed_gates || []).join(","))) +
          "</td></tr>";
      }).join("");
    body.appendChild(tbl);
  }

  if (p.next_experiments && p.next_experiments.length) {
    body.appendChild(el("k", ""));
    const h = el("metric");
    h.style.flex = "1 1 100%";
    h.appendChild(el("k", "measure next"));
    const ul = document.createElement("ul");
    ul.className = "next-list";
    p.next_experiments.forEach((e) => {
      const li = document.createElement("li");
      li.textContent = e.candidate + " — information value " +
        num(e.information_value, 2) + ", band width " + num(e.uncertainty, 2);
      ul.appendChild(li);
    });
    h.appendChild(ul);
    body.appendChild(h);
  }

  if (assay && (assay.evidence_citations || []).length) {
    const cites = el("cites");
    cites.appendChild(el("k", "evidence"));
    const list = document.createElement("div");
    list.className = "cite-list";
    const seen = {};
    assay.evidence_citations.forEach((c) => {
      if (!c || seen[c]) return;
      seen[c] = 1;
      const m = /^PMID:(\d+)$/.exec(c);
      if (m) {
        const a = document.createElement("a");
        a.href = "https://pubmed.ncbi.nlm.nih.gov/" + m[1] + "/";
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = c;
        list.appendChild(a);
      } else {
        list.appendChild(el("cite", c));
      }
    });
    cites.appendChild(list);
    body.appendChild(cites);
  }
  if (p.disclaimer) body.appendChild(el("disclaimer", p.disclaimer));
  card.appendChild(body);
  return card;
}

function feedbackRow(p) {
  const row = el("feedback");
  [["👍", "like"], ["👎", "dislike"]].forEach((pair) => {
    const b = document.createElement("button");
    b.textContent = pair[0];
    b.onclick = () => {
      send({ type: "feedback", rating: pair[1], success: !!p.success,
             summary: (p.summary || "").slice(0, 400) });
      row.querySelectorAll("button").forEach((x) => x.classList.remove("picked"));
      b.classList.add("picked");
    };
    row.appendChild(b);
  });
  return row;
}

/* ----------------------------------------------------------- event switch */

function renderEvent(ev, replaying) {
  const kind = ev.kind;
  const p = ev.payload || {};

  switch (kind) {
    case "status": {
      if (p.worker_connected !== undefined) setWorker(p.worker_connected);
      if (p.snapshot !== undefined && p.snapshot) setSnapshot(p.snapshot, p.covered_materials, p.hazard_resolved);
      if (p.user_prompt) {
        append(el("msg user", p.user_prompt));
        if (!replaying) {
          const c = getCase(activeId);
          if (c && (c.title === "New case" || !c.msgs.length)) {
            c.title = p.user_prompt.slice(0, 48);
            saveCases(cases);
            renderCaseList();
          }
          saveMsg({ kind: "status", payload: { user_prompt: p.user_prompt } });
        }
        return;
      }
      if (p.paused !== undefined) {
        paused = !!p.paused;
        pauseBtn.textContent = paused ? "Resume" : "Pause";
      }
      if (p.msg && p.msg !== "connected") append(el("msg status", p.msg));
      return;
    }

    case "thought": {
      append(thoughtBubble(p.text, p.stream));
      if (!replaying) saveMsg({ kind: "thought", payload: { text: p.text || "" } });
      return;
    }

    case "thought_delta": {
      const node = chat.querySelector('.msg.thought[data-stream="1"] .thought-body');
      if (node) {
        node.textContent += p.text || "";
        chat.scrollTop = chat.scrollHeight;
      }
      if (!replaying) {
        // Patch the stored message so a reload shows the finished text.
        const c = getCase(activeId);
        if (c && c.msgs.length) {
          const last = c.msgs[c.msgs.length - 1];
          if (last.kind === "thought") {
            last.payload.text = (last.payload.text || "") + (p.text || "");
            saveCases(cases);
          }
        }
      }
      return;
    }

    case "stage": {
      setStage(p.stage);
      return;
    }

    case "tool_call": {
      append(toolRow(p.name, p.stage));
      if (!replaying) saveMsg({ kind: "tool_call", payload: p });
      return;
    }

    case "observation": {
      append(obsRow(p.name, p.error ? { error: p.error } : p.result));
      if (!replaying) {
        saveMsg({ kind: "observation",
                  payload: { name: p.name, error: p.error,
                             result: p.error ? undefined : p.result } });
      }
      return;
    }

    case "error": {
      append(el("msg error", p.text || "Something went wrong."));
      blockPipeline();
      if (!replaying) saveMsg({ kind: "error", payload: { text: p.text } });
      return;
    }

    case "result": {
      append(resultCard(p));
      if (!p.success) blockPipeline();
      if (!replaying) {
        append(feedbackRow(p));
        saveMsg({ kind: "result", payload: p });
      }
      setBusy(false);
      return;
    }

    case "mode_change": {
      if (p.mode) { modeSel.value = p.mode; updateModeHint(); }
      return;
    }

    default:
      return;
  }
}

/* ----------------------------------------------------------- transport */

function send(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

function setLink(up) {
  const dot = document.getElementById("link-dot");
  const txt = document.getElementById("link-text");
  dot.className = "dot " + (up ? "on" : "off");
  txt.textContent = up ? "connected" : "reconnecting";
}

/* The evidence snapshot's age, and what it covers. Shown because a
 * recommendation read without knowing the data is five days or five months
 * old is a recommendation read wrong. */
function setSnapshot(iso, materials, hazardResolved) {
  const el2 = document.getElementById("snapshot-text");
  const dot = document.getElementById("snapshot-dot");
  if (!el2) return;
  let days = null;
  try {
    days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  } catch (e) { /* ignore */ }
  const age = days === null ? "" : days <= 0 ? " (today)"
    : days === 1 ? " (1 day old)" : " (" + days + " days old)";
  el2.textContent = "evidence " + String(iso).slice(0, 10) + age;
  el2.title = (materials && materials.length)
    ? "Curated materials: " + materials.join(", ")
    : "";
  if (dot) dot.className = "dot " + (days !== null && days > 90 ? "off" : "on");

  const hz = document.getElementById("hazard-text");
  const hzdot = document.getElementById("hazard-dot");
  if (hz) {
    if (hazardResolved === null || hazardResolved === undefined) {
      hz.textContent = "hazard data unknown";
      if (hzdot) hzdot.className = "dot";
    } else if (hazardResolved > 0) {
      hz.textContent = "hazard resolved (" + hazardResolved + ")";
      if (hzdot) hzdot.className = "dot on";
    } else {
      hz.textContent = "hazard not resolved";
      hz.title = "GHS classification has not been fetched. Run " +
                 "tools/fetch_chemistry.py (needs network access to PubChem).";
      if (hzdot) hzdot.className = "dot off";
    }
  }
}

function setWorker(up) {
  const dot = document.getElementById("worker-dot");
  const txt = document.getElementById("worker-text");
  dot.className = "dot " + (up ? "on" : "off");
  txt.textContent = up ? "worker ready" : "no worker";
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(proto + "://" + location.host + "/ws");
  window.ws = ws;
  ws.onopen = () => setLink(true);
  ws.onclose = () => { setLink(false); setTimeout(connect, 1500); };
  ws.onmessage = (e) => {
    let ev;
    try { ev = JSON.parse(e.data); } catch (err) { return; }
    renderEvent(ev, false);
  };
}

function setBusy(on) {
  busy = on;
  sendBtn.disabled = on;
  sendBtn.textContent = on ? "Running" : "Run";
  pauseBtn.classList.toggle("hidden", !on);
  stopBtn.classList.toggle("hidden", !on);
  if (!on) { paused = false; pauseBtn.textContent = "Pause"; }
}

function submit() {
  const text = input.value.trim();
  if (!text || busy) return;
  resetPipeline();
  input.value = "";
  input.style.height = "auto";
  setBusy(true);
  send({ type: "message", text: text, mode: modeSel.value });
}

function updateModeHint() {
  modeHint.textContent = modeSel.value === "explain"
    ? "Walks the pipeline and explains each stage. Runs no simulations and writes nothing."
    : "Runs retrieval, simulation and the gate battery.";
}

/* ----------------------------------------------------------- wiring */

sendBtn.onclick = submit;
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
});
input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 180) + "px";
});
pauseBtn.onclick = () => { send({ type: paused ? "resume" : "pause" }); };
stopBtn.onclick = () => { send({ type: "stop" }); setBusy(false); };
modeSel.onchange = () => { send({ type: "set_mode", mode: modeSel.value }); updateModeHint(); };

document.getElementById("new-case").onclick = () => {
  createCase("New case");
  renderChat(activeId);
};

document.getElementById("theme-toggle").onclick = () => {
  const light = document.documentElement.classList.toggle("light");
  try { localStorage.setItem("shrapmind-theme", light ? "light" : "dark"); }
  catch (e) { /* ignore */ }
};

/* One delegated listener for the whole page. */
document.addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (chip) {
    input.value = chip.textContent.trim();
    input.focus();
    return;
  }
  const del = e.target.closest("[data-del]");
  if (del) {
    e.stopPropagation();
    cases = cases.filter((c) => c.id !== del.dataset.del);
    saveCases(cases);
    ensureActive();
    renderChat(activeId);
    return;
  }
  const item = e.target.closest(".case-item");
  if (item) {
    setActive(item.dataset.id);
    renderChat(activeId);
    return;
  }
  const obs = e.target.closest(".msg.obs");
  if (obs && !obs.classList.contains("open")) {
    obs.classList.add("open");
    obs.textContent = obs.dataset.full;
  }
});

/* Theme changes in another tab. */
window.addEventListener("storage", (e) => {
  if (e.key === "shrapmind-theme") {
    document.documentElement.classList.toggle("light", e.newValue === "light");
  }
});

function renderChat(id) {
  chat.innerHTML = "";
  resetPipeline();
  const c = getCase(id);
  if (!c || !c.msgs.length) {
    chat.innerHTML =
      '<div class="intro"><h1>Describe the fragment case</h1>' +
      '<p class="intro-lead">Material, location, how long it has been there, ' +
      'and what is already known.</p>' +
      '<div class="scope-note"><strong>Research simulation.</strong> Every result ' +
      'is a hypothesis requiring wet-lab validation. This system does not provide ' +
      'clinical guidance and will refuse requests for it.</div></div>';
    return;
  }
  c.msgs.forEach((m) => renderEvent(m, true));
}

ensureActive();
renderCaseList();
renderChat(activeId);
updateModeHint();
connect();
