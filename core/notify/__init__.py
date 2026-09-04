"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Notification: reaching out about work the register already knows about.

Delivery, not a queue. The outstanding work is derived; this is what makes it
arrive somewhere rather than waiting to be looked at.
"""
from core.notify.channels import EmailChannel, LogChannel, WebhookChannel, build
from core.notify.common import (CHANNELS, CHANNEL_MEANING, STATES, NotifyError)
from core.notify.service import NotificationService

__all__ = ["NotificationService", "NotifyError", "CHANNELS", "CHANNEL_MEANING",
           "STATES", "LogChannel", "WebhookChannel", "EmailChannel", "build"]
