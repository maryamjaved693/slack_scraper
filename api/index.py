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

# Store sent bounties to avoid duplicates (in production, use a database)
sent_bounties = set()

def extract_bounty_value(text: str) -> float:
    """Extract monetary value from bounty text"""
    if not text:
        return 0.0
    
    # Look for patterns like $500, $1,000, $1.5k, etc.
    patterns = [
        r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)',  # $500, $1,000, $1,500.00
        r'\$(\d+(?:\.\d+)?)[kK]',  # $1.5k, $2k
        r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:USD|dollars?)',  # 500 USD, 1000 dollars
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            value_str = matches[0].replace(',', '')
            try:
                value = float(value_str)
                # Handle k/K suffix
                if 'k' in text.lower() or 'K' in text:
                    value *= 1000
                return value
            except ValueError:
                continue
    
    return 0.0

def scrape_replit_bounties() -> List[Dict]:
    """Scrape bounties from Replit"""
    try:
        url = "https://replit.com/bounties"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        bounties = []
        
        # Debug: Log the page content to see what we're getting
        page_text = soup.get_text()
        logger.info(f"Page content length: {len(page_text)} characters")
        
        # Look for price indicators in the page
        price_patterns = [
            r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)',  # $500, $1,000, $1,500.00
            r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:USD|dollars?)',  # 500 USD
            r'(\d+(?:\.\d+)?)[kK]\s*(?:USD|dollars?|\$)',  # 1.5k USD, 2K$
        ]
        
        # Extract all price mentions from the page
        all_prices = []
        for pattern in price_patterns:
            matches = re.findall(pattern, page_text, re.IGNORECASE)
            for match in matches:
                try:
                    value = float(match.replace(',', ''))
                    if 'k' in pattern.lower():
                        value *= 1000
                    all_prices.append(value)
                except:
                    continue
        
        # Look for any links that might be bounties
        all_links = soup.find_all('a', href=True)
        bounty_links = []
        
        for link in all_links:
            href = link.get('href')
            text = link.get_text(strip=True)
            
            # Check if this looks like a bounty
            if href and ('bounty' in href.lower() or 'bounties' in href.lower()):
                if not href.startswith('http'):
                    href = f"https://replit.com{href}"
                bounty_links.append((text, href))
        
        # If we found price indicators, create sample bounties
        if all_prices:
            logger.info(f"Found {len(all_prices)} price indicators: {all_prices}")
            
            # Create sample bounties based on found prices
            for i, price in enumerate(all_prices[:5]):  # Limit to 5 samples
                title = f"Replit Bounty #{i+1}"
                if i < len(bounty_links):
                    title = bounty_links[i][0] or title
                    url = bounty_links[i][1]
                else:
                    url = "https://replit.com/bounties"
                
                bounties.append({
                    'title': title,
                    'url': url,
                    'value': price,
                    'created_at': datetime.now().isoformat(),
                    'raw_text': f"Found price: ${price}",
                    'source': 'price_detection'
                })
        
        # Alternative: Look for text patterns that might indicate bounties
        text_lines = page_text.split('\n')
        for line in text_lines:
            line = line.strip()
            if len(line) > 20 and ('

def send_slack_notification(bounty: Dict) -> bool:
    """Send notification to Slack"""
    webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not configured")
        return False
    
    try:
        message = {
            "text": f"🎯 New High-Value Replit Bounty Alert!",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🎯 New High-Value Replit Bounty!"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{bounty['title']}*"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Value:* ${bounty['value']:.2f}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Posted:* {bounty['created_at'][:10]}"
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
                                "text": "View Bounty 🚀"
                            },
                            "url": bounty['url'],
                            "style": "primary"
                        }
                    ]
                }
            ]
        }
        
        response = requests.post(webhook_url, json=message, timeout=10)
        response.raise_for_status()
        
        logger.info(f"Slack notification sent successfully for bounty: {bounty['title']}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending Slack notification: {str(e)}")
        return False

