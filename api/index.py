from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
import re
from typing import Dict, List, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class BountyScraper:
    def __init__(self, slack_webhook_url: str):
        self.slack_webhook_url = slack_webhook_url
        self.base_url = "https://replit.com"
        self.bounties_url = "https://replit.com/bounties?status=open&order=creationDateDescending"
        self.sent_bounties = set()  # In-memory storage for demo
        
    def scrape_bounties(self) -> List[Dict]:
        """Scrape bounties from Replit"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            response = requests.get(self.bounties_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            bounties = []
            
            # Find bounty cards - these selectors may need adjustment based on actual HTML structure
            bounty_cards = soup.find_all('div', class_=['bounty-card', 'bounty-item']) or soup.find_all('a', href=re.compile(r'/bounties/'))
            
            if not bounty_cards:
                # Fallback: look for any links containing "bounties"
                bounty_cards = soup.find_all('a', href=re.compile(r'/bounties/[^/]+'))
                
            logger.info(f"Found {len(bounty_cards)} potential bounty elements")
            
            for card in bounty_cards[:20]:  # Limit to first 20 for performance
                try:
                    bounty_data = self.parse_bounty_card(card, soup)
                    if bounty_data:
                        bounties.append(bounty_data)
                except Exception as e:
                    logger.error(f"Error parsing bounty card: {e}")
                    continue
                    
            return bounties
            
        except requests.RequestException as e:
            logger.error(f"Error fetching bounties: {e}")
            return []
        except Exception as e:
            logger.error(f"Error scraping bounties: {e}")
            return []
    
    def parse_bounty_card(self, card, soup) -> Optional[Dict]:
        """Parse individual bounty card"""
        try:
            # Extract bounty URL
            bounty_url = None
            if card.name == 'a':
                bounty_url = card.get('href')
            else:
                link = card.find('a', href=re.compile(r'/bounties/'))
                if link:
                    bounty_url = link.get('href')
            
            if not bounty_url:
                return None
                
            if not bounty_url.startswith('http'):
                bounty_url = self.base_url + bounty_url
            
            # Extract title
            title = ""
            title_elements = card.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            if title_elements:
                title = title_elements[0].get_text(strip=True)
            else:
                # Fallback to any text content
                title = card.get_text(strip=True)[:100]
            
            # Extract price/value
            price_text = ""
            value = 0
            
            # Look for price indicators
            price_patterns = [
                r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)',  # $1,000.00
                r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:USD|dollars?)',  # 1000 USD
                r'(\d+(?:,\d{3})*)\s*(?:cycles?)',  # 1000 cycles
            ]
            
            card_text = card.get_text()
            for pattern in price_patterns:
                matches = re.findall(pattern, card_text, re.IGNORECASE)
                if matches:
                    price_text = matches[0]
                    # Convert to numeric value
                    value = float(price_text.replace(',', '').replace('$', ''))
                    break
            
            # Extract creation date (this might be tricky without specific selectors)
            created_at = datetime.now()  # Default to now
            
            # Look for time indicators
            time_patterns = [
                r'(\d+)\s*(?:hours?|hrs?)\s*ago',
                r'(\d+)\s*(?:days?)\s*ago',
                r'(\d+)\s*(?:minutes?|mins?)\s*ago'
            ]
            
            for pattern in time_patterns:
                matches = re.findall(pattern, card_text, re.IGNORECASE)
                if matches:
                    time_value = int(matches[0])
                    if 'hour' in pattern or 'hr' in pattern:
                        created_at = datetime.now() - timedelta(hours=time_value)
                    elif 'day' in pattern:
                        created_at = datetime.now() - timedelta(days=time_value)
                    elif 'minute' in pattern or 'min' in pattern:
                        created_at = datetime.now() - timedelta(minutes=time_value)
                    break
            
            return {
                'title': title,
                'url': bounty_url,
                'value': value,
                'price_text': price_text,
                'created_at': created_at,
                'id': bounty_url.split('/')[-1]  # Use URL slug as ID
            }
            
        except Exception as e:
            logger.error(f"Error parsing bounty card: {e}")
            return None
    
    def filter_recent_bounties(self, bounties: List[Dict], hours: int = 24) -> List[Dict]:
        """Filter bounties posted within the last N hours"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [b for b in bounties if b['created_at'] >= cutoff_time]
    
    def get_highest_value_bounty(self, bounties: List[Dict]) -> Optional[Dict]:
        """Get the highest valued bounty"""
        if not bounties:
            return None
        return max(bounties, key=lambda x: x['value'])
    
    def send_slack_notification(self, bounty: Dict) -> bool:
        """Send bounty notification to Slack"""
        try:
            message = {
                "text": f"🎯 New High-Value Bounty Alert!",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*🎯 New High-Value Bounty Alert!*\n\n*{bounty['title']}*"
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Value:*\n${bounty['value']:.2f}" if bounty['value'] > 0 else f"*Value:*\n{bounty['price_text'] or 'Not specified'}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Posted:*\n{bounty['created_at'].strftime('%Y-%m-%d %H:%M')}"
                            }
                        ]
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "View Bounty"
                                },
                                "url": bounty['url'],
                                "style": "primary"
                            }
                        ]
                    }
                ]
            }
            
            response = requests.post(self.slack_webhook_url, json=message, timeout=10)
            response.raise_for_status()
            
            logger.info(f"Slack notification sent for bounty: {bounty['title']}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")
            return False
    
    def process_bounties(self):
        """Main processing function"""
        try:
            logger.info("Starting bounty scraping process...")
            
            # Scrape bounties
            all_bounties = self.scrape_bounties()
            logger.info(f"Found {len(all_bounties)} total bounties")
            
            # Filter recent bounties
            recent_bounties = self.filter_recent_bounties(all_bounties, hours=24)
            logger.info(f"Found {len(recent_bounties)} recent bounties")
            
            # Get highest value bounty
            highest_bounty = self.get_highest_value_bounty(recent_bounties)
            
            if not highest_bounty:
                logger.info("No recent bounties found")
                return {"status": "success", "message": "No recent bounties found"}
            
            # Check if already sent
            if highest_bounty['id'] in self.sent_bounties:
                logger.info(f"Bounty {highest_bounty['id']} already sent")
                return {"status": "success", "message": "Bounty already sent"}
            
            # Send notification
            if self.send_slack_notification(highest_bounty):
                self.sent_bounties.add(highest_bounty['id'])
                return {
                    "status": "success", 
                    "message": f"Notification sent for bounty: {highest_bounty['title']}",
                    "bounty": highest_bounty
                }
            else:
                return {"status": "error", "message": "Failed to send notification"}
                
        except Exception as e:
            logger.error(f"Error processing bounties: {e}")
            return {"status": "error", "message": str(e)}

