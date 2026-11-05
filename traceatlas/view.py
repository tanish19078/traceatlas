"""Render a standalone, source-mapped company explorer."""
import html
import json
from urllib.parse import urlsplit

from .models import BASE, atomic_write, canonical


STYLE = """
:root {
  color-scheme: light;
  --ink: #19302d;
  --muted: #71817b;
  --line: #dce5df;
  --paper: #ffffff;
  --canvas: #f5f7f3;
  --deep: #102e2a;
  --deep-soft: #1b423b;
  --mint: #dff1e6;
  --green: #267257;
  --lime: #b8df76;
  --gold: #eac177;
  --shadow: 0 16px 36px #1b392914;
}

* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--canvas);
  color: var(--ink);
  font: 15px/1.55 Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
}
button, input { font: inherit; }
a { color: #206b54; text-underline-offset: 3px; }
button:focus-visible, input:focus-visible, summary:focus-visible, a:focus-visible {
  outline: 3px solid #75b896;
  outline-offset: 3px;
}
[hidden] { display: none !important; }

.masthead {
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(ellipse at 86% 14%, #416f4e55 0, transparent 29rem),
    linear-gradient(125deg, #102a29, #133b32 68%, #183a2e);
  color: #f5f8f1;
}
.masthead::after {
  position: absolute;
  right: -130px;
  bottom: -350px;
  width: 590px;
  height: 590px;
  border: 1px solid #ffffff12;
  border-radius: 50%;
  box-shadow: 0 0 0 50px #ffffff08, 0 0 0 105px #ffffff06;
  content: "";
  pointer-events: none;
}
.topbar, .hero, main, footer { width: min(1160px, calc(100% - 48px)); margin-inline: auto; }
.topbar {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 76px;
  border-bottom: 1px solid #ffffff20;
}
.brand { display: inline-flex; align-items: center; gap: 10px; color: #f5f8f1; text-decoration: none; }
.brand-mark { display: grid; width: 34px; height: 34px; place-items: center; border: 1px solid #b8df7655; border-radius: 11px; color: var(--lime); }
.brand-name { font-size: 16px; font-weight: 760; letter-spacing: -.04em; }
.brand-name span { color: #a8d99e; }
.topbar-meta { display: flex; align-items: center; gap: 20px; color: #c5d4cb; font-size: 12px; }
.topbar-meta a { color: inherit; text-decoration: none; }
.topbar-meta a:hover { color: #fff; }
.sample-pill { display: inline-flex; align-items: center; gap: 7px; padding: 6px 10px; border: 1px solid #ffffff32; border-radius: 999px; color: #e1eadf; }
.sample-pill::before { width: 6px; height: 6px; border-radius: 50%; background: var(--lime); content: ""; }

.hero {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(260px, .65fr);
  align-items: center;
  gap: 50px;
  padding-block: 62px 52px;
}
.hero-kicker, .section-kicker {
  margin: 0;
  color: #a7d59b;
  font: 700 11px/1.4 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.hero h1 { max-width: 710px; margin: 13px 0 16px; font-size: clamp(38px, 5.8vw, 65px); line-height: 1.02; letter-spacing: -.06em; }
.hero-copy { max-width: 570px; margin: 0; color: #c4d6ca; font-size: 17px; }
.hero-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin-top: 26px; }
.hero-link { display: inline-flex; align-items: center; gap: 8px; min-height: 42px; padding: 0 15px; border-radius: 8px; background: var(--lime); color: #203d2e; font-size: 13px; font-weight: 750; text-decoration: none; }
.hero-link:hover { background: #c9ed91; }
.hero-caption { color: #a9c4b5; font-size: 12px; }
.trace-card { padding: 20px; border: 1px solid #ffffff26; border-radius: 15px; background: #ffffff0a; box-shadow: 0 18px 50px #071b1870; backdrop-filter: blur(8px); }
.trace-card-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 17px; }
.trace-card-heading strong { font-size: 13px; }
.trace-card-heading span { color: #a9c4b5; font: 10px ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: .1em; }
.trace-step { display: grid; grid-template-columns: 28px 1fr; gap: 11px; padding-block: 11px; border-top: 1px solid #ffffff1b; }
.trace-step-number { display: grid; width: 25px; height: 25px; place-items: center; border-radius: 8px; background: #ffffff12; color: #c1e29a; font: 11px ui-monospace, SFMono-Regular, Consolas, monospace; }
.trace-step strong { display: block; color: #f3f5ec; font-size: 12px; }
.trace-step small { display: block; margin-top: 2px; color: #a9c4b5; font-size: 11px; }
.hero-stats { display: flex; flex-wrap: wrap; gap: 0; margin-top: 46px; border-top: 1px solid #ffffff25; }
.hero-stat { min-width: 142px; padding: 17px 24px 0 0; }
.hero-stat + .hero-stat { padding-left: 24px; border-left: 1px solid #ffffff25; }
.hero-stat strong { display: block; color: #f6f7ef; font-size: 21px; letter-spacing: -.04em; }
.hero-stat span { color: #a9c4b5; font-size: 11px; }

main { padding-block: 43px 76px; }
.directory-heading { display: flex; align-items: end; justify-content: space-between; gap: 18px; margin-bottom: 18px; }
.directory-heading h2 { margin: 4px 0 0; font-size: 28px; letter-spacing: -.045em; }
.directory-heading p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
.directory-heading .section-kicker { color: var(--green); }
.profile-total { color: var(--muted); font-size: 12px; white-space: nowrap; }
.tools { display: grid; grid-template-columns: minmax(260px, 1fr) minmax(340px, 1.05fr); gap: 12px; margin-bottom: 18px; }
.search-panel, .compare-panel { min-height: 78px; border: 1px solid var(--line); border-radius: 12px; background: var(--paper); box-shadow: var(--shadow); }
.search-panel { display: flex; align-items: center; gap: 12px; padding: 12px 15px; }
.search-icon { flex: none; color: #6b8378; }
.search-fields { min-width: 0; flex: 1; }
.search-fields label { display: block; color: #697a72; font-size: 10px; font-weight: 730; letter-spacing: .1em; text-transform: uppercase; }
.search-fields input { width: 100%; padding: 3px 0 0; border: 0; outline: 0; background: transparent; color: var(--ink); font-size: 14px; }
.search-fields input::placeholder { color: #96a19b; }
.search-shortcut { flex: none; padding: 3px 6px; border: 1px solid var(--line); border-radius: 5px; color: #7c8982; font: 10px ui-monospace, SFMono-Regular, Consolas, monospace; }
.compare-panel { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 12px 15px; }
.compare-copy { min-width: 0; }
.compare-copy strong { display: block; font-size: 13px; }
.compare-copy p { margin: 2px 0 0; color: var(--muted); font-size: 11px; }
.compare-actions { display: flex; flex: none; align-items: center; gap: 6px; }
.button { min-height: 38px; padding: 7px 12px; border: 1px solid transparent; border-radius: 7px; cursor: pointer; font-size: 12px; font-weight: 720; }
.button-primary { border-color: var(--deep); background: var(--deep); color: white; }
.button-primary:hover:not(:disabled) { background: var(--deep-soft); }
.button-primary:disabled { opacity: .4; cursor: not-allowed; }
.button-quiet { background: transparent; color: #6c7a73; }
.button-quiet:hover { background: #f0f4ef; }
.search-status { min-height: 18px; margin: -6px 0 8px; color: var(--muted); font-size: 11px; }

.company-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; gap: 14px; }
.company-card { min-width: 0; overflow: hidden; border: 1px solid var(--line); border-radius: 13px; background: var(--paper); box-shadow: var(--shadow); transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease; }
.company-card:hover { transform: translateY(-2px); border-color: #bdd1c3; box-shadow: 0 19px 42px #1b39291e; }
.company-card.is-selected { border-color: #75ad8e; box-shadow: 0 0 0 2px #75ad8e40, var(--shadow); }
.card-header { padding: 18px 18px 14px; }
.card-title-row { display: grid; grid-template-columns: 42px minmax(0, 1fr) auto; align-items: start; gap: 11px; }
.company-mark { display: grid; width: 42px; height: 42px; place-items: center; border: 1px solid #d8e9d9; border-radius: 12px; background: #edf5e9; color: #477352; font: 700 12px ui-monospace, SFMono-Regular, Consolas, monospace; }
.company-name { margin: 0; font-size: 16px; line-height: 1.25; letter-spacing: -.025em; overflow-wrap: anywhere; }
.company-number { margin: 4px 0 0; color: #71817b; font: 10px ui-monospace, SFMono-Regular, Consolas, monospace; }
.company-state { display: inline-flex; align-items: center; gap: 5px; margin-top: 8px; padding: 3px 7px; border-radius: 999px; background: #edf5ef; color: #32674b; font-size: 10px; font-weight: 700; text-transform: capitalize; }
.company-state::before { width: 5px; height: 5px; border-radius: 50%; background: #4e9b67; content: ""; }
.sample-badge { display: inline-flex; align-items: center; margin: 8px 0 0 5px; padding: 3px 7px; border: 1px solid #f0dfb5; border-radius: 999px; background: #fff8e7; color: #76551b; font-size: 9px; font-weight: 750; }
.compare-toggle { min-height: 34px; padding: 6px 9px; border: 1px solid #d7e2da; border-radius: 7px; background: #fff; color: #446c55; cursor: pointer; font-size: 10px; font-weight: 720; white-space: nowrap; }
.compare-toggle:hover, .compare-toggle[aria-pressed="true"] { border-color: #99c6a5; background: var(--mint); }
.compare-toggle:disabled { opacity: .45; cursor: not-allowed; }
.toggle-mark { margin-right: 3px; font-size: 14px; vertical-align: -1px; }
.company-summary { margin: 13px 0 0 53px; color: #5d7067; font-size: 12px; }
.card-metrics { display: flex; flex-wrap: wrap; gap: 12px; margin: 14px 0 0 53px; color: #728078; font-size: 10px; }
.card-metrics span { display: inline-flex; align-items: center; gap: 5px; }
.card-metrics strong { color: #385b49; font-size: 11px; }
.fact-list { border-top: 1px solid #e8ede8; }
.profile-content { border-top: 1px solid #e8ede8; }
.profile-content > summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 18px; color: #315c46; cursor: pointer; font-size: 11px; font-weight: 750; list-style: none; }
.profile-content > summary::-webkit-details-marker { display: none; }
.profile-content > summary::after { content: "+"; font-size: 16px; }
.profile-content[open] > summary::after { content: "−"; }
.profile-content > summary small { margin-left: auto; color: var(--muted); font-size: 9px; font-weight: 600; }
.fact-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: start; gap: 14px; padding: 12px 18px; border-bottom: 1px solid #edf1ed; }
.fact-row:last-child { border-bottom: 0; }
.fact-copy { min-width: 0; }
.fact-label { margin: 0 0 3px; color: #71817a; font: 700 9px ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: .1em; text-transform: uppercase; }
.fact-value { overflow-wrap: anywhere; color: #263f34; font-size: 12px; }
.fact-value > p { margin: 4px 0; }
.fact-value strong { color: #203c30; }
.fact-value blockquote { margin: 8px 0; padding-left: 10px; border-left: 2px solid #b8d4bb; color: #576e62; }
.fact-value details { margin-top: 6px; font-size: 11px; }
.fact-value pre { max-height: 180px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
.evidence-details { flex: none; width: 105px; color: #286748; font-size: 10px; }
.evidence-details summary { display: flex; align-items: center; justify-content: space-between; gap: 4px; min-height: 26px; cursor: pointer; list-style: none; font-weight: 740; }
.evidence-details summary::-webkit-details-marker { display: none; }
.evidence-details summary::after { content: "+"; font-size: 14px; }
.evidence-details[open] summary::after { content: "−"; }
.evidence-panel { width: min(300px, 68vw); margin-top: 8px; padding: 10px; border: 1px solid #dfe9e1; border-radius: 8px; background: #f8faf7; color: #64756c; font-size: 10px; overflow-wrap: anywhere; }
.evidence-panel p { margin: 6px 0; }
.evidence-panel code { color: #75827a; font-size: 9px; overflow-wrap: anywhere; }
.evidence-link { display: inline-flex; align-items: center; gap: 4px; color: #206b54; font-weight: 740; text-decoration: none; }
.evidence-link:hover { text-decoration: underline; }
.synthetic-note { color: #85621e !important; }
.gaps-panel, .profile-details { padding: 0 18px; border-top: 1px solid #e8ede8; }
.gaps-panel summary, .profile-details summary { padding-block: 11px; color: #64766d; cursor: pointer; font-size: 10px; font-weight: 720; }
.gap-item { display: flex; justify-content: space-between; gap: 10px; padding: 7px 0; border-top: 1px solid #edf1ed; color: #758078; font-size: 10px; }
.gap-item strong { color: #586960; font-weight: 650; }
.gap-item div { text-align: right; }
.gap-item small { display: block; max-width: 260px; margin-top: 2px; color: #87938c; }
.last-known-panel { margin-top: 10px; border-top: 1px solid #ead9ad; border-bottom: 1px solid #ead9ad; background: #fffbef; }
.last-known-heading { padding: 11px 18px; color: #6d531f; font-size: 10px; }
.last-known-heading strong { display: block; font-size: 11px; }
.last-known-panel .fact-list { border-color: #efe2c1; }
.last-known-panel .fact-row { border-color: #f1e7cc; }
.profile-details pre { max-height: 210px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; color: #61736a; font-size: 10px; }
.research-status { padding: 0 18px 14px; color: var(--muted); font-size: 10px; }
.research-status p { margin: 4px 0; }
.empty-state { padding: 36px 20px; border: 1px dashed #c7d4c9; border-radius: 12px; background: #fbfcf9; color: var(--muted); text-align: center; }
.sample-notice { margin-bottom: 15px; padding: 12px 15px; border: 1px solid #ebd9ae; border-radius: 9px; background: #fff8e7; color: #705523; font-size: 11px; }
.sample-notice strong { color: #5d4317; }
footer { padding-block: 18px 25px; border-top: 1px solid var(--line); color: #718078; font-size: 11px; }
footer a { color: #526d5c; }

dialog { width: min(1000px, calc(100vw - 30px)); max-width: none; max-height: min(88dvh, 920px); padding: 0; border: 1px solid #cfdbd2; border-radius: 15px; box-shadow: 0 28px 90px #0b24205c; color: var(--ink); }
dialog::backdrop { background: #0d2420a8; backdrop-filter: blur(2px); }
.dialog-header { display: flex; align-items: start; justify-content: space-between; gap: 16px; padding: 20px 22px 16px; border-bottom: 1px solid var(--line); }
.dialog-header h2 { margin: 0; font-size: 21px; letter-spacing: -.035em; }
.dialog-header p { margin: 4px 0 0; color: var(--muted); font-size: 11px; }
.dialog-close { flex: none; min-width: 38px; min-height: 38px; border: 1px solid var(--line); border-radius: 7px; background: white; color: var(--ink); cursor: pointer; font-size: 18px; }
.comparison-scroll { max-height: calc(88dvh - 105px); overflow: auto; padding: 0 20px 20px; }
.comparison-table { width: 100%; min-width: 610px; border-collapse: collapse; font-size: 12px; }
.comparison-table th, .comparison-table td { padding: 12px; border-bottom: 1px solid #e7ede8; text-align: left; vertical-align: top; overflow-wrap: anywhere; }
.comparison-table thead th { position: sticky; top: 0; z-index: 1; background: white; color: #395849; }
.comparison-table thead th:first-child, .comparison-table tbody th { width: 140px; color: #728078; font-size: 10px; text-transform: capitalize; }
.comparison-table tbody td { width: 39%; }
.comparison-fact + .comparison-fact { margin-top: 10px; padding-top: 10px; border-top: 1px dashed #dce5df; }
.comparison-fact p { margin: 0 0 6px; }
.comparison-fact .provenance { display: flex; flex-wrap: wrap; gap: 4px 10px; color: var(--muted); font-size: 10px; }
.comparison-fact a { font-weight: 700; }
.no-fact { color: #87938c; font-style: italic; }
.dialog-actions { display: flex; justify-content: flex-end; padding: 10px 20px; border-top: 1px solid var(--line); }

@media (min-width: 1200px) { .company-list { gap: 16px; } }
@media (max-width: 820px) {
  .hero { grid-template-columns: minmax(0, 1fr) minmax(230px, .7fr); gap: 28px; padding-block: 48px 40px; }
  .tools { grid-template-columns: 1fr; }
  .company-list { grid-template-columns: 1fr; }
}
@media (max-width: 620px) {
  .topbar, .hero, main, footer { width: min(100% - 32px, 1160px); }
  .topbar { min-height: 64px; }
  .topbar-meta { gap: 11px; font-size: 11px; }
  .hero { display: block; padding-block: 38px 30px; }
  .hero h1 { max-width: 470px; font-size: clamp(38px, 11vw, 52px); }
  .hero-copy { font-size: 15px; }
  .trace-card { display: none; }
  .hero-stats { margin-top: 34px; }
  .hero-stat { min-width: 0; flex: 1; padding-right: 10px; }
  .hero-stat + .hero-stat { padding-left: 13px; }
  .hero-stat strong { font-size: 18px; }
  .hero-stat span { font-size: 9px; }
  main { padding-block: 30px 50px; }
  .directory-heading { align-items: start; flex-direction: column; gap: 4px; }
  .directory-heading h2 { font-size: 24px; }
  .profile-total { white-space: normal; }
  .compare-panel { align-items: flex-start; }
  .compare-actions { align-self: center; }
  .search-shortcut { display: none; }
  .card-header { padding: 15px 13px 12px; }
  .card-title-row { grid-template-columns: 38px minmax(0, 1fr) auto; gap: 9px; }
  .company-mark { width: 38px; height: 38px; }
  .company-name { font-size: 15px; }
  .company-summary, .card-metrics { margin-left: 47px; }
  .company-summary { font-size: 11px; }
  .fact-row { grid-template-columns: minmax(0, 1fr); gap: 6px; padding: 11px 13px; }
  .evidence-details { width: auto; }
  .evidence-details summary { justify-content: flex-start; gap: 8px; min-height: 22px; }
  .evidence-panel { width: 100%; }
  .gaps-panel, .profile-details { padding-inline: 13px; }
  .research-status { padding-inline: 13px; }
  .sample-notice { font-size: 10px; }
  .comparison-scroll { padding-inline: 10px; }
  .dialog-header { padding: 17px 14px 13px; }
  .dialog-actions { padding-inline: 14px; }
}
@media (max-width: 380px) {
  .topbar, .hero, main, footer { width: calc(100% - 24px); }
  .topbar-meta a { display: none; }
  .hero-stat + .hero-stat { padding-left: 9px; }
  .hero-stat span { font-size: 8px; }
  .compare-panel { flex-direction: column; }
  .compare-actions { width: 100%; justify-content: space-between; }
  .compare-toggle { padding-inline: 6px; font-size: 9px; }
  .sample-badge { display: block; width: max-content; margin-left: 0; }
}
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; } }
"""


