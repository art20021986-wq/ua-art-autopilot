"""Shared application boundary for the website and Telegram adapters."""
from dataclasses import dataclass
import re

from .contract import digest, normalize


@dataclass(frozen=True)
class Principal:
    owner: str
    channel: str
    event_id: str | None = None

    def __post_init__(self):
        if self.channel not in ('site', 'telegram_bot', 'telegram_mini_app'):
            raise ValueError('Unknown channel')
        prefix = 'web:' if self.channel == 'site' else 'telegram:'
        if not self.owner.startswith(prefix) or len(self.owner) <= len(prefix):
            raise ValueError('Invalid verified identity')
        if prefix == 'telegram:' and not re.fullmatch(r'telegram:[1-9][0-9]{0,18}', self.owner):
            raise ValueError('Invalid Telegram identity')


class OrderService:
    def __init__(self, catalog, repository, consent_version):
        if not consent_version:
            raise ValueError('The existing company consent text must be configured')
        self.catalog, self.repository = catalog, repository
        self.consent_version = consent_version

    def normalize(self, payload, principal):
        return normalize(payload, self.catalog, self.consent_version,
                         verified_contact=principal.owner.startswith('telegram:'))

    def submit(self, payload, principal):
        data = self.normalize(payload, principal)
        event = f'{principal.channel}:{principal.event_id}' if principal.event_id else None
        return self.repository.save(data, digest(data), principal.owner, principal.channel, event)

    def handoff(self, payload, principal):
        data = self.normalize(payload, principal)
        return self.repository.create_draft(data, principal.owner)
