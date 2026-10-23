// Obole — thèse d'entreprise : rendu markdown, sommaire et cases à cocher.
//
// Module PUR (aucun `fetch`, aucune I/O) : toute la logique de document vit ici,
// la même que celle testée par `web-tests/markdown.test.js`. C'est le pendant
// front de `thresholds.js` — un module de logique importable, pas un habillage.
//
// Les POINTS DE CONTRÔLE SUIVIS ne vivent PAS ici : c'est une liste persistée à
// part (bande « Suivi », `suivi.js`), indépendante du document. Ce module ne
// connaît que les cases GFM du document lui-même (`isTaskLine`, `setTask`).
//
// Deux invariants structurels (chantier #21) :
//
//  1. Le SOMMAIRE n'est jamais persisté. Il est dérivé des titres à l'affichage.
//     L'écrire dans le contenu le ferait exporter, dupliquer au ré-import et
//     diverger dès le premier renommage de titre.
//  2. Les `id` des titres rendus sont posés PAR NOUS, dans le même ordre et avec
//     la même fonction de slug que le sommaire : la parité ancre <-> titre est
//     garantie par construction, pas par la bonne volonté du parseur.
//
// `marked` et `DOMPurify` sont vendorisés (`vendor/marked.min.js`,
// `vendor/dompurify.min.js`) et exposés en global par `index.html` : le front n'a
// pas de build, donc pas d'import de package.

const MAX_DEPTH_TOC = 3;

function markedLib() {
  return typeof window !== "undefined" ? window.marked : undefined;
}

function purifyLib() {
  return typeof window !== "undefined" ? window.DOMPurify : undefined;
}

// --- Slugs ------------------------------------------------------------------

// Dépliage des diacritiques latins courants : les titres français doivent
// produire des ancres stables et lisibles (« Résultats » -> « resultats »).
const ACCENTS =
  "àâäáãåçèéêëìíîïñòóôöõùúûüýÿÀÂÄÁÃÅÇÈÉÊËÌÍÎÏÑÒÓÔÖÕÙÚÛÜÝ";
const PLAIN =
  "aaaaaaceeeeiiiinooooouuuuyyAAAAAACEEEEIIIINOOOOOUUUUY";

export function slugify(text) {
  let out = String(text == null ? "" : text);
  for (let i = 0; i < ACCENTS.length; i++) {
    out = out.split(ACCENTS[i]).join(PLAIN[i]);
  }
  out = out
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  return out || "section";
}

// --- Extraction des titres ---------------------------------------------------