# Initialize scraper
scraper = None

@app.route('/')
def home():
    """Home endpoint"""
    return jsonify({
        "message": "🎯 Replit Bounty Scraper API",
        "status": "running",
        "endpoints": {
            "/": "Home - API documentation",
            "/api/cron": "Cron job endpoint (POST)",
            "/api/manual": "Manual trigger endpoint (POST)",
            "/api/test": "Test scraping endpoint (GET)"
        },
        "description": "Automated bounty scraping bot for Replit bounties with Slack notifications"
    })

@app.route('/api/cron', methods=['POST'])
def cron_job():
    """Cron job endpoint - triggered by Vercel cron"""
    global scraper
    
    if not scraper:
        slack_webhook = os.getenv('SLACK_WEBHOOK_URL')
        if not slack_webhook:
            return jsonify({"error": "SLACK_WEBHOOK_URL not configured"}), 500
        scraper = BountyScraper(slack_webhook)
    
    result = scraper.process_bounties()
    
    if result["status"] == "success":
        return jsonify(result)
    else:
        return jsonify(result), 500

@app.route('/api/manual', methods=['POST'])
def manual_trigger():
    """Manual trigger endpoint for testing"""
    global scraper
    
    if not scraper:
        slack_webhook = os.getenv('SLACK_WEBHOOK_URL')
        if not slack_webhook:
            return jsonify({"error": "SLACK_WEBHOOK_URL not configured"}), 500
        scraper = BountyScraper(slack_webhook)
    
    result = scraper.process_bounties()
    return jsonify(result)

@app.route('/api/test', methods=['GET'])
def test_scraping():
    """Test endpoint to check scraping without sending notifications"""
    global scraper
    
    if not scraper:
        slack_webhook = os.getenv('SLACK_WEBHOOK_URL', 'https://hooks.slack.com/test')
        scraper = BountyScraper(slack_webhook)
    
    try:
        bounties = scraper.scrape_bounties()
        recent_bounties = scraper.filter_recent_bounties(bounties)
        highest_bounty = scraper.get_highest_value_bounty(recent_bounties)
        
        return jsonify({
            "status": "success",
            "total_bounties": len(bounties),
            "recent_bounties": len(recent_bounties),
            "highest_bounty": highest_bounty,
            "sample_bounties": bounties[:3]  # Show first 3 for testing
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# For Vercel deployment
if __name__ == '__main__':
    app.run(debug=True)
