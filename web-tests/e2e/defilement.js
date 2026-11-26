import { expect } from "@playwright/test";

// Défilement e2e sans délai fixe, partagé par les specs qui font défiler le
// document pour mesurer ce qui COLLE (en-tête, plan de thèse, bandeau du
// portefeuille). Aucune d'elles ne teste la molette elle-même.
//
// Pourquoi pas `mouse.wheel` : sur le runner WebKit Linux de la CI, une molette
// de 600 ou 900 px ne déplaçait parfois le document que de 57 à 131 px (et, partie
// de (0, 0), tombait sur le rail qui défile sur lui-même). Le défilement par
// script est déterministe ; on attend quand même qu'il soit stable.

// Défilement fini : deux lectures de `scrollY` identiques à 200 ms d'écart.
export async function attendreDefilementStable(page) {
  await expect
    .poll(async () => {
      const a = await page.evaluate(() => window.scrollY);
      await new Promise((r) => setTimeout(r, 200));
      return a === (await page.evaluate(() => window.scrollY));
    })
    .toBe(true);
}

// Mise en page posée : hauteur du document identique à 200 ms d'écart. Un clic
// d'ancre ou un défilement lancé pendant qu'une vue se remplit encore vise une
// position qui bouge ensuite (CI : titre d'ancre décalé sous l'en-tête).
export async function attendreMiseEnPageStable(page) {
  await expect
    .poll(async () => {
      const h = await page.evaluate(() => document.documentElement.scrollHeight);
      await new Promise((r) => setTimeout(r, 200));
      return h === (await page.evaluate(() => document.documentElement.scrollHeight));
    })
    .toBe(true);
}

// Fait défiler le document de `dy` px puis rend la main une fois immobile.
// `scrollTo(y0 + dy)` est IDEMPOTENT : on peut le rejouer tant que la vue n'est
// pas encore assez haute pour défiler (CI : `scrollY` resté à 0 sur une vue
// Paramètres encore vide). Déjà en bas de page au départ : rien à faire, c'est
// au test de juger la position.
export async function defiler(page, dy) {
  await attendreMiseEnPageStable(page);
  const y0 = await page.evaluate(() => window.scrollY);
  await expect
    .poll(
      () =>
        page.evaluate(
          ([depart, d]) => {
            const max = document.documentElement.scrollHeight - window.innerHeight;
            if (depart >= max - 1) return true;
            window.scrollTo(0, depart + d);
            return window.scrollY !== depart;
          },
          [y0, dy],
        ),
      { message: `le document n'a pas défilé de ${dy} px depuis ${y0}` },
    )
    .toBe(true);
  await attendreDefilementStable(page);
}
