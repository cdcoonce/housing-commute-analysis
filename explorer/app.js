/* RQ4 event-study explorer — vanilla JS + hand-rolled SVG.
   Data: explorer/data/rq4.json (scripts/export_rq4_explorer.py). */

"use strict";

const VARS = [
  "commute_min_proxy_2019",
  "distance_to_cbd_km",
  "log_job_accessibility_2019",
];
const VAR_SHORT = {
  commute_min_proxy_2019: "Commute time",
  distance_to_cbd_km: "Distance to CBD",
  log_job_accessibility_2019: "Job accessibility",
};
const VAR_UNIT = {
  commute_min_proxy_2019: "log rent per minute",
  distance_to_cbd_km: "log rent per km",
  log_job_accessibility_2019: "log rent per log-point",
};
/* Which sign is periphery-favoring for each gradient. */
const PERIPHERY_SIGN = {
  commute_min_proxy_2019: +1,
  distance_to_cbd_km: +1,
  log_job_accessibility_2019: -1,
};
const TCRIT = 1.96;

let DATA = null;
let metro = "DEN";
let model = "joint";

const $ = (sel) => document.querySelector(sel);
const el = (tag, attrs = {}, text) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text != null) n.textContent = text;
  return n;
};
const svgEl = (tag, attrs = {}) => {
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
};
const fmt = (x, d = 4) =>
  x == null ? "—" : (+x).toFixed(d).replace("-", "−");
const fmtP = (p) => {
  if (p == null) return "—";
  if (p < 0.0001) return "<0.0001";
  return (+p).toFixed(4);
};

/* ---------------- tooltip ---------------- */
const tip = el("div", { class: "tip", role: "status" });
document.body.appendChild(tip);
function showTip(html, x, y) {
  tip.innerHTML = html;
  const pad = 14;
  const w = tip.offsetWidth || 200;
  tip.style.left = Math.min(x + pad, window.innerWidth - w - 10) + "px";
  tip.style.top = y + pad + "px";
  tip.classList.add("show");
}
function hideTip() { tip.classList.remove("show"); }

/* ---------------- metro switcher ---------------- */
function renderSwitcher() {
  const nav = $("#metro-switch");
  nav.replaceChildren();
  for (const code of DATA.metro_order) {
    const m = DATA.metros[code];
    const b = el("button", {
      class: "chip" + (code === metro ? " is-on" : ""),
      type: "button",
      role: "radio",
      "aria-checked": String(code === metro),
    }, m.name.split("-")[0].split(",")[0] === "Dallas" ? "Dallas–Fort Worth" : m.name.replace(/-.*$/, "").replace(/,.*$/, ""));
    b.addEventListener("click", () => { metro = code; renderAll(); });
    nav.appendChild(b);
  }
}

/* ---------------- verdict card ---------------- */
function renderVerdict() {
  const m = DATA.metros[metro];
  const card = $("#verdict-card");
  card.replaceChildren();
  card.appendChild(el("h2", {}, m.name));

  const badges = el("div", { class: "badges" });
  badges.appendChild(el("span", { class: "badge" }, "Pre-trend: " + m.editorial.pretrend));
  if (m.flags.includes("under_identified")) {
    badges.appendChild(el("span", { class: "badge" }, "⚠ Under-identified"));
  }
  const surv = bootstrapSurvivors(m);
  badges.appendChild(el("span", { class: "badge" },
    surv.length ? "✓ Coarse-cluster bootstrap survivors: " + surv.join(", ")
                : "✗ No coarse-cluster bootstrap survivors"));
  card.appendChild(badges);

  card.appendChild(el("p", { class: "reading" }, m.editorial.verdict));

  const stats = el("div", { class: "statrow" });
  const cov = Math.round(m.coverage.share_covered * 100);
  const addStat = (label, val) => {
    const s = el("span");
    s.appendChild(el("b", {}, String(val)));
    s.appendChild(document.createTextNode(label));
    stats.appendChild(s);
  };
  addStat("covered ZCTAs", `${m.coverage.n_covered} / ${m.coverage.n_universe}`);
  addStat("coverage", cov + "%");
  addStat("identifying ZCTAs", m.n_identifying);
  addStat("ZIP-month observations", m.n_obs.toLocaleString());
  addStat("months (pre / post)", `${m.n_pre_months} / ${m.n_post_months}`);
  card.appendChild(stats);
}

