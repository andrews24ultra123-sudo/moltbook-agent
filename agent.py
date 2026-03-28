"""
Moltbook AI Referring Agent
Automatically posts and replies to relevant threads with referral link
"""

import os
import sys
import time
import sqlite3
import requests
import schedule
import logging
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
MOLTBOOK_API_BASE = "https://www.moltbook.com/api/v1"
MOLTBOOK_API_KEY = os.getenv("MOLTBOOK_API_KEY")
REFERRAL_URL = os.getenv("REFERRAL_URL", "https://free1usdt-lrwmwdym.manus.space/?ref=AGENT_ID")
DB_PATH = os.getenv("DB_PATH", "/tmp/moltbook_agent.db")
AGENT_NAME = os.getenv("AGENT_NAME", "usdt bot")

# Keywords to search for
KEYWORDS = ["yield", "DeFi", "USDT", "RWA", "passive income", "AI finance", "wallet"]

# Post variations
POST_VARIATIONS = [
    "Hey — there's a zero-risk demo running right now. Connect your wallet on BNB Chain, fill a short form, get 1 USDT. No transaction signing needed. Just wallet connect + form. {referral_link}",
    "Quick heads up: Free 1 USDT demo live now. BNB Chain only. Connect wallet → fill form → instant USDT. No signing required. {referral_link}",
    "Zero-risk USDT giveaway: Connect your BNB wallet, submit a quick form, get 1 USDT instantly. No transaction signing. Try it: {referral_link}",
    "1 USDT waiting for you on BNB Chain. Just connect wallet + form. No signing, no risk. {referral_link}",
]


