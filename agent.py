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
        self.init_db()
        self.post_index = 0

    def init_db(self):
        """Initialize SQLite database for tracking posts and replies"""
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
                    updated_at TIMESTA