SCRIPT = """
(() => {
  const cards = [...document.querySelectorAll('.company-card')];
  const search = document.getElementById('company-search');
  const searchStatus = document.getElementById('search-status');
  const emptyState = document.getElementById('empty-state');
  const compareStatus = document.getElementById('compare-status');
  const openButton = document.getElementById('open-comparison');
  const clearButton = document.getElementById('clear-comparison');
  const dialog = document.getElementById('comparison-dialog');
  const compareContent = document.getElementById('comparison-content');
  const selected = new Set();

  search.addEventListener('input', () => {
    const query = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    for (const card of cards) {
      card.hidden = !card.dataset.search.includes(query);
      if (!card.hidden) visible += 1;
    }
    emptyState.hidden = visible !== 0;
    searchStatus.textContent = query ? `${visible} of ${cards.length} profiles shown` : '';
  });

  document.addEventListener('keydown', event => {
    const target = event.target;
    const typing = target instanceof HTMLElement
      && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName));
    if (!typing && (event.key === '/' || ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k'))) {
      event.preventDefault();
      search.focus();
    }
  });

  function profileFor(card) {
    return JSON.parse(card.dataset.comparison);
  }

  function updateSelection(message = '') {
    for (const card of cards) {
      const button = card.querySelector('.compare-toggle');
      const active = selected.has(card);
      card.classList.toggle('is-selected', active);
      button.setAttribute('aria-pressed', String(active));
      button.disabled = selected.size === 2 && !active;
      button.querySelector('.toggle-label').textContent = active ? 'Remove' : 'Compare';
      button.querySelector('.toggle-mark').textContent = active ? '✓' : '+';
    }

    const profiles = [...selected].map(profileFor);
    if (message) compareStatus.textContent = message;
    else if (profiles.length === 0) compareStatus.textContent = 'Pick two profiles to review facts and sources side by side.';
    else if (profiles.length === 1) compareStatus.textContent = `${profiles[0].name} selected. Choose one more.`;
    else compareStatus.textContent = `${profiles[0].name} and ${profiles[1].name} are ready.`;

    openButton.textContent = `Compare ${selected.size} of 2`;
    openButton.disabled = selected.size !== 2;
    clearButton.hidden = selected.size === 0;
  }

  for (const card of cards) {
    card.querySelector('.compare-toggle').addEventListener('click', () => {
      if (selected.has(card)) selected.delete(card);
      else if (selected.size < 2) selected.add(card);
      else {
        updateSelection('Two profiles are selected. Remove one to choose another.');
        return;
      }
      updateSelection();
    });
  }

  clearButton.addEventListener('click', () => {
    selected.clear();
    updateSelection();
  });

  function appendFact(cell, fact) {
    const item = document.createElement('div');
    item.className = 'comparison-fact';
    const value = document.createElement('p');
    value.textContent = fact.value;
    item.append(value);

    const provenance = document.createElement('div');
    provenance.className = 'provenance';
    const locator = document.createElement('span');
    locator.textContent = fact.locator;
    provenance.append(locator);

    if (fact.source_url) {
      const link = document.createElement('a');
      link.href = fact.source_url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'Open source ↗';
      provenance.append(link);
    } else if (fact.synthetic) {
      const label = document.createElement('span');
      label.textContent = 'Synthetic fixture';
      provenance.append(label);
    }

    const retrieval = document.createElement('span');
    retrieval.textContent = `Retrieved ${fact.retrieved_at}`;
    provenance.append(retrieval);
    item.append(provenance);
    cell.append(item);
  }

  function appendRow(body, label, values) {
    const row = document.createElement('tr');
    const heading = document.createElement('th');
    heading.scope = 'row';
    heading.textContent = label;
    row.append(heading);

    for (const value of values) {
      const cell = document.createElement('td');
      if (Array.isArray(value)) {
        if (value.length) value.forEach(fact => appendFact(cell, fact));
        else {
          const missing = document.createElement('span');
          missing.className = 'no-fact';
          missing.textContent = 'No verified fact in this profile';
          cell.append(missing);
        }
      } else {
        cell.textContent = value || 'Not reported';
      }
      row.append(cell);
    }
    body.append(row);
  }

  openButton.addEventListener('click', () => {
    if (selected.size !== 2) return;
    const profiles = [...selected].map(profileFor);
    const table = document.createElement('table');
    table.className = 'comparison-table';
    const head = document.createElement('thead');
    const headRow = document.createElement('tr');
    for (const label of ['Profile fact', ...profiles.map(profile => profile.name)]) {
      const cell = document.createElement('th');
      cell.scope = 'col';
      cell.textContent = label;
      headRow.append(cell);
    }
    head.append(headRow);
    table.append(head);

    const body = document.createElement('tbody');
    appendRow(body, 'Organisation number', profiles.map(profile => profile.number));
    appendRow(body, 'Registry status', profiles.map(profile => profile.state));
    appendRow(body, 'Summary', profiles.map(profile => profile.summary));
    const fields = new Set(profiles.flatMap(profile => profile.facts.map(fact => fact.field)));
    for (const field of [...fields].sort((left, right) => left.localeCompare(right))) {
      appendRow(body, field, profiles.map(profile => profile.facts.filter(fact => fact.field === field)));
    }
    table.append(body);
    compareContent.replaceChildren(table);
    dialog.showModal();
  });

  for (const button of dialog.querySelectorAll('.dialog-close')) {
    button.addEventListener('click', () => dialog.close());
  }
  dialog.addEventListener('click', event => {
    if (event.target === dialog) dialog.close();
  });
})();
"""


