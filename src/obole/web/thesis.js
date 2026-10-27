// Obole — section « Thèse & Société » (#21).
//
// Deux zones dans une seule section :
//
//  1. PROFIL SOCIÉTÉ — lecture seule, alimentée par `/api/stock` (`profile`) :
//     dirigeants, effectif, siège, description, agenda (détachement). Le prochain
//     résultat est sorti de cette carte : il vit dans la bande « Suivi »
//     (`suivi.js`), une seule occurrence par fiche.
//     Aucune donnée société n'entre dans le document (CA-TOC12).
//  2. THÈSE — un document markdown possédé par l'auteur (ou écrit par l'IA via
//     MCP). Son sommaire et son plan sont DÉRIVÉS du texte (cf. `markdown.js`) :
//     rien n'est persisté en plus du document. Ses cases GFM restent cliquables
//     (document libre), indépendamment des points de contrôle suivis de la bande.
//
// Aucun LLM serveur (PRD §12.4) : l'UI ne propose donc jamais un bouton
// « Générer » qui mentirait — elle propose de copier le prompt, d'écrire, ou de
// passer par l'IA connectée (MCP).
import { api } from "./api.js";
import { THESIS_SKELETON, agendaRow, renderThesis, setTask } from "./markdown.js";

const AUTOSAVE_MS = 800;
const CEO_HINTS = ["ceo", "chief executive", "chairman", "président", "president", "directeur général"];

// Préférence d'affichage du PLAN latéral (#21.2). C'est une préférence LOCALE au
// navigateur (elle dépend de la largeur d'écran), pas un réglage de méthode : elle
// vit donc dans `localStorage`, jamais dans la table `settings` ni la sauvegarde.
const PLAN_PREF_KEY = "obole.thesis.planOpen";

// Lecture DÉFENSIVE du stockage local. Peut lever (mode privé, quota, contexte
// `file://`) ou renvoyer n'importe quoi : on ne laisse jamais cela casser la
// fiche. Valeur reconnue = "1" explicite ; tout le reste vaut « fermé ».
function readFlag(key) {
  try {
    return window.localStorage?.getItem(key) === "1";
  } catch {
    return false;
  }
}

// Écriture défensive : un échec (quota, stockage refusé) est sans conséquence
// sur l'état en mémoire — la bascule reste effective pour la session.
function writeFlag(key, value) {
  try {
    window.localStorage?.setItem(key, value ? "1" : "0");
  } catch {
    /* préférence non persistée : sans gravité, on continue */
  }
}

