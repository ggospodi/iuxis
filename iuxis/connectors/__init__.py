"""
Iuxis Connector Layer — external source adapters.

Current connectors:
  - FileWatcher: monitors ~/iuxis-inbox/ for dropped files

Planned connectors (v1.1):
  - SlackBot: @iuxis mention in Slack workspace
  - NotionAdapter: poll designated Notion database
  - LinearAdapter: poll project issues from Linear
"""

from .file_watcher import FileWatcherConnector

__all__ = ["FileWatcherConnector"]
