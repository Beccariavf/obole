import { expect } from "@playwright/test";

// Défilement e2e sans délai fixe, partagé par les specs qui font défiler le
// document. Deux pièges vus sur le runner WebKit de la CI :
//   - `mouse.wheel` part de la position courante de la souris ; laissée en
//     (0, 0), elle tombe sur le rail, qui défile sur lui-même, et le document
//     ne bouge pas. On la pose donc au centre de la zone principale.
//   - le défilement est asynchrone : on attend qu'il ait commencé PUIS qu'il
//     soit stable, au lieu d'un `waitForTimeout`.

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

// Molette de `dy` px depuis le contenu ; rend la main une fois le document
// immobile, après avoir vérifié qu'il a bien bougé (ou qu'il est en bas).
export async function molette(page, dy) {
  const main = await page.locator(".app-main").boundingBox();
  const vue = page.viewportSize();
  await page.mouse.move(main.x + main.width / 2, Math.min(main.y + main.height / 2, vue.height / 2));
  const avant = await page.evaluate(() => window.scrollY);
  await page.mouse.wheel(0, dy);
  // A bougé, ou ne PEUT plus bouger (déjà en bas de page) : les deux sont un
  // état final valable, c'est au test de juger la position obtenue.
  await expect
    .poll(() =>
      page.evaluate(
        (y0) =>
          window.scrollY !== y0 ||
          window.scrollY >= document.documentElement.scrollHeight - window.innerHeight - 1,
        avant,
      ),
    )
    .toBe(true);
  await attendreDefilementStable(page);
}