/* Survivors: significant at p<0.05 under BOTH conventional ZCTA clustering and
   the ZIP3 wild bootstrap, in at least one phase. Label carries the phase(s). */
function bootstrapSurvivors(m) {
  const out = [];
  for (const v of VARS) {
    const conv = m.spec_a_joint.coefs[v];
    const boot = (m.bootstrap_pvalues.zip3 || {})[v] || {};
    const phases = [];
    for (const ph of ["post1", "post2"]) {
      if (conv[ph + "_pvalue"] < 0.05 && boot[ph] < 0.05) phases.push(ph === "post1" ? "P1" : "P2");
    }
    if (phases.length) out.push(`${VAR_SHORT[v]} (${phases.join("+")})`);
  }
  return out;
}

/* ---------------- coefficient plot ---------------- */
function coefRows(m) {
  const src = model === "joint" ? m.spec_a_joint.coefs : m.spec_a_single;
  const rows = [];
  for (const v of VARS) {
    const c = src[v];
    for (const ph of ["post1", "post2"]) {
      rows.push({
        variable: v,
        phase: ph,
        coef: c[ph + "_coef"],
        se: c[ph + "_se"],
        p: c[ph + "_pvalue"],
        boot: ((m.bootstrap_pvalues.zip3 || {})[v] || {})[ph],
      });
    }
  }
  return rows;
}

