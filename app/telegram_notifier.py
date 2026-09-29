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


# Convention forex pour l'or : 1 pip = 0.10 $ de cours (seul actif tradé, Spot Gold $1).
PIP_SIZE     = 0.10
PIP_REMINDER = f"ℹ️ 1 pip = {PIP_SIZE:.2f} $ de cours · valeur = lot × {PIP_SIZE:.2f} $ par pip"


def _points(entry: float, level: float, direction: str) -> float:
    """Écart en points (1 point = 1 unité de cours), signé du point de vue du trade."""
    return (level - entry) if direction == "BUY" else (entry - level)


def _pips(pts: float) -> float:
    return pts / PIP_SIZE


def _fmt_points(pts: float, qty: Optional[float] = None, point_value: float = 1.0) -> str:
    """'+109.8 pips' ou '+109.8 pips · +115.29 $' si la taille est connue."""
    text = f"{_pips(pts):+.1f} pips"
    if qty:
        text += f" · {pts * qty * point_value:+.2f} $"
    return text


def _format_open_position(idx: int, pos: dict, cache_entry: Optional[dict]) -> str:
    """
    Formate une position ouverte avec numéro, SL/TP et barre de progression.

    Args:
        idx:         Numéro d'affichage (1, 2, 3…), remplacé par le numéro de trade s'il existe
        pos:         Dict retourné par get_open_positions() —
                     clés : epic, direction, entry_price, current_price, size, unrealized_pl
        cache_entry: Dict depuis _signal_cache — clés : sl, tp, direction, qty, trade_no
                     None si la position a été ouverte avant la mise à jour du bot.
    """
    direction = "🚀 LONG" if pos["direction"] == "BUY" else "🔻 SHORT"
    entry     = pos.get("entry_price", 0.0)
    current   = pos.get("current_price", 0.0)
    qty       = pos.get("size") or (cache_entry or {}).get("qty")
    pts       = _points(entry, current, pos["direction"])
    # IG ne renvoie pas de P&L latent dans /positions : on le recalcule (1 $/point/contrat).
    pnl       = pos["unrealized_pl"] if "unrealized_pl" in pos else pts * (qty or 0.0)
    pnl_str   = f"{'+'if pnl > 0 else ''}{pnl:.2f} $"
    tier      = cache_entry.get("tier") if cache_entry else None
    tier_str  = f" (Position {tier}/3)" if tier and tier > 1 else ""
    number    = (cache_entry or {}).get("trade_no") or idx
    name      = (cache_entry or {}).get("asset_name") or pos["epic"]

    lines = [
        f"<b>#{number} {direction} {name}{tier_str}</b>",
        f"   Entrée  : {entry:.2f} → Actuel : {current:.2f}",
        f"   P&amp;L  : {pnl_str} ({_fmt_points(pts)})",
    ]
    if qty:
        lines.append(f"   Lot     : {qty:g}  ({qty * PIP_SIZE:.2f} $ par pip)")

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

    def __init__(self, token: str, chat_id: str, thread_id: Optional[int] = None):
        self._token     = token
        self._chat_id   = chat_id
        self._thread_id = thread_id
        self._enabled   = bool(token and chat_id)
        self._client    = httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        await self._client.aclose()

    # ── Envoi ─────────────────────────────────────────────────────

    async def _send(self, text: str) -> None:
        if not self._enabled:
            logger.debug("Telegram désactivé (token/chat_id manquants)")
            return
        url = TELEGRAM_API.format(token=self._token)
        payload = {
            "chat_id":    self._chat_id,
            "text":       text,
            "parse_mode": "HTML",
        }
        if self._thread_id:
            payload["message_thread_id"] = self._thread_id
        try:
            await self._client.post(url, json=payload)
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
            resp = await self._client.get(url, params={"offset": -1, "timeout": 0})
            updates = resp.json().get("result", [])
            if updates:
                offset = updates[-1]["update_id"] + 1
                logger.info("Telegram : %d message(s) ignoré(s) au démarrage (offset=%d)",
                            len(updates), offset)
        except Exception as e:
            logger.warning("Telegram drain startup failed: %s", e)

        poll_client = httpx.AsyncClient(timeout=40.0)
        while True:
            try:
                resp = await poll_client.get(url, params={
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
                msg       = update.get("message", {})
                text      = msg.get("text", "")
                chat_id   = str(msg.get("chat", {}).get("id", ""))
                thread_id = msg.get("message_thread_id")

                # Sécurité : n'accepter que les messages du chat configuré
                if chat_id != self._chat_id:
                    continue
                if not text.startswith("/"):
                    continue

                parts   = text.split()
                command = parts[0].lower().split("@")[0]   # gère /cmd@botname
                args    = parts[1:]

                # Si un topic dédié est configuré, ignorer les commandes tapées
                # ailleurs dans le groupe (ex: éviter que Raspi_algo02 réponde à
                # une commande tapée dans le topic La Verticale).
                if self._thread_id and thread_id and thread_id != self._thread_id:
                    continue

                logger.info("Commande Telegram reçue : %s %s", command, args)
                try:
                    await callback(command, args)
                except Exception as e:
                    logger.warning("Erreur handler commande %s : %s", command, e)

    # ── Notifications sortantes ───────────────────────────────────

    async def send_test_message(self) -> None:
        await self._send("✅ ZorionBot connecté et opérationnel.")

    async def send_startup(self, demo: bool, assets: list) -> None:
        from datetime import datetime, timezone
        mode       = "DEMO 🧪" if demo else "LIVE ⚠️"
        assets_str = ", ".join(assets) if assets else "aucun actif configuré"
        now_str    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        await self._send(
            f"🤖 <b>ZorionBot démarré</b>\n"
            f"📅 {now_str}\n"
            f"Mode   : {mode}\n"
            f"Actifs : {assets_str}"
        )

    async def send_signal(
        self, signal: dict, demo: bool, trade_no: Optional[int] = None,
        point_value: float = 1.0,
    ) -> None:
        direction = "🚀 LONG" if signal["direction"] == "BUY" else "🔻 SHORT"
        mode_tag  = "[DEMO] " if demo else ""
        tier      = signal.get("tier")
        tier_str  = f" — Position {tier}/3" if tier and tier > 1 else ""
        no_str    = f"Trade #{trade_no} · " if trade_no else ""
        entry     = signal["entry_price"]
        qty       = signal["qty"]
        sl_pts    = _points(entry, signal["sl_price"], signal["direction"])
        tp_pts    = _points(entry, signal["tp_price"], signal["direction"])
        await self._send(
            f"{direction} {mode_tag}<b>{no_str}{signal['asset_name']}</b>{tier_str}\n"
            f"Entrée : {entry:.2f}\n"
            f"SL     : {signal['sl_price']:.2f}  ({_fmt_points(sl_pts, qty, point_value)})\n"
            f"TP     : {signal['tp_price']:.2f}  ({_fmt_points(tp_pts, qty, point_value)})\n"
            f"Lot    : {qty:g}  ({qty * point_value * PIP_SIZE:.2f} $ par pip)\n"
            f"{PIP_REMINDER}"
        )

    async def send_trade_closed(
        self, symbol: str, direction: str, pnl: float, demo: bool, tier: int = 0,
        trade_no: Optional[int] = None, entry: Optional[float] = None,
        exit_price: Optional[float] = None, sl: Optional[float] = None,
        tp: Optional[float] = None, qty: Optional[float] = None,
    ) -> None:
        emoji         = "💰" if pnl >= 0 else "💸"
        result        = "WIN ✅" if pnl >= 0 else "LOSS ❌"
        direction_str = "LONG" if direction == "BUY" else "SHORT"
        mode_tag      = "[DEMO] " if demo else ""
        pnl_str       = f"{'+'if pnl >= 0 else ''}{pnl:.2f} $"
        tier_str      = f" — Position {tier}/3" if tier and tier > 1 else ""
        no_str        = f"#{trade_no} " if trade_no else ""
        lines = [
            f"{emoji} <b>Trade {no_str}fermé {mode_tag}{symbol}</b>{tier_str}",
            f"Direction : {direction_str}",
        ]
        if entry and exit_price:
            pts = _points(entry, exit_price, direction)
            lines.append(f"Entrée    : {entry:.2f} → Sortie : {exit_price:.2f}  ({_fmt_points(pts)})")
        if sl and tp:
            lines.append(f"SL / TP   : {sl:.2f} / {tp:.2f}")
        if qty:
            lines.append(f"Lot       : {qty:g}  ({qty * PIP_SIZE:.2f} $ par pip)")
        lines += [
            f"P&amp;L    : {pnl_str}",
            f"Résultat  : <b>{result}</b>",
        ]
        if entry and exit_price:
            lines.append(PIP_REMINDER)
        await self._send("\n".join(lines))

    async def send_error(self, context: str, message: str) -> None:
        await self._send(f"❌ <b>Erreur — {context}</b>\n{message}")

    async def send_daily_summary(
        self,
        trades_today:   int,
        open_positions: list,
        closed_today:   list,
        signal_cache:   dict,
    ) -> None:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%d/%m/%Y")

        lines = [
            f"📊 <b>ZorionBot — Résumé du {today}</b>",
            f"Trades du jour : {trades_today}",
        ]

        if open_positions:
            lines.append(f"\n<b>Positions ouvertes ({len(open_positions)}) :</b>")
            for idx, pos in enumerate(open_positions, 1):
                # deal_id-keyed sur IG, epic-keyé sur Alpaca (legacy) — au plus
                # un des deux .get() trouvera quelque chose. Pas de BROKER visible
                # ici (pas d'import config), donc ce fallback marche pour les deux.
                cache_entry = signal_cache.get(pos["deal_id"]) or signal_cache.get(pos["epic"])
                lines.append(_format_open_position(idx, pos, cache_entry))
            lines.append(PIP_REMINDER)
        else:
            lines.append("Aucune position ouverte")

        if closed_today:
            lines.append(f"\n<b>Trades clôturés aujourd'hui ({len(closed_today)}) :</b>")
            for t in closed_today:
                emoji  = "✅" if t["pnl"] >= 0 else "❌"
                d_str  = "LONG" if t["direction"] == "BUY" else "SHORT"
                pnl_s  = f"{'+'if t['pnl'] > 0 else ''}{t['pnl']:.2f} $"
                time_s = t["closed_at"][11:16]
                number = t.get("trade_no") or t["id"]
                lines.append(f"#{number} {emoji} {d_str} {t['symbol']} | {pnl_s} | {time_s}")

        await self._send("\n".join(lines))
