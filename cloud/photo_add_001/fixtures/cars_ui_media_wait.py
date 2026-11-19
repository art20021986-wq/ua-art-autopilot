# Excerpt of the live cars_ui.py catch_message (sha256 c927ff01, PHOTO-ADD-PROBE-20261119): media sent to an open
# card section. Wrapped in a function for the tests; the body lines are verbatim.


async def media_wait(update, context, msg, user_id):
    wait = context.user_data.get("car_media_wait")
    if wait:
        target = wait["target"]
        tag = ""
        file_id = None
        if msg.photo:
            file_id = msg.photo[-1].file_id
            if target in ("photos", "condition_photos"):
                unique_id = getattr(msg.photo[-1], "file_unique_id", None) or file_id
                _v166_result = _v165_spool_enqueue(
                    wait["card_id"], target, file_id, user_id, tag,
                    unique_id=unique_id, message_id=msg.message_id)
                _v166_session_ids = wait.setdefault("_fast_session_ids", [])
                state = _v166_result.get("state")
                if state == "accepted" and file_id not in _v166_session_ids:
                    _v166_session_ids.append(file_id)
                elif str(state).startswith("duplicate"):
                    wait["_fast_session_duplicates"] = int(
                        wait.get("_fast_session_duplicates") or 0) + 1
                elif state == "limit":
                    wait["_fast_session_rejected"] = int(
                        wait.get("_fast_session_rejected") or 0) + 1
                _v165_schedule_progress(
                    context, msg, wait["card_id"], target, _v166_session_ids,
                    wait.get("_fast_session_duplicates", 0),
                    wait.get("_fast_session_rejected", 0))
                raise ApplicationHandlerStop
        elif msg.video:
            file_id = msg.video.file_id
            if target in ("videos", "video_h", "video_v"):
                target = "videos"
                slot = _orient(msg.video)
                tag = {"video_h": "гориз", "video_v": "вертик"}.get(slot, "")
        elif msg.video_note:
            file_id = msg.video_note.file_id
        elif msg.document:
            file_id = msg.document.file_id
        card = card_of(wait["card_id"])
        if not card:
            context.user_data.pop("car_media_wait", None)
            return
        if file_id:
            answer = await asyncio.to_thread(save_media, card, target, file_id, user_id, tag)
            if answer:
                await msg.reply_text(answer)
            raise ApplicationHandlerStop
        if msg.text and target == "diag_report":
            pass
        return

