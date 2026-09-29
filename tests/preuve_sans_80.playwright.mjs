/**
 * Preuve prod FRONT-VERITE-2 — a lancer par le proprietaire apres merge.
 * Pas execute en CI.
 *
 *   npx playwright install chromium
 *   BASE_URL=https://<site> node tests/preuve_sans_80.playwright.mjs
 *
 * Verifie 1280 px et 390 px : 0 fois « /80 » sur les 7 pages, la fiche SNTS,
 * les fenetres Analyse IA / Backtest / Markowitz et Commodites.
 * Controle aussi le PDF, Partager (« Copie ! ») et /api/chat en 404.
 */
import { execFileSync } from "child_process";
import { writeFileSync, unlinkSync } from "fs";
import { chromium } from "playwright";

const base = (process.env.BASE_URL || "http://127.0.0.1:5000").replace(/\/$/, "");
const pages = ["welcome", "rank", "screener", "news", "signals", "glossaire", "settings"];
const viewports = [
  { width: 1280, height: 800, label: "1280" },
  { width: 390, height: 844, label: "390" },
];

function erreurs(liste, message) {
  liste.push(message);
  console.error("ECHEC " + message);
}

async function texteVisible(page) {
  return page.evaluate(function () {
    var el = document.querySelector(".main") || document.body;
    return (el.innerText || "").replace(/\s+/g, " ");
  });
}

async function ouvrir(page, hash) {
  await page.goto(base + "/#" + hash, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1200);
}

const browser = await chromium.launch();
const echecs = [];
const page = await browser.newPage();
const consoleErreurs = [];
page.on("console", function (msg) {
  if (msg.type() === "error") consoleErreurs.push(msg.text());
});
page.on("pageerror", function (err) {
  consoleErreurs.push(String(err));
});

const accueil = await page.request.get(base + "/");
if (accueil.status() !== 200) erreurs(echecs, "/ status " + accueil.status());
const chat = await page.request.get(base + "/api/chat");
if (chat.status() !== 404) erreurs(echecs, "/api/chat status " + chat.status());

const pdf = await page.request.get(base + "/api/rapport/SNTS");
if (pdf.status() !== 200) {
  erreurs(echecs, "PDF SNTS status " + pdf.status());
} else {
  const type = pdf.headers()["content-type"] || "";
  if (type.indexOf("pdf") === -1) erreurs(echecs, "PDF SNTS type " + type);
  const tmp = "/tmp/brvm-preuve-snts.pdf";
  writeFileSync(tmp, await pdf.body());
  try {
    const texte = execFileSync("pdftotext", ["-layout", tmp, "-"], { encoding: "utf8" });
    if (texte.indexOf("/10") === -1) erreurs(echecs, "PDF sans /10");
    if (texte.indexOf("/ 80") !== -1 || texte.indexOf("/80") !== -1) erreurs(echecs, "PDF contient /80");
    if (texte.indexOf("Verdict IA") !== -1) erreurs(echecs, "PDF contient Verdict IA");
  } catch (e) {
    console.log("pdftotext absent : ouvrir le PDF a la main pour la preuve texte");
  }
  try { unlinkSync(tmp); } catch (e2) {}
}

for (const vp of viewports) {
  await page.setViewportSize({ width: vp.width, height: vp.height });
  for (const id of pages) {
    await ouvrir(page, id);
    const texte = await texteVisible(page);
    if (texte.indexOf("/80") !== -1) erreurs(echecs, vp.label + " page " + id + " contient /80");
  }

  await ouvrir(page, "marche");
  await page.click("button.tab-btn >> text=Commodités").catch(function () {});
  await page.waitForTimeout(800);
  const comm = await texteVisible(page);
  if (comm.indexOf("/80") !== -1) erreurs(echecs, vp.label + " commodites contient /80");
  if (vp.label === "1280" && comm.indexOf("SCRC") !== -1 && /\bSCRC\b[\s\S]{0,80}7\.0\b/.test(comm) && comm.indexOf("0.9") === -1 && comm.indexOf("0,9") === -1) {
    erreurs(echecs, "SCRC encore affiche comme 7.0");
  }

  await ouvrir(page, "stock/SNTS");
  await page.waitForTimeout(1500);
  const fiche = await texteVisible(page);
  if (fiche.indexOf("/80") !== -1) erreurs(echecs, vp.label + " fiche SNTS contient /80");
  if (fiche.indexOf("est Note") !== -1) erreurs(echecs, "fiche dit encore est Note");
  if (fiche.indexOf("obtient") === -1 || fiche.indexOf("/10") === -1) {
    erreurs(echecs, vp.label + " fiche sans obtient /10");
  }

  if (vp.width >= 800) {
    const partager = page.locator("button", { hasText: "Partager" }).first();
    if (await partager.count()) {
      await partager.click();
      const banner = page.locator("#share-copie-banner");
      try {
        await banner.waitFor({ state: "visible", timeout: 3000 });
        const lu = await banner.innerText();
        if (lu.indexOf("Copié") === -1) erreurs(echecs, "confirmation partage illisible");
      } catch (e) {
        erreurs(echecs, "Copié ! absent apres Partager");
      }
    } else {
      erreurs(echecs, "bouton Partager introuvable");
    }
  }

  for (const ouverture of ["openCompareAnalysis", "openBacktest", "openMarkowitz"]) {
    await page.evaluate(function (nom) {
      if (typeof window[nom] === "function") window[nom](["SNTS"]);
    }, ouverture);
    await page.waitForTimeout(400);
    const fenetre = await texteVisible(page);
    if (fenetre.indexOf("/80") !== -1) erreurs(echecs, vp.label + " " + ouverture + " contient /80");
    await page.keyboard.press("Escape").catch(function () {});
    await page.evaluate(function () {
      ["ca-modal", "bt-modal", "mrk-modal"].forEach(function (id) {
        var m = document.getElementById(id);
        if (m) m.style.display = "none";
      });
    });
  }
}

await browser.close();
if (consoleErreurs.length) {
  erreurs(echecs, "erreurs console: " + consoleErreurs.slice(0, 5).join(" | "));
}
if (echecs.length) {
  console.error(echecs.length + " echec(s)");
  process.exit(1);
}
console.log("preuve sans /80 OK sur " + base);
