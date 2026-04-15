"""
telegram_notifier.py — Notifications et écoute de commandes Telegram.
Si TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID est vide, tout est silencieusement désactivé.

Commandes supportées (depuis le chat configuré uniquement) :
  /help    — liste des commandes
  /status  — solde, positions, état du bot
  /logs    — dernières lignes de log
  /pause   — suspendre les nouveaux ordres
  /resume  — reprendre les signaux
"""
import asyncio
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API     = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_UPDATES = "https://api.telegram.org/bot{token}/getUpdates"


def _format_open_position(idx: int, pos: dict, cache_entry: Optional[dict]) -> str:
    """
    Formate une position ouverte avec numéro, SL/TP et barre de progression.

    Args:
        idx:         Numéro d'affichage (1, 2, 3…)
        pos:         Dict retourné par get_open_positions() —
                     clés : epic, direction, entry_price, current_price, unrealized_pl
        cache_entry: Dict depuis _signal_cache — clés : sl, tp, direction
                     None si la position a été ouverte avant la mise à jour du bot.
    """
    direction = "🚀 LONG" if pos["direction"] == "BUY" else "🔻 SHORT"
    pnl       = pos.get("unrealized_pl", 0.0)
    pnl_str   = f"{'+'if pnl > 0 else ''}{pnl:.2f} $"
    entry     = pos.get("entry_price", 0.0)
    current   = pos.get("current_price", 0.0)

    lines = [
        f"<b>#{idx} {direction} {pos['epic']}</b>",
        f"   Entrée  : {entry:.2f} → Actuel : {current:.2f}",
        f"   P&amp;L  : {pnl_str}",
    ]

    if cache_entry:
        sl = cache_entry.get("sl", 0.0)
        tp = cache_entry.get("tp", 0.0)
        lines.append(f"   SL      : {sl:.2f}  |  TP : {tp:.2f}")
        if tp != entry:
            if pos["direction"] == "BUY":
                prog = (current - entry) / (tp - entry) * 100.0
            else:
                prog = (entry - current) / (entry - tp) * 100.0
            prog    = max(0.0, min(100.0, prog))
            filled  = int(prog / 10)
            bar     = "▓" * filled + "░" * (10 - filled)
            lines.append(f"   Prog.   : {bar} {prog:.0f}% vers TP")
    else:
        lines.append("   SL/TP  : N/A")

    return "\n".join(lines)


