"""Telegram bot (python-telegram-bot, async). Not aiogram.

Flow: link -> create job -> analyze -> card with quality buttons -> download -> deliver.
Progress is streamed from Redis and rendered into an editable message.
"""
from __future__ import annotations

import asyncio
import contextlib
import json

import redis.asyncio as aioredis
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import settings
from .db import SessionLocal
from .deps import _get_or_create_user_by_telegram
from .logging_config import get_logger
from .models import DownloadJob, JobStatus, SelectedFormat
from .queue import enqueue_analyze, enqueue_download, publish_progress, request_cancel
from .services import jobs as jobs_svc
from .services.serialize import load_job

log = get_logger("bot")

STAGE_TEXT = {
    "analysis": "🔍 Анализ", "analyzed": "✅ Проанализировано", "waiting": "⏳ Ожидание в очереди",
    "downloading": "📥 Скачивание", "merging": "🔗 Объединение", "converting": "🎞 Конвертация",
    "uploading": "📤 Загрузка в Telegram", "done": "✅ Готово", "cancelled": "🚫 Отменено",
}


def _fmt_size(n: int | None) -> str:
    if not n:
        return "?"
    x = float(n)
    for u in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if x < 1024 or u == "ТБ":
            return f"{x:.1f} {u}"
        x /= 1024
    return f"{x:.1f} ТБ"


async def _resolve_user(update: Update):
    tg = update.effective_user
    async with SessionLocal() as session:
        user = await _get_or_create_user_by_telegram(session, {
            "id": tg.id, "username": tg.username, "first_name": tg.first_name,
            "language_code": tg.language_code,
        })
        await session.commit()
        return user.id, user.is_blocked


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я ShareTube.\n\n"
        "Пришли ссылку на видео, аудио или фото — с YouTube, VK, TikTok, Instagram, "
        "Vimeo, Twitch, X и других источников.\n\n"
        "Я покажу карточку, дам выбрать качество и пришлю результат сюда либо ссылкой, "
        "если файл большой.\n\n"
        "Команды: /history — последние загрузки."
    )


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, blocked = await _resolve_user(update)
    if blocked:
        await update.message.reply_text("⛔ Доступ ограничен.")
        return
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(DownloadJob).where(DownloadJob.user_id == user_id)
            .order_by(DownloadJob.created_at.desc()).limit(10)
        )).scalars().all()
    if not rows:
        await update.message.reply_text("История пуста.")
        return
    lines = ["🗂 Последние загрузки:\n"]
    kb = []
    for r in rows:
        icon = {"done": "✅", "failed": "❌", "cancelled": "🚫"}.get(r.status, "⏳")
        title = (r.normalized_url or "")[:48]
        lines.append(f"{icon} {title}")
        if r.status == "done" and r.telegram_file_id:
            kb.append([InlineKeyboardButton(f"↻ Отправить снова: {title[:24]}",
                                            callback_data=f"resend:{r.id}")])
    await update.message.reply_text("\n".join(lines),
                                    reply_markup=InlineKeyboardMarkup(kb) if kb else None)


async def on_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text.lower().startswith(("http://", "https://")) and "." not in text:
        return
    user_id, blocked = await _resolve_user(update)
    if blocked:
        await update.message.reply_text("⛔ Доступ ограничен.")
        return

    chat_id = update.effective_chat.id
    # Auto flow: user sends a link and just gets the ready video back.
    async with SessionLocal() as session:
        try:
            job = await jobs_svc.create_job(session, user_id=user_id, raw_url=text, origin="bot")
        except jobs_svc.JobError as exc:
            if exc.code == "duplicate":
                # a previous (possibly stuck) job for this link is still active —
                # cancel it and start fresh instead of blocking the user.
                await _cancel_active_for_url(session, user_id, text)
                await session.commit()
                try:
                    job = await jobs_svc.create_job(session, user_id=user_id, raw_url=text, origin="bot")
                except jobs_svc.JobError as exc2:
                    await update.message.reply_text(f"❌ {exc2.message}")
                    return
            else:
                await update.message.reply_text(f"❌ {exc.message}")
                return
        job.deliver_to_telegram = True
        job.tg_chat_id = chat_id
        await session.commit()
        job_id = job.id

    # delete the user's link message (best-effort; ignored if not permitted)
    with contextlib.suppress(Exception):
        await context.bot.delete_message(chat_id, update.message.message_id)

    status = await context.bot.send_message(chat_id, "🔍 Обрабатываю ссылку…")
    async with SessionLocal() as session:
        job = await session.get(DownloadJob, job_id)
        job.tg_progress_message_id = status.message_id
        await session.commit()

    await enqueue_analyze(job_id)
    # one status message tracks the whole job (analysis -> download -> delivery)
    asyncio.create_task(_track_progress(context, chat_id, status.message_id, job_id))