def _safe_source(url, evidence):
    if evidence.get('synthetic'):
        return False
    if url.startswith(BASE):
        return True
    source_class = evidence.get('source_class')
    if source_class in {
        'verified_company_website', 'legal_news_report', 'legal_filing_report'
    }:
        from .web import normalize_url

        try:
            return normalize_url(url) == url
        except ValueError:
            return False
    if source_class in {
        'official_accounts', 'official_registry_roles', 'official_registry_locations'
    }:
        try:
            parsed = urlsplit(url)
            return (parsed.scheme == 'https' and parsed.hostname == 'data.brreg.no'
                    and parsed.username is None and parsed.password is None
                    and parsed.port in (None, 443))
        except ValueError:
            return False
    if source_class == 'verified_social_page':
        from .web import SOCIAL_HOSTS, normalize_url

        try:
            normalized = normalize_url(url)
            host = urlsplit(normalized).hostname
            root_host = host[4:] if host.startswith('www.') else host
            return normalized == url and root_host in SOCIAL_HOSTS
        except ValueError:
            return False
    return False


def _locator(claim):
    if 'json_ld_block' in claim:
        pointer = claim.get('json_pointer') or '(root)'
        return f"JSON-LD block {claim['json_ld_block']} · Pointer: {pointer}"
    if claim.get('extraction_method') == 'company_meta_description_v1':
        return 'HTML meta description'
    if claim.get('json_pointer') is not None:
        return 'JSON pointer: ' + str(claim['json_pointer'])
    if 'json_pointer' in claim:
        return 'Structured source record'
    return 'Text span: ' + str(claim.get('text_span', 'missing'))