export const thesisMixin = {
  // --- état -----------------------------------------------------------------
  thesisLoaded: false,
  thesisLoading: false,
  thesisTicker: null,       // ticker auquel le contenu affiché appartient
  thesisContent: "",        // markdown courant (source unique du document)
  thesisOriginal: "",       // dernière version enregistrée (détection de changement)
  thesisUpdatedAt: null,    // horodatage serveur de la version chargée
  thesisEditing: false,
  thesisPreview: false,
  thesisSaving: false,
  thesisStatus: "idle",     // idle | dirty | saving | saved | error
  thesisSavedAt: "",
  thesisError: "",
  thesisConflict: false,
  thesisDragOver: false,
  thesisOutlineOpen: false,
  thesisActiveHeading: null,
  // Plan latéral (#21.2) : FERMÉ par défaut. À l'ouverture d'une thèse, le
  // sommaire intégré donne déjà la structure ; le plan sert PENDANT la lecture.
  // `null` = jamais chargé (la préférence est lue une fois, au démarrage).
  thesisPlanOpen: null,
  thesisView: { html: "", headings: [], toc: [], tocMain: [] },
  thesisNotice: "",
  _thesisTimer: null,
  _thesisObserver: null,

  // --- helpers d'affichage ---------------------------------------------------

  thesisHasContent() {
    return String(this.thesisContent || "").trim().length > 0;
  },

  thesisDirty() {
    return this.thesisContent !== this.thesisOriginal;
  },

  thesisTocVisible() {
    return this.thesisView.tocMain.length >= 2;
  },

  // --- plan latéral (#21.2) --------------------------------------------------

  // Charge la préférence UNE fois par session de navigation (idempotent) :
  // recharger la page la restitue, changer de fiche aussi (elle est globale, pas
  // par ticker — cf. CA-PL8).
  loadThesisPlanPreference() {
    if (this.thesisPlanOpen !== null) return;
    this.thesisPlanOpen = readFlag(PLAN_PREF_KEY);
  },

  toggleThesisPlan() {
    this.loadThesisPlanPreference();
    this.thesisPlanOpen = !this.thesisPlanOpen;
    writeFlag(PLAN_PREF_KEY, this.thesisPlanOpen);
  },

  // Le plan n'existe que s'il a de quoi afficher (un sommaire à plusieurs
  // niveaux) et hors édition : en édition, le textarea est la seule surface de
  // travail (même règle que la liste des points de contrôle suivis).
  thesisPlanVisible() {
    return !!this.thesisPlanOpen && this.thesisPlanAvailable();
  },

  // La POIGNÉE (#21.3) n'a de sens que si le plan peut exister : hors édition
  // et avec un sommaire à plusieurs niveaux. Elle est indépendante de l'état
  // ouvert/fermé — c'est le MÊME contrôle qui ouvre et referme, à toute hauteur
  // de lecture (l'ancien bouton d'en-tête sortait du champ au défilement).
  thesisPlanAvailable() {
    return !this.thesisEditing && this.thesisTocVisible();
  },

  // Pastille de l'onglet : le drapeau vient du payload `/api/stock` (`has_thesis`),
  // donc sans appel réseau supplémentaire (CA-UI2).
  thesisExists() {
    return !!this.data?.has_thesis;
  },

  // Dirigeant principal : la première entrée dont le titre ressemble à une
  // direction générale ; à défaut le premier dirigeant listé (yfinance met
  // souvent le CEO en tête).
  thesisCeo() {
    const officers = this.data?.profile?.officers || [];
    if (!officers.length) return null;
    const match = officers.find((o) => {
      const title = String(o.title || "").toLowerCase();
      return CEO_HINTS.some((h) => title.includes(h));
    });
    return match || officers[0];
  },

  profileFacts() {
    const p = this.data?.profile || {};
    const id = this.data?.identity || {};
    const ceo = this.thesisCeo();
    const facts = [];
    if (ceo) facts.push({ label: "Direction générale", value: ceo.name, note: ceo.title });
    if (p.employees) {
      facts.push({ label: "Effectif", value: p.employees.toLocaleString("fr-FR") });
    }
    if (p.address) facts.push({ label: "Siège", value: p.address });
    if (id.industry) facts.push({ label: "Industrie", value: id.industry });
    if (id.website) facts.push({ label: "Site web", value: id.website, href: id.website });
    return facts;
  },

  // Agenda : dates société restantes. Le PROCHAIN RÉSULTAT n'est plus ici : il
  // vit dans la bande « Suivi » (une seule occurrence par fiche, cf. `suivi.js`).
  // La mise en forme (date absolue, relatif, « passé ») vient de `markdown.js` :
  // une seule implémentation pour l'agenda du profil ET la bande « Suivi ».
  profileAgenda() {
    const p = this.data?.profile || {};
    const row = agendaRow(p.ex_dividend, { pastLabel: "passé" });
    if (!row) return [];
    return [{ label: "Ex-dividende", estimated: false, ...row }];
  },

  // --- chargement ------------------------------------------------------------

  // Réinitialise l'état de la thèse quand on change de fiche. Sans cela, le
  // contenu (et le mode édition) de RI.PA resterait à l'écran sur AI.PA, et
  // l'auto-save écrirait le texte de l'un sous le ticker de l'autre.
  resetThesisState() {
    if (this._thesisTimer) {
      clearTimeout(this._thesisTimer);
      this._thesisTimer = null;
    }
    this.stopThesisScrollSpy();
    this.thesisContent = "";
    this.thesisOriginal = "";
    this.thesisUpdatedAt = null;
    this.thesisTicker = null;
    this.thesisLoaded = false;
    this.thesisEditing = false;
    this.thesisPreview = false;
    this.thesisConflict = false;
    this.thesisStatus = "idle";
    this.thesisError = "";
    this.thesisActiveHeading = null;
    this.thesisView = { html: "", headings: [], toc: [], tocMain: [] };
  },

  async loadThesis() {
    if (this.data?.kind_payload !== "stock") return;
    const ticker = this.data.identity?.ticker;
    if (!ticker) return;
    // Fiche différente de celle dont le contenu est affiché : on repart de zéro
    // AVANT toute autre considération (sinon une saisie en cours sur l'ancien
    // ticker serait conservée et sauvegardée sous le nouveau).
    if (this.thesisTicker !== ticker) {
      this.resetThesisState();
    }
    // Une saisie en cours ne doit JAMAIS être écrasée par un rechargement : on
    // se contente alors de vérifier si la version serveur a bougé (CA-UI5).
    // Ne concerne que la MÊME fiche (le cas inter-fiches est traité ci-dessus).
    if (this.thesisLoaded && this.thesisEditing) {
      await this.checkThesisConflict();
      return;
    }
    this.thesisLoading = true;
    this.thesisError = "";
    try {
      const payload = await api.thesis(ticker);
      this.thesisTicker = ticker;
      this.thesisContent = this._contentToString(payload.content);
      this.thesisOriginal = this.thesisContent;
      this.thesisUpdatedAt = payload.updated_at || null;
      this.thesisConflict = false;
      this.thesisStatus = "idle";
    } catch (e) {
      // 404 = pas encore de thèse : ce n'est pas une erreur, c'est l'état vide.
      this.thesisTicker = ticker;
      this.thesisContent = "";
      this.thesisOriginal = "";
      this.thesisUpdatedAt = null;
      this.thesisStatus = "idle";
      if (!/404|Aucune thèse/i.test(String(e?.message || ""))) {
        this.thesisError = String(e?.message || e);
      }
    } finally {
      this.thesisLoading = false;
      this.thesisLoaded = true;
      this._thesisRecompute();
    }
  },

  // Une thèse historique peut être un objet JSON (jalon #09.3) : on l'affiche
  // comme une fiche markdown minimale plutôt que de la perdre.
  _contentToString(content) {
    if (content == null) return "";
    if (typeof content === "string") return content;
    if (typeof content === "object") {
      return Object.entries(content)
        .map(([key, value]) => `## ${key}\n\n${String(value)}`)
        .join("\n\n");
    }
    return String(content);
  },

  _thesisRecompute() {
    this.thesisView = renderThesis(this.thesisContent);
  },

  // --- édition ---------------------------------------------------------------

  startThesisEdit() {
    if (!this.thesisHasContent() && !this.thesisContent) this.thesisContent = "";
    this.thesisEditing = true;
    this.thesisPreview = false;
    this.thesisError = "";
    this.$nextTick?.(() => {
      const el = document.getElementById("thesis-editor");
      if (el) {
        el.focus();
        el.setSelectionRange(el.value.length, el.value.length);
      }
    });
  },

  stopThesisEdit() {
    this.thesisEditing = false;
    this.thesisPreview = false;
    this.onThesisInput();
    this._thesisRecompute();
  },

  onThesisInput() {
    this._thesisRecompute();
    if (this.thesisContent === this.thesisOriginal) {
      this.thesisStatus = "idle";
      return;
    }
    this.thesisStatus = "dirty";
    this._scheduleSave();
  },

  _scheduleSave() {
    if (this._thesisTimer) clearTimeout(this._thesisTimer);
    this._thesisTimer = setTimeout(() => this.saveThesisNow(), AUTOSAVE_MS);
  },

  async saveThesisNow() {
    if (this._thesisTimer) {
      clearTimeout(this._thesisTimer);
      this._thesisTimer = null;
    }
    if (!this.thesisDirty() || this.thesisSaving) return;
    const ticker = this.data?.identity?.ticker;
    if (!ticker) return;
    const sent = this.thesisContent;
    this.thesisSaving = true;
    this.thesisStatus = "saving";
    this.thesisError = "";
    const res = await api.saveThesis(ticker, sent);
    this.thesisSaving = false;
    if (!res.ok) {
      // Échec non silencieux : le contenu reste dans l'éditeur, l'utilisateur
      // peut réessayer. On ne réécrit jamais `thesisOriginal`.
      this.thesisStatus = "error";
      this.thesisError = res.data?.detail || `Échec de l'enregistrement (${res.status})`;
      return;
    }
    this.thesisOriginal = sent;
    this.thesisUpdatedAt = res.data?.updated_at ?? this.thesisUpdatedAt;
    if (this.data) this.data.has_thesis = true;
    // L'utilisateur a continué à taper pendant la requête : le document affiché
    // n'est plus celui qu'on vient d'enregistrer. On l'annonce honnêtement
    // (statut « dirty » + relance du debounce) plutôt que d'afficher
    // « Enregistré » sur un texte non sauvegardé.
    if (this.thesisContent !== sent) {
      this.thesisStatus = "dirty";
      this._scheduleSave();
      return;
    }
    this.thesisStatus = "saved";
    this.thesisSavedAt = new Date().toLocaleTimeString("fr-FR", {
      hour: "2-digit",
      minute: "2-digit",
    });
  },

  // Cochage d'un point de contrôle SANS entrer en mode édition (CA-UI6).
  // On fixe l'état VOULU (index + coché) plutôt que de basculer : un même clic
  // peut être dispatché deux fois (case + libellé), une bascule l'annulerait.
  thesisToggleTask(index, checked = null) {
    const lines = String(this.thesisContent || "").split("\n");
    let seen = 0;
    let current = false;
    for (const line of lines) {
      if (!/^\s*[-*+]\s+\[[ xX]\]\s+/.test(line)) continue;
      if (seen === index) {
        current = /^\s*[-*+]\s+\[[xX]\]/.test(line);
        break;
      }
      seen += 1;
    }
    const want = checked == null ? !current : !!checked;
    if (want === current) return;
    const next = setTask(this.thesisContent, index, want);
    if (next === this.thesisContent) return;
    this.thesisContent = next;
    this.onThesisInput();
  },

  // Index de la case cliquée, compté sur les cases du conteneur rendu : l'ordre
  // y est celui du document, comme dans `setTask`.
  onThesisBodyClick(ev) {
    const box = ev.target?.closest?.('input[type="checkbox"]');
    if (box) {
      const boxes = [...ev.currentTarget.querySelectorAll('input[type="checkbox"]')];
      const index = boxes.indexOf(box);
      if (index >= 0) this.thesisToggleTask(index, box.checked);
      return;
    }
    const link = ev.target?.closest?.('a[href^="#"]');
    if (!link) return;
    // Défilement interne : jamais d'écriture de `location.hash`, sinon le
    // routeur de sections croirait à un changement de fiche (CA-TOC5).
    ev.preventDefault();
    const slug = link.getAttribute("href").slice(1);
    const el = document.getElementById(slug);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    this.thesisActiveHeading = slug;
  },

  // Détection « modifiée ailleurs » (MCP, autre onglet) : on recharge pour
  // comparer, sans jamais écraser une saisie en cours.
  //
  // Trois déclencheurs, choisis pour ne coûter aucune requête inutile :
  //  1. au retour sur l'onglet (`visibilitychange`) — le cas réel : l'IA a écrit
  //     pendant qu'on regardait ailleurs ;
  //  2. au retour du focus fenêtre (`focus`) — changement d'application ;
  //  3. à l'ouverture de la section (dans `loadThesis`, cf. plus bas).
  // Aucun polling : une requête par geste utilisateur, jamais en boucle.
  checkThesisConflict() {
    const ticker = this.data?.identity?.ticker;
    if (!ticker || this.thesisEditing) return;
    return api.thesis(ticker).then(
      (payload) => {
        // `>` strict : une écriture locale vient de fixer `thesisUpdatedAt` à la
        // valeur serveur (cf. `saveThesisNow`), donc seule une version PLUS
        // récente signale un conflit.
        if (
          payload.updated_at &&
          this.thesisUpdatedAt &&
          payload.updated_at > this.thesisUpdatedAt
        ) {
          this.thesisConflict = true;
        }
        return payload;
      },
      () => {
        /* pas de thèse : rien à signaler */
      },
    );
  },

  // Branché sur `visibilitychange` / `focus`. Le coût est nul hors section
  // « these » : on sort immédiatement (aucune requête pour les autres sections).
  onThesisWindowFocus() {
    if (this.activeSection !== "these") return;
    if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
    void this.checkThesisConflict();
  },

  async reloadThesisFromServer() {
    this.thesisConflict = false;
    this.thesisEditing = false;
    await this.loadThesis();
  },

  keepLocalThesis() {
    this.thesisConflict = false;
    this.thesisOriginal = this.thesisContent;
    this.thesisStatus = "dirty";
    this._scheduleSave();
  },

  // --- toolbar ---------------------------------------------------------------

  insertMarkdown(before, after = "", opts = {}) {
    const el = document.getElementById("thesis-editor");
    const value = this.thesisContent;
    if (!el) {
      this.thesisContent = value + before + (opts.text || "") + after;
      this.onThesisInput();
      return;
    }
    const start = el.selectionStart ?? value.length;
    const end = el.selectionEnd ?? value.length;
    const selected = value.slice(start, end) || opts.text || "";
    const block = opts.block
      ? this._blockInsert(value, start, before, selected, after)
      : before + selected + after;
    const next = value.slice(0, start) + block + value.slice(end);
    this.thesisContent = next;
    this.onThesisInput();
    const caret = start + block.length - after.length;
    this.$nextTick?.(() => {
      el.focus();
      el.setSelectionRange(caret, caret);
    });
  },

  _blockInsert(value, start, before, selected, after) {
    // Saut de ligne seulement si l'insertion n'est pas déjà en début de ligne :
    // évite les lignes vides parasites quand on clique la toolbar en tête.
    const atLineStart = start === 0 || value[start - 1] === "\n";
    const head = atLineStart ? "" : "\n";
    const text = selected || after;
    return `${head}${before}${text}`;
  },

  insertHeading(level) {
    this.insertMarkdown(`${"#".repeat(level)} `, "", { block: true, text: "" });
  },

  insertBold() {
    this.insertMarkdown("**", "**", { text: "gras" });
  },

  insertItalic() {
    this.insertMarkdown("*", "*", { text: "italique" });
  },

  insertBullet() {
    this.insertMarkdown("- ", "", { block: true, text: "" });
  },

  insertTask() {
    this.insertMarkdown("- [ ] ", "", { block: true, text: "" });
  },

  insertLink() {
    this.insertMarkdown("[", "](https://)", { text: "libellé" });
  },

  insertImage(url) {
    const src = url || "https://";
    this.insertMarkdown(`![`, `](${src})`, { text: "légende" });
  },

  // Upload d'une image : le serveur valide (type, taille, signature), régénère
  // le nom et renvoie l'URL à insérer. Rien n'est inséré tant que l'upload n'a
  // pas abouti — jamais de lien mort dans le document.
  async uploadThesisImage(file) {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    try {
      const payload = await api.uploadThesisAsset(form);
      this.insertImage(payload.url);
      this.thesisNotice = "Image insérée.";
      setTimeout(() => {
        this.thesisNotice = "";
      }, 2500);
    } catch (e) {
      this.thesisError = String(e?.message || e);
      this.thesisStatus = "error";
    }
  },

  thesisPickImage(ev) {
    const file = ev.target?.files?.[0];
    if (file) this.uploadThesisImage(file);
    if (ev.target) ev.target.value = "";
  },

  // Coller une image dans l'éditeur (capture d'écran) : même voie que le bouton.
  onThesisPaste(ev) {
    const item = [...(ev.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
    if (!item) return;
    const file = item.getAsFile();
    if (file) {
      ev.preventDefault();
      this.uploadThesisImage(file);
    }
  },

  insertSkeleton() {
    if (this.thesisHasContent()) {
      this.thesisContent += `\n${THESIS_SKELETON}`;
    } else {
      this.thesisContent = THESIS_SKELETON;
    }
    this.onThesisInput();
    this.thesisOutlineOpen = false;
  },

  thesisMenuGoTo(slug) {
    const el = document.getElementById(slug);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    this.thesisOutlineOpen = false;
  },

  onThesisKeydown(ev) {
    const meta = ev.metaKey || ev.ctrlKey;
    if (meta && ev.key.toLowerCase() === "b") {
      ev.preventDefault();
      this.insertBold();
    } else if (meta && ev.key.toLowerCase() === "i") {
      ev.preventDefault();
      this.insertItalic();
    } else if (meta && ev.key.toLowerCase() === "s") {
      ev.preventDefault();
      this.saveThesisNow();
    } else if (ev.key === "Escape") {
      ev.preventDefault();
      this.stopThesisEdit();
    }
  },

  // --- rendu : plan latéral et ancres -----------------------------------------

  startThesisScrollSpy() {
    this.stopThesisScrollSpy();
    if (typeof IntersectionObserver === "undefined") return;
    const root = document.getElementById("thesis-body");
    if (!root) return;
    this._thesisObserver = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            this.thesisActiveHeading = entry.target.id;
            break;
          }
        }
      },
      { root: null, rootMargin: "-10% 0px -70% 0px", threshold: 0 },
    );
    for (const slug of this.thesisView.toc.map((t) => t.slug)) {
      const el = document.getElementById(slug);
      if (el) this._thesisObserver.observe(el);
    }
  },

  stopThesisScrollSpy() {
    if (this._thesisObserver) {
      this._thesisObserver.disconnect();
      this._thesisObserver = null;
    }
  },

  // --- import / export --------------------------------------------------------

  // Suppression : même convention que les autres collections d'Obole
  // (indices, événements, comptes du portefeuille) — confirmation explicite.
  // Seul moyen de revenir à l'état vide : écrire ou importer écrase.
  async deleteThesisNow() {
    const ticker = this.data?.identity?.ticker;
    if (!ticker) return;
    if (!confirm(`Supprimer définitivement la thèse de ${ticker} ?`)) return;
    const res = await api.deleteThesis(ticker);
    if (!res.ok && res.status !== 404) {
      this.thesisError = res.data?.detail || `Suppression impossible (${res.status})`;
      this.thesisStatus = "error";
      return;
    }
    if (this._thesisTimer) {
      clearTimeout(this._thesisTimer);
      this._thesisTimer = null;
    }
    this.thesisContent = "";
    this.thesisOriginal = "";
    this.thesisUpdatedAt = null;
    this.thesisEditing = false;
    this.thesisConflict = false;
    this.thesisStatus = "idle";
    this.thesisError = "";
    this._thesisRecompute();
    if (this.data) this.data.has_thesis = false;
    this.thesisNotice = "Thèse supprimée.";
    setTimeout(() => {
      this.thesisNotice = "";
    }, 2500);
  },

  // Le bouton est mis en avant comme LE différenciateur MCP : il ne doit jamais
  // échouer en silence. Un échec pose donc `thesisStatus = "error"` — sans quoi
  // `thesisError` resterait invisible (il n'est rendu que par le bloc
  // `.save-status` conditionné à ce statut).
  copyThesisPrompt() {
    const ticker = this.data?.identity?.ticker;
    if (!ticker) return;
    api.thesisPrompt(ticker).then(
      (res) => {
        if (!res.ok) {
          this.thesisError = res.data?.detail || `Prompt indisponible (${res.status})`;
          this.thesisStatus = "error";
          return;
        }
        this._writeClipboard(
          res.data?.prompt || "",
          "Prompt copié — colle-le dans ton IA.",
        );
      },
      (e) => {
        this.thesisError = String(e?.message || e);
        this.thesisStatus = "error";
      },
    );
  },

  _writeClipboard(text, message) {
    const fallback = () => {
      const el = document.createElement("textarea");
      el.value = text;
      document.body.appendChild(el);
      el.select();
      try {
        document.execCommand("copy");
      } finally {
        document.body.removeChild(el);
      }
    };
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).catch(fallback);
    } else {
      fallback();
    }
    this.thesisNotice = message;
    setTimeout(() => {
      this.thesisNotice = "";
    }, 2500);
  },

  exportThesis() {
    const ticker = this.data?.identity?.ticker || "these";
    const blob = new Blob([this.thesisContent], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${ticker}-these.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  thesisDrop(ev) {
    this.thesisDragOver = false;
    const file = ev.dataTransfer?.files?.[0];
    if (file) this.importThesisFile(file);
  },

  thesisPickFile(ev) {
    const file = ev.target?.files?.[0];
    if (file) this.importThesisFile(file);
    if (ev.target) ev.target.value = "";
  },

  // Import d'un document : le contenu EN COURS n'est jamais écrasé sans accord
  // (une thèse est du travail rédigé — même exigence que les suppressions
  // d'indices, d'événements et de comptes du portefeuille).
  importThesisFile(file) {
    if (!file) return;
    if (
      this.thesisHasContent() &&
      !confirm(
        "Remplacer la thèse actuelle par le contenu de ce fichier ? " +
          "La version actuelle sera perdue (elle n'est pas archivée).",
      )
    ) {
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      this.thesisContent = String(reader.result || "");
      this.thesisEditing = true;
      this.onThesisInput();
    };
    reader.onerror = () => {
      this.thesisError = "Lecture du fichier impossible.";
    };
    reader.readAsText(file);
  },
};