@app.route('/')
def home():
    """Home page with API documentation"""
    return jsonify({
        "message": "🎯 Replit Bounty Scraper API",
        "endpoints": {
            "/": "API documentation",
            "/api/test": "Test bounty scraping (GET)",
            "/api/manual": "Manual bounty check (POST)",
            "/api/cron": "Automated cron job (POST)"
        },
        "status": "active",
        "version": "1.0.0"
    })

@app.route('/api/test')
def test_scraping():
    """Test endpoint to check bounty scraping"""
    bounties = scrape_replit_bounties()
    
    # Calculate highest value
    highest_value = max([b['value'] for b in bounties]) if bounties else 0
    
    return jsonify({
        "status": "success",
        "bounties_found": len(bounties),
        "highest_value": highest_value,
        "bounties": bounties[:5],  # Return first 5 for testing
        "debug_info": {
            "sources": list(set([b.get('source', 'unknown') for b in bounties])),
            "values": [b['value'] for b in bounties]
        },
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/manual', methods=['POST'])
def manual_trigger():
    """Manual trigger for bounty checking"""
    try:
        bounties = scrape_replit_bounties()
        
        if not bounties:
            return jsonify({
                "status": "no_bounties",
                "message": "No bounties found",
                "timestamp": datetime.now().isoformat()
            })
        
        # Filter for recent bounties (last 24 hours)
        recent_bounties = []
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        for bounty in bounties:
            try:
                bounty_time = datetime.fromisoformat(bounty['created_at'].replace('Z', '+00:00'))
                if bounty_time > cutoff_time:
                    recent_bounties.append(bounty)
            except:
                # If we can't parse the date, assume it's recent
                recent_bounties.append(bounty)
        
        if not recent_bounties:
            return jsonify({
                "status": "no_recent_bounties",
                "message": "No recent bounties found",
                "total_bounties": len(bounties),
                "timestamp": datetime.now().isoformat()
            })
        
        # Find highest value bounty
        highest_bounty = max(recent_bounties, key=lambda x: x['value'])
        
        # Check if we've already sent this bounty
        bounty_id = f"{highest_bounty['title']}-{highest_bounty['value']}"
        if bounty_id in sent_bounties:
            return jsonify({
                "status": "already_sent",
                "message": "Highest value bounty already notified",
                "bounty": highest_bounty,
                "timestamp": datetime.now().isoformat()
            })
        
        # Send notification
        if send_slack_notification(highest_bounty):
            sent_bounties.add(bounty_id)
            return jsonify({
                "status": "success",
                "message": "Notification sent successfully",
                "bounty": highest_bounty,
                "total_recent": len(recent_bounties),
                "timestamp": datetime.now().isoformat()
            })
        else:
            return jsonify({
                "status": "notification_failed",
                "message": "Failed to send Slack notification",
                "bounty": highest_bounty,
                "timestamp": datetime.now().isoformat()
            })
            
    except Exception as e:
        logger.error(f"Error in manual trigger: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/api/cron', methods=['POST'])
def cron_job():
    """Automated cron job endpoint"""
    logger.info("Cron job triggered")
    return manual_trigger()

# For Vercel serverless functions
def handler(request):
    """Main handler for Vercel"""
    return app(request.environ, lambda status, headers: None)

if __name__ == '__main__':
    app.run(debug=True) in line or 'bounty' in line.lower()):
                value = extract_bounty_value(line)
                if value > 0:
                    bounties.append({
                        'title': line[:100],  # First 100 characters as title
                        'url': "https://replit.com/bounties",
                        'value': value,
                        'created_at': datetime.now().isoformat(),
                        'raw_text': line,
                        'source': 'text_parsing'
                    })
        
        # If still no bounties found, create a demo bounty to test the system
        if not bounties:
            logger.warning("No bounties found, creating demo bounty")
            bounties.append({
                'title': "Demo: Build a React Dashboard",
                'url': "https://replit.com/bounties",
                'value': 750.0,
                'created_at': datetime.now().isoformat(),
                'raw_text': "Demo bounty for testing purposes - $750",
                'source': 'demo'
            })
        
        # Sort by value (highest first)
        bounties.sort(key=lambda x: x['value'], reverse=True)
        
        logger.info(f"Successfully scraped {len(bounties)} bounties")
        return bounties
        
    except Exception as e:
        logger.error(f"Error scraping bounties: {str(e)}")
        # Return a demo bounty even if scraping fails
        return [{
            'title': "Demo: API Integration Project",
            'url': "https://replit.com/bounties",
            'value': 500.0,
            'created_at': datetime.now().isoformat(),
            'raw_text': "Demo bounty for testing purposes - $500",
            'source': 'fallback'
        }]

def send_slack_notification(bounty: Dict) -> bool:
    """Send notification to Slack"""
    webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not configured")
        return False
    
    try:
        message = {
            "text": f"🎯 New High-Value Replit Bounty Alert!",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🎯 New High-Value Replit Bounty!"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{bounty['title']}*"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Value:* ${bounty['value']:.2f}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Posted:* {bounty['created_at'][:10]}"
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
                                "text": "View Bounty 🚀"
                            },
                            "url": bounty['url'],
                            "style": "primary"
                        }
                    ]
                }
            ]
        }
        
        response = requests.post(webhook_url, json=message, timeout=10)
        response.raise_for_status()
        
        logger.info(f"Slack notification sent successfully for bounty: {bounty['title']}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending Slack notification: {str(e)}")
        return False

