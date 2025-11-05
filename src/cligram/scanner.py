import asyncio
import logging
import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from rich.style import Style
from telethon import TelegramClient, errors, events, functions
from telethon.tl.custom.dialog import Dialog
from telethon.tl.types import ChannelParticipantsAdmins, Message, MessageService, User

from . import utils
from .app import Application
from .config import Config, ScanMode
from .exceptions import SessionNotFoundError
from .proxy_manager import ProxyManager
from .state_manager import StateManager

logger = None  # Will be initialized later


class TelegramScanner:
    """
    Manages Telegram scanning operations and message forwarding.

    The scanner provides functionality for:
    - Scanning group messages within defined windows
    - Processing users based on configured criteria
    - Forwarding messages with rate limiting
    - Managing multiple proxies for connection resilience
    """

    def __init__(self, app: Application):
        """
        Initialize scanner with configuration and state management.

        Args:
            app: Application instance
        """
        global logger
        logger = logging.getLogger("cligram.scanner")

        self.app: Application = app
        self.config: Config = app.config
        self.state: StateManager = app.state
        self.proxy_manager: ProxyManager = ProxyManager.from_config(app.config)

        self.delay_variation = 10
        self._thresholds = {
            "skip": (
                20 if self.config.scan.mode in (ScanMode.FULL, ScanMode.SEND) else 50
            ),
            "scan": (
                50 if self.config.scan.mode in (ScanMode.FULL, ScanMode.SEND) else 100
            ),
            "process": 20,
        }

        self._cached_ids: Dict[str, str] = {}
        self._entity_cache: Dict[str, User] = {}

    def _get_random_threshold(self, type_: str) -> int:
        """
        Generate a randomized threshold value for rate limiting.

        Args:
            type_: Type of threshold ('skip', 'scan', or 'process')

        Returns:
            Randomized threshold value based on configured base value
        """
        base = self._thresholds[type_]
        return max(
            1, base + random.randint(-self.delay_variation, self.delay_variation)
        )

    async def get_saved_messages(self, client: TelegramClient) -> List[int]:
        """
        Retrieve message IDs from configured source chat.

        Args:
            client: Active Telegram client instance

        Returns:
            List of message IDs from source chat
        """
        limit = self.config.scan.messages.limit
        entity = await client.get_entity(self.config.scan.messages.source)
        logger.debug(f"[SCAN] Using entity {entity.id} for message retrieval")
        msg_ids = []

        if self.config.scan.messages.randomize:
            msgs: List[Message] = await client.get_messages(entity, limit=limit)
            msg_ids = [
                msg.id
                for msg in msgs
                if msg
                and isinstance(msg, Message)
                and not isinstance(msg, MessageService)
                and msg.message
                and not msg.noforwards
            ]
            logger.info(f"[SCAN] Found {len(msg_ids)} message IDs in source")
        else:
            msg_id = self.config.scan.messages.msg_id
            msg = await client.get_messages(entity, ids=msg_id)
            if msg:
                msg_ids.append(msg.id)
                logger.info(f"[SCAN] Using configured message ID {msg.id} from source")
            else:
                raise ValueError(f"Configured message ID {msg_id} not found in source")

        return msg_ids

    async def get_group_id(self, client: TelegramClient, group: str) -> str:
        """
        Resolve a group identifier to its numeric ID.

        Args:
            client: Active Telegram client instance
            group: Group username, URL, or ID string

        Returns:
            String representation of group's numeric ID, or None if resolution fails
        """
        if group in self._cached_ids:
            return self._cached_ids[group]

        try:
            # Check if group is already an ID
            gid = int(group)
            logger.debug(f"[GROUP] {group} is already an ID")
            return str(gid)
        except ValueError:
            pass

        try:
            entity = await client.get_entity(group)
            gid = str(entity.id)
            self._cached_ids[group] = gid
            logger.debug(f"[GROUP] Resolved {group} to ID {gid}")
            return gid
        except Exception as e:
            logger.error(f"[GROUP] Failed to resolve {group}: {e}")
            return None

    async def human_delay(self, shutdown_event: Optional[asyncio.Event] = None):
        """
        Implement a configurable delay with random variation.

        Args:
            shutdown_event: Optional event to interrupt delay

        The delay duration is chosen based on configured normal and long break periods,
        with long break periods occurring based on probability settings.
        """
        delay = self.config.app.delays.random()
        logger.debug(f"[DELAY] Sleeping for {delay:.2f} seconds")

        # Sleep with cancellation support
        try:
            if shutdown_event:
                await asyncio.wait_for(shutdown_event.wait(), timeout=delay)
                logger.debug("[DELAY] Interrupted by shutdown")
                return
            else:
                await asyncio.sleep(delay)
        except asyncio.TimeoutError:
            pass  # Normal delay completion

    async def _resolve_user(
        self, client: TelegramClient, username: str
    ) -> Optional[User]:
        """
        Resolve username to Telegram User entity with caching.

        Args:
            client: Active Telegram client instance
            username: Username to resolve (without @ symbol)

        Returns:
            User entity if resolution successful, None otherwise
        """
        if username in self._entity_cache:
            logger.debug(f"[USER] Using cached entity for @{username}")
            return self._entity_cache[username]

        try:
            entity = await client.get_entity(f"@{username}")
            if not isinstance(entity, User):
                return None
            self._entity_cache[username] = entity
            logger.debug(f"[USER] Resolved @{username} to User ID {entity.id}")
            return entity
        except Exception as e:
            logger.error(f"[USER] Failed to resolve @{username}: {e}")
            return None

    async def process_user(
        self, client: TelegramClient, user: User, msg_ids: List[int]
    ) -> bool:
        """
        Process a user according to current operation mode.

        Args:
            client: Active Telegram client instance
            user: User entity to process
            msg_ids: List of message IDs available for forwarding

        Returns:
            True if user was successfully processed, False if skipped

        Handles scanning, eligibility checking, and message forwarding based on
        configured operation mode.
        """
        uid = user.id
        username = getattr(user, "username", None)

        try:
            # For scan/send modes, require username
            if self.config.scan.mode != ScanMode.FULL and not username:
                logger.debug(f"[SKIP] User {uid} has no username")
                return False

            if uid in self.state.users.messaged:
                logger.debug(f"[SKIP] User {username or uid} already messaged")
                return False

            if self.config.scan.mode == ScanMode.SCAN:
                if username and username in self.state.users.eligible:
                    logger.debug(f"[SKIP] User {username} already eligible")
                    return False
                self.state.users.eligible.add(username)
                logger.info(f"[DONE] Added username {username} to eligible list")
                return True

            if self.config.scan.mode in (ScanMode.FULL, ScanMode.SEND):
                msg_id = random.choice(msg_ids)
                if not self.config.scan.test:
                    logger.info(
                        f"[SEND] Forwarding message {msg_id} to user {username or uid}"
                    )
                    await client.forward_messages(
                        user, msg_id, from_peer=self.config.scan.messages.source
                    )
                    logger.info(
                        f"[DONE] Message {msg_id} forwarded successfully to {username or uid}"
                    )
                else:
                    logger.info(
                        f"[TEST] Would forward message {msg_id} to user {username or uid}"
                    )

                self.state.users.messaged.add(uid)
                logger.info(
                    f"[INFO] Total messaged users: {len(self.state.users.messaged)}"
                )
                return True

        except errors.UserIsBlockedError:
            logger.warning(f"[SKIP] User {uid} has blocked us")
        except errors.UserDeactivatedError:
            logger.warning(f"[SKIP] User {uid} account deactivated")
        except errors.FloodWaitError as e:
            logger.warning(
                f"[FLOOD] Rate limit exceeded for request {e.request.__class__.__name__} (wait {e.seconds} seconds)"
            )
            raise
        except errors.PeerFloodError as e:
            logger.error(
                f"[FLOOD] Peer flood error for request {e.request.__class__.__name__}"
            )
            raise
        except Exception as e:
            logger.error(
                f"[ERROR] Failed to process user {uid} ({e.__class__.__name__}): {str(e)}"
            )
            raise

    async def send_mode(
        self,
        client: TelegramClient,
        saved_msgs: List[int],
        shutdown_event: asyncio.Event,
    ):
        """
        Execute send mode operations.

        Args:
            client: Active Telegram client instance
            saved_msgs: List of message IDs available for forwarding
            shutdown_event: Event to signal operation shutdown

        Processes eligible users by sending configured messages with rate limiting
        and delay intervals.
        """
        sent = skipped = 0
        for username in list(
            self.state.users.eligible
        ):  # Create copy since we'll modify
            if shutdown_event.is_set():
                break

            user = await self._resolve_user(client, username)
            if not user:
                logger.warning(f"[SKIP] Could not resolve user @{username}")
                skipped += 1
                continue

            if user.id in self.state.users.messaged:
                logger.debug(f"[SKIP] User {username} already messaged")
                skipped += 1
                continue

            try:
                if await self.process_user(client, user, saved_msgs):
                    sent += 1
                    self.state.users.eligible.discard(username)
                    if self.config.app.rapid_save:
                        await self.state.save()
                else:
                    skipped += 1

                await self.human_delay(shutdown_event)

                if (sent + skipped) % 10 == 0:
                    logger.info(f"[INFO] Progress: {sent} sent, {skipped} skipped")

            except Exception as e:
                logger.error(f"[ERROR] Failed to process @{username}: {e}")
                break  # Stop on any error to avoid flooding logs

        logger.info(f"[INFO] Total: {sent + skipped}, sent: {sent}, skipped: {skipped}")

    async def scan_mode(
        self,
        client: TelegramClient,
        saved_msgs: List[int],
        shutdown_event: asyncio.Event,
    ):
        """
        Execute scan mode operations.

        Args:
            client: Active Telegram client instance
            saved_msgs: List of message IDs available for forwarding
            shutdown_event: Event to signal operation shutdown

        Scans configured groups for eligible users, maintaining message windows
        for incremental scanning.
        """
        total_groups = len(self.config.scan.targets)
        logger.info(f"[SCAN] Starting scan of {total_groups} groups")

        for idx, group in enumerate(self.config.scan.targets, 1):
            if shutdown_event.is_set():
                break

            logger.info(f"[SCAN] Group {idx}/{total_groups}: {group}")

            # Get group ID and window
            gid = await self.get_group_id(client, group)
            if not gid:
                logger.error(f"[SCAN] Failed to resolve group {group}, skipping")
                continue
            group_info = self.state.groups.get(gid)
            highest_id = group_info.max
            lowest_id = group_info.min
            logger.info(
                f"[SCAN] Group {group} (ID: {gid}) window: highest={highest_id}, lowest={lowest_id}"
            )

            try:
                # Use min_id for newer messages (above highest_id)
                if highest_id:
                    logger.info(f"[SCAN] Scanning messages newer than {highest_id}")
                    await self._scan_messages(
                        client,
                        group,
                        saved_msgs,
                        shutdown_event,
                        min_id=highest_id,
                        ref_point="newer",
                    )

                # Use max_id for older messages (below lowest_id)
                if lowest_id:
                    logger.info(f"[SCAN] Scanning messages older than {lowest_id}")
                    await self._scan_messages(
                        client,
                        group,
                        saved_msgs,
                        shutdown_event,
                        max_id=lowest_id,
                        ref_point="older",
                    )

                # If no window exists, scan without restrictions
                if not highest_id and not lowest_id:
                    logger.info("[SCAN] No existing window, scanning all messages")
                    await self._scan_messages(client, group, saved_msgs, shutdown_event)

            except Exception as e:
                logger.error(f"[ERROR] Failed to scan group {group}: {e}")

    async def _scan_messages(
        self,
        client: TelegramClient,
        group: str,
        saved_msgs: List[int],
        shutdown_event: asyncio.Event,
        min_id: Optional[int] = None,
        max_id: Optional[int] = None,
        ref_point: str = "all",
    ) -> None:
        """
        Scan messages in a group with window tracking.

        Args:
            client: Active Telegram client instance
            group: Group identifier to scan
            saved_msgs: List of message IDs available for forwarding
            shutdown_event: Event to signal scanning shutdown
            min_id: Optional minimum message ID for window
            max_id: Optional maximum message ID for window
            ref_point: Reference point for logging ("newer", "older", or "all")

        Scans messages within specified window, processes found users, and
        updates scanning window state.
        """
        scanned = processed = skipped = errors = 0
        start_time = time.time()
        gid = await self.get_group_id(client, group)
        if not gid:
            logger.error(f"[SCAN] Failed to resolve group {group}, skipping")
            return
        group_info = self.state.groups.get(gid)

        # Use Telethon's native window support
        iter_params = {"limit": self.config.scan.limit}
        if min_id:
            iter_params["min_id"] = min_id
            iter_params["reverse"] = True
        if max_id:
            iter_params["max_id"] = max_id

        admins = await client.get_participants(group, filter=ChannelParticipantsAdmins)
        admin_ids = {admin.id for admin in admins}
        logger.debug(f"[SCAN] Found {len(admins)} admins in {group}")

        logger.debug(f"[SCAN] Message iterator params: {iter_params}")

        # Get thresholds at start
        skip_threshold = self._get_random_threshold("skip")
        scan_threshold = self._get_random_threshold("scan")
        process_threshold = self._get_random_threshold("process")

        async for msg in client.iter_messages(group, **iter_params):
            if shutdown_event.is_set():
                break

            scanned += 1
            logger.debug(
                f"[SCAN] Found message {msg.id} ({scanned}/{self.config.scan.limit})"
            )

            # Always update both bounds with each message
            group_info.max = max(msg.id, group_info.max or msg.id)
            group_info.min = min(msg.id, group_info.min or msg.id)

            # Message processing
            if not msg.sender:
                logger.debug(f"[SKIP] Message {msg.id}: No sender")
                skipped += 1
                if skipped % 50 == 0:  # Add delay every 50 skips
                    await self.human_delay(shutdown_event)
                continue

            if not isinstance(msg.sender, User):
                logger.debug(
                    f"[SKIP] Message {msg.id}: Sender type {type(msg.sender).__name__}"
                )
                skipped += 1
                if skipped % 50 == 0:
                    await self.human_delay(shutdown_event)
                continue

            user: User = msg.sender
            uid = user.id
            username = getattr(user, "username", None)

            if user.bot:
                logger.debug(
                    f"[SKIP] Message {msg.id}: User {username or uid} is a bot"
                )
                skipped += 1
                if skipped % skip_threshold == 0:
                    skip_threshold = self._get_random_threshold("skip")
                    await self.human_delay(shutdown_event)
                continue

            if uid in admin_ids:
                logger.debug(
                    f"[SKIP] Message {msg.id}: User {username or uid} is an admin"
                )
                skipped += 1
                if skipped % skip_threshold == 0:
                    skip_threshold = self._get_random_threshold("skip")
                    await self.human_delay(shutdown_event)
                continue

            if uid in self.state.users.messaged:
                logger.debug(
                    f"[SKIP] Message {msg.id}: User {username or uid} already messaged"
                )
                skipped += 1
                if skipped % skip_threshold == 0:
                    skip_threshold = self._get_random_threshold("skip")
                    await self.human_delay(shutdown_event)
                continue

            if username in self.state.users.eligible:
                logger.debug(
                    f"[SKIP] Message {msg.id}: User {username or uid} already eligible"
                )
                skipped += 1
                if skipped % skip_threshold == 0:
                    skip_threshold = self._get_random_threshold("skip")
                    await self.human_delay(shutdown_event)
                continue

            # Rate limiting with random threshold
            if scanned % scan_threshold == 0:
                scan_threshold = self._get_random_threshold("scan")
                await self.human_delay(shutdown_event)

            try:
                logger.info(
                    f"[PROCESS] Message {msg.id}: Processing user {username or uid}"
                )
                if await self.process_user(client, user, saved_msgs):
                    processed += 1
                    if self.config.app.rapid_save:
                        await self.state.save()
                    # Only delay every N successful processes in scan mode
                    if self.config.scan.mode != ScanMode.SCAN or processed % 20 == 0:
                        await self.human_delay(shutdown_event)
                else:
                    logger.debug(
                        f"[SKIP] Message {msg.id}: User {uid} not processed (returned False)"
                    )
                    skipped += 1

                if processed % process_threshold == 0:
                    process_threshold = self._get_random_threshold("process")
                    await self.human_delay(shutdown_event)

                if processed % 10 == 0:
                    rate = processed / max(1, time.time() - start_time)
                    logger.info(f"[INFO] Processing rate: {rate*60:.1f} users/minute")
                    await self.state.save()  # Regular state saves

            except Exception as e:
                logger.error(
                    f"[ERROR] Message {msg.id}: Failed to process user {uid}: {str(e)}"
                )
                errors += 1
                break

        elapsed = time.time() - start_time
        if errors > 0:
            logger.error(
                f"[ERROR] {ref_point.title()} messages scan encountered {errors} errors"
            )
        else:
            logger.info(
                f"[COMPLETE] {ref_point.title()} messages scan finished in {elapsed:.1f}s:"
            )
        logger.info(
            f"[INFO] Scanned: {scanned}, Processed: {processed}, Skipped: {skipped}"
        )
        if processed > 0:
            logger.info(f"[INFO] Rate: {(processed/elapsed)*60:.1f} users/minute")

        # Save state after each direction scan
        await self.state.save()

    async def receive_mode(
        self, client: TelegramClient, shutdown_event: asyncio.Event
    ) -> None:
        """
        Execute receive mode operations.

        Args:
            client: Active Telegram client instance
            shutdown_event: Event to signal operation shutdown

        Receives and displays new messages from the configured source chat.
        """
        logger.info("[RECEIVE] Starting to receive new messages")

        @client.on(events.NewMessage)
        async def handler(event: events.NewMessage.Event):
            msg: Message = event.message
            user = await client.get_entity(msg.peer_id)
            logger.info(f"[MESSAGE] From {user.id}\n{msg.message}")

            # mark message as read
            await client(
                functions.messages.ReadHistoryRequest(peer=msg.peer_id, max_id=msg.id)
            )

        # Wait for shutdown event
        await shutdown_event.wait()

        # Remove event handler
        client.remove_event_handler(handler)
        logger.info("[RECEIVE] Stopped receiving messages")

    async def _resolve_exclusions(
        self, client: TelegramClient, shutdown_event: asyncio.Event
    ) -> None:
        """Resolve excluded usernames to UIDs and add to messaged state."""
        total = resolved = 0
        for username in self.config.exclusions:
            total += 1
            user = await self._resolve_user(client, username)

            if shutdown_event.is_set():
                return

            if user:
                if username in self.state.users.eligible:
                    self.state.users.eligible.discard(username)
                    logger.info(f"[USER] Removed @{username} from eligible list")
                if user.id not in self.state.users.messaged:
                    self.state.users.messaged.add(user.id)
                    logger.info(f"[USER] Added {user.id} to messaged list")
                else:
                    logger.debug(f"[SKIP] {user.id} already in messaged list")
                resolved += 1
            else:
                logger.warning(f"[USER] Failed to resolve @{username}")

            if total % 15 == 0:
                await self.human_delay(shutdown_event)
        logger.info(f"[INFO] Resolved {resolved}/{total} excluded users")

    async def run(self, shutdown_event: asyncio.Event):
        """
        Execute main scanner operations.

        Args:
            shutdown_event: Event to signal operation shutdown

        Sets up proxy connection, initializes client, and executes operations
        based on configured mode.
        """
        try:
            # Get session
            session = utils.get_session(self.config)

            # Test proxies and get working one
            self.app.status.update("Testing connections...")
            logger.info("Testing connections")
            await self.proxy_manager.test_proxies(shutdown_event=shutdown_event)
            working_connection = self.proxy_manager.current_proxy

            if shutdown_event.is_set():
                return

            if working_connection:
                if working_connection.is_direct:
                    logger.info("Using direct connection")
                else:
                    self.app.console.print(
                        f"Using {working_connection.type.value} proxy: {working_connection.host}:{working_connection.port}"
                    )
                    logger.info(
                        f"Using proxy: [{working_connection.type.name}] {working_connection.host}:{working_connection.port}"
                    )
            else:
                self.app.console.print("No working connection available, aborting")
                logger.error("No working connection available, aborting")
                return

            self.app.status.update("Initializing client...")
            # Create actual client with working connection
            client: TelegramClient = utils.get_client(
                config=self.config, proxy=working_connection, session=session
            )

            self.app.status.update("Logging in...")
            logger.info(f"Logging in with {client.session.filename} session")

            # Continue with client operations
            async with client:
                if shutdown_event.is_set():
                    return

                self.app.status.update("Fetching account information...")
                logger.debug("Fetching account information")
                me: User = await client.get_me()

                if me.first_name and me.last_name:
                    name = f"{me.first_name} {me.last_name}"
                else:
                    name = me.first_name

                self.app.status.update("Updating status...")
                logger.debug("Updating status to online")
                result = await client(
                    functions.account.UpdateStatusRequest(offline=False)
                )
                if not result:
                    self.app.console.print(
                        "Failed to set status to online", style=Style(color="red")
                    )
                    logger.error("Failed to set status to online")
                else:
                    logger.debug("Status set to online successfully")

                self.app.console.print(f"Logged in as {name} (ID: {me.id})")
                logger.info(f"Logged in as {name} (ID: {me.id})")

                # Log detailed account info for debugging
                if self.config.app.verbose:
                    logger.debug(f"Account ID: {me.id}")
                    logger.debug(f"Full Name: {name}")
                    logger.debug(f"Username: {me.username}")
                    logger.debug(f"Phone: {me.phone}")

                # Show unread messages count
                self.app.status.update("Checking unread messages...")
                logger.debug("Checking for unread messages")
                total_unread = 0
                async for dialog in client.iter_dialogs(limit=50):
                    logger.debug(f"Processing {dialog.name} ({dialog.id})")
                    try:
                        unread = int(getattr(dialog, "unread_count", 0) or 0)
                    except Exception:
                        unread = 0
                    logger.debug(f"Unread count: {unread}")
                    if unread <= 0:
                        continue
                    muted = self._is_dialog_muted(dialog)
                    logger.debug(f"Is muted: {muted}")
                    if muted:
                        continue
                    total_unread += unread

                if total_unread > 0:
                    self.app.console.print(
                        f"You have {total_unread} unread messages",
                        style=Style(color="yellow"),
                    )
                    logger.warning(f"You have {total_unread} unread messages")
                else:
                    logger.debug("No unread messages")

                try:
                    await self.start(client, shutdown_event)
                finally:
                    self.app.status.update("Shutting down client...")
                    if not client.is_connected():
                        if self.config.scan.mode != ScanMode.LOGOUT:
                            logger.warning("Client disconnected unexpectedly")

                        return

                    logger.debug("Updating status to offline")
                    result = await client(
                        functions.account.UpdateStatusRequest(offline=True)
                    )
                    if not result:
                        logger.error("Failed to set status to offline")
                    else:
                        logger.debug("Status set to offline successfully")

            logger.info("Client session closed")

        except SessionNotFoundError as e:
            self.app.console.print(
                "Session not found:",
                self.config.telegram.session,
                style=Style(color="red"),
            )
            logger.error(f"Session not found: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise

    async def start(self, client: TelegramClient, shutdown_event: asyncio.Event):
        self.app.status.update("Starting operations...")

        if self.config.scan.mode == ScanMode.HALT:
            return

        # Account logout
        if self.config.scan.mode == ScanMode.LOGOUT:
            user_input = self.app.console.input(
                "Are you sure you want to log out and delete the session? (y/N): "
            )
            if user_input.lower() == "y":
                self.app.status.update("Logging out...")
                logger.info("Logging out and deleting session")
                result = await client.log_out()
                if result:
                    self.app.console.print(
                        "Logged out successfully", style=Style(color="green")
                    )
                    logger.info("Logged out successfully")
                else:
                    self.app.console.print(
                        "Failed to log out", style=Style(color="red")
                    )
                    logger.error("Failed to log out")
            else:
                self.app.console.print("Logout canceled", style=Style(color="yellow"))
                logger.info("Logout canceled")
            return

        # Process exclusions if any
        if hasattr(self.config, "exclusions") and self.config.exclusions:
            await self._resolve_exclusions(client, shutdown_event)
            return

        if self.config.scan.mode == ScanMode.RECEIVE:
            await self.receive_mode(client, shutdown_event)
            return

        saved_msgs = await self.get_saved_messages(client)
        if not saved_msgs:
            logger.error("No saved messages available")
            return

        if self.config.scan.mode == ScanMode.SEND:
            await self.send_mode(client, saved_msgs, shutdown_event)
        else:
            await self.scan_mode(client, saved_msgs, shutdown_event)

    @staticmethod
    def _is_dialog_muted(dialog: Dialog) -> bool:
        try:
            if not dialog.dialog.notify_settings.mute_until:
                return False

            return (
                dialog.dialog.notify_settings.mute_until.timestamp()
                > datetime.now().timestamp()
            )
        except Exception:
            return False

    delay_variation: int
    """Maximum variation in seconds to add/subtract from base thresholds"""

    _thresholds: Dict[str, int]
    """Base thresholds for different operation types:
    - skip: Messages to skip before delay
    - scan: Messages to scan before delay
    - process: Users to process before delay
    """

    _cached_ids: Dict[str, str]
    """Cache of resolved group identifiers to numeric IDs"""

    _entity_cache: Dict[str, User]
    """Cache of resolved usernames to User entities"""
