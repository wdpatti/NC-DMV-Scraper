import asyncio
import threading
import time
import random
import requests
import os
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException
from geopy.distance import distance as geopy_distance
from geopy.geocoders import Nominatim
from decimal import Decimal
from datetime import datetime, timedelta, time as dt_time, date
import calendar
from collections import OrderedDict

# Optional async imports (fallback to sync if not available)
try:
    import aiohttp
    ASYNC_AVAILABLE = True
except ImportError:
    ASYNC_AVAILABLE = False
    print("⚠️  aiohttp not available, using synchronous notifications")

# --- OPTIMIZED Configuration ---

YOUR_DISCORD_WEBHOOK_URL = os.getenv("YOUR_DISCORD_WEBHOOK_URL", "YOUR_WEBHOOK_URL_HERE")
GECKODRIVER_PATH = os.getenv('GECKODRIVER_PATH','YOUR_GECKODRIVER_PATH_HERE')
SIGNAL_NUMBER = os.getenv("SIGNAL_NUMBER")
SIGNAL_GROUP = os.getenv("SIGNAL_GROUP")

YOUR_ADDRESS = os.getenv("YOUR_ADDRESS")
DISTANCE_RANGE_MILES_STR = os.getenv("DISTANCE_RANGE")

if os.path.isfile("/app/ncdot_locations_coordinates_only.json"):
    LOCATION_DATA_FILE = "/app/ncdot_locations_coordinates_only.json"
elif os.path.isfile("ncdot_locations_coordinates_only.json"):
    LOCATION_DATA_FILE = "ncdot_locations_coordinates_only.json"
else:
    print("Location data file not set, please set one")

APPOINTMENT_TYPE = os.getenv("APPOINTMENT_TYPE", "Driver License - First Time")

# Date/Time filtering env vars
DATE_RANGE_START_STR = os.getenv("DATE_RANGE_START")
DATE_RANGE_END_STR = os.getenv("DATE_RANGE_END")
DATE_RANGE_RELATIVE_STR = os.getenv("DATE_RANGE")
TIME_RANGE_START_STR = os.getenv("TIME_RANGE_START")
TIME_RANGE_END_STR = os.getenv("TIME_RANGE_END")

if GECKODRIVER_PATH == 'YOUR_GECKODRIVER_PATH_HERE':
    print("Please set your geckodriver path in scrapedmv.py. If you do not know how, please look at the readme.")
    exit()

# 🚀 OPTIMIZATION SETTINGS - Maximum Speed Configuration
BASE_INTERVAL_SECONDS = int(os.getenv('BASE_INTERVAL_SECONDS', 20))  # Faster scanning
MIN_RANDOM_DELAY_SECONDS = 0  # No delay for maximum speed
MAX_RANDOM_DELAY_SECONDS = 2  # Minimal random delay
NCDOT_APPOINTMENT_URL = "https://skiptheline.ncdot.gov"
MAX_DISCORD_MESSAGE_LENGTH = 1950

# 🔥 PERFORMANCE OPTIMIZATION FLAGS
INSTANT_NOTIFICATIONS = True    # Send notifications in background threads
PERSISTENT_BROWSER = True       # Keep browser alive between runs  
EARLY_EXIT_ENABLED = True       # Stop immediately when appointment found
REDUCED_TIMEOUTS = True         # Use faster timeouts
SMART_LOCATION_SORTING = True   # Process closest locations first
LIMIT_DATE_PROCESSING = True    # Limit dates processed per location for speed

PROOF_OF_LIFE = False
if os.getenv("PROOF_OF_LIFE") == "True" or os.getenv("PROOF_OF_LIFE") == True:
    PROOF_OF_LIFE = True

INTRO_MESSAGE = os.getenv("INTRO_MESSAGE", f"🚨 URGENT: Appointments found at {NCDOT_APPOINTMENT_URL}:\n")

FIREFOX_BINARY_PATH = os.getenv("FIREFOX_BINARY_PATH")
if not FIREFOX_BINARY_PATH and os.path.isfile("C:/Program Files/Mozilla Firefox/firefox.exe"):
    FIREFOX_BINARY_PATH = "C:/Program Files/Mozilla Firefox/firefox.exe"

# Global optimization variables
persistent_driver = None
cached_locations_data = None
first_appointment_found = False
scan_start_time = None

# --- 🚀 OPTIMIZED FUNCTIONS ---

