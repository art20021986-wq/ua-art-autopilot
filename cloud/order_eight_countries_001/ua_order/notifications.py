"""One bounded outbox operation, scheduled by the existing bot job queue."""
import asyncio


async def dispatch_once(repository, deliver):
    claim=await asyncio.to_thread(repository.claim_notification)
    if not claim: return False
    try:
        row=await asyncio.to_thread(repository.notification_data,claim['request_id'])
        # deliver is the existing manager notification adapter, not a new token
        # or recipient. A timeout can mean delivery succeeded; external delivery
        # is at-least-once and always carries the same order number.
        await asyncio.wait_for(deliver(row),timeout=20)
    except (Exception, asyncio.CancelledError):
        await asyncio.to_thread(repository.finish_notification,claim,delivered=False)
        raise
    await asyncio.to_thread(repository.finish_notification,claim,delivered=True)
    return True