class MoltbookAgent:
    def __init__(self):
        self.api_key = MOLTBOOK_API_KEY
        self.referral_url = REFERRAL_URL
        self.agent_name = AGENT_NAME
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.db_path = DB_PATH
        self.post_index = 0

        # Circuit breaker state
        self.consecutive_failures = 0
        self.circuit_open = False
        self.circuit_open_until = None

        self.init_db()

    # ------------------------------------------------------------------ #
    # Circuit breaker
    # ------------------------------------------------------------------ #

    def is_circuit_open(self) -> bool:
        """Return True if we should skip API calls right now."""
        if self.circuit_open:
            if datetime.now() < self.circuit_open_until:
                remaining = int((self.circuit_open_until - datetime.now()).total_seconds() / 60)
                logger.warning(f"Circuit breaker open — Moltbook API still degraded. Retrying in ~{remaining} min.")
                return True
            else:
                logger.info("Circuit breaker reset — retrying Moltbook API.")
                self.circuit_open = False
                self.consecutive_failures = 0
        return False

    def record_failure(self):
        self.consecutive_failures += 1
        if self.consecutive_failures >= 3:
            wait_minutes = min(60, 10 * self.consecutive_failures)
            self.circuit_open = True
            self.circuit_open_until = datetime.now() + timedelta(minutes=wait_minutes)
            logger.warning(
                f"3+ consecutive API failures — circuit breaker tripped for {wait_minutes} minutes. "
                f"Moltbook is likely experiencing an outage."
            )

    def record_success(self):
        if self.consecutive_failures > 0:
            logger.info("API call succeeded — resetting failure counter.")
        self.consecutive_failures = 0
        self.circuit_open = False

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #

    def init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    submolt_name TEXT,
                    title TEXT,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT UNIQUE,
                    thread_title TEXT,
                    submolt_name TEXT,
                    replied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS agent_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()
            logger.info(f"Database initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")

    def save_post(self, post_id: str, submolt: str, title: str, content: str):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute(
                "INSERT OR REPLACE INTO posts (id, submolt_name, title, content) VALUES (?, ?, ?, ?)",
                (post_id, submolt, title, content)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to save post: {e}")

    def has_replied_to_thread(self, thread_id: str) -> bool:
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT id FROM replies WHERE thread_id = ?", (thread_id,))
            result = c.fetchone()
            conn.close()
            return result is not None
        except Exception as e:
            logger.error(f"Failed to check reply status: {e}")
            return False

    def mark_thread_as_replied(self, thread_id: str, thread_title: str, submolt: str):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute(
                "INSERT OR REPLACE INTO replies (thread_id, thread_title, submolt_name) VALUES (?, ?, ?)",
                (thread_id, thread_title, submolt)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to mark thread as replied: {e}")

    # ------------------------------------------------------------------ #
    # API calls
    # ------------------------------------------------------------------ #

    def check_agent_status(self) -> bool:
        try:
            response = requests.get(
                f"{MOLTBOOK_API_BASE}/agents/status",
                headers=self.headers,
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                logger.info(f"Agent status: {status}")
                return status == "claimed"
            else:
                logger.error(f"Status check failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Status check error: {e}")
            return False

    def search_posts(self, keyword: str, limit: int = 20) -> list:
        if self.is_circuit_open():
            return []
        try:
            response = requests.get(
                f"{MOLTBOOK_API_BASE}/search",
                headers=self.headers,
                params={"q": keyword, "limit": limit},
                timeout=15
            )
            if response.status_code == 200:
                self.record_success()
                return response.json().get("posts", [])
            else:
                self.record_failure()
                logger.warning(f"Search failed for '{keyword}': {response.status_code} - {response.text}")
                return []
        except Exception as e:
            self.record_failure()
            logger.error(f"Search error for '{keyword}': {e}")
            return []

    def reply_to_post(self, post_id: str, content: str) -> bool:
        if self.is_circuit_open():
            return False
        try:
            response = requests.post(
                f"{MOLTBOOK_API_BASE}/posts/{post_id}/comments",
                headers=self.headers,
                json={"content": content},
                timeout=15
            )
            if response.status_code in [200, 201]:
                self.record_success()
                logger.info(f"Successfully replied to post {post_id}")
                return True
            else:
                self.record_failure()
                logger.warning(f"Reply failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            self.record_failure()
            logger.error(f"Reply error: {e}")
            return False

    def create_post(self, title: str, content: str, submolt: str = "general") -> str:
        if self.is_circuit_open():
            return None
        try:
            response = requests.post(
                f"{MOLTBOOK_API_BASE}/posts",
                headers=self.headers,
                json={
                    "submolt": submolt,
                    "title": title,
                    "content": content
                },
                timeout=15
            )
            if response.status_code in [200, 201]:
                self.record_success()
                data = response.json()
                post_id = data.get("post", {}).get("id")
                logger.info(f"Post created: {post_id}")
                self.save_post(post_id, submolt, title, content)
                return post_id
            elif response.status_code == 429:
                data = response.json()
                retry_after = data.get("retry_after_minutes", "unknown")
                logger.warning(f"Post cooldown active. Retry after {retry_after} minutes.")
                return None
            else:
                self.record_failure()
                logger.warning(f"Post creation failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            self.record_failure()
            logger.error(f"Post creation error: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Main logic
    # ------------------------------------------------------------------ #

    def is_relevant_post(self, title: str, content: str) -> bool:
        text = f"{title} {content}".lower()
        return any(kw.lower() in text for kw in KEYWORDS)

    def check_and_reply(self):
        if self.is_circuit_open():
            logger.info("Skipping check-and-reply cycle — circuit breaker is open.")
            return

        logger.info("Starting check and reply cycle...")

        for keyword in KEYWORDS:
            # Stop early if circuit trips mid-cycle
            if self.is_circuit_open():
                logger.info("Circuit breaker tripped mid-cycle — stopping keyword search.")
                break

            logger.info(f"Searching for posts with keyword: {keyword}")
            posts = self.search_posts(keyword, limit=10)

            for post in posts:
                post_id = post.get("id")
                title = post.get("title", "")

                if self.has_replied_to_thread(post_id):
                    logger.info(f"Already replied to post {post_id}, skipping")
                    continue

                if self.is_relevant_post(title, post.get("content", "")):
                    reply_content = POST_VARIATIONS[0].format(referral_link=self.referral_url)
                    if self.reply_to_post(post_id, reply_content):
                        self.mark_thread_as_replied(post_id, title, post.get("submolt_name", "general"))
                        time.sleep(3)

    def post_original(self):
        if self.is_circuit_open():
            logger.info("Skipping original post — circuit breaker is open.")
            return

        logger.info("Creating original post...")
        variation = POST_VARIATIONS[self.post_index % len(POST_VARIATIONS)]
        content = variation.format(referral_link=self.referral_url)
        title = "Free 1 USDT on BNB Chain - Zero Risk Demo"

        post_id = self.create_post(title, content, "general")
        if post_id:
            self.post_index += 1
            logger.info(f"Original post created successfully: {post_id}")
        else:
            logger.warning("Original post not created (cooldown, circuit breaker, or error) — will retry next cycle.")

    def run_scheduler(self):
        logger.info(f"Agent '{self.agent_name}' scheduler started")
        logger.info(f"API Key: {self.api_key[:20]}...")
        logger.info(f"Referral URL: {self.referral_url}")

        schedule.every(4).hours.do(self.check_and_reply)
        schedule.every(6).hours.do(self.post_original)

        # Run check/reply immediately on startup
        self.check_and_reply()

        # Delay first post by 2 minutes
        logger.info("Waiting 2 minutes before first post...")
        time.sleep(120)
        self.post_original()

        while True:
            schedule.run_pending()
            time.sleep(60)


def main():
    if not MOLTBOOK_API_KEY:
        logger.error("MOLTBOOK_API_KEY environment variable not set")
        sys.exit(1)

    agent = MoltbookAgent()

    if not agent.check_agent_status():
        logger.warning("Agent status check failed or not yet claimed. Continuing anyway...")

    try:
        agent.run_scheduler()
    except KeyboardInterrupt:
        logger.info("Agent stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