def parse_datetime_filters(start_date_str, end_date_str, relative_range_str, start_time_str, end_time_str):
    """Optimized datetime filter parsing"""
    date_filter_active = False
    start_date = None
    end_date = None
    time_filter_active = False
    start_time = None
    end_time = None
    today = datetime.now().date()

    try:
        if relative_range_str:
            relative_range_str = relative_range_str.lower().strip()
            num = int(relative_range_str[:-1])
            unit = relative_range_str[-1]
            if num <= 0:
                raise ValueError("DATE_RANGE number must be positive.")
            start_date = today
            if unit == 'd':
                end_date = today + timedelta(days=num)
            elif unit == 'w':
                end_date = today + timedelta(weeks=num)
            elif unit == 'm':
                current_year, current_month, current_day = today.year, today.month, today.day
                total_months_offset = current_month + num
                year_offset = (total_months_offset - 1) // 12
                target_year = current_year + year_offset
                target_month = (total_months_offset - 1) % 12 + 1
                _, days_in_target_month = calendar.monthrange(target_year, target_month)
                target_day = min(current_day, days_in_target_month)
                end_date = date(target_year, target_month, target_day)
            else:
                raise ValueError(f"Invalid DATE_RANGE unit: '{unit}'. Use 'd', 'w', or 'm'.")
            
            date_filter_active = True
            
        elif start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, "%m/%d/%Y").date()
            end_date = datetime.strptime(end_date_str, "%m/%d/%Y").date()
            if start_date > end_date:
                raise ValueError("DATE_RANGE_START cannot be after DATE_RANGE_END.")
            date_filter_active = True
    except Exception as e:
        print(f"Date filtering disabled: {e}")
        date_filter_active = False
        start_date = None
        end_date = None

    try:
        if start_time_str and end_time_str:
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.strptime(end_time_str, "%H:%M").time()
            time_filter_active = True
    except Exception as e:
        print(f"Time filtering disabled: {e}")
        time_filter_active = False
        start_time = None
        end_time = None

    return date_filter_active, start_date, end_date, time_filter_active, start_time, end_time


def get_filtered_locations_optimized(your_address, distance_range_str, location_file):
    """Optimized location filtering with caching and distance sorting"""
    global cached_locations_data
    
    try:
        if not (your_address and distance_range_str):
            return None, False
        distance_range_miles = Decimal(distance_range_str)
        if distance_range_miles <= 0:
            raise ValueError("Distance range must be positive.")
    except Exception as e:
        print(f"Distance filtering disabled: {e}")
        return None, False

    # Load and cache location data
    if cached_locations_data is None:
        try:
            with open(location_file, 'r') as f:
                cached_locations_data = json.load(f)
            print(f"📍 Cached location data from {location_file}")
        except Exception as e:
            print(f"Error loading location data: {e}")
            return None, False

    try:
        geolocator = Nominatim(user_agent="dmv_scraper_optimized")
        user_location = geolocator.geocode(your_address, timeout=5)  # Reduced timeout
        if not user_location:
            raise ValueError("Could not geocode YOUR_ADDRESS")
        user_coords = (user_location.latitude, user_location.longitude)
    except Exception as e:
        print(f"Geocoding error: {e}")
        return None, False

    # Sort locations by distance for prioritized processing
    if SMART_LOCATION_SORTING:
        location_distances = []
        for item in cached_locations_data:
            try:
                location_address = item["address"] 
                location_coords = item["coordinates"]
                if len(location_coords) != 2:
                    continue
                dist = geopy_distance(user_coords, tuple(location_coords)).miles
                if Decimal(dist) <= distance_range_miles:
                    location_distances.append((location_address, float(dist)))
            except Exception:
                continue

        # Sort by distance (closest first for faster detection)
        location_distances.sort(key=lambda x: x[1])
        allowed_locations = OrderedDict((addr, dist) for addr, dist in location_distances)
        print(f"📍 Found {len(allowed_locations)} locations, sorted by distance")
        return allowed_locations, True
    else:
        # Original behavior
        allowed_locations = set()
        for item in cached_locations_data:
            try:
                location_address = item["address"] 
                location_coords = item["coordinates"]
                if len(location_coords) != 2:
                    continue
                dist = geopy_distance(user_coords, tuple(location_coords)).miles
                if Decimal(dist) <= distance_range_miles:
                    allowed_locations.add(location_address)
            except Exception:
                continue 

        print(f"📍 Found {len(allowed_locations)} locations within range")
        return allowed_locations, True