async def _cancel_active_for_url(session, user_id: int, raw_url: str) -> None:
    from .security.ssrf import UrlValidationError, validate_url
    try:
        norm = validate_url(raw_url).normalized
    except UrlValidationError:
        return
    rows = (await session.execute(
        select(DownloadJob).where(
            DownloadJob.user_id == user_id,
            DownloadJob.normalized_url == norm,
            DownloadJob.status.in_(jobs_svc.ACTIVE_STATUSES),
        )
    )).scalars().all()
    for j in rows:
        await request_cancel(j.id)
        j.error_code = "cancelled"
        await jobs_svc.transition(session, j, JobStatus.CANCELLED, stage="cancelled")


async def _show_card(context, job, chat_id, message_id):
    async with SessionLocal() as session:
        j = await load_job(session, job.id)
        src = j.media_sources[0] if j.media_sources else None
        formats = sorted(src.formats, key=lambda f: (f.height or 0), reverse=True) if src else []

    title = (src.title if src else None) or "Без названия"
    author = (src.author if src else None) or "—"
    dur = src.duration_sec if src else None
    dur_s = f"{dur // 60}:{dur % 60:02d}" if dur else "—"
    ctype = j.content_type

    caption = (f"🎬 <b>{title[:200]}</b>\n"
               f"👤 {author}\n"
               f"⏱ {dur_s}   •   📦 {ctype}   •   🌐 {j.source}\n")
    if src and src.item_count > 1:
        caption += f"🖼 Элементов: {src.item_count}\n"

    # build quality buttons only for really available formats
    buttons = []
    row = []
    label_map = {"auto": "Авто", "1080p": "1080p", "720p": "720p", "480p": "480p",
                 "min": "Мин. размер", "original": "Оригинал", "audio": "🎵 Только аудио"}
    for f in formats:
        lbl = label_map.get(f.label, f.label)
        size = f" (~{_fmt_size(f.approx_size_bytes)})" if f.approx_size_bytes else ""
        row.append(InlineKeyboardButton(f"{lbl}{size}", callback_data=f"dl:{j.id}:{f.id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data=f"cancel:{j.id}")])

    kb = InlineKeyboardMarkup(buttons)
    try:
        if src and src.thumbnail_url:
            await context.bot.delete_message(chat_id, message_id)
            await context.bot.send_photo(chat_id, src.thumbnail_url, caption=caption,
                                         parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await context.bot.edit_message_text(caption, chat_id, message_id,
                                                parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        await context.bot.send_message(chat_id, caption, parse_mode=ParseMode.HTML, reply_markup=kb)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if data.startswith("dl:"):
        _, job_id, fmt_id = data.split(":")
        await _start_download(context, query, job_id, int(fmt_id))
    elif data.startswith("cancel:"):
        job_id = data.split(":", 1)[1]
        await request_cancel(job_id)  # worker checks this flag mid-download
        async with SessionLocal() as session:
            job = await session.get(DownloadJob, job_id)
            # cancel pre-download states immediately; active downloads stop on the flag
            if job and job.status in (JobStatus.ANALYZED.value, JobStatus.QUEUED.value,
                                      JobStatus.PENDING.value, JobStatus.ANALYZING.value):
                job.error_code = "cancelled"
                await jobs_svc.transition(session, job, JobStatus.CANCELLED, stage="cancelled")
                await session.commit()
                await publish_progress(job_id, {"job_id": job_id, "status": "cancelled"})
        with contextlib.suppress(Exception):
            await query.edit_message_reply_markup(None)
    elif data.startswith("resend:"):
        job_id = data.split(":", 1)[1]
        await _resend(context, query, job_id)


async def _start_download(context, query, job_id, fmt_id):
    chat_id = query.message.chat_id
    async with SessionLocal() as session:
        job = await session.get(DownloadJob, job_id)
        if not job or job.status not in (JobStatus.ANALYZED.value, JobStatus.FAILED.value):
            with contextlib.suppress(Exception):
                await query.edit_message_reply_markup(None)
            return
        fmt = await session.get(SelectedFormat, fmt_id)
        job.selected_format_id = fmt_id
        job.approx_size_bytes = fmt.approx_size_bytes if fmt else None
        await jobs_svc.transition(session, job, JobStatus.QUEUED, stage="waiting", progress=0.0)
        await session.commit()

    prog = await context.bot.send_message(chat_id, "⏳ Задание поставлено в очередь…")
    async with SessionLocal() as session:
        job = await session.get(DownloadJob, job_id)
        job.tg_progress_message_id = prog.message_id
        await session.commit()
    with contextlib.suppress(Exception):
        await query.edit_message_reply_markup(None)

    await enqueue_download(job_id)
    asyncio.create_task(_track_progress(context, chat_id, prog.message_id, job_id))


async def _track_progress(context, chat_id, message_id, job_id):
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(f"progress:{job_id}")
    last_text = ""
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data=f"cancel:{job_id}")]])
    try:
        deadline = settings.JOB_TIMEOUT_MINUTES * 60
        waited = 0
        while waited < deadline:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
            if not msg:
                waited += 15
                continue
            data = json.loads(msg["data"])
            status = data.get("status")
            stage = STAGE_TEXT.get(data.get("stage") or status, status)
            terminal = status in ("done", "failed", "cancelled")
            if status == "downloading":
                pct = data.get("progress") or 0.0
                bar_len = 12
                filled = int(pct / 100 * bar_len)
                bar = "█" * filled + "░" * (bar_len - filled)
                speed = data.get("speed")
                text = (f"{stage}\n{bar} {pct:.1f}%\n"
                        f"⬇️ {_fmt_size(data.get('downloaded_bytes'))} / "
                        f"{_fmt_size(data.get('total_bytes'))}"
                        + (f"\n🚀 {_fmt_size(speed)}/с" if speed else ""))
            elif status == "done":
                text = "✅ Готово! Файл отправлен."
                if data.get("download_url"):
                    text += f"\n🔗 Ссылка: {data['download_url']}"
            elif status == "failed":
                text = f"❌ {data.get('error', 'Ошибка загрузки.')}"
            elif status == "cancelled":
                text = "🚫 Отменено."
            else:
                text = stage or "…"
            if text != last_text:
                with contextlib.suppress(Exception):
                    await context.bot.edit_message_text(
                        text, chat_id, message_id,
                        reply_markup=None if terminal else cancel_kb)
                last_text = text
            if terminal:
                break
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(f"progress:{job_id}")
            await r.aclose()