class TelegramNotifier:

    def __init__(self, token: str, chat_id: str):
        self._token   = token
        self._chat_id = chat_id
        self._enabled = bool(token and chat_id)

    # ── Envoi ─────────────────────────────────────────────────────

    async def _send(self, text: str) -> None:
        if not self._enabled:
            logger.debug("Telegram désactivé (token/chat_id manquants)")
            return
        url = TELEGRAM_API.format(token=self._token)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json={
                    "chat_id":    self._chat_id,
                    "text":       text,
                    "parse_mode": "HTML",
                })
        except Exception as e:
            logger.warning("Telegram send failed: %s", e)

    # ── Écoute des commandes (long-polling) ───────────────────────

    async def poll_commands(self, callback) -> None:
        """
        Écoute en continu les messages entrants via long-polling.
        Appelle await callback(command, args) pour chaque commande reçue
        depuis le chat_id configuré.
        Tourne indéfiniment — annuler la tâche pour arrêter.
        """
        if not self._enabled:
            logger.info("Telegram désactivé — écoute des commandes inactive")
            return

        url    = TELEGRAM_UPDATES.format(token=self._token)
        offset = 0

        # Drain les messages en attente au démarrage (évite de re-traiter d'anciens messages)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params={"offset": -1, "timeout": 0})
                updates = resp.json().get("result", [])
                if updates:
                    offset = updates[-1]["update_id"] + 1
                    logger.info("Telegram : %d message(s) ignoré(s) au démarrage (offset=%d)",
                                len(updates), offset)
        except Exception as e:
            logger.warning("Telegram drain startup failed: %s", e)

        while True:
            try:
                async with httpx.AsyncClient(timeout=40.0) as client:
                    resp = await client.get(url, params={
                        "offset":          offset,
                        "timeout":         30,
                        "allowed_updates": ["message"],
                    })
                    data = resp.json()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Telegram getUpdates failed: %s", e)
                await asyncio.sleep(5)
                continue

            for update in data.get("result", []):
                offset  = update["update_id"] + 1
                msg     = update.get("message", {})
                text    = msg.get("text", "")
                chat_id = str(msg.get("chat", {}).get("id", ""))

                # Sécurité : n'accepter que les messages du chat configuré
                if chat_id != self._chat_id:
                    continue
                if not text.startswith("/"):
                    continue

                parts   = text.split()
                command = parts[0].lower().split("@")[0]   # gère /cmd@botname
                args    = parts[1:]

                logger.info("Commande Telegram reçue : %s %s", command, args)
                try:
                    await callback(command, args)
                except Exception as e:
                    logger.warning("Erreur handler commande %s : %s", command, e)

    # ── Notifications sortantes ───────────────────────────────────

    async def send_test_message(self) -> None:
        await self._send("✅ DonchianBot connecté et opérationnel.")

    async def send_startup(self, demo: bool, assets: list) -> None:
        from datetime import datetime, timezone
        mode       = "DEMO 🧪" if demo else "LIVE ⚠️"
        assets_str = ", ".join(assets) if assets else "aucun actif configuré"
        now_str    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        await self._send(
            f"🤖 <b>DonchianBot démarré</b>\n"
            f"📅 {now_str}\n"
            f"Mode   : {mode}\n"
            f"Actifs : {assets_str}"
        )

    async def send_signal(self, signal: dict, demo: bool) -> None:
        direction = "🚀 LONG" if signal["direction"] == "BUY" else "🔻 SHORT"
        mode_tag  = "[DEMO] " if demo else ""
        await self._send(
            f"{direction} {mode_tag}<b>{signal['asset_name']}</b>\n"
            f"Entry : {signal['entry_price']:.2f}\n"
            f"SL    : {signal['sl_price']:.2f}\n"
            f"TP    : {signal['tp_price']:.2f}\n"
            f"Qté   : {signal['qty']:.4f}"
        )

    async def send_trade_closed(
        self, symbol: str, direction: str, pnl: float, demo: bool
    ) -> None:
        emoji         = "💰" if pnl >= 0 else "💸"
        result        = "WIN ✅" if pnl >= 0 else "LOSS ❌"
        direction_str = "LONG" if direction == "BUY" else "SHORT"
        mode_tag      = "[DEMO] " if demo else ""
        pnl_str       = f"{'+'if pnl >= 0 else ''}{pnl:.2f} $"
        await self._send(
            f"{emoji} <b>Trade fermé {mode_tag}{symbol}</b>\n"
            f"Direction : {direction_str}\n"
            f"P&amp;L    : {pnl_str}\n"
            f"Résultat  : <b>{result}</b>"
        )

    async def send_error(self, context: str, message: str) -> None:
        await self._send(f"❌ <b>Erreur — {context}</b>\n{message}")

    async def send_daily_summary(self, trades_today: int, open_positions: list) -> None:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%d/%m/%Y")

        lines = [
            f"📊 <b>DonchianBot — Résumé du {today}</b>",
            f"Trades du jour : {trades_today}",
        ]

        if open_positions:
            lines.append(f"\n<b>Positions ouvertes ({len(open_positions)}) :</b>")
            for pos in open_positions:
                direction = "🚀 LONG" if pos["direction"] == "BUY" else "🔻 SHORT"
                pnl       = pos.get("unrealized_pl", 0)
                pnl_str   = f"{'+'if pnl >= 0 else ''}{pnl:.2f} $"
                entry     = pos.get("entry_price", 0)
                current   = pos.get("current_price", 0)
                lines.append(
                    f"• {direction} {pos['epic']}\n"
                    f"  Entrée : {entry:.2f} → Actuel : {current:.2f}\n"
                    f"  P&amp;L flottant : {pnl_str}"
                )
        else:
            lines.append("Aucune position ouverte")

        await self._send("\n".join(lines))
