// Obole — événements (annotations datées des graphiques).
import { api } from "./api.js";

export const eventsMixin = {
  _eventRef() {
    const id = this.data.identity;
    if (this.isBasket()) return "INDEX:" + id.index_id;
    if (this.isRatio()) return (id.ticker_a + "/" + id.ticker_b).toUpperCase().replace(/\s/g, "");
    return (id.ticker || "").toUpperCase();
  },

  // Query string ciblant le graphe courant pour /api/events/{kind}.

  _eventsQuery() {
    const id = this.data.identity;
    if (this.isRatio()) {
      return `?a=${encodeURIComponent(id.ticker_a)}&b=${encodeURIComponent(id.ticker_b)}`;
    }
    return `?ref=${encodeURIComponent(this._eventRef())}`;
  },

  events() { return this.data?.events || []; },

  // Événements dans la fenêtre visible [i0, i1] (auto-hide hors zoom).
  // Recherche binaire sur les dates triées (O(events · log window)) : premier
  // index dont la date >= event_date (le jour exact peut être férié/week-end).
  // Un événement daté AVANT la fenêtre est masqué (pas épinglé au bord gauche,
  // ce qui suggérerait qu'il a eu lieu à cette date) : tolérance d'une semaine
  // pour les week-ends/fériés, au-delà l'écart signifie « hors fenêtre ».

  _visibleEvents(i0, i1) {
    const d = this.data.chart.dates;
    const WEEK_MS = 7 * 864e5;
    const out = [];
    for (const ev of this.events()) {
      let lo = i0, hi = i1, idx = -1;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (d[mid] >= ev.date) { idx = mid; hi = mid - 1; } else { lo = mid + 1; }
      }
      if (idx < 0) continue;
      if (new Date(d[idx]) - new Date(ev.date) > WEEK_MS) continue;
      out.push({ ...ev, idx });
    }
    return out;
  },

  openEvents() {
    if (!this.data) return;
    this.eventError = "";
    this.eventsOpen = true;
  },

  closeEvents() { this.eventsOpen = false; },

  resetEventForm() {
    this.eventForm = { id: null, date: "", label: "", description: "" };
    this.eventError = "";
  },

  startEditEvent(ev) {
    this.eventForm = { id: ev.id, date: ev.date, label: ev.label, description: ev.description || "" };
    this.eventError = "";
  },

  // Validation front (miroir des bornes de data/events.py).

  _eventFormValid() {
    const f = this.eventForm;
    if (!f.date || !/^\d{4}-\d{2}-\d{2}$/.test(f.date)) return false;
    const label = f.label.trim();
    if (!label || label.length > 60) return false;
    if (f.description && f.description.trim().length > 300) return false;
    return true;
  },

  // Type d'événement pour l'URL API : stock | ratio | index.

  _eventKind() {
    if (this.isBasket()) return "index";
    if (this.isRatio()) return "ratio";
    return "stock";
  },

  async saveEvent() {
    if (!this._eventFormValid()) {
      this.eventError = "Date requise (AAAA-MM-JJ) et libellé requis (60 caractères max).";
      return;
    }
    this.eventSaving = true;
    this.eventError = "";
    const f = this.eventForm;
    const body = { date: f.date, label: f.label.trim(), description: f.description.trim() || null };
    try {
      const url = f.id != null ? `/api/events/${f.id}`
        : `/api/events/${this._eventKind()}${this._eventsQuery()}`;
      const { ok, data } = await api.saveEvent(url, f.id != null ? "PUT" : "POST", body);
      if (!ok) { this.eventError = data.detail || "Enregistrement impossible"; return; }
      await this.reloadEvents();
      this.resetEventForm();
    } catch {
      this.eventError = "Enregistrement impossible (réseau).";
    } finally {
      this.eventSaving = false;
    }
  },

  async deleteEvent(ev) {
    if (!confirm(`Supprimer l'événement « ${ev.label} » (${ev.date}) ?`)) return;
    try {
      const { ok, data } = await api.deleteEvent(ev.id);
      if (!ok) throw new Error(data.detail || "Suppression impossible");
      await this.reloadEvents();
    } catch (e) {
      this.eventError = e.message;
    }
  },

  // Recharge la liste d'événements puis redessine le graphe héro.
  // Source de vérité : `data.events` est posé au load() par le payload du
  // serveur, puis maintenu à jour ICI après chaque save/delete (le payload
  // complet n'est pas re-fetché : les prix sont cachés mais l'analyse est
  // coûteuse). Toute mutation d'événement doit repasser par cette méthode.

  async reloadEvents() {
    try {
      const data = await api.events(this._eventKind(), this._eventsQuery());
      if (data == null) return;
      this.data.events = data;
      this.$nextTick(() => { try { this.drawChart(); } catch { /* graphe absent */ } });
    } catch { /* silencieux : la liste courante reste affichée */ }
  },

};