# --- 🚀 OPTIMIZED NOTIFICATION SYSTEM ---

async def send_notification_async(webhook_url, message_content):
    """Async notification sending for maximum speed"""
    if not ASYNC_AVAILABLE or not webhook_url or webhook_url == "YOUR_WEBHOOK_URL_HERE":
        return

    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if message_content is None:
                if PROOF_OF_LIFE:
                    await session.post(webhook_url, json={"content": "No appointments found"})
                return

            full_message = INTRO_MESSAGE + message_content
            
            if "https://ntfy.sh/" in webhook_url:
                await session.post(webhook_url, data=full_message, headers={"Markdown": "yes"})
            else:
                payload = {
                    "number": SIGNAL_NUMBER,
                    "message": full_message,
                    "recipients": [SIGNAL_GROUP]
                }
                await session.post(webhook_url, json=payload)
                
        print("⚡ Async notification sent!")
    except Exception as e:
        print(f"Async notification error: {e}")


def send_notification_threaded(webhook_url, message_content, is_urgent=False):
    """Send notification in background thread - NEVER BLOCKS SCANNING!"""
    
    def send_notification_sync():
        try:
            if not webhook_url or webhook_url == "YOUR_WEBHOOK_URL_HERE":
                return

            if message_content is None:
                if PROOF_OF_LIFE:
                    requests.post(webhook_url, json={"content": "No appointments found"}, timeout=5)
                return

            full_message = INTRO_MESSAGE + message_content

            # Try async first, fallback to sync
            if ASYNC_AVAILABLE:
                try:
                    asyncio.run(send_notification_async(webhook_url, message_content))
                    return
                except Exception:
                    pass  # Fall back to sync

            # Synchronous fallback
            if "https://ntfy.sh/" in webhook_url:
                requests.post(webhook_url, data=full_message, timeout=5, headers={"Markdown": "yes"})
            else:
                payload = {
                    "number": SIGNAL_NUMBER,
                    "message": full_message,
                    "recipients": [SIGNAL_GROUP]
                }
                requests.post(webhook_url, json=payload, timeout=5)
            
            status = "🚨 URGENT" if is_urgent else "📤"
            print(f"{status} Notification sent in background!")
            
        except Exception as e:
            print(f"Notification error: {e}")

    if INSTANT_NOTIFICATIONS:
        # Send in background thread - NEVER BLOCKS!
        thread = threading.Thread(target=send_notification_sync, daemon=True)
        thread.start()
        return thread
    else:
        # Fallback to blocking send
        send_notification_sync()


def send_discord_notification(webhook_url, message_content):
    """Optimized notification dispatcher"""
    return send_notification_threaded(webhook_url, message_content)


# --- 🚀 OPTIMIZED BROWSER MANAGEMENT ---

def create_optimized_driver():
    """Create browser with maximum speed optimizations"""
    try:
        print("🚀 Creating optimized Firefox driver...")
        firefox_options = Options()
        firefox_options.add_argument("--headless")
        
        # AGGRESSIVE PERFORMANCE OPTIMIZATIONS
        if REDUCED_TIMEOUTS:
            firefox_options.set_preference("dom.max_script_run_time", 10)
            firefox_options.set_preference("dom.max_chrome_script_run_time", 10)
            
        # Disable unnecessary features for speed
        firefox_options.set_preference("browser.cache.disk.enable", False)
        firefox_options.set_preference("browser.cache.memory.enable", False)
        firefox_options.set_preference("media.autoplay.enabled", False)
        firefox_options.set_preference("permissions.default.image", 2)  # Disable images
        
        # Network optimizations
        firefox_options.set_preference("network.http.max-connections", 10)
        firefox_options.set_preference("network.http.max-connections-per-server", 8)
        
        # Geolocation setup (optimized)
        if YOUR_ADDRESS:
            try:
                geolocator = Nominatim(user_agent="dmv_scraper_optimized")
                location = geolocator.geocode(YOUR_ADDRESS, timeout=5)
                if location:
                    lat, lon = location.latitude, location.longitude
                    firefox_options.set_preference("geo.enabled", True)
                    firefox_options.set_preference("geo.provider.network.url", 
                        f"data:application/json,{{\"location\": {{\"lat\": {lat}, \"lng\": {lon}}}, \"accuracy\": 27000.0}}")
                else:
                    firefox_options.set_preference("geo.enabled", False)
            except Exception:
                firefox_options.set_preference("geo.enabled", False)
        else:
            firefox_options.set_preference("geo.enabled", False)
            
        if FIREFOX_BINARY_PATH:
            firefox_options.binary_location = FIREFOX_BINARY_PATH
            
        service = FirefoxService(executable_path=GECKODRIVER_PATH)
        driver = webdriver.Firefox(service=service, options=firefox_options)
        
        # Optimized timeouts
        if REDUCED_TIMEOUTS:
            driver.implicitly_wait(1)      # Reduced from 2
            driver.set_page_load_timeout(45)  # Reduced from 90
        else:
            driver.implicitly_wait(2)
            driver.set_page_load_timeout(90)
            
        print("✅ Optimized driver ready!")
        return driver
        
    except Exception as e:
        print(f"❌ Driver creation failed: {e}")
        return None