def _comparison_payload(result, evidence_by_id):
    facts = []
    for claim in result['claims']:
        evidence = evidence_by_id[claim['evidence_id']]
        source_url = evidence['source_url']
        facts.append({
            'field': claim['field'].replace('_', ' '),
            'value': canonical(claim['value']),
            'source_url': source_url if _safe_source(source_url, evidence) else None,
            'retrieved_at': evidence['retrieved_at'],
            'locator': _locator(claim),
            'synthetic': bool(evidence.get('synthetic')),
        })
    return {
        'number': result['organisation_number'],
        'name': result['legal_identity'].get('name', 'Unresolved company'),
        'state': result['state'],
        'summary': result['summary'],
        'facts': facts,
    }


def _fact_value(claim):
    value = claim['value']
    if claim['field'] == 'financials' and isinstance(value, dict) and value.get('metric'):
        label = html.escape(str(value['metric']).replace('_', ' ').title())
        amount = value.get('amount')
        shown = format(amount, ',.0f') if isinstance(amount, (int, float)) else str(amount)
        currency = html.escape(str(value.get('currency') or 'currency unreported'))
        period = html.escape(str(value.get('period_end') or 'period unreported'))
        scope = 'consolidated accounts' if value.get('report_type') == 'KONSERN' else 'company accounts'
        return f'<strong>{label}</strong><p>{html.escape(shown)} {currency} · {period} · {scope}</p>'
    if claim['field'] == 'jobs' and isinstance(value, dict):
        title = html.escape(value.get('title', 'Job posting'))
        posted = html.escape(value.get('datePosted', 'unknown'))
        expiry = html.escape(value.get('validThrough', 'not reported'))
        record = html.escape(json.dumps(value, ensure_ascii=False, indent=2))
        return (
            f'<strong>{title}</strong><p>Posted {posted}</p><p>Expiry: {expiry}</p>'
            '<details><summary>Original structured record</summary>'
            f'<pre>{record}</pre></details>'
        )
    if claim['field'] == 'news' and isinstance(value, dict):
        headline = html.escape(value.get('headline', 'News article'))
        published = html.escape(value.get('datePublished', 'unknown'))
        record = html.escape(json.dumps(value, ensure_ascii=False, indent=2))
        return (
            f'<strong>{headline}</strong><p>Published {published}</p>'
            '<details><summary>Original structured article</summary>'
            f'<pre>{record}</pre></details>'
        )
    if claim['field'] == 'legal_cases':
        kind = html.escape(value['source_kind'])
        published = html.escape(value['published_at'])
        reference = html.escape(value['case_reference'] or 'not reported')
        passage = html.escape(value['reported_text'])
        return (
            f'<strong>Source report · {kind}</strong>'
            f'<p>Published {published} · Case reference: {reference}</p>'
            f'<blockquote>{passage}</blockquote>'
            '<p>Reported by the linked source. Liability and court outcome are not inferred.</p>'
        )
    return html.escape(canonical(value))


