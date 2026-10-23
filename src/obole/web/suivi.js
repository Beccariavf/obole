// Obole — bande « Suivi » de la fiche action (#21).
//
// Deux informations, réunies au-dessus de la thèse :
//
//  1. ÉCHÉANCE — la date du prochain résultat (donnée société, indépendante du
//     document) : date absolue, compte à rebours relatif, badge « estimé ».
//  2. POINTS DE CONTRÔLE — une liste de choses à cocher, POSSÉDÉE par
//     l'utilisateur et **indépendante** du markdown de la thèse (les deux ne
//     portent pas forcément les mêmes éléments). Persistée côté serveur.
//
// Aucun calcul métier ici : le compteur est dérivé de la liste reçue, et les
// bornes de libellé viennent de `config.py` (jamais un seuil littéral).
import { api } from "./api.js";
import { agendaRow } from "./markdown.js";
import { CHECKPOINT_LABEL_MAX } from "./thresholds.js";

export const checkpointsMixin = {
  // --- état -----------------------------------------------------------------
  // Alignement de fiche OBLIGATOIRE : sans le ticker suivi, une liste validée sur
  // une fiche s'afficherait (et s'écrirait) sous le ticker de la suivante — c'est
  // exactement la fuite d'état corrigée sur la thèse.
  cpTicker: null,
  cpLoaded: false,
  cpLoading: false,
  cpItems: [],
  cpDraft: "",
  cpError: "",
  cpBusy: false, // mutation en vol : on sérialise les écritures
  // Borne du libellé : SOURCE UNIQUE `config.py`, reçue par `/api/meta` et posée
  // au démarrage (cf. `app.js`). Aucun seuil littéral ici — le serveur valide de
  // toute façon (422) si le champ n'a pas encore reçu sa borne.
  cpLabelMax() {
    return CHECKPOINT_LABEL_MAX;
  },

  // --- échéance -------------------------------------------------------------

  // Ligne « prochain résultat » : date absolue + relatif, « publié » si passée.
  // Source unique : le bloc `profile` du payload `/api/stock` (0 appel de plus)
  // et la mise en forme de `markdown.js` (agendaRow), partagée avec l'agenda du
  // profil. La donnée n'est PAS dupliquée dans cet agenda (CA-B1).
  cpEarnings() {
    const iso = this.data?.profile?.next_earnings;
    const row = agendaRow(iso, { pastLabel: "publié" });
    if (!row) return null;
    return {
      ...row,
      // « estimé » ne qualifie qu'une date À VENIR : une échéance passée est un
      // fait, pas une prévision.
      estimated: !row.after && this.data?.profile?.next_earnings_estimated === true,
    };
  },

  // La bande existe-t-elle ? L'échéance est une donnée société : elle s'affiche
  // même sans thèse. Elle n'a de sens que sur une action (la section « these »
  // n'est de toute façon disponible que là).
  cpVisible() {
    return this.data?.kind_payload === "stock";
  },

  // --- compteur -------------------------------------------------------------

  cpTotal() {
    return this.cpItems.length;
  },

  cpDone() {
    return this.cpItems.filter((c) => c.done).length;
  },

  cpLabel() {
    const total = this.cpTotal();
    return total ? `${this.cpDone()}/${total}` : "";
  },

  cpProgress() {
    const total = this.cpTotal();
    return total ? Math.round((this.cpDone() / total) * 100) : 0;
  },

  // #21.4 : à 1 point, une barre vide n'exprime aucune progression — elle se lit
  // comme un filet de séparation et ajoute du bruit. La barre n'apparaît donc
  // qu'à partir de 2 points, où elle porte une information réelle.
  cpBarVisible() {
    return this.cpTotal() >= 2;
  },

  // #21.4 : le libellé visible « Points de contrôle » a disparu (densité), le
  // compteur est donc muet pour un lecteur d'écran sans un intitulé explicite.
  // Deux accords DISTINCTS : « validé(s) » suit le nombre de points cochés,
  // « point(s) de contrôle » suit le total — les lier à une seule variable
  // produisait « 1 point validé sur 1 points de contrôle ».
  cpLabelTitle() {
    const total = this.cpTotal();
    if (!total) return "";
    const done = this.cpDone();
    const valides = done > 1 ? "points validés" : "point validé";
    const sur = total > 1 ? "points de contrôle" : "point de contrôle";
    return `${done} ${valides} sur ${total} ${sur}`;
  },

  // Couleur du compteur : neutre tant que rien n'est coché (l'absence d'accent
  // évite de faire briller un « 0/1 » qui ne signale rien), accent dès le premier.
  cpHasDone() {
    return this.cpDone() > 0;
  },

  // En édition, le textarea fait foi : deux surfaces d'édition du même contenu
  // prêteraient à confusion (la liste reprend la main à la sortie du mode).
  cpListVisible() {
    return this.cpLoaded && !this.thesisEditing;
  },

  // --- chargement -----------------------------------------------------------

  resetCheckpoints() {
    this.cpTicker = null;
    this.cpLoaded = false;
    this.cpItems = [];
    this.cpDraft = "";
    this.cpError = "";
  },

  async loadCheckpoints() {
    if (!this.cpVisible()) return;
    const ticker = this.data?.identity?.ticker;
    if (!ticker) return;
    if (this.cpTicker !== ticker) this.resetCheckpoints();
    this.cpLoading = true;
    this.cpError = "";
    try {
      const items = await api.checkpoints(ticker);
      this.cpTicker = ticker;
      this.cpItems = Array.isArray(items) ? items : [];
    } catch (e) {
      // Une liste vide est la réponse normale d'un titre sans point de contrôle ;
      // toute autre erreur doit être visible, jamais avalée.
      this.cpTicker = ticker;
      this.cpItems = [];
      this.cpError = String(e?.message || e);
    } finally {
      this.cpLoading = false;
      this.cpLoaded = true;
    }
  },

  // --- mutations ------------------------------------------------------------
  // Toutes sérialisées par `cpBusy` : deux écritures concurrentes sur la même
  // liste ne doivent pas se chevaucher.

  async cpAdd() {
    const label = String(this.cpDraft || "").trim();
    if (!label || this.cpBusy) return;
    const ticker = this.data?.identity?.ticker;
    if (!ticker) return;
    this.cpBusy = true;
    this.cpError = "";
    const res = await api.addCheckpoint(ticker, label);
    this.cpBusy = false;
    if (!res.ok) {
      this.cpError = res.data?.detail || `Ajout impossible (${res.status})`;
      return;
    }
    this.cpDraft = "";
    await this.loadCheckpoints();
  },

  // Cochage optimiste : la case répond au geste, puis l'état serveur fait foi.
  // En cas d'échec, on REVIENT à l'état précédent et on l'annonce (jamais
  // silencieux) — un point coché à tort se lirait comme un travail fait.
  async cpToggle(item, done = null) {
    if (!item || this.cpBusy) return;
    const want = done == null ? !item.done : !!done;
    if (want === item.done) return;
    const previous = item.done;
    item.done = want;
    this.cpBusy = true;
    this.cpError = "";
    const res = await api.saveCheckpoint(item.id, item.label, want);
    this.cpBusy = false;
    if (!res.ok) {
      item.done = previous;
      this.cpError = res.data?.detail || `Enregistrement impossible (${res.status})`;
    }
  },

  async cpRemove(item) {
    if (!item || this.cpBusy) return;
    this.cpBusy = true;
    this.cpError = "";
    const res = await api.deleteCheckpoint(item.id);
    this.cpBusy = false;
    if (!res.ok && res.status !== 404) {
      this.cpError = res.data?.detail || `Suppression impossible (${res.status})`;
      return;
    }
    this.cpItems = this.cpItems.filter((c) => c.id !== item.id);
  },

  cpSubmit(ev) {
    ev.preventDefault();
    void this.cpAdd();
  },
};