def get_persistent_driver():
    """Get or create persistent browser - HUGE TIME SAVER!"""
    global persistent_driver
    
    if PERSISTENT_BROWSER and persistent_driver:
        try:
            # Quick test if driver is alive
            persistent_driver.current_url
            print("♻️  Reusing persistent browser (saves 30-60 seconds!)")
            return persistent_driver
        except Exception:
            print("🔄 Persistent driver died, creating new one...")
            persistent_driver = None
    
    persistent_driver = create_optimized_driver()
    return persistent_driver


def cleanup_persistent_driver():
    """Cleanup persistent driver"""
    global persistent_driver
    if persistent_driver:
        try:
            persistent_driver.quit()
        except Exception:
            pass
        persistent_driver = None

# --- 🚀 OPTIMIZED HELPER FUNCTIONS ---

class options_loaded_in_select(object):
    def __init__(self, locator):
        self.locator = locator

    def __call__(self, driver):
        try:
            select_element = driver.find_element(*self.locator)
            if not select_element.is_enabled():
                return False
            options = select_element.find_elements(By.TAG_NAME, "option")
            if len(options) > 1 and options[1].get_attribute("data-datetime"):
                return True
            return False
        except NoSuchElementException:
            return False


def format_results_for_discord_optimized(raw_results):
    """Optimized result formatting with limits for faster notifications"""
    if not raw_results:
        return None
        
    message_lines = []
    found_valid_times = False
    
    for location, result in raw_results.items():
        if isinstance(result, list) and result:
            message_lines.append(f"\n**📍 {location}**")
            # Limit to first 3 appointments for faster notifications
            for dt_str in result[:3]:
                message_lines.append(f"⏰ {dt_str}")
            if len(result) > 3:
                message_lines.append(f"... and {len(result) - 3} more!")
            found_valid_times = True

    return "\n".join(message_lines) if found_valid_times else None


def format_results_for_discord(raw_results):
    """Legacy function for compatibility"""
    return format_results_for_discord_optimized(raw_results)


def parse_datetime_for_sort(datetime_str):
    """Optimized datetime parsing for sorting"""
    try:
        return datetime.strptime(datetime_str, "%m/%d/%Y %I:%M:%S %p")
    except ValueError:
        return datetime.max


def wait_for_options_in_select(driver, locator, timeout=20):  # Reduced default timeout
    """Optimized wait function with faster polling"""
    start_wait = time.time()
    while time.time() - start_wait < timeout:
        try:
            select_element = driver.find_element(*locator)
            options = select_element.find_elements(By.TAG_NAME, "option")
            if len(options) > 1:
                return select_element
        except Exception:
            pass
        time.sleep(0.2)  # Faster polling
    return None


def fast_wait_for_element(driver, locator, timeout=10):
    """Fast element waiting with shorter timeouts"""
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(locator)
        )
    except TimeoutException:
        return None

# --- 🚀 MAIN OPTIMIZED EXTRACTION FUNCTION ---