async def _resend(context, query, job_id):
    async with SessionLocal() as session:
        job = await session.get(DownloadJob, job_id)
    if not job or not job.telegram_file_id:
        await query.answer("Файл больше недоступен.", show_alert=True)
        return
    from .services import telegram_delivery as tg
    kind = "audio" if job.content_type == "audio" else "video"
    with contextlib.suppress(Exception):
        if kind == "audio":
            await tg.send_audio(query.message.chat_id, "", cached_file_id=job.telegram_file_id)
        else:
            await tg.send_video(query.message.chat_id, "", cached_file_id=job.telegram_file_id)


def build_application() -> Application:
    base_url = f"{settings.LOCAL_BOT_API_BASE}/bot" if settings.LOCAL_BOT_API_ENABLED else None
    builder = Application.builder().token(settings.BOT_TOKEN)
    if base_url:
        builder = builder.base_url(base_url)
    proxy = settings.telegram_proxy
    if proxy:
        # cloud Bot API is unreachable on the host's direct route -> tunnel via proxy
        builder = builder.proxy(proxy).get_updates_proxy(proxy)
    app = builder.build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_link))
    return app


def main() -> None:
    from .logging_config import configure_logging
    configure_logging()
    if not settings.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN not configured")
    app = build_application()
    if settings.TELEGRAM_USE_WEBHOOK and settings.PUBLIC_BASE_URL.startswith("https"):
        path = f"/tg/webhook/{settings.TELEGRAM_WEBHOOK_SECRET or 'hook'}"
        log.info("bot_webhook", url=settings.PUBLIC_BASE_URL + path)
        app.run_webhook(listen="0.0.0.0", port=8080, url_path=path.lstrip("/"),
                        webhook_url=settings.PUBLIC_BASE_URL + path,
                        secret_token=settings.TELEGRAM_WEBHOOK_SECRET or None,
                        drop_pending_updates=True)
    else:
        log.info("bot_polling")
        app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
