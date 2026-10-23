// Obole — helpers génériques (slug d'id, parsing CSV).

export function slug(s) { return s.replace(/[^a-zA-Z0-9]/g, "-"); }

// Délimiteurs candidats d'un CSV « venu de l'extérieur » : virgule (norme),
// point-virgule (Excel FR), tabulation (copier-coller d'un tableur). Miroir de
// `data/manual._DELIMITERS` côté serveur.
const DELIMITERS = [",", ";", "\t"];

// Choisit le délimiteur de la première ligne non vide (le plus fréquent).
// Miroir de `data/manual._detect_delimiter` : l'aperçu front et l'import serveur
// reconnaissent donc les MÊMES fichiers.
export function detectDelimiter(text) {
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue;
    let best = ",", bestCount = 0;
    for (const d of DELIMITERS) {
      const count = line.split(d).length - 1;
      if (count > bestCount) { best = d; bestCount = count; }
    }
    return bestCount > 0 ? best : ",";
  }
  return ",";
}

// Parse une ligne CSV en gérant les champs entre guillemets (virgules internes).
export function parseCSVLine(line, delimiter = ",") {
  const result = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      inQuotes = !inQuotes;
    } else if (ch === delimiter && !inQuotes) {
      result.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  result.push(current.trim());
  return result;
}

// Parse le texte CSV complet : lignes filtrées (vides ignorées), cellules gérant
// les guillemets. Le délimiteur est détecté si non fourni.
export function parseCSV(text, delimiter) {
  const d = delimiter || detectDelimiter(text);
  return text.split(/\r?\n/)
    .filter((l) => l.trim())
    .map((l) => parseCSVLine(l, d));
}

// Symboles ignorés dans une cellule numérique (miroir de `data/manual`).
const THOUSANDS_CHARS = " \u00a0\u202f'’";
const CURRENCY_CHARS = "€$£¥%";

// Convertit une cellule en nombre, ou null si elle n'est pas numérique.
// Miroir de `data/manual._parse_number` : virgule décimale, séparateurs de
// milliers, parenthèses négatives, devise. Une LETTRE invalide la cellule (sinon
// « pomme0 » passerait pour 0).
export function parseNumber(raw) {
  if (raw == null) return null;
  let s = String(raw).trim();
  if (!s) return null;
  let negative = false;
  if (s.startsWith("(") && s.endsWith(")")) { negative = true; s = s.slice(1, -1).trim(); }
  // Ne garde que les caractères numériques et les symboles connus ; toute autre
  // lettre/symbole invalide la cellule.
  if ([...s].some((ch) => !/[0-9.,+-]/.test(ch) && !THOUSANDS_CHARS.includes(ch) && !CURRENCY_CHARS.includes(ch))) return null;
  s = [...s].filter((ch) => !THOUSANDS_CHARS.includes(ch) && !CURRENCY_CHARS.includes(ch)).join("");
  if (!s) return null;
  if (s.startsWith("-")) { negative = !negative; s = s.slice(1).trim(); }
  else if (s.startsWith("+")) { s = s.slice(1).trim(); }
  const hasDot = s.includes("."), hasComma = s.includes(",");
  if (hasDot && hasComma) {
    if (s.lastIndexOf(",") > s.lastIndexOf(".")) s = s.replaceAll(".", "").replace(",", ".");
    else s = s.replaceAll(",", "");
  } else if (hasComma) {
    const parts = s.split(",");
    if (parts.length === 2 && parts[1].length !== 3) s = `${parts[0]}.${parts[1]}`;
    else s = s.replaceAll(",", "");
  }
  const value = Number(s);
  if (!Number.isFinite(value)) return null;
  return negative ? -value : value;
}