def extract_times_for_all_locations_firefox(
    url, driver_path, binary_path,
    allowed_locations_filter, filtering_active,
    date_filter_enabled, start_date, end_date,
    time_filter_enabled, start_time, end_time,
    user_address=None
):
    """Ultra-optimized extraction with all performance improvements"""
    global first_appointment_found, scan_start_time
    first_appointment_found = False
    scan_start_time = time.time()
    
    driver = get_persistent_driver()
    if driver is None:
        return {}, False

    raw_location_results = {}
    start_run_time_str = time.strftime('%H:%M:%S')

    try:
        print(f"🚀 [{start_run_time_str}] Starting optimized scan...")
        
        # Navigate to site with optimized timeouts
        driver.get(url)

        try:
            timeout = 60 if REDUCED_TIMEOUTS else 90
            make_appointment_button = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.ID, "cmdMakeAppt"))
            )
            make_appointment_button.click()
        except Exception as e:
            print(f"❌ Make appointment button error: {e}")
            return {}, False

        try:
            first_layer_button_xpath = f"//div[contains(@class, 'QflowObjectItem') and .//div[contains(text(), '{APPOINTMENT_TYPE}')]]"
            time.sleep(1)  # Reduced from 2
            timeout = 30 if REDUCED_TIMEOUTS else 50
            first_layer_button = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, first_layer_button_xpath))
            )
            first_layer_button.click()
        except Exception as e:
            print(f"❌ Appointment type button error: {e}")
            return {}, False

        # Get location buttons with optimized timeout
        timeout = 30 if REDUCED_TIMEOUTS else 45
        location_button_wait = WebDriverWait(driver, timeout)
        second_layer_button_selector = "div.QflowObjectItem.form-control.ui-selectable"

        try:
            location_button_wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, second_layer_button_selector)))
        except Exception as e:
            print(f"❌ No location buttons found: {e}")
            return {}, False

        initial_buttons = driver.find_elements(By.CSS_SELECTOR, second_layer_button_selector)
        num_initial_buttons = len(initial_buttons)
        print(f"📍 Processing {num_initial_buttons} location buttons...")

        # 🚀 MAIN LOCATION LOOP WITH ALL OPTIMIZATIONS
        for index in range(num_initial_buttons):
            # 🔥 EARLY EXIT CHECK - STOP IMMEDIATELY WHEN APPOINTMENT FOUND
            if EARLY_EXIT_ENABLED and first_appointment_found:
                print("⚡ EARLY EXIT: First appointment found, stopping scan!")
                break
                
            location_name = f"Unknown Location {index}"
            location_address_from_site = "Unknown Address"
            location_processed_successfully = False

            try:
                timeout = 10 if REDUCED_TIMEOUTS else 15
                WebDriverWait(driver, timeout).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, second_layer_button_selector)))
                location_button_elements = driver.find_elements(By.CSS_SELECTOR, second_layer_button_selector)
                
                if index >= len(location_button_elements):
                    continue

                current_button = location_button_elements[index]
                
                # Quick button validation with reduced checks
                try:
                    is_displayed = current_button.is_displayed()
                    is_enabled = current_button.is_enabled()
                    has_disabled_class = "disabled-unit" in current_button.get_attribute("class")
                    has_hover_div = len(current_button.find_elements(By.CSS_SELECTOR, "div.hover-div")) > 0
                    
                    if not is_displayed or not is_enabled or has_disabled_class or has_hover_div:
                        continue
                except Exception:
                    continue

                # Get location info
                try:
                    button_lines = current_button.text.splitlines()
                    if button_lines:
                        location_name = button_lines[0].strip()
                    address_element = current_button.find_element(By.CSS_SELECTOR, "div.form-control-child")
                    location_address_from_site = address_element.text.strip()
                    
                    # Smart location sorting check
                    if SMART_LOCATION_SORTING and isinstance(allowed_locations_filter, OrderedDict):
                        distance = allowed_locations_filter.get(location_address_from_site, 999)
                        print(f"🔍 Checking: {location_name} ({distance:.1f}mi)")
                    else:
                        print(f"🔍 Checking: {location_name}")
                except Exception:
                    pass

                # Apply filtering (optimized for OrderedDict)
                if filtering_active:
                    if isinstance(allowed_locations_filter, OrderedDict):
                        if location_address_from_site not in allowed_locations_filter:
                            continue
                    else:
                        if location_address_from_site not in allowed_locations_filter:
                            continue

                # Click location
                current_button.click()
                location_processed_successfully = True
                time.sleep(3)  # Reduced from 5

                valid_appointment_datetimes_for_location = []
                
                # Wait for datepicker with optimized timeout
                datepicker_table_selector_css = "table.ui-datepicker-calendar"
                error_locator_id = "547650da-008d-4fd0-a164-31a44e94"

                try:
                    timeout = 20 if REDUCED_TIMEOUTS else 30
                    WebDriverWait(driver, timeout).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, datepicker_table_selector_css))
                    )
                    
                    # Quick error check
                    try:
                        error_element = driver.find_element(By.ID, error_locator_id)
                        error_html = error_element.get_attribute('innerHTML')
                        if "does not currently have any appointments available" in error_html:
                            raw_location_results[location_name] = "No appointments in next 90 days"
                            continue
                    except NoSuchElementException:
                        pass

                except Exception:
                    raw_location_results[location_name] = "Datepicker Not Found"
                    continue

                # 🚀 OPTIMIZED DATE PROCESSING
                clickable_dates_selector_css = "td[data-handler='selectDay']:not(.ui-datepicker-unselectable):not(.ui-state-disabled) a.ui-state-default"
                time_select_locator = (By.ID, "6f1a7b21-2558-41bb-8e4d-2cba7a8b1608")

                try:
                    timeout = 8 if REDUCED_TIMEOUTS else 10
                    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, datepicker_table_selector_css)))
                    date_elements = driver.find_elements(By.CSS_SELECTOR, clickable_dates_selector_css)
                    num_dates = len(date_elements)

                    # 🔥 LIMIT DATE PROCESSING FOR SPEED
                    max_dates = 5 if LIMIT_DATE_PROCESSING else num_dates
                    process_dates = min(num_dates, max_dates)

                    for date_index in range(process_dates):
                        # 🚀 EARLY EXIT CHECK DURING DATE PROCESSING
                        if EARLY_EXIT_ENABLED and first_appointment_found:
                            break
                            
                        try:
                            current_date_links = driver.find_elements(By.CSS_SELECTOR, clickable_dates_selector_css)
                            if date_index >= len(current_date_links):
                                break

                            date_link_element = current_date_links[date_index]
                            date_link_element.click()

                            timeout = 15 if REDUCED_TIMEOUTS else 25
                            time_select_element = wait_for_options_in_select(driver, time_select_locator, timeout)

                            if time_select_element:
                                time_options = time_select_element.find_elements(By.TAG_NAME, "option")
                                for option in time_options[1:]:
                                    try:
                                        datetime_str = option.get_attribute("data-datetime")
                                        if not datetime_str:
                                            continue

                                        appointment_dt = datetime.strptime(datetime_str, "%m/%d/%Y %I:%M:%S %p")
                                        appointment_date = appointment_dt.date()
                                        appointment_time = appointment_dt.time()

                                        date_ok = not date_filter_enabled or (start_date <= appointment_date <= end_date)
                                        time_ok = not time_filter_enabled or (start_time <= appointment_time <= end_time)

                                        if date_ok and time_ok:
                                            valid_appointment_datetimes_for_location.append(datetime_str)
                                            
                                            # 🚨 INSTANT CRITICAL NOTIFICATION ON FIRST APPOINTMENT!
                                            if not first_appointment_found:
                                                first_appointment_found = True
                                                elapsed = time.time() - scan_start_time
                                                urgent_msg = f"🚨 FIRST APPOINTMENT DETECTED in {elapsed:.1f}s!\n**{location_name}**\n⏰ {datetime_str}\n"
                                                print("⚡ SENDING INSTANT CRITICAL ALERT!")
                                                send_notification_threaded(YOUR_DISCORD_WEBHOOK_URL, urgent_msg, is_urgent=True)
                                                
                                                # Early exit if enabled
                                                if EARLY_EXIT_ENABLED:
                                                    print("⚡ Early exit enabled - stopping after first find!")
                                                    break
                                                    
                                    except Exception:
                                        continue
                                        
                                # Break from date loop if early exit and found appointment
                                if EARLY_EXIT_ENABLED and first_appointment_found:
                                    break

                        except Exception:
                            continue

                except Exception as e:
                    raw_location_results[location_name] = "Error processing dates"

                # Store results with optimized sorting
                if valid_appointment_datetimes_for_location:
                    try:
                        valid_appointment_datetimes_for_location.sort(key=parse_datetime_for_sort)
                    except Exception:
                        pass
                    raw_location_results[location_name] = valid_appointment_datetimes_for_location
                elif location_name not in raw_location_results:
                    raw_location_results[location_name] = []

            except Exception as location_e:
                print(f"❌ Error processing location {index}: {location_e}")
                raw_location_results[location_name] = f"Error: {type(location_e).__name__}"

            finally:
                if location_processed_successfully:
                    try:
                        driver.back()
                        time.sleep(1.5)  # Reduced from 2.0
                        timeout = 15 if REDUCED_TIMEOUTS else 25
                        WebDriverWait(driver, timeout).until(
                             EC.presence_of_all_elements_located((By.CSS_SELECTOR, second_layer_button_selector))
                        )
                        time.sleep(0.3)  # Reduced from 0.5
                    except Exception:
                        pass

        total_elapsed = time.time() - scan_start_time
        print(f"✅ Scan completed in {total_elapsed:.1f} seconds")

    except Exception as e:
        print(f"💥 Major error: {e}")
        return {}, False

    return raw_location_results, True