def _source_label(url, evidence):
    if evidence.get('synthetic'):
        return 'Synthetic fixture'
    if url.startswith(BASE):
        return 'Brønnøysundregistrene'
    if evidence.get('source_class') == 'verified_company_website':
        return urlsplit(url).hostname or 'Verified company site'
    if evidence.get('source_class') == 'official_accounts':
        return 'Brønnøysund annual accounts'
    if evidence.get('source_class') == 'official_registry_roles':
        return 'Brønnøysund registered roles'
    if evidence.get('source_class') == 'official_registry_locations':
        return 'Brønnøysund operating locations'
    if evidence.get('source_class') == 'verified_social_page':
        return urlsplit(url).hostname or 'Verified social profile'
    if evidence.get('source_class') == 'legal_news_report':
        return 'Attributed news report'
    if evidence.get('source_class') == 'legal_filing_report':
        return 'Public filing'
    return 'Source record'


def _evidence_details(claim, evidence):
    esc = lambda value: html.escape(str(value), quote=True)
    url = evidence['source_url']
    if _safe_source(url, evidence):
        source = (
            '<a class="evidence-link" href="' + esc(url)
            + '" target="_blank" rel="noopener noreferrer">Open source ↗</a>'
        )
    else:
        source = '<span>' + esc(_source_label(url, evidence)) + '</span>'

    synthetic_note = (
        '<p class="synthetic-note">Sample only. This fact is not about a real company.</p>'
        if evidence.get('synthetic') else ''
    )
    evidence_id = esc(evidence['id'])
    retrieved = esc(evidence['retrieved_at'])
    locator = esc(_locator(claim))
    source_label = esc(_source_label(url, evidence))
    return (
        '<details class="evidence-details"><summary><span>Evidence</span></summary>'
        '<div class="evidence-panel"><p><strong>' + source_label + '</strong></p>'
        + source + '<p>Retrieved ' + retrieved + '</p><p>' + locator + '</p>'
        + '<code>SHA-256 ' + evidence_id + '</code>' + synthetic_note + '</div></details>'
    )


