"""
Web scraper for Claude.ai share URLs.
"""

import time
import random
from typing import Optional, Dict, Any
import cloudscraper
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Advanced browser automation imports
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# SeleniumBase imports (UC Mode)
try:
    from seleniumbase import SB, Driver
    SELENIUMBASE_AVAILABLE = True
except ImportError:
    SELENIUMBASE_AVAILABLE = False

# Undetected ChromeDriver imports
try:
    import undetected_chromedriver as uc
    UNDETECTED_CHROME_AVAILABLE = True
except ImportError:
    UNDETECTED_CHROME_AVAILABLE = False

from .utils import get_user_agent, is_valid_claude_share_url


class RateLimiter:
    """Simple rate limiter to avoid overwhelming servers."""
    
    def __init__(self, min_delay: float = 1.0, max_delay: float = 3.0):
        """
        Initialize rate limiter.
        
        Args:
            min_delay: Minimum delay between requests in seconds
            max_delay: Maximum delay between requests in seconds
        """
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.last_request = 0.0
    
    def wait(self) -> None:
        """Wait appropriate amount of time before next request."""
        now = time.time()
        elapsed = now - self.last_request
        delay = random.uniform(self.min_delay, self.max_delay)
        
        if elapsed < delay:
            time.sleep(delay - elapsed)
        
        self.last_request = time.time()


