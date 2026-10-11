/* Football Tracker card – served by the football_tracker integration. */
const CARD_VERSION = "0.1.2";

const I18N = {
  de: {
    live: "LIVE", next: "Nächstes Spiel", last: "Letztes Spiel",
    upcoming: "Spielplan", results: "Ergebnisse", table: "Tabelle", lineup: "Aufstellung",
    all: "Alle", today: "Heute", tomorrow: "Morgen", in: "in", days: "Tagen", day: "Tag", hours: "Std.", min: "Min.",
    noUpcoming: "Keine weiteren Spiele angesetzt", noResults: "Noch keine Ergebnisse",
    noEntity: "Entity nicht gefunden", bench: "Ersatzbank", ht: "Halbzeit", pens: "i.E.",
    matchday: (n) => `${n}. Spieltag`, leg: (n) => (n === 1 ? "Hinspiel" : "Rückspiel"),
    W: "S", L: "N", D: "U",
    cols: ["#", "Verein", "Sp", "S", "U", "N", "Tore", "Diff", "Pkt"],
    events: { goal: "Tor", penalty: "Elfmeter", own_goal: "Eigentor", yellow: "Gelb", red: "Rot" },
    assist: "Vorlage",
    rounds: {
      "league phase": "Ligaphase", "group stage": "Gruppenphase", "knockout round playoffs": "Playoffs",
      "round of 32": "Sechzehntelfinale", "round of 16": "Achtelfinale", "quarterfinals": "Viertelfinale",
      "semifinals": "Halbfinale", "final": "Finale", "first round": "1. Runde", "second round": "2. Runde",
      "third round": "3. Runde",
    },
    // ESPN uses English club names.
    clubs: {
      "Bayern Munich": "FC Bayern München", "FC Cologne": "1. FC Köln", "Hamburg SV": "Hamburger SV",
      "Mainz": "1. FSV Mainz 05", "St. Pauli": "FC St. Pauli", "VfL Osnabruck": "VfL Osnabrück",
      "Nuremberg": "1. FC Nürnberg", "Fortuna Dusseldorf": "Fortuna Düsseldorf", "Hertha Berlin": "Hertha BSC",
      "Internazionale": "Inter Mailand", "AC Milan": "AC Mailand", "Bodo/Glimt": "Bodø/Glimt",
      "Slavia Prague": "Slavia Prag", "Sparta Prague": "Sparta Prag", "Club Brugge": "FC Brügge",
      "Sporting CP": "Sporting Lissabon", "Benfica": "Benfica Lissabon", "Atalanta": "Atalanta Bergamo",
      "Union St.-Gilloise": "Union Saint-Gilloise", "Red Star Belgrade": "Roter Stern Belgrad",
      "Napoli": "SSC Neapel", "Juventus": "Juventus Turin", "AS Roma": "AS Rom", "Lazio": "Lazio Rom",
      "Celtic": "Celtic Glasgow", "Rangers": "Glasgow Rangers", "Copenhagen": "FC Kopenhagen",
      "Shakhtar Donetsk": "Schachtar Donezk", "Dinamo Zagreb": "Dinamo Zagreb", "Galatasaray": "Galatasaray Istanbul",
    },
  },
  en: {
    live: "LIVE", next: "Next match", last: "Last match",
    upcoming: "Fixtures", results: "Results", table: "Table", lineup: "Lineups",
    all: "All", today: "Today", tomorrow: "Tomorrow", in: "in", days: "days", day: "day", hours: "h", min: "min",
    noUpcoming: "No further matches scheduled", noResults: "No results yet",
    noEntity: "Entity not found", bench: "Bench", ht: "Half time", pens: "pens",
    matchday: (n) => `Matchday ${n}`, leg: (n) => (n === 1 ? "1st leg" : "2nd leg"),
    W: "W", L: "L", D: "D",
    cols: ["#", "Club", "P", "W", "D", "L", "Goals", "GD", "Pts"],
    events: { goal: "Goal", penalty: "Penalty", own_goal: "Own goal", yellow: "Yellow", red: "Red" },
    assist: "Assist",
    rounds: {},
    clubs: {},
  },
};

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