# --- 🚀 MAIN OPTIMIZED EXECUTION ---

# Pre-calculate filters with optimized functions
allowed_locations, filtering_enabled = get_filtered_locations_optimized(YOUR_ADDRESS, DISTANCE_RANGE_MILES_STR, LOCATION_DATA_FILE)

date_filter, dt_start, dt_end, time_filter, tm_start, tm_end = parse_datetime_filters(
    DATE_RANGE_START_STR, DATE_RANGE_END_STR, DATE_RANGE_RELATIVE_STR, 
    TIME_RANGE_START_STR, TIME_RANGE_END_STR
)

if YOUR_DISCORD_WEBHOOK_URL == "YOUR_WEBHOOK_URL_HERE":
    print("⚠️  WARNING: DISCORD WEBHOOK URL IS NOT SET!")

print("🚀 ULTRA-OPTIMIZED DMV APPOINTMENT SCANNER STARTING")
print("⚡ Features: Instant notifications, persistent browser, early exit, smart sorting")
print("🎯 Early exit on first appointment found")
print("=" * 70)

consecutive_errors = 0
max_consecutive_errors = 3

while True:
    print(f"\n🔍 OPTIMIZED SCAN START: {time.strftime('%H:%M:%S')}")
    
    try:
        results, success = extract_times_for_all_locations_firefox(
            NCDOT_APPOINTMENT_URL,
            GECKODRIVER_PATH,
            FIREFOX_BINARY_PATH,
            allowed_locations,
            filtering_enabled,
            date_filter, dt_start, dt_end,
            time_filter, tm_start, tm_end,
            YOUR_ADDRESS
        )
        
        if not success:
            consecutive_errors += 1
            print(f"❌ Scan failed ({consecutive_errors}/{max_consecutive_errors})")
            if consecutive_errors >= max_consecutive_errors:
                print("🔄 Restarting browser after consecutive failures...")
                cleanup_persistent_driver()
                consecutive_errors = 0
            continue
        
        consecutive_errors = 0
        print(f"📊 Results: {results}")

        # Send comprehensive notification if not already sent urgently
        if not first_appointment_found:
            discord_message_content = format_results_for_discord_optimized(results)
            if discord_message_content:
                print("📤 Sending comprehensive results...")
                send_notification_threaded(YOUR_DISCORD_WEBHOOK_URL, discord_message_content)
            else:
                send_notification_threaded(YOUR_DISCORD_WEBHOOK_URL, None)
        else:
            print("⚡ Urgent notification already sent for first appointment!")

    except Exception as e:
        consecutive_errors += 1
        print(f"❌ Unexpected error: {e}")
        if consecutive_errors >= max_consecutive_errors:
            print("🔄 Restarting browser due to consecutive errors...")
            cleanup_persistent_driver()
            consecutive_errors = 0
        continue

    # 🚀 DYNAMIC SLEEP CALCULATION
    if first_appointment_found:
        # If we found appointments, scan more frequently
        sleep_time = max(BASE_INTERVAL_SECONDS // 2, 10)
        print(f"⚡ Found appointments - scanning faster ({sleep_time}s)")
    else:
        sleep_time = BASE_INTERVAL_SECONDS + random.randint(MIN_RANDOM_DELAY_SECONDS, MAX_RANDOM_DELAY_SECONDS)
        
    print(f"😴 Sleeping {sleep_time}s...")
    
    try:
        time.sleep(sleep_time)
    except KeyboardInterrupt:
        print("\n🛑 Stopping optimized scanner...")
        cleanup_persistent_driver()
        print("🏁 Scanner shutdown complete")
        break