def _fact_row(claim, evidence):
    label = html.escape(claim['field'].replace('_', ' '))
    return (
        '<div class="fact-row"><div class="fact-copy"><p class="fact-label">'
        + label + '</p><div class="fact-value">' + _fact_value(claim)
        + '</div></div>' + _evidence_details(claim, evidence) + '</div>'
    )


def _company_card(result):
    esc = lambda value: html.escape(str(value), quote=True)
    last_known = result.get('last_known', {})
    all_evidence = result['evidence'] + last_known.get('evidence', [])
    evidence_by_id = {item['id']: item for item in all_evidence}
    identity = result['legal_identity'] or last_known.get('legal_identity', {})
    fact_rows = ''.join(
        _fact_row(claim, evidence_by_id[claim['evidence_id']])
        for claim in result['claims']
    )
    evidence_count = len({claim['evidence_id'] for claim in result['claims']})
    website_pages = result.get('website_research', {}).get('pages_verified', 0)
    search_value = ' '.join(
        [result['organisation_number'], result['state'],
         identity.get('name', ''), result['summary']]
        + [canonical(claim['value']) for claim in result['claims']]
        + [canonical(claim['value']) for claim in last_known.get('claims', [])]
    ).casefold()
    comparison = json.dumps(
        _comparison_payload(result, evidence_by_id), ensure_ascii=False, separators=(',', ':')
    )
    synthetic = any(item.get('synthetic') for item in all_evidence)
    badge = '<span class="sample-badge">Sample</span>' if synthetic else ''
    initials = ''.join(
        part[0] for part in identity.get('name', 'Co').split()[:2]
        if part and part[0].isalnum()
    ).upper() or 'Co'
    state = html.escape(result['state'].replace('_', ' '))

    availability = result['availability']
    gaps = [
        '<div class="gap-item"><span>' + esc(field.replace('_', ' '))
        + '</span><div><strong>' + esc(status['state'].replace('_', ' ')) + '</strong>'
        + ('<small>' + esc(status['reason'].replace('_', ' ')) + '</small>'
           if status.get('reason') else '') + '</div></div>'
        for field, status in availability.items() if status['state'] != 'available'
    ]
    gaps_panel = ''
    if gaps:
        gaps_panel = (
            '<details class="gaps-panel"><summary>Research gaps ('
            + str(len(gaps)) + ')</summary>' + ''.join(gaps) + '</details>'
        )

    stale_claims = last_known.get('claims', [])
    stale_panel = ''
    if stale_claims:
        stale_rows = ''.join(
            _fact_row(claim, evidence_by_id[claim['evidence_id']]) for claim in stale_claims
        )
        stale_panel = (
            '<section class="last-known-panel"><div class="last-known-heading">'
            '<strong>Last verified facts</strong>Verified as of '
            + esc(last_known.get('as_of', 'unknown'))
            + '; retained as historical, not current.</div><div class="fact-list">'
            + stale_rows + '</div></section>'
        )

    changes = result['refresh']['changes']
    history = ''
    if changes:
        history = (
            '<details class="profile-details"><summary>Refresh history ('
            + str(len(changes)) + ')</summary><pre>'
            + html.escape(json.dumps(changes, ensure_ascii=False, indent=2))
            + '</pre></details>'
        )

    status_lines = []
    website = result.get('website_research')
    if website:
        status_lines.append(
            '<p>Website research · ' + str(website['pages_verified'])
            + ' verified pages · ' + str(website['requests']) + ' requests</p>'
        )
        if website['errors']:
            status_lines.append('<p>Research notes · ' + esc(', '.join(website['errors'])) + '</p>')
    search = result.get('search_research')
    if search:
        status_lines.append(
            '<p>Web search · ' + str(search.get('successful_queries', 0))
            + '/' + str(search.get('queries', 0)) + ' successful queries · '
            + str(search.get('candidates', 0)) + ' candidates</p>'
        )
        if search.get('errors'):
            status_lines.append('<p>Search notes · ' + esc(', '.join(search['errors'])) + '</p>')
    candidate_items = []
    for candidate in result.get('candidates', []):
        if isinstance(candidate, dict) and isinstance(candidate.get('value'), str):
            candidate_items.append(
                '<li><code>' + esc(candidate['value']) + '</code> · '
                + esc(candidate.get('kind', 'candidate')) + ' · '
                + esc(candidate.get('status', 'unknown')) + '</li>'
            )
    if candidate_items:
        status_lines.append(
            '<details><summary>Discovered source candidates (' + str(len(candidate_items))
            + ')</summary><ul>' + ''.join(candidate_items)
            + '</ul><p>Search results are leads; only identity-verified pages support claims.</p></details>'
        )
    if result['errors']:
        status_lines.append('<p>Errors · ' + esc(', '.join(result['errors'])) + '</p>')
    status_section = (
        '<div class="research-status">' + ''.join(status_lines) + '</div>'
        if status_lines else ''
    )

    summary = html.escape(result['summary'])
    company_name = html.escape(identity.get('name', 'Unresolved company'))
    profile_count = len(result['claims']) + len(stale_claims)
    profile_content = (
        '<details class="profile-content"><summary><span>Open company profile</span><small>'
        + str(profile_count) + ' facts and history</small></summary><div class="fact-list">'
        + fact_rows + '</div>' + stale_panel + gaps_panel + history + status_section
        + '</details>'
    )
    return (
        '<article class="company-card" data-search="' + esc(search_value)
        + '" data-comparison="' + esc(comparison) + '">'
        '<div class="card-header"><div class="card-title-row">'
        '<div class="company-mark" aria-hidden="true">' + esc(initials) + '</div>'
        '<div><h3 class="company-name">' + company_name + '</h3>'
        '<p class="company-number">ORG. NO. ' + esc(result['organisation_number']) + '</p>'
        '<span class="company-state">' + state + '</span>' + badge + '</div>'
        '<button class="compare-toggle" type="button" aria-pressed="false">'
        '<span class="toggle-mark" aria-hidden="true">+</span>'
        '<span class="toggle-label">Compare</span></button></div>'
        '<p class="company-summary">' + summary + '</p>'
        '<div class="card-metrics"><span><strong>' + str(len(result['claims']))
        + '</strong> supported facts</span><span><strong>' + str(evidence_count)
        + '</strong> evidence records</span><span><strong>' + str(website_pages)
        + '</strong> verified pages</span></div></div>'
        + profile_content + '</article>'
    )