class FootballTrackerCard extends HTMLElement {
  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => id.startsWith("sensor.") && hass.states[id].attributes.football_tracker
    );
    return { entity: entity || "sensor.bayern_munchen_spiele" };
  }

  setConfig(config) {
    if (!config.entity) throw new Error("entity is required");
    this._config = { upcoming_count: 8, show_timeline: true, ...config };
    this._tab = config.default_tab || "upcoming";
    this._filter = "all";
    this._table = null;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const state = hass.states[this._config.entity];
    if (state !== this._state) {
      this._state = state;
      this._render();
    }
  }

  connectedCallback() {
    this._timer = setInterval(() => this._render(), 30000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  getCardSize() {
    return 9;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  /* ---------------------------------------------------------------- helpers */

  get _lang() {
    return (this._config.language || "de").startsWith("en") ? "en" : "de";
  }

  get _t() {
    return I18N[this._lang];
  }

  get _tz() {
    return this._hass?.config?.time_zone || Intl.DateTimeFormat().resolvedOptions().timeZone;
  }

  _fmt(date, opts) {
    return new Intl.DateTimeFormat(this._lang === "de" ? "de-DE" : "en-GB", { timeZone: this._tz, ...opts }).format(date);
  }

  _dayKey(date) {
    return this._fmt(date, { year: "numeric", month: "2-digit", day: "2-digit" });
  }

  _club(team) {
    return this._t.clubs[team.name] || team.name;
  }

  _round(m) {
    const t = this._t;
    if (m.matchday && (!m.round || /league phase|group/i.test(m.round))) {
      const phase = m.round ? `${t.rounds[m.round.toLowerCase()] || m.round} · ` : "";
      return `${phase}${t.matchday(m.matchday)}`;
    }
    if (!m.round) return "";
    const name = t.rounds[m.round.toLowerCase()] || m.round;
    return m.leg ? `${name} · ${t.leg(m.leg)}` : name;
  }

  _comp(m, withRound = true) {
    const round = withRound ? this._round(m) : "";
    return round ? `${m.league} · ${round}` : m.league;
  }

  _badge(team, size = "m") {
    if (!team.logo) return `<span class="badge ${size} no-img"><span class="abbr">${esc(team.abbr || "")}</span></span>`;
    // In dark mode prefer ESPN's dark crest; fall back to the normal one on a light tile.
    const dark = this._dark && team.logo.includes("/500/");
    const src = dark ? team.logo.replace("/500/", "/500-dark/") : team.logo;
    const onError = dark
      ? `this.onerror=function(){this.closest('.badge').classList.add('no-img');this.remove()};this.src='${esc(team.logo)}';this.closest('.badge').classList.add('tile')`
      : `this.closest('.badge').classList.add('no-img');this.remove()`;
    return `<span class="badge ${size}"><img src="${esc(src)}" alt="" onerror="${onError}"><span class="abbr">${esc(team.abbr || "")}</span></span>`;
  }

  _countdown(date) {
    const t = this._t;
    const diff = date - Date.now();
    if (diff <= 0) return "";
    const d = Math.floor(diff / 86400000);
    const h = Math.floor((diff % 86400000) / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    if (d > 1) return `${t.in} ${d} ${t.days}`;
    if (d === 1) return `${t.in} ${d} ${t.day} ${h} ${t.hours}`;
    if (h > 0) return `${t.in} ${h} ${t.hours} ${m} ${t.min}`;
    return `${t.in} ${m} ${t.min}`;
  }

  _when(date) {
    const t = this._t;
    const today = this._dayKey(new Date());
    const tomorrow = this._dayKey(new Date(Date.now() + 86400000));
    const key = this._dayKey(date);
    const time = this._fmt(date, { hour: "2-digit", minute: "2-digit" });
    if (key === today) return `${t.today}, ${time}`;
    if (key === tomorrow) return `${t.tomorrow}, ${time}`;
    return `${this._fmt(date, { weekday: "long", day: "numeric", month: "long" })} · ${time}`;
  }

  _tv(m) {
    const channels = m.tv_de || [];
    if (!channels.length) return "";
    return `<div class="tv"><ha-icon icon="mdi:television-classic"></ha-icon>${channels.map((c) => `<span class="chip">${esc(c)}</span>`).join("")}</div>`;
  }

  _shootout(m) {
    return m.home.shootout != null && m.away.shootout != null
      ? `${m.home.shootout}:${m.away.shootout} ${this._t.pens}`
      : "";
  }

  /* ---------------------------------------------------------------- sections */

  _hero(m, kind, attrs) {
    const t = this._t;
    const date = new Date(m.date);
    let status;
    if (kind === "live") {
      const label = m.status === "STATUS_HALFTIME" ? t.ht : m.clock || m.status_detail || "";
      status = `<span class="live-pill"><span class="dot"></span>${t.live}${label ? ` · ${esc(label)}` : ""}</span>`;
    } else if (kind === "next") {
      status = `<span class="label">${t.next}</span><span class="countdown">${this._countdown(date)}</span>`;
    } else {
      status = `<span class="label">${t.last}</span>${m.result ? `<span class="pill r-${m.result}">${t[m.result]}</span>` : ""}`;
    }

    const shootout = this._shootout(m);
    const centre = kind !== "next"
      ? `<div class="score ${kind === "live" ? "is-live" : ""}">${m.home.score ?? 0}<span>:</span>${m.away.score ?? 0}</div>${shootout ? `<div class="pens">${esc(shootout)}</div>` : ""}`
      : `<div class="vs">${this._fmt(date, { hour: "2-digit", minute: "2-digit" })}</div>`;
    const place = [m.venue, m.city].filter(Boolean).join(", ");

    return `
      <section class="hero ${kind}">
        <div class="hero-top"><span class="comp">${esc(this._comp(m))}</span><span class="status">${status}</span></div>
        <div class="hero-main">
          <div class="side">${this._badge(m.home, "xl")}<div class="name">${esc(this._club(m.home))}</div></div>
          <div class="centre">${this._heroLogo(m)}${centre}</div>
          <div class="side">${this._badge(m.away, "xl")}<div class="name">${esc(this._club(m.away))}</div></div>
        </div>
        <div class="hero-meta"><span>${esc(this._when(date))}</span>${place ? `<span>· ${esc(place)}</span>` : ""}</div>
        ${kind !== "last" ? this._tv(m) : ""}
        ${this._config.show_timeline && kind !== "next" ? this._timeline(m, attrs) : ""}
      </section>`;
  }

  _timeline(m, attrs) {
    const events = (attrs.timelines || {})[m.id] || [];
    if (!events.length) return "";
    const t = this._t;
    const icon = (k) =>
      k === "yellow" ? '<span class="card-y"></span>'
      : k === "red" ? '<span class="card-r"></span>'
      : '<ha-icon class="ball" icon="mdi:soccer"></ha-icon>';
    const row = (e) => {
      const isHome = e.team_id === m.home.id;
      const extra = e.kind === "penalty" || e.kind === "own_goal" ? ` <span class="kind">(${t.events[e.kind]})</span>` : "";
      const assist = e.assist ? `<span class="assist">${t.assist}: ${esc(e.assist)}</span>` : "";
      const text = `<span class="who">${icon(e.kind)}<b>${esc(e.player || t.events[e.kind])}</b>${extra}</span>${assist}`;
      return `<div class="ev ${isHome ? "home" : "away"} k-${e.kind}">
        <span class="h">${isHome ? text : ""}</span>
        <span class="min">${esc(e.minute || "")}</span>
        <span class="a">${isHome ? "" : text}</span></div>`;
    };
    return `<div class="timeline">${events.map(row).join("")}</div>`;
  }

  _row(m, past) {
    const date = new Date(m.date);
    const day = this._fmt(date, { day: "2-digit" });
    const mon = this._fmt(date, { month: "short" });
    const time = this._fmt(date, { weekday: "short", hour: "2-digit", minute: "2-digit" });
    const us = m.is_home ? "home" : "away";
    const team = (side) => `
      <div class="t ${side} ${side === us ? "us" : ""}">
        ${side === "away" ? this._badge(m[side], "s") : ""}
        <span class="tn">${esc(this._club(m[side]))}</span>
        <span class="ta">${esc(m[side].abbr)}</span>
        ${side === "home" ? this._badge(m[side], "s") : ""}
      </div>`;
    const shootout = past ? this._shootout(m) : "";
    const mid = past || m.state === "in"
      ? `<div class="mid score-s ${m.state === "in" ? "live" : ""}">${m.home.score ?? "–"}<span>:</span>${m.away.score ?? "–"}</div>`
      : `<div class="mid vs-s">${esc(this._fmt(date, { hour: "2-digit", minute: "2-digit" }))}</div>`;
    const right = past
      ? `<span class="pill r-${m.result || "D"}">${this._t[m.result] || "–"}</span>`
      : (m.tv_de || []).length
      ? `<span class="tv-s"><ha-icon icon="mdi:television-classic"></ha-icon>${esc(m.tv_de[0])}</span>`
      : "";
    // Fixtures show the competition as a logo column, so the sub line only needs the round.
    const sub = [past ? this._round(m) : `${time} · ${this._round(m) || m.league}`, shootout].filter(Boolean).join(" · ");
    const comp = past ? "" : `<div class="comp-logo" title="${esc(m.league)}">${this._leagueLogo(m)}</div>`;
    return `
      <div class="row ${past ? "" : "with-comp"}">
        <div class="date"><span class="d">${day}</span><span class="mo">${esc(mon)}</span></div>
        <div class="match">
          <div class="teams">${team("home")}${mid}${team("away")}</div>
          ${sub ? `<div class="sub">${esc(sub)}</div>` : ""}
        </div>
        ${comp}
        <div class="right">${right}</div>
      </div>`;
  }

  _heroLogo(m) {
    // Big competition logo so the tournament is visible at a glance; nothing if ESPN has none.
    const logo = (this._attrs?.league_logos || {})[m.league_id];
    if (!logo?.light) return "";
    const src = this._dark && logo.dark ? logo.dark : logo.light;
    const fallback = src !== logo.light ? `this.onerror=function(){this.remove()};this.src='${esc(logo.light)}'` : "this.remove()";
    return `<img class="hero-comp" src="${esc(src)}" alt="${esc(m.league)}" title="${esc(m.league)}" onerror="${fallback}">`;
  }

  _leagueLogo(m) {
    const logo = (this._attrs?.league_logos || {})[m.league_id];
    const text = `<span class="comp-name">${esc(m.league)}</span>`;
    if (!logo?.light) return text;
    const src = this._dark && logo.dark ? logo.dark : logo.light;
    const fallback = src !== logo.light ? `this.onerror=null;this.src='${esc(logo.light)}'` : `this.replaceWith(this.nextElementSibling.content.cloneNode(true))`;
    return `<img src="${esc(src)}" alt="${esc(m.league)}" onerror="${fallback}"><template>${text}</template>`;
  }

  _upcoming(matches, heroId) {
    const list = matches.filter((m) => m.state === "pre" && m.id !== heroId).slice(0, this._config.upcoming_count);
    if (!list.length) return `<div class="empty">${this._t.noUpcoming}</div>`;
    return list.map((m) => this._row(m, false)).join("");
  }

  _results(matches) {
    const past = matches.filter((m) => m.state === "post").reverse();
    if (!past.length) return `<div class="empty">${this._t.noResults}</div>`;
    const groups = new Map();
    for (const m of past) {
      const key = `${m.league_id}|${m.season}`;
      if (!groups.has(key)) groups.set(key, { title: `${m.league} ${m.season_label}`, items: [] });
      groups.get(key).items.push(m);
    }
    if (this._filter !== "all" && !groups.has(this._filter)) this._filter = "all";
    const chips = [`<button class="fchip ${this._filter === "all" ? "on" : ""}" data-filter="all">${this._t.all}</button>`]
      .concat([...groups].map(([k, g]) => `<button class="fchip ${this._filter === k ? "on" : ""}" data-filter="${esc(k)}">${esc(g.title)}</button>`))
      .join("");
    const t = this._t;
    const body = [...groups]
      .filter(([k]) => this._filter === "all" || this._filter === k)
      .map(([, g]) => {
        const count = (r) => g.items.filter((m) => m.result === r).length;
        return `<div class="group"><div class="gh"><span>${esc(g.title)}</span><span class="rec">${count("W")}${t.W} ${count("D")}${t.D} ${count("L")}${t.L}</span></div>${g.items.map((m) => this._row(m, true)).join("")}</div>`;
      })
      .join("");
    return `<div class="filters">${chips}</div>${body}`;
  }

  _standings(attrs) {
    const tables = attrs.standings || {};
    const names = {};
    for (const m of attrs.matches || []) names[m.league_id] = m.league;
    const keys = Object.keys(tables).filter((k) => tables[k].groups?.length);
    if (!keys.length) return "";
    if (!this._table || !tables[this._table]) {
      // Prefer the competition of the next/live match.
      const focus = (attrs.matches || []).find((m) => m.state !== "post" && tables[m.league_id]);
      this._table = focus ? focus.league_id : keys[0];
    }
    const t = this._t;
    const chips = keys.length > 1
      ? `<div class="filters">${keys.map((k) => `<button class="fchip ${k === this._table ? "on" : ""}" data-table="${esc(k)}">${esc(names[k] || k)}</button>`).join("")}</div>`
      : "";
    const teamId = attrs.team?.id;
    const html = tables[this._table].groups
      .map((g) => `
        ${g.name ? `<div class="gh"><span>${esc(g.name)}</span></div>` : ""}
        <table class="tbl"><thead><tr>${t.cols.map((c, i) => `<th class="${i === 1 ? "l" : ""} ${[3, 4, 5, 6].includes(i) ? "opt" : ""}">${c}</th>`).join("")}</tr></thead>
        <tbody>${g.rows.map((r) => `
          <tr class="${r.id === teamId ? "us" : ""}" title="${esc(r.zone_name || "")}">
            <td class="rank" style="${r.zone ? `--zone:${esc(r.zone)}` : ""}">${esc(r.rank ?? "")}</td>
            <td class="l"><span class="tcell">${this._badge(r, "xs")}<span class="tn">${esc(this._club(r))}</span></span></td>
            <td>${esc(r.gp ?? "")}</td><td class="opt">${esc(r.w ?? "")}</td><td class="opt">${esc(r.d ?? "")}</td><td class="opt">${esc(r.l ?? "")}</td>
            <td class="opt">${esc(r.gf ?? "")}:${esc(r.ga ?? "")}</td><td>${esc(r.gd ?? "")}</td><td class="pts">${esc(r.pts ?? "")}</td>
          </tr>`).join("")}</tbody></table>`)
      .join("");
    // Legend of qualification zones.
    const zones = new Map();
    for (const g of tables[this._table].groups) for (const r of g.rows) if (r.zone && r.zone_name) zones.set(r.zone_name, r.zone);
    const legend = zones.size
      ? `<div class="legend">${[...zones].map(([n, c]) => `<span><i style="background:${esc(c)}"></i>${esc(n)}</span>`).join("")}</div>`
      : "";
    return chips + html + legend;
  }

  _lineups(m, attrs) {
    const lineups = m ? (attrs.lineups || {})[m.id] : null;
    if (!lineups) return "";
    const col = (team) => {
      const lineup = lineups[team.id];
      if (!lineup) return "";
      const players = lineup.players || [];
      const li = (p) => `<li><span class="no">${p.no ?? ""}</span><span class="pn">${esc(p.name)}${p.out ? ' <span class="sub-out">▼</span>' : ""}${p.in ? ' <span class="sub-in">▲</span>' : ""}</span><span class="pos">${esc(p.pos || "")}</span></li>`;
      const bench = players.filter((p) => !p.starter);
      return `<div class="lcol"><div class="lh">${this._badge(team, "s")}<span>${esc(this._club(team))}</span>${lineup.formation ? `<span class="formation">${esc(lineup.formation)}</span>` : ""}</div>
        <ol>${players.filter((p) => p.starter).map(li).join("")}</ol>
        ${bench.length ? `<div class="bench">${this._t.bench}</div><ol>${bench.map(li).join("")}</ol>` : ""}</div>`;
    };
    return `<div class="lineups">${col(m.home)}${col(m.away)}</div>`;
  }

  /* ---------------------------------------------------------------- render */

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const state = this._state;
    if (!state) {
      this.shadowRoot.innerHTML = `<ha-card><div class="empty">${this._hass ? `${this._t.noEntity}: ${esc(this._config.entity)}` : ""}</div></ha-card>`;
      return;
    }
    this._dark = !!this._hass?.themes?.darkMode;
    const attrs = state.attributes;
    this._attrs = attrs;
    const matches = attrs.matches || [];
    const team = attrs.team || {};
    const live = matches.filter((m) => m.state === "in");
    const next = matches.find((m) => m.state === "pre");
    const last = [...matches].reverse().find((m) => m.state === "post");

    let heroes = "";
    let heroId = null;
    if (live.length) {
      heroes = live.map((m) => this._hero(m, "live", attrs)).join("");
    } else if (next) {
      heroes = this._hero(next, "next", attrs);
      heroId = next.id;
    } else if (last) {
      heroes = this._hero(last, "last", attrs);
    }
    // Lineups of the live/next match once published, else of the last match.
    const lineupMatch = [live[0], next, last].find((m) => m && (attrs.lineups || {})[m.id]);
    const lineupHtml = this._lineups(lineupMatch, attrs);
    const tableHtml = this._standings(attrs);

    const tabs = [["upcoming", this._t.upcoming], ["results", this._t.results]];
    if (tableHtml) tabs.push(["table", this._t.table]);
    if (lineupHtml) tabs.push(["lineup", this._t.lineup]);
    if (!tabs.some(([k]) => k === this._tab)) this._tab = "upcoming";

    const content = {
      upcoming: () => this._upcoming(matches, heroId),
      results: () => this._results(matches),
      table: () => tableHtml,
      lineup: () => lineupHtml,
    }[this._tab]();

    const accent = this._config.accent_color || (team.color ? `#${team.color}` : "#dc052d");
    const title = this._config.title ?? (team.name ? this._club(team) : "");
    const scroll = this.shadowRoot.querySelector(".content")?.scrollTop || 0;

    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card class="${this._dark ? "dark" : ""}" style="--ft-accent:${esc(accent)}">
        ${title ? `<div class="head">${team.logo ? this._badge(team, "s") : ""}<span class="title">${esc(title)}</span></div>` : ""}
        ${heroes}
        <nav class="tabs">${tabs.map(([k, label]) => `<button class="tab ${k === this._tab ? "on" : ""}" data-tab="${k}">${label}</button>`).join("")}</nav>
        <div class="content" style="${this._config.max_height ? `max-height:${esc(this._config.max_height)};overflow-y:auto` : ""}">${content}</div>
      </ha-card>`;

    const contentEl = this.shadowRoot.querySelector(".content");
    if (contentEl) contentEl.scrollTop = scroll;
    this.shadowRoot.querySelectorAll("[data-tab]").forEach((el) =>
      el.addEventListener("click", () => { this._tab = el.dataset.tab; this._render(); }));
    this.shadowRoot.querySelectorAll("[data-filter]").forEach((el) =>
      el.addEventListener("click", () => { this._filter = el.dataset.filter; this._render(); }));
    this.shadowRoot.querySelectorAll("[data-table]").forEach((el) =>
      el.addEventListener("click", () => { this._table = el.dataset.table; this._render(); }));
  }
}

const STYLE = `
  :host { --ft-live: #e53935; --ft-win: #2e7d32; --ft-loss: #c62828; --ft-draw: #757575; }
  ha-card { display: block; overflow: hidden; container-type: inline-size; }
  button { font: inherit; color: inherit; cursor: pointer; }
  .head { display: flex; align-items: center; gap: 10px; padding: 14px 16px 6px; }
  .title { font-size: 1.15rem; font-weight: 600; }

  /* crests */
  .badge { position: relative; display: inline-flex; align-items: center; justify-content: center; flex: none; font-size: .7rem; font-weight: 700; box-sizing: border-box; }
  .badge img { width: 100%; height: 100%; object-fit: contain; display: block; }
  .badge .abbr { display: none; }
  .badge.no-img .abbr { display: inline; }
  .badge.xs { width: 22px; height: 22px; }
  .badge.s { width: 26px; height: 26px; }
  .badge.xl { width: 84px; height: 84px; }
  .badge.tile { background: #f2f2f2; border-radius: 7px; padding: 3px; }
  .badge.tile.xl { border-radius: 16px; padding: 9px; }

  /* hero */
  .hero { margin: 8px 12px 4px; padding: 14px 16px 12px; border-radius: 16px;
    background: linear-gradient(135deg, color-mix(in srgb, var(--ft-accent) 18%, transparent), color-mix(in srgb, var(--ft-accent) 4%, transparent));
    border: 1px solid color-mix(in srgb, var(--ft-accent) 28%, transparent); }
  .hero.live { border-color: color-mix(in srgb, var(--ft-live) 55%, transparent); }
  .hero-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: .85rem; }
  .comp { color: var(--secondary-text-color); font-weight: 500; }
  .status { display: flex; align-items: center; gap: 8px; flex: none; }
  .label { text-transform: uppercase; letter-spacing: .06em; font-size: .72rem; font-weight: 600; color: var(--secondary-text-color); }
  .countdown { font-weight: 600; color: var(--primary-text-color); }
  .live-pill { display: inline-flex; align-items: center; gap: 6px; background: var(--ft-live); color: #fff; padding: 3px 10px; border-radius: 999px; font-weight: 700; font-size: .78rem; letter-spacing: .04em; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #fff; animation: pulse 1.4s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .25; } }
  .hero-main { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 8px; margin: 14px 0 8px; }
  .side { display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center; min-width: 0; }
  .name { font-size: 1.1rem; font-weight: 600; line-height: 1.2; }
  .centre { display: flex; flex-direction: column; align-items: center; gap: 8px; }
  .hero-comp { width: 104px; height: 80px; object-fit: contain; }
  .score { font-size: 3.2rem; font-weight: 800; font-variant-numeric: tabular-nums; letter-spacing: -.02em; line-height: 1; }
  .score span, .score-s span { opacity: .45; margin: 0 .12em; }
  .score.is-live { color: var(--ft-live); }
  .pens { font-size: .85rem; color: var(--secondary-text-color); margin-top: 4px; }
  .vs { font-size: 2rem; font-weight: 700; opacity: .85; font-variant-numeric: tabular-nums; }
  .hero-meta { display: flex; flex-wrap: wrap; justify-content: center; gap: 4px; color: var(--secondary-text-color); font-size: .88rem; }
  .tv { display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 6px; margin-top: 10px; }
  .tv ha-icon { --mdc-icon-size: 18px; color: var(--secondary-text-color); }
  .chip { padding: 3px 10px; border-radius: 999px; background: var(--card-background-color); border: 1px solid var(--divider-color); font-size: .8rem; font-weight: 500; }

  .timeline { margin-top: 12px; border-top: 1px solid var(--divider-color); padding-top: 8px; max-height: 190px; overflow-y: auto; font-size: .84rem; }
  .ev { display: grid; grid-template-columns: 1fr 48px 1fr; gap: 6px; padding: 3px 0; align-items: center; }
  .ev .h { text-align: right; } .ev .min { text-align: center; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .ev .h, .ev .a { display: flex; flex-direction: column; }
  .ev .h { align-items: flex-end; } .ev .a { align-items: flex-start; }
  .who { display: inline-flex; align-items: center; gap: 5px; }
  .ev.k-yellow b, .ev.k-red b { font-weight: 500; }
  .ball { --mdc-icon-size: 15px; }
  .kind, .assist { color: var(--secondary-text-color); font-size: .76rem; }
  .card-y, .card-r { display: inline-block; width: 9px; height: 12px; border-radius: 2px; }
  .card-y { background: #fbc02d; } .card-r { background: #d32f2f; }

  /* tabs & filters */
  .tabs { display: flex; gap: 4px; padding: 10px 12px 0; border-bottom: 1px solid var(--divider-color); overflow-x: auto; scrollbar-width: none; }
  .tab { background: none; border: 0; padding: 10px 14px; border-bottom: 3px solid transparent; color: var(--secondary-text-color); font-weight: 600; white-space: nowrap; }
  .tab.on { color: var(--primary-text-color); border-bottom-color: var(--ft-accent); }
  .content { padding: 6px 12px 14px; }
  .filters { display: flex; gap: 6px; flex-wrap: wrap; padding: 8px 0 4px; }
  .fchip { border: 1px solid var(--divider-color); background: none; padding: 5px 12px; border-radius: 999px; font-size: .82rem; }
  .fchip.on { background: var(--ft-accent); border-color: var(--ft-accent); color: #fff; }
  .empty { padding: 24px 16px; text-align: center; color: var(--secondary-text-color); }

  /* match rows */
  .group { margin-top: 6px; }
  .gh { display: flex; justify-content: space-between; align-items: baseline; padding: 12px 4px 4px; font-size: .78rem; text-transform: uppercase; letter-spacing: .06em; color: var(--secondary-text-color); font-weight: 600; }
  .rec { font-variant-numeric: tabular-nums; letter-spacing: 0; }
  .row { display: grid; grid-template-columns: 48px 1fr auto; gap: 10px; align-items: center; padding: 10px 4px; border-bottom: 1px solid var(--divider-color); }
  .row.with-comp { grid-template-columns: 48px 1fr 40px auto; }
  .row:last-child { border-bottom: 0; }
  .comp-logo { display: flex; align-items: center; justify-content: center; width: 40px; height: 32px; }
  .comp-logo img { max-width: 100%; max-height: 100%; object-fit: contain; }
  .comp-name { font-size: .64rem; font-weight: 600; line-height: 1.1; text-align: center; color: var(--secondary-text-color); }
  .date { display: flex; flex-direction: column; align-items: center; line-height: 1.05; }
  .date .d { font-size: 1.3rem; font-weight: 700; }
  .date .mo { font-size: .72rem; text-transform: uppercase; color: var(--secondary-text-color); }
  .match { min-width: 0; }
  .teams { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 10px; }
  .t { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .t.home { justify-content: flex-end; text-align: right; }
  .t.us .tn, .t.us .ta { font-weight: 700; }
  .tn { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ta { display: none; }
  .mid { min-width: 56px; text-align: center; }
  .score-s { font-weight: 800; font-size: 1.1rem; font-variant-numeric: tabular-nums; }
  .score-s.live { color: var(--ft-live); }
  .vs-s { color: var(--secondary-text-color); font-size: .85rem; font-variant-numeric: tabular-nums; }
  .sub { margin-top: 4px; text-align: center; font-size: .78rem; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .right { display: flex; justify-content: flex-end; min-width: 28px; }
  .pill { display: inline-flex; align-items: center; justify-content: center; min-width: 24px; height: 24px; padding: 0 6px; border-radius: 6px; color: #fff; font-weight: 700; font-size: .8rem; }
  .r-W { background: var(--ft-win); } .r-L { background: var(--ft-loss); } .r-D { background: var(--ft-draw); }
  .tv-s { display: inline-flex; align-items: center; gap: 4px; font-size: .78rem; color: var(--secondary-text-color); white-space: nowrap; }
  .tv-s ha-icon { --mdc-icon-size: 16px; }

  /* table */
  .tbl { width: 100%; border-collapse: collapse; font-size: .9rem; font-variant-numeric: tabular-nums; }
  .tbl th { font-size: .72rem; color: var(--secondary-text-color); font-weight: 600; padding: 8px 4px; text-align: center; }
  .tbl td { padding: 6px 4px; text-align: center; border-top: 1px solid var(--divider-color); }
  .tbl .l { text-align: left; }
  .tbl td.rank { box-shadow: inset 4px 0 0 var(--zone, transparent); padding-left: 8px; }
  .tbl tr.us td { background: color-mix(in srgb, var(--ft-accent) 14%, transparent); font-weight: 700; }
  .tbl .pts { font-weight: 700; }
  .tcell { display: flex; align-items: center; gap: 8px; }
  .legend { display: flex; flex-wrap: wrap; gap: 12px; padding: 10px 4px 0; font-size: .75rem; color: var(--secondary-text-color); }
  .legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }

  /* lineups */
  .lineups { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding-top: 8px; }
  .lh { display: flex; align-items: center; gap: 8px; font-weight: 700; padding-bottom: 6px; border-bottom: 2px solid var(--ft-accent); }
  .formation { margin-left: auto; font-weight: 600; font-size: .8rem; color: var(--secondary-text-color); }
  .lineups ol { list-style: none; margin: 0; padding: 0; }
  .lineups li { display: grid; grid-template-columns: 26px 1fr auto; gap: 6px; padding: 4px 0; font-size: .86rem; border-bottom: 1px solid var(--divider-color); }
  .no { font-weight: 700; color: var(--secondary-text-color); text-align: right; font-variant-numeric: tabular-nums; }
  .pos { font-size: .72rem; color: var(--secondary-text-color); }
  .sub-in { color: var(--ft-win); font-size: .7rem; } .sub-out { color: var(--ft-loss); font-size: .7rem; }
  .bench { margin-top: 10px; font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; color: var(--secondary-text-color); font-weight: 600; }

  /* narrow cards (phones, small grid cells) */
  @container (max-width: 460px) {
    .tn { display: none; } .ta { display: inline; }
    .tbl .tn { display: inline; }
    .score { font-size: 2.4rem; }
    .hero-comp { width: 72px; height: 56px; }
    .badge.xl { width: 64px; height: 64px; }
    .name { font-size: .95rem; }
    .tbl .opt { display: none; }
    .lineups { grid-template-columns: 1fr; }
    .row { grid-template-columns: 34px 1fr auto; gap: 6px; }
    .row.with-comp { grid-template-columns: 34px 1fr 30px auto; }
    .comp-logo { width: 30px; height: 26px; }
    .teams { gap: 6px; }
    .tv-s { display: none; }
  }
`;

customElements.get("football-tracker-card") || customElements.define("football-tracker-card", FootballTrackerCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "football-tracker-card")) {
  window.customCards.push({
    type: "football-tracker-card",
    name: "Football Tracker",
    description: "Live scores, fixtures, results, tables and lineups for a football club.",
    preview: true,
  });
}
console.info(`%c FOOTBALL-TRACKER-CARD %c ${CARD_VERSION} `, "background:#dc052d;color:#fff;font-weight:700", "");
