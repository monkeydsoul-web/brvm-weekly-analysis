"""
BRVM Alerter — Phase 4
Envoie des alertes email automatiques quand:
  - Une action franchit un seuil de score composite
  - Un dividende est confirmé
  - Une news importante est détectée (résultats, fusion, nomination)
  - Le rapport hebdomadaire est prêt

Configuration: fichier config_email.json à la racine du projet
"""

import os
import json
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

logger = logging.getLogger(__name__)

CONFIG_FILE = "config_email.json"
ALERTS_LOG = "data/alerts_sent.json"

# ── Template de configuration ─────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "enabled": False,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": "TON_EMAIL@gmail.com",
    "sender_password": "TON_MOT_DE_PASSE_APPLICATION",
    "recipient_emails": ["TON_EMAIL@gmail.com"],
    "thresholds": {
        "score_fort": 55,
        "score_hausse": 5,
        "score_baisse": -5,
        "sentiment_alerte": 3,
    },
    "alert_types": {
        "rapport_hebdo": True,
        "dividende_confirme": True,
        "resultats_importants": True,
        "score_franchissement": True,
        "news_negative": True,
    }
}


def load_email_config() -> dict:
    """Charge la configuration email"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Config email invalide: {e}")
    return DEFAULT_CONFIG


def save_default_config():
    """Crée le fichier de config si inexistant"""
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        logger.info(f"Config email créée: {CONFIG_FILE} — Remplis tes identifiants")


def load_alerts_log() -> list:
    """Charge le journal des alertes déjà envoyées"""
    if os.path.exists(ALERTS_LOG):
        try:
            with open(ALERTS_LOG) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_alerts_log(alerts: list):
    """Sauvegarde le journal des alertes"""
    os.makedirs(os.path.dirname(ALERTS_LOG), exist_ok=True)
    with open(ALERTS_LOG, "w") as f:
        json.dump(alerts[-200:], f, indent=2)  # Garder les 200 dernières alertes


def send_email(
    config: dict,
    subject: str,
    body_html: str,
    attachments: list[str] = None,
) -> bool:
    """Envoie un email via SMTP Gmail"""
    if not config.get("enabled"):
        logger.info(f"Email désactivé — sujet: {subject}")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = config["sender_email"]
        msg["To"] = ", ".join(config["recipient_emails"])
        msg["Subject"] = subject

        # Corps HTML
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        # Pièces jointes
        for filepath in (attachments or []):
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                filename = os.path.basename(filepath)
                part.add_header("Content-Disposition", f"attachment; filename={filename}")
                msg.attach(part)

        # Envoi SMTP
        with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
            server.ehlo()
            server.starttls()
            server.login(config["sender_email"], config["sender_password"])
            server.sendmail(
                config["sender_email"],
                config["recipient_emails"],
                msg.as_string()
            )

        logger.info(f"✅ Email envoyé: {subject}")
        return True

    except Exception as e:
        logger.error(f"❌ Erreur envoi email: {e}")
        return False


def email_html_template(title: str, content: str, week_label: str) -> str:
    """Template HTML pour les emails d'alerte"""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, Arial, sans-serif; margin: 0; padding: 0; background: #f5f5f5; }}
  .container {{ max-width: 600px; margin: 20px auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  .header {{ background: #1A5C2A; padding: 24px 28px; color: white; }}
  .header h1 {{ margin: 0; font-size: 20px; font-weight: 500; }}
  .header p {{ margin: 4px 0 0; opacity: 0.8; font-size: 13px; }}
  .content {{ padding: 24px 28px; }}
  .badge {{ display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 500; margin: 2px; }}
  .badge-vert {{ background: #D4EDDA; color: #1A5C2A; }}
  .badge-amber {{ background: #FEF3C7; color: #854F0B; }}
  .badge-rouge {{ background: #FDE8E8; color: #9B1C1C; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 13px; }}
  th {{ background: #1A5C2A; color: white; padding: 8px 10px; text-align: left; font-weight: 500; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #f0f0f0; }}
  tr:hover td {{ background: #f9f9f9; }}
  .score-fort {{ color: #1A5C2A; font-weight: 500; }}
  .score-mod {{ color: #854F0B; font-weight: 500; }}
  .footer {{ background: #f9f9f9; padding: 16px 28px; font-size: 11px; color: #888; border-top: 1px solid #eee; }}
  h2 {{ font-size: 16px; font-weight: 500; color: #1A5C2A; margin: 20px 0 8px; }}
  .alert-box {{ padding: 12px 16px; border-radius: 8px; margin: 10px 0; font-size: 13px; }}
  .alert-pos {{ background: #D4EDDA; border-left: 4px solid #1A5C2A; }}
  .alert-neg {{ background: #FDE8E8; border-left: 4px solid #9B1C1C; }}
  .alert-info {{ background: #E6F1FB; border-left: 4px solid #185FA5; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📈 {title}</h1>
    <p>{week_label} · Analyse BRVM automatisée</p>
  </div>
  <div class="content">
    {content}
  </div>
  <div class="footer">
    ⚠️ Ce rapport est généré automatiquement à des fins d'information uniquement.
    Il ne constitue pas un conseil en investissement.
    Données BRVM © BRVM — Bourse Régionale des Valeurs Mobilières.
  </div>
</div>
</body>
</html>"""


def send_weekly_report(
    df_scores,
    pdf_path: str,
    market_summary: str,
    sentiment_results: dict,
    macro: dict,
    config: dict = None,
) -> bool:
    """Envoie le rapport hebdomadaire complet par email"""
    if config is None:
        config = load_email_config()

    if not config.get("alert_types", {}).get("rapport_hebdo", True):
        return False

    week_label = datetime.now().strftime("Semaine du %d %B %Y")
    top10 = df_scores.head(10)

    # Construire le tableau Top 10
    rows_html = ""
    for _, row in top10.iterrows():
        score = row.get("composite_adj", 0)
        cls = "score-fort" if score >= 55 else "score-mod"
        price = f"{row['price']:,.0f}" if row.get("price") else "N/D"
        div = f"{row['div_yield']:.1f}%" if row.get("div_yield") else "—"
        sentiment = row.get("sentiment_label", "Neutre")
        sent_cls = "badge-vert" if "positif" in sentiment.lower() else ("badge-rouge" if "négatif" in sentiment.lower() else "badge-amber")
        rows_html += f"""<tr>
          <td>#{int(row['rank'])}</td>
          <td><strong>{row['ticker']}</strong><br><small style="color:#888">{row['name'][:25]}</small></td>
          <td>{price} XOF</td>
          <td>{div}</td>
          <td class="{cls}">{score:.0f}/80</td>
          <td><span class="badge {sent_cls}">{sentiment}</span></td>
        </tr>"""

    # Résumé macro
    brvm_ci = macro.get("BRVM_COMPOSITE", "N/D")
    fcfa_usd = macro.get("FCFA_per_USD", "N/D")
    n_strong = len(df_scores[df_scores["composite_adj"] >= 55])
    n_pos_sentiment = len([v for v in sentiment_results.values() if v.get("sentiment_score", 0) > 0])

    content = f"""
    <h2>Résumé de marché</h2>
    <div class="alert-box alert-info">{market_summary}</div>

    <table>
      <tr>
        <th>Indicateur</th><th>Valeur</th>
        <th>Indicateur</th><th>Valeur</th>
      </tr>
      <tr>
        <td>BRVM Composite</td><td><strong>{brvm_ci}</strong></td>
        <td>FCFA/USD</td><td><strong>{fcfa_usd}</strong></td>
      </tr>
      <tr>
        <td>Actions score Fort</td><td><strong class="score-fort">{n_strong}</strong></td>
        <td>Sentiment positif</td><td><strong class="score-fort">{n_pos_sentiment}</strong></td>
      </tr>
    </table>

    <h2>🏆 Top 10 — Classement de la semaine</h2>
    <table>
      <tr><th>#</th><th>Action</th><th>Cours</th><th>Div.</th><th>Score/80</th><th>Sentiment</th></tr>
      {rows_html}
    </table>

    <p style="font-size:12px;color:#888;margin-top:16px;">
      📎 Le rapport PDF complet est joint à cet email.
    </p>
    """

    html = email_html_template("Rapport Hebdomadaire BRVM", content, week_label)
    subject = f"📊 BRVM Hebdo — {week_label}"

    return send_email(config, subject, html, attachments=[pdf_path])


def send_dividend_alert(ticker: str, name: str, dividend: float, yield_pct: float, ex_date: str, config: dict = None) -> bool:
    """Alerte quand un dividende est confirmé"""
    if config is None:
        config = load_email_config()
    if not config.get("alert_types", {}).get("dividende_confirme", True):
        return False

    # Vérifier si cette alerte a déjà été envoyée
    alerts_log = load_alerts_log()
    alert_key = f"div_{ticker}_{dividend}_{datetime.now().strftime('%Y-%m')}"
    if alert_key in [a.get("key") for a in alerts_log]:
        logger.info(f"Alerte dividende {ticker} déjà envoyée")
        return False

    week_label = datetime.now().strftime("Semaine du %d %B %Y")
    content = f"""
    <div class="alert-box alert-pos">
      <strong>🎉 Dividende confirmé : {ticker}</strong><br>
      {name} vient d'annoncer le paiement d'un dividende.
    </div>
    <table>
      <tr><th>Détail</th><th>Valeur</th></tr>
      <tr><td>Ticker</td><td><strong>{ticker}</strong></td></tr>
      <tr><td>Société</td><td>{name}</td></tr>
      <tr><td>Dividende net/action</td><td><strong>{dividend:,.0f} XOF</strong></td></tr>
      <tr><td>Rendement</td><td><strong class="score-fort">{yield_pct:.1f}%</strong></td></tr>
      <tr><td>Date de détachement</td><td>{ex_date or "Non communiquée"}</td></tr>
    </table>
    <p style="font-size:12px;color:#555;">
      Pour recevoir ce dividende, tu dois détenir l'action avant la date de détachement.
    </p>
    """

    html = email_html_template(f"💰 Dividende — {ticker}", content, week_label)
    sent = send_email(config, f"💰 Dividende {ticker} confirmé : {dividend:,.0f} XOF ({yield_pct:.1f}%)", html)

    if sent:
        alerts_log.append({"key": alert_key, "date": datetime.now().isoformat(), "type": "dividende"})
        save_alerts_log(alerts_log)

    return sent


def send_score_alert(ticker: str, name: str, score: float, prev_score: float, config: dict = None) -> bool:
    """Alerte quand le score d'une action change significativement"""
    if config is None:
        config = load_email_config()
    if not config.get("alert_types", {}).get("score_franchissement", True):
        return False

    threshold = config.get("thresholds", {}).get("score_hausse", 5)
    change = score - prev_score
    if abs(change) < threshold:
        return False

    week_label = datetime.now().strftime("Semaine du %d %B %Y")
    is_up = change > 0
    direction = "hausse" if is_up else "baisse"
    icon = "📈" if is_up else "📉"
    alert_cls = "alert-pos" if is_up else "alert-neg"

    content = f"""
    <div class="alert-box {alert_cls}">
      <strong>{icon} Variation significative du score : {ticker}</strong><br>
      Le score composite de {name} a changé de {change:+.1f} points cette semaine.
    </div>
    <table>
      <tr><th>Métrique</th><th>Avant</th><th>Maintenant</th><th>Variation</th></tr>
      <tr>
        <td>Score composite</td>
        <td>{prev_score:.0f}/80</td>
        <td><strong>{score:.0f}/80</strong></td>
        <td class="{'score-fort' if is_up else 'score-mod'}">{change:+.1f}</td>
      </tr>
    </table>
    """

    html = email_html_template(f"{icon} Alerte score {ticker}", content, week_label)
    return send_email(config, f"{icon} {ticker} — Score {direction} de {change:+.1f} pts ({score:.0f}/80)", html)


def send_news_alert(ticker: str, name: str, news_title: str, sentiment: str, config: dict = None) -> bool:
    """Alerte pour une news importante (résultats, fusion, etc.)"""
    if config is None:
        config = load_email_config()
    if not config.get("alert_types", {}).get("resultats_importants", True):
        return False

    week_label = datetime.now().strftime("Semaine du %d %B %Y")
    content = f"""
    <div class="alert-box alert-info">
      <strong>📰 Actualité importante : {ticker}</strong>
    </div>
    <table>
      <tr><th>Champ</th><th>Info</th></tr>
      <tr><td>Action</td><td><strong>{ticker}</strong> — {name}</td></tr>
      <tr><td>Actualité</td><td>{news_title}</td></tr>
      <tr><td>Sentiment IA</td><td>{sentiment}</td></tr>
    </table>
    """

    html = email_html_template(f"📰 Actualité {ticker}", content, week_label)
    return send_email(config, f"📰 {ticker} — Actualité importante", html)


def process_all_alerts(
    df_scores,
    pdf_path: str,
    market_summary: str,
    sentiment_results: dict,
    confirmed_dividends: dict,
    macro: dict,
    prev_scores: dict = None,
) -> int:
    """Lance toutes les alertes nécessaires. Retourne le nombre d'alertes envoyées."""
    config = load_email_config()
    if not config.get("enabled"):
        logger.info("Alertes email désactivées (enabled=false dans config_email.json)")
        return 0

    sent_count = 0

    # 1. Rapport hebdomadaire
    logger.info("Envoi rapport hebdomadaire...")
    if send_weekly_report(df_scores, pdf_path, market_summary, sentiment_results, macro, config):
        sent_count += 1

    # 2. Alertes dividendes confirmés
    alerts_log = load_alerts_log()
    for ticker, div_data in confirmed_dividends.items():
        alert_key = f"div_{ticker}_{div_data['dividend']}_{datetime.now().strftime('%Y-%m')}"
        if alert_key not in [a.get("key") for a in alerts_log]:
            row = df_scores[df_scores["ticker"] == ticker]
            name = row["name"].values[0] if len(row) > 0 else ticker
            if send_dividend_alert(
                ticker, name,
                div_data["dividend"],
                div_data.get("yield_pct") or 0,
                div_data.get("ex_date", ""),
                config
            ):
                sent_count += 1

    # 3. Alertes variations de score
    if prev_scores:
        for _, row in df_scores.iterrows():
            ticker = row["ticker"]
            current_score = row.get("composite_adj", 0)
            prev_score = prev_scores.get(ticker, current_score)
            if send_score_alert(ticker, row["name"], current_score, prev_score, config):
                sent_count += 1

    # 4. Alertes news importantes avec sentiment très positif/négatif
    threshold_sentiment = config.get("thresholds", {}).get("sentiment_alerte", 3)
    for ticker, sr in sentiment_results.items():
        score = abs(sr.get("sentiment_score", 0))
        if score >= threshold_sentiment:
            row = df_scores[df_scores["ticker"] == ticker]
            if len(row) > 0:
                send_news_alert(
                    ticker,
                    row["name"].values[0],
                    sr.get("resume", ""),
                    sr.get("sentiment_label", ""),
                    config
                )
                sent_count += 1

    logger.info(f"Total alertes envoyées: {sent_count}")
    return sent_count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    save_default_config()
    print("=== ALERTER BRVM ===")
    print(f"Fichier de config: {CONFIG_FILE}")
    cfg = load_email_config()
    if not cfg.get("enabled"):
        print("\n⚠ Les alertes sont désactivées.")
        print("Pour les activer:")
        print(f"  1. Ouvre {CONFIG_FILE}")
        print("  2. Remplis sender_email et sender_password (mot de passe d'application Gmail)")
        print("  3. Mets enabled: true")
        print("\n📧 Pour créer un mot de passe d'application Gmail:")
        print("  myaccount.google.com → Sécurité → Mots de passe des applications")