// Texte brut d'un titre : on retire le markdown inline (`**gras**`, `[lien](url)`,
// `code`) pour que le sommaire affiche une étiquette propre.
export function headingText(raw) {
  return String(raw == null ? "" : raw)
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[*_`~]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

// Titres du document, dans l'ordre DOCUMENT, avec ancres uniques.
//
// On part des TOKENS de `marked` (et non d'un scan ligne à ligne) : un `#` dans
// un bloc de code Est déjà typé `code` par le parseur et ne peut donc pas être
// pris pour un titre. C'est ce qui rend CA-TOC4 vrai par construction.
//
// La collecte est RÉCURSIVE (citations, listes) pour rester alignée sur le HTML
// produit : `marked` rend `<hN>` même pour un titre cité, et `applyHeadingIds`
// apparie les deux listes par POSITION. Ignorer ici un titre que le rendu
// produit décalerait tous les `id` suivants et ferait pointer le sommaire sur
// le mauvais bloc (il pointerait sur la citation).
//
// `topLevel` distingue les titres de la structure propre du document (ceux que
// le SOMMAIRE expose) de ceux imbriqués dans une citation ou une liste, qui
// reçoivent une ancre — pour l'alignement — mais restent hors sommaire.
function collectHeadingTokens(tokens, out, topLevel = true) {
  for (const token of tokens || []) {
    if (!token) continue;
    if (token.type === "heading") {
      out.push({ token, topLevel });
      continue;
    }
    if (token.type === "blockquote") {
      collectHeadingTokens(token.tokens, out, false);
      continue;
    }
    if (token.type === "list") {
      for (const item of token.items || []) {
        collectHeadingTokens(item?.tokens, out, false);
      }
    }
  }
  return out;
}

export function extractHeadings(markdown) {
  const md = markedLib();
  if (!md || !md.lexer) return [];
  let tokens;
  try {
    tokens = md.lexer(String(markdown == null ? "" : markdown));
  } catch {
    return [];
  }
  const flat = collectHeadingTokens(tokens, []);
  const used = new Map();
  return flat.map(({ token, topLevel }) => {
    const level = token.depth || 1;
    const text = headingText(token.text);
    let slug = slugify(text);
    const count = used.get(slug) || 0;
    used.set(slug, count + 1);
    if (count > 0) slug = `${slug}-${count + 1}`;
    return { level, text, slug, topLevel };
  });
}

// Sommaire : entrées plates (niveau -> classe) au-dessus de `maxDepth`.
// Seuls les titres de PREMIER NIVEAU sont exposés (une citation n'est pas une
// section de la thèse), mais leurs `id` restent posés dans le document.
export function buildToc(headings, maxDepth = MAX_DEPTH_TOC) {
  const list = Array.isArray(headings) ? headings : [];
  return list
    .filter((h) => h.topLevel !== false && h.level <= maxDepth)
    .map((h, index) => ({ ...h, index: index + 1 }));
}

// --- Rendu ------------------------------------------------------------------

const HEADING_RE = /<h([1-6])(\s[^>]*)?>/gi;

function applyHeadingIds(html, headings) {
  let i = 0;
  return html.replace(HEADING_RE, (match, level, attrs) => {
    const heading = headings[i++];
    const cleaned = (attrs || "").replace(/\sid="[^"]*"/gi, "");
    if (!heading) return `<h${level}${cleaned}>`;
    return `<h${level}${cleaned} id="${heading.slug}">`;
  });
}

export function escapeHtml(text) {
  return String(text == null ? "" : text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Rendu sûr : le HTML produit par `marked` est TOUJOURS passé à DOMPurify.
// `x-html` était jusqu'ici réservé aux SVG inline (aucun contenu utilisateur) :
// ce module est le seul endroit qui casse cette propriété, il doit donc la
// rétablir lui-même, à chaque appel.

// Sources d'image admises dans une thèse : les assets servis par Obole, en
// relatif (`/api/thesis/assets/...`) et les URL `blob:`/`data:` d'aperçu local
// que l'éditeur produit avant l'envoi. Tout le reste (http(s) externe,
// `data:text/html`) est retiré : une thèse est un document, pas un canal
// d'exfiltration ni un vecteur XSS.
const ALLOWED_IMG_SRC = [
  /^\/api\/thesis\/assets\/[A-Za-z0-9._-]+$/,
  /^blob:/,
  /^data:image\/(png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+$/,
];

function sanitize(html, purify) {
  if (!purify || !purify.sanitize) return html;
  // Le hook est posé puis retiré : DOMPurify est global et ses hooks
  // s'accumulent — un rendu ne doit pas laisser de trace pour le suivant.
  const hook = (node) => {
    if (node.tagName === "IMG") {
      const src = String(node.getAttribute("src") || "");
      if (!ALLOWED_IMG_SRC.some((re) => re.test(src))) {
        node.removeAttribute("src");
        node.setAttribute("alt", node.getAttribute("alt") || "");
      }
    }
  };
  purify.addHook("afterSanitizeAttributes", hook);
  try {
    return purify.sanitize(html, { ADD_ATTR: ["target"] });
  } finally {
    purify.removeHook("afterSanitizeAttributes");
  }
}

export function renderMarkdown(markdown, headings) {
  const md = markedLib();
  const purify = purifyLib();
  const src = String(markdown == null ? "" : markdown);
  if (!md || !md.parse) return `<p>${escapeHtml(src)}</p>`;
  let html;
  try {
    html = md.parse(src, { gfm: true, breaks: false });
  } catch {
    return `<p>${escapeHtml(src)}</p>`;
  }
  const list = headings || extractHeadings(src);
  html = applyHeadingIds(html, list);
  const safe = sanitize(html, purify);
  // Les cases GFM sortent `disabled` : on les rend cliquables (le cochage est
  // routé vers `toggleTask`, cf. `thesis.js`) sans toucher au reste du HTML.
  return safe.replace(/<input([^>]*type="checkbox"[^>]*)>/gi, (m, attrs) =>
    `<input${String(attrs).replace(/\s?disabled(="[^"]*")?/i, "")}>`,
  );
}

// Rendu complet pour la fiche : corps + sommaire dérivé. Le sommaire n'est PAS
// ajouté ici (il est rendu par son propre template, donc jamais stocké).
//
// DEUX profondeurs, pour deux usages (CA-TOC3) :
//  - `toc`      -> 3 niveaux, sert le PLAN latéral et le menu d'édition (on
//                  navigue plus finement dans un document long) ;
//  - `tocMain`  -> 2 niveaux, sert le SOMMAIRE intégré (au-delà, illisible dans
//                  la colonne de lecture de 72 caractères).
// Aucun compteur de points de contrôle ici : les points de contrôle SUIVIS
// vivent dans leur propre liste persistée (bande « Suivi », `suivi.js`). Le
// document reste libre et ses cases GFM restent cliquables (`setTask`), mais
// aucun compteur n'en dérive — il n'y aurait plus qu'un seul « n/N » à l'écran.
export function renderThesis(markdown) {
  const headings = extractHeadings(markdown);
  return {
    html: renderMarkdown(markdown, headings),
    headings,
    toc: buildToc(headings, MAX_DEPTH_TOC),
    tocMain: buildToc(headings, 2),
  };
}

// --- Cases à cocher du document ----------------------------------------------

// Lignes de task-list GFM : `- [ ] …` / `- [x] …` (indentation tolérée).
export function isTaskLine(line) {
  return /^\s*[-*+]\s+\[[ xX]\]\s+/.test(line);
}

// Coche/décoche la n-ième case du document (index 0 fondé sur les cases, pas sur
// les lignes) : c'est le geste de coche EN LECTURE du document, sans passer par
// le mode édition.
export function setTask(markdown, taskIndex, checked) {
  const lines = String(markdown == null ? "" : markdown).split("\n");
  let seen = 0;
  for (let i = 0; i < lines.length; i++) {
    if (!isTaskLine(lines[i])) continue;
    if (seen !== taskIndex) {
      seen += 1;
      continue;
    }
    lines[i] = lines[i].replace(/\[[ xX]\]/, checked ? "[x]" : "[ ]");
    return lines.join("\n");
  }
  return markdown;
}

// Bascule une case, à partir de l'état courant — API d'appoint pour un usage
// direct (script, console) ET pour les tests : l'application, elle, passe par
// `setTask` (état voulu explicite, insensible au double dispatch d'un clic).
export const toggleTask = (markdown, taskIndex) => {
  const lines = String(markdown == null ? "" : markdown).split("\n");
  let seen = 0;
  for (const line of lines) {
    if (!isTaskLine(line)) continue;
    if (seen === taskIndex) {
      return setTask(
        markdown,
        taskIndex,
        !/^\s*[-*+]\s+\[[xX]\]/.test(line),
      );
    }
    seen += 1;
  }
  return markdown;
};

// Squelette de structure : geste d'ÉDITION (on écrit du markdown, l'auteur le
// possède ensuite). La liste des titres suit `services/thesis.PROMPT_TEMPLATE`
// — une source unique de la structure attendue, jamais un seuil ni une formule.
export const THESIS_SKELETON = [
  "# Thèse",
  "",
  "## Pitch",
  "",
  "## Bull case",
  "",
  "## Bear case",
  "",
  "## Catalyseurs",
  "",
  "## Points de contrôle",
  "",
  "- [ ] ",
  "",
].join("\n");

// --- Dates d'agenda ----------------------------------------------------------

const DAY_MS = 86400000;

// Nombre de jours entre `isoDate` et `now` (négatif si la date est passée).
// `null` si la date est absente ou illisible. C'est la SOURCE UNIQUE du calcul :
// on ne déduit jamais « c'est passé » en inspectant le libellé renvoyé par
// `relativeDays` (un renommage du texte casserait silencieusement l'affichage).
export function daysUntil(isoDate, now = new Date()) {
  if (!isoDate) return null;
  const target = new Date(`${String(isoDate).slice(0, 10)}T00:00:00`);
  if (Number.isNaN(target.getTime())) return null;
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((target - today) / DAY_MS);
}

// « dans 45 j » — la date absolue seule ne se lit pas. Le calcul est fait
// relativement à `now` pour être testable.
export function relativeDays(isoDate, now = new Date()) {
  const days = daysUntil(isoDate, now);
  if (days === null) return null;
  if (days === 0) return "aujourd'hui";
  if (days === 1) return "demain";
  if (days < 0) return `il y a ${Math.abs(days)} j`;
  return `dans ${days} j`;
}

// Date ISO -> « 3 octobre 2026 » (français). SOURCE UNIQUE : la même
// présentation sert l'agenda du profil et la bande « Suivi » — deux copies
// divergeraient à la première retouche.
export function formatDate(isoDate) {
  if (!isoDate) return "";
  const d = new Date(`${String(isoDate).slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return String(isoDate);
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

// Ligne d'agenda : date absolue + relatif + état (« passé » si la date est
// révolue). `pastLabel` distingue le vocabulaire du résultat (« publié ») de
// celui du détachement (« passé »).
export function agendaRow(isoDate, { pastLabel = "passé", now = new Date() } = {}) {
  if (!isoDate) return null;
  const days = daysUntil(isoDate, now);
  if (days === null) return null;
  const past = days < 0;
  return {
    date: formatDate(isoDate),
    relative: past ? "" : relativeDays(isoDate, now),
    after: past ? pastLabel : "",
  };
}

export const thesisMarkdown = {
  slugify,
  headingText,
  extractHeadings,
  buildToc,
  renderMarkdown,
  renderThesis,
  isTaskLine,
  setTask,
  toggleTask,
  relativeDays,
  daysUntil,
  formatDate,
  agendaRow,
  escapeHtml,
  THESIS_SKELETON,
};