function renderCoefPlot() {
  const m = DATA.metros[metro];
  const host = $("#coef-plot");
  host.replaceChildren();

  const legend = el("div", { class: "legend", role: "list" });
  for (const [label, cls] of [["Post1 · disruption (2020-03…2021-12)", "--accent-soft"], ["Post2 · return-to-office (2022-01+)", "--accent"]]) {
    const k = el("span", { class: "key", role: "listitem" });
    const sw = el("span", { class: "swatch" });
    sw.style.background = `var(${cls})`;
    k.appendChild(sw);
    k.appendChild(document.createTextNode(label));
    legend.appendChild(k);
  }
  const kg = el("span", { class: "key" }, "hollow = p ≥ 0.05 (ZCTA-clustered)");
  legend.appendChild(kg);
  host.appendChild(legend);

  const rows = coefRows(m);
  const W = 1040, rowH = 44, padT = 8, padB = 24, labelW = 190, padR = 88;
  const H = padT + VARS.length * (rowH * 2 + 18) + padB;
  const plotX0 = labelW, plotX1 = W - padR;

  /* Per-variable symmetric scales (units differ across gradients); the
     shared dashed zero line stays aligned because every scale centers on 0. */
  const limOf = {};
  for (const v of VARS) {
    const vr = rows.filter((r) => r.variable === v);
    limOf[v] = Math.max(...vr.map((r) => Math.abs(r.coef) + TCRIT * r.se)) * 1.12;
  }
  const xFor = (v) => (val) => plotX0 + ((val + limOf[v]) / (2 * limOf[v])) * (plotX1 - plotX0);

  const svg = svgEl("svg", { class: "coef-svg", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Two-phase coefficient plot" });

  const xZero = plotX0 + 0.5 * (plotX1 - plotX0);
  svg.appendChild(svgEl("line", { x1: xZero, x2: xZero, y1: padT, y2: H - padB + 4, stroke: "var(--zero)", "stroke-width": 1.5, "stroke-dasharray": "1 3" }));
  const zl = svgEl("text", { x: xZero, y: H - padB + 18, "text-anchor": "middle", "font-size": 11, fill: "var(--text-secondary)" });
  zl.textContent = "0";
  svg.appendChild(zl);

  let y = padT + 6;
  for (const v of VARS) {
    const x = xFor(v);
    const lim = limOf[v];
    /* per-group scale edge labels */
    for (const s of [-lim / 1.12, lim / 1.12]) {
      const t = svgEl("text", { x: x(s), y: y + rowH * 2 - 8, "text-anchor": "middle", "font-size": 10.5, fill: "var(--text-muted)" });
      t.textContent = fmt(s, lim < 0.02 ? 3 : 2);
      svg.appendChild(t);
      svg.appendChild(svgEl("line", { x1: x(s), x2: x(s), y1: y + 4, y2: y + rowH * 2 - 22, stroke: "var(--grid)", "stroke-width": 1 }));
    }
    const name = svgEl("text", { x: 0, y: y + 14, "font-size": 14, "font-weight": 600, fill: "var(--text-primary)" });
    name.textContent = VAR_SHORT[v];
    svg.appendChild(name);
    const unit = svgEl("text", { x: 0, y: y + 32, "font-size": 11.5, fill: "var(--text-muted)" });
    unit.textContent = VAR_UNIT[v];
    svg.appendChild(unit);
    /* periphery direction annotation */
    const dir = PERIPHERY_SIGN[v] > 0 ? "periphery →" : "← periphery";
    const dt = svgEl("text", {
      x: PERIPHERY_SIGN[v] > 0 ? plotX1 : plotX0 + 6,
      y: y + 6, "font-size": 10.5, fill: "var(--text-muted)",
      "text-anchor": PERIPHERY_SIGN[v] > 0 ? "end" : "start",
    });
    dt.textContent = dir;
    svg.appendChild(dt);

    for (const ph of ["post1", "post2"]) {
      const r = rows.find((q) => q.variable === v && q.phase === ph);
      const cy = y + (ph === "post1" ? 14 : 14 + rowH * 0.72);
      const color = ph === "post1" ? "var(--accent-soft)" : "var(--accent)";
      const sig = r.p < 0.05;
      /* CI whisker */
      svg.appendChild(svgEl("line", {
        x1: x(r.coef - TCRIT * r.se), x2: x(r.coef + TCRIT * r.se),
        y1: cy, y2: cy, stroke: sig ? color : "var(--deemph)", "stroke-width": 2, "stroke-linecap": "round",
      }));
      /* dot: filled = significant, hollow ring = not */
      const dot = svgEl("circle", {
        cx: x(r.coef), cy, r: 5.5,
        fill: sig ? color : "var(--surface-1)",
        stroke: sig ? "var(--surface-1)" : "var(--deemph)",
        "stroke-width": 2,
      });
      svg.appendChild(dot);
      /* value label for significant marks (selective direct labels) */
      if (sig) {
        const t = svgEl("text", {
          x: x(r.coef + TCRIT * r.se) + 7, y: cy + 4,
          "font-size": 11.5, fill: "var(--text-secondary)",
        });
        t.textContent = fmt(r.coef);
        svg.appendChild(t);
      }
      /* invisible fat hit target */
      const hit = svgEl("rect", {
        x: x(r.coef - TCRIT * r.se) - 8, y: cy - 12,
        width: Math.max(24, x(r.coef + TCRIT * r.se) - x(r.coef - TCRIT * r.se) + 16), height: 24,
        fill: "transparent",
      });
      hit.addEventListener("mousemove", (e) => showTip(
        `<b>${VAR_SHORT[v]} × ${ph === "post1" ? "Post1" : "Post2"}</b><br>` +
        `coef <b>${fmt(r.coef)}</b> ± ${fmt(TCRIT * r.se)}<br>` +
        `ZCTA-clustered p = <b>${fmtP(r.p)}</b><br>` +
        (r.boot != null ? `ZIP3 wild bootstrap p = <b>${fmtP(r.boot)}</b><br>` : "") +
        `<span style="opacity:.8">${model === "joint" ? "joint model (conditional)" : "single-interaction (marginal)"}</span>`,
        e.clientX, e.clientY));
      hit.addEventListener("mouseleave", hideTip);
      svg.appendChild(hit);
    }
    y += rowH * 2 + 18;
  }
  host.appendChild(svg);
  renderCoefTable(m, rows);
}

function renderCoefTable(m, rows) {
  const host = $("#coef-table");
  host.replaceChildren();
  const wrap = el("div", { class: "twrap" });
  const table = el("table");
  const head = el("tr");
  for (const h of ["Gradient", "Phase", "Coefficient", "SE", "p (ZCTA-clustered)", "p (ZIP3 bootstrap)"]) head.appendChild(el("th", {}, h));
  table.appendChild(head);
  for (const r of rows) {
    const tr = el("tr");
    tr.appendChild(el("td", {}, VAR_SHORT[r.variable]));
    tr.appendChild(el("td", {}, r.phase === "post1" ? "Post1" : "Post2"));
    tr.appendChild(el("td", {}, fmt(r.coef)));
    tr.appendChild(el("td", {}, fmt(r.se)));
    tr.appendChild(el("td", {}, fmtP(r.p)));
    tr.appendChild(el("td", {}, fmtP(r.boot)));
    table.appendChild(tr);
  }
  wrap.appendChild(table);
  host.appendChild(wrap);
}

/* ---------------- event study ---------------- */
function renderEventStudy() {
  const m = DATA.metros[metro];
  const host = $("#event-study");
  host.replaceChildren();
  const grid = el("div", { class: "es-grid" });

  const drift = {
    commute_min_proxy_2019: driftNote(m, "commute"),
    distance_to_cbd_km: driftNote(m, "distance"),
    log_job_accessibility_2019: driftNote(m, "access"),
  };

  for (const v of VARS) {
    const cell = el("div", { class: "es-cell" });
    cell.appendChild(el("h3", {}, VAR_SHORT[v]));
    cell.appendChild(el("p", { class: "drift" }, VAR_UNIT[v]));
    cell.appendChild(esPanel(m, v));
    grid.appendChild(cell);
  }
  host.appendChild(grid);
  renderEsTable(m);
}

function driftNote() { return ""; }

function esPanel(m, v) {
  const rows = m.event_study
    .filter((r) => r.variable === v)
    .sort((a, b) => a.bin_order - b.bin_order);

  const W = 340, H = 240, padL = 46, padR = 8, padT = 10, chartB = 168, stripT = 186, stripB = 216;
  const xs = (i) => padL + (i / (rows.length - 1)) * (W - padL - padR);

  const lim = Math.max(...rows.map((r) => Math.max(Math.abs(r.ci_lo), Math.abs(r.ci_hi)))) * 1.06 || 1;
  const yv = (val) => {
    const t = (val + lim) / (2 * lim);
    return chartB - t * (chartB - padT);
  };
  const maxN = Math.max(...rows.map((r) => r.n_identifying));

  const svg = svgEl("svg", { class: "es-svg", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Event study, ${VAR_SHORT[v]}` });

  /* base-bin band */
  const baseIdx = rows.findIndex((r) => r.bin_order === 0);
  const bw = (W - padL - padR) / (rows.length - 1);
  svg.appendChild(svgEl("rect", {
    x: xs(baseIdx) - bw / 2, y: padT, width: bw, height: chartB - padT,
    fill: "var(--base-band)",
  }));

  /* zero + break lines */
  svg.appendChild(svgEl("line", { x1: padL, x2: W - padR, y1: yv(0), y2: yv(0), stroke: "var(--zero)", "stroke-width": 1, "stroke-dasharray": "1 3" }));
  const breakX = xs(baseIdx) + bw / 2;
  svg.appendChild(svgEl("line", { x1: breakX, x2: breakX, y1: padT, y2: stripB, stroke: "var(--zero)", "stroke-width": 1, "stroke-dasharray": "4 3" }));

  /* y ticks (two) */
  for (const s of [lim * 0.75, -lim * 0.75]) {
    const t = svgEl("text", { x: padL - 6, y: yv(s) + 3.5, "text-anchor": "end", "font-size": 9.5, fill: "var(--text-muted)" });
    t.textContent = fmt(s, lim < 0.02 ? 3 : 2);
    svg.appendChild(t);
    svg.appendChild(svgEl("line", { x1: padL, x2: W - padR, y1: yv(s), y2: yv(s), stroke: "var(--grid)", "stroke-width": 0.75 }));
  }

  /* CI whiskers + line + dots */
  const path = rows.map((r, i) => `${i ? "L" : "M"}${xs(i)},${yv(r.coef)}`).join("");
  svg.appendChild(svgEl("path", { d: path, fill: "none", stroke: "var(--accent)", "stroke-width": 2 }));
  rows.forEach((r, i) => {
    if (r.bin_order !== 0) {
      svg.appendChild(svgEl("line", { x1: xs(i), x2: xs(i), y1: yv(r.ci_lo), y2: yv(r.ci_hi), stroke: "var(--accent)", "stroke-width": 1.5, opacity: 0.55 }));
    }
    svg.appendChild(svgEl("circle", {
      cx: xs(i), cy: yv(r.coef), r: 3.6,
      fill: r.bin_order === 0 ? "var(--surface-1)" : "var(--accent)",
      stroke: r.bin_order === 0 ? "var(--zero)" : "var(--surface-1)",
      "stroke-width": 1.5,
    }));
  });

  /* identifying-count strip (aligned, own scale — not a second axis) */
  rows.forEach((r, i) => {
    const h = (r.n_identifying / maxN) * (stripB - stripT);
    svg.appendChild(svgEl("rect", {
      x: xs(i) - bw / 2 + 1, y: stripB - h, width: bw - 2, height: h,
      fill: "var(--count-fill)", rx: 2,
    }));
  });
  const nlab = svgEl("text", { x: padL - 6, y: stripB - 2, "text-anchor": "end", "font-size": 9.5, fill: "var(--text-muted)" });
  nlab.textContent = "n ZCTAs";
  svg.appendChild(nlab);

  /* x labels: first, base, last */
  for (const i of [0, baseIdx, rows.length - 1]) {
    const t = svgEl("text", { x: xs(i), y: H - 8, "text-anchor": "middle", "font-size": 10, fill: "var(--text-muted)" });
    t.textContent = rows[i].bin;
    svg.appendChild(t);
  }

  /* hover targets per bin */
  rows.forEach((r, i) => {
    const hit = svgEl("rect", { x: xs(i) - bw / 2, y: padT, width: bw, height: stripB - padT, fill: "transparent" });
    hit.addEventListener("mousemove", (e) => showTip(
      `<b>${VAR_SHORT[v]} · ${r.bin}</b><br>` +
      (r.bin_order === 0
        ? "reference bin (2019-03…2020-02)"
        : `coef <b>${fmt(r.coef)}</b> [${fmt(r.ci_lo)}, ${fmt(r.ci_hi)}]`) +
      `<br>identifying ZCTAs: <b>${r.n_identifying}</b>`,
      e.clientX, e.clientY));
    hit.addEventListener("mouseleave", hideTip);
    svg.appendChild(hit);
  });

  return svg;
}

function renderEsTable(m) {
  const host = $("#es-table");
  host.replaceChildren();
  const wrap = el("div", { class: "twrap" });
  const table = el("table");
  const head = el("tr");
  for (const h of ["Bin", ...VARS.map((v) => VAR_SHORT[v] + " (coef)"), "n ZCTAs"]) head.appendChild(el("th", {}, h));
  table.appendChild(head);
  const bins = [...new Set(m.event_study.map((r) => r.bin_order))].sort((a, b) => a - b);
  for (const b of bins) {
    const rs = m.event_study.filter((r) => r.bin_order === b);
    const tr = el("tr");
    tr.appendChild(el("td", {}, rs[0].bin));
    for (const v of VARS) {
      const r = rs.find((q) => q.variable === v);
      tr.appendChild(el("td", {}, b === 0 ? "ref" : fmt(r.coef)));
    }
    tr.appendChild(el("td", {}, String(rs[0].n_identifying)));
    table.appendChild(tr);
  }
  wrap.appendChild(table);
  host.appendChild(wrap);
}

/* ---------------- shell ---------------- */
function renderAll() {
  renderSwitcher();
  renderVerdict();
  renderCoefPlot();
  renderEventStudy();
}

document.addEventListener("click", (e) => {
  const b = e.target.closest(".model-chip");
  if (!b) return;
  model = b.dataset.model;
  document.querySelectorAll(".model-chip").forEach((c) => {
    c.classList.toggle("is-on", c === b);
  });
  renderCoefPlot();
});

$("#theme-toggle").addEventListener("click", () => {
  const root = document.documentElement;
  const cur = root.getAttribute("data-theme");
  const sysDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const next = cur ? (cur === "dark" ? "light" : "dark") : (sysDark ? "light" : "dark");
  root.setAttribute("data-theme", next);
});

fetch("data/rq4.json")
  .then((r) => r.json())
  .then((d) => { DATA = d; renderAll(); })
  .catch((err) => {
    $("#verdict-card").textContent = "Failed to load data: " + err;
  });