def _metric(label, value, note):
    return (
        '<div class="hero-stat"><strong>' + html.escape(str(value))
        + '</strong><span>' + html.escape(label) + ' · ' + html.escape(note) + '</span></div>'
    )


def render(results, target):
    results = list(results)
    cards = ''.join(_company_card(result) for result in results)
    claims_count = sum(len(result['claims']) for result in results)
    source_count = sum(
        len({claim['evidence_id'] for claim in result['claims']}) for result in results
    )
    synthetic_count = sum(
        any(evidence.get('synthetic') for evidence in result['evidence'])
        for result in results
    )
    sample_notice = ''
    if synthetic_count:
        profiles = f'{synthetic_count} of {len(results)}' if synthetic_count != len(results) else str(synthetic_count)
        sample_notice = (
            '<aside class="sample-notice" role="note"><strong>Demonstration data.</strong> '
            + profiles + ' profiles include synthetic facts. These examples are labelled '
            'and are here to show how TraceAtlas search, comparison, and evidence work.</aside>'
        )

    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="description" content="Find Norwegian companies, compare profiles, and inspect the source behind every fact.">'
        '<meta name="theme-color" content="#102e2a">'
        '<title>TraceAtlas · Company research with sources</title><style>' + STYLE + '</style></head>'
        '<body><header class="masthead"><nav class="topbar" aria-label="Main navigation">'
        '<a class="brand" href="#top" aria-label="TraceAtlas home"><span class="brand-mark" aria-hidden="true">'
        '<svg width="19" height="19" viewBox="0 0 19 19" fill="none" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M3 5.5h4.5v4.5H3zM11.5 3H16v4.5h-4.5zM11.5 11.5H16V16h-4.5zM3 13.75h4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg></span><span class="brand-name">Trace<span>Atlas</span></span></a>'
        '<div class="topbar-meta"><a href="#directory">Explore companies</a><a href="#about">How it works</a>'
        '<span class="sample-pill">' + ('Sample gallery' if synthetic_count else 'Research explorer')
        + '</span></div></nav><section id="top" class="hero"><div><p class="hero-kicker">Evidence-first company intelligence</p>'
        '<h1>Research you can check.</h1><p class="hero-copy">Find a company, compare its profile with another, '
        'and follow every useful fact back to its source.</p><div class="hero-actions"><a class="hero-link" '
        'href="#directory">Explore company profiles <span aria-hidden="true">↓</span></a>'
        '<span class="hero-caption">Public facts, clear gaps, inspectable sources.</span></div><div class="hero-stats">'
        + _metric('company profiles', len(results), 'in this run')
        + _metric('supported facts', claims_count, 'with evidence')
        + _metric('source records', source_count, 'linked to claims')
        + '</div></div><aside class="trace-card" aria-label="How evidence is traced"><div class="trace-card-heading">'
        '<strong>Every fact has a trail</strong><span>TRACE / 01</span></div>'
        '<div class="trace-step"><span class="trace-step-number">01</span><div><strong>Company claim</strong>'
        '<small>Value and reporting period</small></div></div><div class="trace-step">'
        '<span class="trace-step-number">02</span><div><strong>Original source</strong><small>Link plus exact locator</small></div></div>'
        '<div class="trace-step"><span class="trace-step-number">03</span><div><strong>Checked at a time</strong>'
        '<small>Retrieval date and snapshot hash</small></div></div></aside></section></header>'
        + sample_notice + '<main id="directory"><section aria-labelledby="directory-title">'
        '<div class="directory-heading"><div><p class="section-kicker">Company directory</p>'
        '<h2 id="directory-title">Find the right profile</h2><p>Search by company name, number, place, or activity.</p>'
        '</div><span class="profile-total">' + str(len(results)) + ' profiles in this run</span></div>'
        '<div class="tools"><div class="search-panel"><svg class="search-icon" width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">'
        '<circle cx="8.8" cy="8.8" r="5.8" stroke="currentColor" stroke-width="1.6"/>'
        '<path d="m13 13 4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>'
        '<div class="search-fields"><label for="company-search">Search profiles</label>'
        '<input id="company-search" type="search" placeholder="Try Bergen or 900000006" autocomplete="off" aria-controls="company-list"></div>'
        '<span class="search-shortcut" aria-hidden="true">/</span></div>'
        '<section class="compare-panel" aria-label="Company comparison"><div class="compare-copy">'
        '<strong>Compare companies</strong><p id="compare-status" aria-live="polite">Pick two profiles to review facts and sources side by side.</p>'
        '</div><div class="compare-actions"><button id="clear-comparison" class="button button-quiet" type="button" hidden>Clear</button>'
        '<button id="open-comparison" class="button button-primary" type="button" disabled>Compare 0 of 2</button></div></section></div>'
        '<p id="search-status" class="search-status" aria-live="polite"></p>'
        '<div id="company-list" class="company-list">' + cards + '</div>'
        '<p id="empty-state" class="empty-state" hidden>No profiles match that search. Try a company name, place, or number.</p>'
        '</section></main><footer id="about">TraceAtlas · Every published fact stays tied to its evidence. '
        'Missing information stays visible.</footer><dialog id="comparison-dialog" aria-labelledby="comparison-title">'
        '<div class="dialog-header"><div><h2 id="comparison-title">Compare company profiles</h2>'
        '<p>Values stay paired with their locator, source, and retrieval time.</p></div>'
        '<button class="dialog-close" type="button" aria-label="Close comparison">×</button></div>'
        '<div id="comparison-content" class="comparison-scroll"></div>'
        '<div class="dialog-actions"><button class="dialog-close button button-quiet" type="button">Close comparison</button></div>'
        '</dialog><script>' + SCRIPT + '</script></body></html>'
    )
    atomic_write(target, page)
