// Obole — paramètres, sauvegarde/restauration, purge du cache.
import { api } from "./api.js";

export const settingsMixin = {
  async openSettings() {
    this.settingsOpen = true;
    this.settingsError = "";
    try {
      const payload = await api.settings();
      if (!payload) { this.settingsError = "Impossible de charger les paramètres."; return; }
      this.settingDefs = payload.defs || {};
      this.settingGroups = payload.groups || [];
      this.settingsForm = { ...(payload.values || {}) };
    } catch {
      this.settingsError = "Paramètres indisponibles (réseau).";
    }
  },

  closeSettings() { this.settingsOpen = false; },

  hasGroup(g) { return (this.settingGroups || []).includes(g); },

  // Réglages d'un groupe, pour générer les champs de la modale dynamiquement
  // (source unique = config.SETTING_DEFS renvoyé par l'API).

  groupDefs(g) {
    const out = {};
    for (const [k, d] of Object.entries(this.settingDefs || {})) {
      if (d.group === g) out[k] = d;
    }
    return out;
  },

  async saveSettings() {
    this.settingsSaving = true;
    this.settingsError = "";
    try {
      const { ok, data: payload } = await api.saveSettings(this.settingsForm);
      if (!ok) { this.settingsError = payload.detail || "Enregistrement impossible"; return; }
      this.settingsForm = { ...payload.values };
      this._maShort = payload.values.trend_ma_short;
      this._maLong = payload.values.trend_ma_long;
      // Recharge la VUE courante pour appliquer les nouvelles MM au tracé et à
      // la tendance (le serveur précalcule les moyennes à ce moment). On ne
      // peut pas toujours appeler `load()` : il se résout sur `query`, vide
      // quand on regarde un indice (basket) — on dispatche selon le type.
      if (this.data) {
        const id = this.data.identity;
        if (this.isBasket()) this.loadIndex(id.index_id);
        else this.load();
      } else {
        this.load();
      }
    } catch (e) {
      this.settingsError = "Enregistrement impossible (réseau).";
    } finally {
      this.settingsSaving = false;
    }
  },

  // Rétablit les valeurs par défaut (sans persister) pour que l'utilisateur
  // voie l'aperçu avant de cliquer « Enregistrer ».

  resetSettings() {
    const form = {};
    for (const [k, d] of Object.entries(this.settingDefs || {})) form[k] = d.default;
    this.settingsForm = form;
    this.settingsError = "";
  },

  // --- Sauvegarde / restauration des données utilisateur -------------------

  // Télécharge l'archive JSON (Blob + <a download>, même pattern que l'export CSV).

  async downloadBackup() {
    this.backupBusy = true;
    this.backupMessage = "";
    this.backupError = "";
    try {
      const r = await api.backup();
      if (!r.ok) { this.backupError = "Sauvegarde impossible (" + r.status + ")"; return; }
      const text = await r.text();
      const fname = this._filenameFromDisposition(r) || "obole-backup.json";
      const blob = new Blob([text], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = fname;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      this.backupMessage = "Sauvegarde téléchargée.";
    } catch {
      this.backupError = "Sauvegarde impossible (réseau).";
    } finally {
      this.backupBusy = false;
    }
  },

  // Nom de fichier proposé par le serveur (Content-Disposition), sinon défaut.

  _filenameFromDisposition(res) {
    const cd = res.headers.get("content-disposition") || "";
    const m = cd.match(/filename="?([^";]+)"?/);
    return m ? m[1] : "";
  },

  pickBackupFile() {
    this.backupMessage = "";
    this.backupError = "";
    this.$refs.restoreInput.value = "";  // réautorise la sélection du même fichier
    this.$refs.restoreInput.click();
  },

  async restoreBackup(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    if (!confirm("Remplacer vos données actuelles (comptes manuels, indices, événements, réglages) par celles de cette archive ?")) return;
    this.backupBusy = true;
    this.backupMessage = "";
    this.backupError = "";
    try {
      const body = new FormData();
      body.append("file", file);
      const { ok, status, data: payload } = await api.restore(body);
      if (!ok) { this.backupError = payload.detail || "Restauration impossible (" + status + ")"; return; }
      const total = Object.values(payload.tables || {}).reduce((a, b) => a + b, 0);
      this.backupMessage = "Données restaurées (" + total + " lignes). Rechargement…";
      // La vue courante peut afficher des données remplacées (indices, événements).
      setTimeout(() => location.reload(), 800);
    } catch {
      this.backupError = "Restauration impossible (réseau).";
    } finally {
      this.backupBusy = false;
    }
  },

  async purgeCache() {
    if (!confirm("Vider le cache (cours, comptes, métadonnées) ? Les données saisies sont conservées.")) return;
    this.backupBusy = true;
    this.backupMessage = "";
    this.backupError = "";
    try {
      const { ok, status, data: payload } = await api.purgeCache();
      if (!ok) { this.backupError = payload.detail || "Purge impossible (" + status + ")"; return; }
      this.backupMessage = "Cache vidé (" + (payload.removed ?? 0) + " entrées). Les cours seront rechargés au prochain affichage.";
    } catch {
      this.backupError = "Purge impossible (réseau).";
    } finally {
      this.backupBusy = false;
    }
  },

};