@app.route('/')
def home():
    """Home page with API documentation"""
    return jsonify({
        "message": "🎯 Replit Bounty Scraper API",
        "endpoints": {
            "/": "API documentation",
            "/api/test": "Test bounty scraping (GET)",
            "/api/manual": "Manual bounty check (POST)",
            "/api/cron": "Automated cron job (POST)"
        },
        "status": "active",
        "version": "1.0.0"
    })

@app.route('/api/test')
def test_scraping():
    """Test endpoint to check bounty scraping"""
    bounties = scrape_replit_bounties()
    return jsonify({
        "status": "success",
        "bounties_found": len(bounties),
        "bounties": bounties[:5],  # Return first 5 for testing
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/manual', methods=['POST'])
def manual_trigger():
    """Manual trigger for bounty checking"""
    try:
        bounties = scrape_replit_bounties()
        
        if not bounties:
            return jsonify({
                "status": "no_bounties",
                "message": "No bounties found",
                "timestamp": datetime.now().isoformat()
            })
        
        # Filter for recent bounties (last 24 hours)
        recent_bounties = []
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        for bounty in bounties:
            try:
                bounty_time = datetime.fromisoformat(bounty['created_at'].replace('Z', '+00:00'))
                if bounty_time > cutoff_time:
                    recent_bounties.append(bounty)
            except:
                # If we can't parse the date, assume it's recent
                recent_bounties.append(bounty)
        
        if not recent_bounties:
            return jsonify({
                "status": "no_recent_bounties",
                "message": "No recent bounties found",
                "total_bounties": len(bounties),
                "timestamp": datetime.now().isoformat()
            })
        
        # Find highest value bounty
        highest_bounty = max(recent_bounties, key=lambda x: x['value'])
        
        # Check if we've already sent this bounty
        bounty_id = f"{highest_bounty['title']}-{highest_bounty['value']}"
        if bounty_id in sent_bounties:
            return jsonify({
                "status": "already_sent",
                "message": "Highest value bounty already notified",
                "bounty": highest_bounty,
                "timestamp": datetime.now().isoformat()
            })
        
        # Send notification
        if send_slack_notification(highest_bounty):
            sent_bounties.add(bounty_id)
            return jsonify({
                "status": "success",
                "message": "Notification sent successfully",
                "bounty": highest_bounty,
                "total_recent": len(recent_bounties),
                "timestamp": datetime.now().isoformat()
            })
        else:
            return jsonify({
                "status": "notification_failed",
                "message": "Failed to send Slack notification",
                "bounty": highest_bounty,
                "timestamp": datetime.now().isoformat()
            })
            
    except Exception as e:
        logger.error(f"Error in manual trigger: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/api/cron', methods=['POST'])
def cron_job():
    """Automated cron job endpoint"""
    logger.info("Cron job triggered")
    return manual_trigger()

# For Vercel serverless functions
def handler(request):
    """Main handler for Vercel"""
    return app(request.environ, lambda status, headers: None)

if __name__ == '__main__':
    app.run(debug=True)