class ClaudeShareScraper:
    """Scraper for Claude.ai share URLs with robust error handling and rate limiting."""
    
    def __init__(self, rate_limit_delay: tuple = (1.0, 3.0), timeout: int = 30, 
                 max_retries: int = 3, backoff_factor: float = 0.3):
        """
        Initialize scraper.
        
        Args:
            rate_limit_delay: Tuple of (min_delay, max_delay) for rate limiting
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            backoff_factor: Backoff factor for retries
        """
        self.rate_limiter = RateLimiter(*rate_limit_delay)
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        
        # Configure cloudscraper session - no additional adapters needed
        self.session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin', 
                'desktop': True
            }
        )
        
        # Cloudscraper handles anti-bot measures internally
        # Do not add custom adapters or headers as they can interfere
    
    def _establish_session(self) -> tuple[bool, str]:
        """
        Establish a session with Claude.ai by visiting the main page first.
        This helps get past Cloudflare protection.
        
        Returns:
            Tuple of (success, error_message)
        """
        try:
            # First visit claude.ai main page to get cookies
            main_page_response = self.session.get(
                'https://claude.ai/', 
                timeout=self.timeout
            )
            
            # Small delay to look more human-like
            time.sleep(random.uniform(1, 3))
            
            if main_page_response.status_code == 200:
                return True, ""
            else:
                return False, f"HTTP {main_page_response.status_code}: {main_page_response.reason}"
        except Exception as e:
            return False, f"Exception: {str(e)}"

    def fetch_conversation(self, url: str) -> Dict[str, Any]:
        """
        Fetch conversation from Claude share URL.
        
        Args:
            url: Claude.ai share URL
            
        Returns:
            Dictionary containing:
                - success: bool
                - html_content: str (if successful)
                - error: str (if failed)
                - status_code: int
                - headers: dict
        """
        # Validate URL
        if not is_valid_claude_share_url(url):
            return {
                'success': False,
                'error': 'Invalid Claude.ai share URL',
                'status_code': None,
                'html_content': None,
                'headers': {}
            }
        
        # Apply rate limiting
        self.rate_limiter.wait()
        
        try:
            # Implement custom retry logic for cloudscraper
            for attempt in range(self.max_retries + 1):
                try:
                    # First visit to any Cloudflare site may take ~5 seconds
                    if attempt == 0:
                        # Visit main page first for session establishment
                        self.session.get('https://claude.ai/', timeout=30)  # Longer timeout for first visit
                        time.sleep(random.uniform(2, 4))  # Allow Cloudflare processing
                    
                    # Get the share URL
                    response = self.session.get(url, timeout=self.timeout)
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    if attempt == self.max_retries:
                        raise e  # Final attempt failed
                    # Wait before retry
                    time.sleep(self.backoff_factor * (2 ** attempt))
            
            result = {
                'success': response.status_code == 200,
                'status_code': response.status_code,
                'headers': dict(response.headers),
                'html_content': response.text if response.status_code == 200 else None,
                'error': None
            }
            
            if response.status_code != 200:
                result['error'] = f"HTTP {response.status_code}: {response.reason}"
            
            return result
            
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': f'Request timeout after {self.timeout} seconds',
                'status_code': None,
                'html_content': None,
                'headers': {}
            }
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': 'Connection error - check internet connection',
                'status_code': None,
                'html_content': None,
                'headers': {}
            }
        except requests.exceptions.TooManyRedirects:
            return {
                'success': False,
                'error': 'Too many redirects',
                'status_code': None,
                'html_content': None,
                'headers': {}
            }
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'Request error: {str(e)}',
                'status_code': None,
                'html_content': None,
                'headers': {}
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'status_code': None,
                'html_content': None,
                'headers': {}
            }
    
    def fetch_multiple_conversations(self, urls: list) -> Dict[str, Dict[str, Any]]:
        """
        Fetch multiple conversations from Claude share URLs.
        
        Args:
            urls: List of Claude.ai share URLs
            
        Returns:
            Dictionary mapping URL to fetch result
        """
        results = {}
        
        for i, url in enumerate(urls):
            print(f"Fetching {i+1}/{len(urls)}: {url}")
            result = self.fetch_conversation(url)
            results[url] = result
            
            if result['success']:
                print(f" Successfully fetched conversation")
            else:
                print(f" Failed: {result['error']}")
        
        return results
    
    def check_url_accessibility(self, url: str) -> Dict[str, Any]:
        """
        Check if a Claude share URL is accessible without downloading full content.
        
        Args:
            url: Claude.ai share URL
            
        Returns:
            Dictionary with accessibility info
        """
        if not is_valid_claude_share_url(url):
            return {
                'accessible': False,
                'error': 'Invalid Claude.ai share URL',
                'status_code': None
            }
        
        self.rate_limiter.wait()
        
        try:
            # Use HEAD request to check accessibility
            response = self.session.head(url, timeout=self.timeout)
            
            return {
                'accessible': response.status_code == 200,
                'status_code': response.status_code,
                'error': None if response.status_code == 200 else f"HTTP {response.status_code}",
                'headers': dict(response.headers)
            }
            
        except requests.exceptions.RequestException as e:
            return {
                'accessible': False,
                'error': str(e),
                'status_code': None,
                'headers': {}
            }
    
    def fetch_conversation_with_browser(self, url: str) -> Dict[str, Any]:
        """
        Fetch conversation using Selenium browser to handle JavaScript rendering.
        
        Args:
            url: Claude.ai share URL
            
        Returns:
            Dictionary containing response data
        """
        if not SELENIUM_AVAILABLE:
            return {
                'success': False,
                'error': 'Selenium not available. Install with: uv add selenium webdriver-manager',
                'status_code': None,
                'html_content': None,
                'headers': {}
            }
        
        if not is_valid_claude_share_url(url):
            return {
                'success': False,
                'error': 'Invalid Claude.ai share URL',
                'status_code': None,
                'html_content': None,
                'headers': {}
            }
        
        driver = None
        try:
            # Configure Chrome options for better Cloudflare bypass
            chrome_options = Options()
            # Don't run headless - some detection systems flag headless browsers
            # chrome_options.add_argument('--headless')  # Commented out for now
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # More realistic browser profile
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-plugins-discovery')
            chrome_options.add_argument('--start-maximized')
            chrome_options.add_argument('--window-size=1920,1080')
            
            # Use a more realistic user agent
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
            
            # Disable various automation indicators
            chrome_options.add_argument('--disable-automation')
            chrome_options.add_argument('--disable-infobars')
            chrome_options.add_argument('--disable-browser-side-navigation')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--no-first-run')
            chrome_options.add_argument('--disable-default-apps')
            
            # Initialize driver
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Execute script to remove webdriver property and other automation indicators
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
            driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
            
            # First visit Claude.ai main page to establish session
            print("Visiting claude.ai main page...")
            driver.get('https://claude.ai/')
            time.sleep(random.uniform(3, 6))  # Random wait like a human
            
            # Navigate to the share URL
            print(f"Navigating to share URL...")
            driver.get(url)
            
            # Longer wait for heavy JavaScript apps like Claude.ai
            wait = WebDriverWait(driver, 60)  # Increased from 30 to 60 seconds
            
            # First, wait for the loading spinner to disappear
            try:
                # Wait for loading spinner to be gone
                wait.until_not(EC.presence_of_element_located((By.CSS_SELECTOR, '.animate-spin')))
                print("Loading spinner disappeared")
            except:
                # Spinner might not be present or might have different class
                pass
            
            # Look for actual conversation content patterns
            content_indicators = [
                # Text patterns that indicate conversation content
                "//*[contains(text(), 'Human') or contains(text(), 'Claude') or contains(text(), 'Assistant')]",
                # Common conversation UI patterns
                "[data-testid*='message']",
                "[class*='message']",
                "[class*='conversation']",
                # Try to find any significant text content (not just loading UI)
                "//*[string-length(normalize-space(text())) > 50]"
            ]
            
            content_found = False
            for indicator in content_indicators:
                try:
                    if indicator.startswith("//"):
                        # XPath selector
                        element = wait.until(EC.presence_of_element_located((By.XPATH, indicator)))
                    else:
                        # CSS selector
                        element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, indicator)))
                    
                    # Additional check: make sure we have substantial content
                    if element and len(element.text.strip()) > 20:
                        content_found = True
                        print(f"Found content with: {indicator}")
                        break
                except:
                    continue
            
            # Give content time to fully load
            print("Waiting for content to fully render...")
            time.sleep(15)  # Give substantial time for JS to execute
            
            # Simple scroll to bottom and back to trigger any lazy loading
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(2)
            except Exception as e:
                print(f"Scroll error (non-fatal): {e}")
                # Continue even if scrolling fails
            
            # Get the fully rendered HTML with error handling
            try:
                html_content = driver.page_source
                print(f"Successfully retrieved {len(html_content)} characters of HTML")
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Failed to get page source: {str(e)}',
                    'status_code': None,
                    'html_content': None,
                    'headers': {}
                }
            
            # Quick validation - check if we actually have conversation content
            if 'animate-spin' in html_content and len(html_content) < 50000:
                # Likely still showing loading page
                return {
                    'success': False,
                    'error': 'Page still loading - content not fully rendered',
                    'status_code': None,
                    'html_content': html_content,  # Include it for debugging
                    'headers': {}
                }
                
            # Check for Cloudflare challenge page indicators
            cloudflare_indicators = [
                'Just a moment...',
                'checking if the site connection is secure',
                'needs to review the security of your connection',
                'Enable JavaScript and cookies to continue',
                'cf-browser-verification'
            ]
            
            content_lower = html_content.lower()
            for indicator in cloudflare_indicators:
                if indicator.lower() in content_lower:
                    return {
                        'success': False,
                        'error': f'Cloudflare challenge detected: {indicator}',
                        'status_code': None,
                        'html_content': html_content,
                        'headers': {}
                    }
            
            return {
                'success': True,
                'status_code': 200,
                'html_content': html_content,
                'headers': {},
                'error': None
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Browser error: {str(e)}',
                'status_code': None,
                'html_content': None,
                'headers': {}
            }
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    print(f"Error closing browser (non-fatal): {e}")
                    # Try force kill if normal quit fails
                    try:
                        driver.service.process.terminate()
                    except:
                        pass
    
    def fetch_conversation_with_seleniumbase_uc(self, url: str) -> Dict[str, Any]:
        """
        Fetch conversation using SeleniumBase UC Mode for advanced Cloudflare bypass.
        
        Args:
            url: Claude.ai share URL
            
        Returns:
            Dictionary containing response data
        """
        if not SELENIUMBASE_AVAILABLE:
            return {
                'success': False,
                'error': 'SeleniumBase not available. Install with: uv add seleniumbase',
                'status_code': None,
                'html_content': None,
                'headers': {}
            }
        
        if not is_valid_claude_share_url(url):
            return {
                'success': False,
                'error': 'Invalid Claude.ai share URL',
                'status_code': None,
                'html_content': None,
                'headers': {}
            }
        
        print("Using SeleniumBase UC Mode for advanced Cloudflare bypass...")
        
        try:
            with SB(uc=True, headless=False, test=True, xvfb=False) as sb:
                # Visit Claude.ai main page first
                print("Establishing session with Claude.ai...")
                sb.uc_open_with_reconnect("https://claude.ai/", 4)
                sb.sleep(random.uniform(2, 5))
                
                # Navigate to the share URL
                print("Loading share URL with UC reconnect...")
                sb.uc_open_with_reconnect(url, 6)  # Wait up to 6 seconds for reconnect
                
                # Wait for content to load - try multiple strategies
                content_loaded = False
                
                # Strategy 1: Look for specific conversation elements
                conversation_selectors = [
                    '[data-testid*="message"]',
                    '[class*="message"]',
                    '[class*="conversation"]',
                    'main'
                ]
                
                for selector in conversation_selectors:
                    try:
                        if sb.is_element_present(selector, timeout=10):
                            content_loaded = True
                            print(f"Content detected with selector: {selector}")
                            break
                    except:
                        continue
                
                # Strategy 2: Wait for page stability (no loading spinners)
                try:
                    # Wait for loading spinners to disappear
                    if sb.is_element_present('.animate-spin', timeout=2):
                        print("Waiting for loading spinner to disappear...")
                        sb.wait_for_element_not_visible('.animate-spin', timeout=30)
                except:
                    pass  # Spinner might not be present
                
                # Strategy 3: Wait for substantial page content
                sb.sleep(10)  # Give time for JavaScript to fully execute
                
                # Check for Cloudflare challenges and handle them
                cloudflare_indicators = [
                    'Just a moment...',
                    'Checking if the site connection is secure',
                    'Enable JavaScript and cookies to continue'
                ]
                
                page_text = sb.get_text('body').lower()
                for indicator in cloudflare_indicators:
                    if indicator.lower() in page_text:
                        print(f"Detected Cloudflare challenge: {indicator}")
                        # Try the GUI click captcha method
                        try:
                            sb.uc_gui_click_captcha()
                            sb.sleep(5)  # Wait after solving
                            print("Attempted to solve Cloudflare challenge")
                        except:
                            print("Could not solve Cloudflare challenge automatically")
                
                # Scroll to trigger any lazy loading
                try:
                    sb.scroll_to_bottom()
                    sb.sleep(2)
                    sb.scroll_to_top()
                    sb.sleep(1)
                except:
                    pass  # Continue if scrolling fails
                
                # Get the fully rendered HTML
                html_content = sb.get_page_source()
                print(f"Successfully retrieved {len(html_content)} characters with SeleniumBase UC Mode")
                
                # Final validation
                if any(indicator.lower() in html_content.lower() for indicator in cloudflare_indicators):
                    return {
                        'success': False,
                        'error': 'Cloudflare challenge not bypassed with UC Mode',
                        'status_code': None,
                        'html_content': html_content,
                        'headers': {}
                    }
                
                return {
                    'success': True,
                    'status_code': 200,
                    'html_content': html_content,
                    'headers': {},
                    'error': None
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'SeleniumBase UC Mode error: {str(e)}',
                'status_code': None,
                'html_content': None,
                'headers': {}
            }
    
    def fetch_conversation_with_undetected_chrome(self, url: str) -> Dict[str, Any]:
        """
        Fetch conversation using undetected-chromedriver for stealth browsing.
        
        Args:
            url: Claude.ai share URL
            
        Returns:
            Dictionary containing response data
        """
        if not UNDETECTED_CHROME_AVAILABLE:
            return {
                'success': False,
                'error': 'Undetected ChromeDriver not available. Install with: uv add undetected-chromedriver',
                'status_code': None,
                'html_content': None,
                'headers': {}
            }
        
        if not is_valid_claude_share_url(url):
            return {
                'success': False,
                'error': 'Invalid Claude.ai share URL',
                'status_code': None,
                'html_content': None,
                'headers': {}
            }
        
        print("Using undetected-chromedriver for stealth browsing...")
        
        driver = None
        try:
            # Configure undetected ChromeDriver options
            options = uc.ChromeOptions()
            
            # Use realistic window size
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            
            # Disable some automation indicators
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-extensions')
            
            # Don't use headless mode - it's more detectable
            # options.add_argument('--headless')  # Keep commented
            
            # Initialize undetected ChromeDriver
            driver = uc.Chrome(options=options, version_main=None)  # Auto-detect Chrome version
            
            # Set realistic viewport
            driver.set_window_size(1920, 1080)
            
            # Visit Claude.ai main page first to establish session
            print("Establishing session with Claude.ai...")
            driver.get("https://claude.ai/")
            time.sleep(random.uniform(3, 6))
            
            # Navigate to share URL
            print("Loading share URL...")
            driver.get(url)
            
            # Wait for content to load
            wait = WebDriverWait(driver, 60)
            
            # Look for content indicators
            content_indicators = [
                (By.CSS_SELECTOR, '[data-testid*="message"]'),
                (By.CSS_SELECTOR, '[class*="message"]'),
                (By.CSS_SELECTOR, 'main'),
                (By.XPATH, "//*[string-length(normalize-space(text())) > 50]")
            ]
            
            content_found = False
            for by_method, selector in content_indicators:
                try:
                    element = wait.until(EC.presence_of_element_located((by_method, selector)))
                    if element and len(element.text.strip()) > 20:
                        content_found = True
                        print(f"Content found with: {selector}")
                        break
                except:
                    continue
            
            # Wait for loading to complete
            print("Waiting for page to fully load...")
            time.sleep(15)
            
            # Scroll to trigger lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)
            
            # Get HTML content
            html_content = driver.page_source
            print(f"Retrieved {len(html_content)} characters with undetected-chromedriver")
            
            # Check for Cloudflare challenges
            cloudflare_indicators = [
                'Just a moment...',
                'checking if the site connection is secure',
                'needs to review the security of your connection',
                'Enable JavaScript and cookies to continue'
            ]
            
            content_lower = html_content.lower()
            for indicator in cloudflare_indicators:
                if indicator.lower() in content_lower:
                    return {
                        'success': False,
                        'error': f'Cloudflare challenge detected with undetected-chrome: {indicator}',
                        'status_code': None,
                        'html_content': html_content,
                        'headers': {}
                    }
            
            return {
                'success': True,
                'status_code': 200,
                'html_content': html_content,
                'headers': {},
                'error': None
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Undetected ChromeDriver error: {str(e)}',
                'status_code': None,
                'html_content': None,
                'headers': {}
            }
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    print(f"Error closing undetected browser (non-fatal): {e}")
    
    def fetch_conversation_advanced(self, url: str) -> Dict[str, Any]:
        """
        Advanced fetch with multiple bypass methods in fallback order.
        Tries methods from most to least sophisticated.
        
        Args:
            url: Claude.ai share URL
            
        Returns:
            Dictionary containing response data
        """
        methods = [
            ('SeleniumBase UC Mode', self.fetch_conversation_with_seleniumbase_uc),
            ('Undetected ChromeDriver', self.fetch_conversation_with_undetected_chrome),
            ('Enhanced Browser (Selenium)', self.fetch_conversation_with_browser),
            ('Cloudscraper', self.fetch_conversation)
        ]
        
        print(f"Trying {len(methods)} bypass methods...")
        
        for method_name, method_func in methods:
            print(f"\nAttempting {method_name}...")
            
            try:
                result = method_func(url)
                
                if result['success']:
                    print(f"✅ {method_name} succeeded!")
                    return result
                else:
                    print(f"❌ {method_name} failed: {result['error']}")
                    
            except Exception as e:
                print(f"❌ {method_name} crashed: {str(e)}")
                continue
        
        return {
            'success': False,
            'error': 'All bypass methods failed',
            'status_code': None,
            'html_content': None,
            'headers': {}
        }
    
    def close(self) -> None:
        """Close the session."""
        if self.session:
            self.session.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()