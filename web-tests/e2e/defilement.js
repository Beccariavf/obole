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

// Fait défiler le document de `dy` px puis rend la main une fois immobile.
export async function defiler(page, dy) {
  await page.evaluate((d) => window.scrollBy(0, d), dy);
  await attendreDefilementStable(page);
}
