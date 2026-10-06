"""app/models/__init__.py — import all models to register with Base.metadata"""
from app.models.client import Client
from app.models.campaign import Campaign
from app.models.mailbox import Mailbox
from app.models.campaign_mailbox import CampaignMailbox
from app.models.mailbox_stat import MailboxStat
from app.models.report import Report

__all__ = ["Client", "Campaign", "Mailbox", "CampaignMailbox", "MailboxStat", "Report"]
