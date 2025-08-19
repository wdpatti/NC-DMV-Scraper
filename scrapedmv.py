from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException, WebDriverException
import time
import random
import requests
import os
import json
from geopy.distance import distance as geopy_distance
from geopy.geocoders import Nominatim
from decimal import Decimal
from datetime import datetime, timedelta, time as dt_time, date
import calendar

# --- Configuration ---

YOUR_DISCORD_WEBHOOK_URL = os.getenv("YOUR_DISCORD_WEBHOOK_URL", "YOUR_WEBHOOK_URL_HERE") # !!! REPLACE WITH YOUR ACTUAL WEBHOOK URL !!!
GECKODRIVER_PATH = os.getenv('GECKODRIVER_PATH','YOUR_GECKODRIVER_PATH_HERE') # Replace with your geckodriver path

SIGNAL_NUMBER = os.getenv("SIGNAL_NUMBER") # Replace with your Signal number
SIGNAL_GROUP = os.getenv("SIGNAL_GROUP") # Replace with your Signal group ID


# Can change address via environment values or manually edit this code 
# YOUR_ADDRESS = "1226 Testing Avenue, Charlotte, NC"
# DISTANCE_RANGE_MILES_STR = 25
YOUR_ADDRESS = os.getenv("YOUR_ADDRESS")
DISTANCE_RANGE_MILES_STR = os.getenv("DISTANCE_RANGE")
if os.path.isfile("/app/ncdot_locations_coordinates_only.json"):
    LOCATION_DATA_FILE = "/app/ncdot_locations_coordinates_only.json"
elif os.path.isfile("ncdot_locations_coordinates_only.json"):
    LOCATION_DATA_FILE = "ncdot_locations_coordinates_only.json"
else:
    print("Location data file not set, please set one")

APPOINTMENT_TYPE = os.getenv("APPOINTMENT_TYPE", "Teen Driver Level 2")
# APPOINTMENT_TYPE = os.getenv("APPOINTMENT_TYPE", "Motorcycle Skills Test")
# APPOINTMENT_TYPE = "Motorcycle Skills Test"
# APPOINTMENT_TYPE = os.getenv("APPOINTMENT_TYPE", "Legal Presence")
# You could also define:
# APPOINTMENT_TYPE = "Permits"
# APPOINTMENT_TYPE = "Teen Driver Level 1"
# APPOINTMENT_TYPE = "ID Card"
# etc. Just get the name off the button you want to click from skiptheline.ncdot.gov .

# Date/Time filtering env vars
# examples of syntax:
# DATE_RANGE_START_STR = "01/23/2025"
# DATE_RANGE_END_STR = "09/23/2025"
# DATE_RANGE_RELATIVE_STR = "2w"
# TIME_RANGE_START_STR = "3:00"
# TIME_RANGE_END_STR = "19:00"
DATE_RANGE_START_STR = os.getenv("DATE_RANGE_START")
DATE_RANGE_END_STR = os.getenv("DATE_RANGE_END")
DATE_RANGE_RELATIVE_STR = os.getenv("DATE_RANGE")
TIME_RANGE_START_STR = os.getenv("TIME_RANGE_START")
TIME_RANGE_END_STR = os.getenv("TIME_RANGE_END")

if GECKODRIVER_PATH == 'YOUR_GECKODRIVER_PATH_HERE':
    print("Please set your geckodriver path in scrapedmv.py. If you do not know how, please look at the readme.")
    exit()

BASE_INTERVAL_SECONDS = int(os.getenv('BASE_INTERVAL_SECONDS', 30))
MIN_RANDOM_DELAY_SECONDS = 1
MAX_RANDOM_DELAY_SECONDS = 3
NCDOT_APPOINTMENT_URL = "https://skiptheline.ncdot.gov"
MAX_DISCORD_MESSAGE_LENGTH = 1950 # Slightly less than 2000 for safety margin

# if you want it to notify you even when there are no appointments available, then set this to true
PROOF_OF_LIFE = False

if os.getenv("PROOF_OF_LIFE") == "True" or os.getenv("PROOF_OF_LIFE") == True:
    PROOF_OF_LIFE = True

INTRO_MESSAGE = os.getenv("INTRO_MESSAGE", f"Appointments available at {NCDOT_APPOINTMENT_URL}:\n")

# dont need to set this unless you get error
FIREFOX_BINARY_PATH = os.getenv("FIREFOX_BINARY_PATH")
if not FIREFOX_BINARY_PATH and os.path.isfile("C:/Program Files/Mozilla Firefox/firefox.exe"):
    FIREFOX_BINARY_PATH = "C:/Program Files/Mozilla Firefox/firefox.exe"

# --- End Configuration ---

def is_driver_healthy(driver):
    """Check if the webdriver is still healthy and responsive."""
    if driver is None:
        return False
    try:
        # Try to get the current URL to check if driver is responsive
        driver.current_url
        return True
    except (WebDriverException, Exception):
        return False

def parse_datetime_filters(start_date_str, end_date_str, relative_range_str, start_time_str, end_time_str):
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
                # Calculate target month and year
                total_months_offset = current_month + num
                year_offset = (total_months_offset - 1) // 12
                target_year = current_year + year_offset
                target_month = (total_months_offset - 1) % 12 + 1
                # Get max days in target month
                _, days_in_target_month = calendar.monthrange(target_year, target_month)
                # Adjust day if current day is invalid for target month
                target_day = min(current_day, days_in_target_month)
                end_date = date(target_year, target_month, target_day)
            else:
                raise ValueError(f"Invalid DATE_RANGE unit: '{unit}'. Use 'd', 'w', or 'm'.")
            
            date_filter_active = True
            print(f"Relative date filtering active: Today ({start_date.strftime('%m/%d/%Y')}) + {num}{unit} -> {end_date.strftime('%m/%d/%Y')}")
            
        elif start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, "%m/%d/%Y").date()
            end_date = datetime.strptime(end_date_str, "%m/%d/%Y").date()
            if start_date > end_date:
                raise ValueError("DATE_RANGE_START cannot be after DATE_RANGE_END.")
            date_filter_active = True
            print(f"Absolute date filtering active: {start_date.strftime('%m/%d/%Y')} to {end_date.strftime('%m/%d/%Y')}")
    except Exception as e:
        print(f"Disabling date filtering due to error (check DATE_RANGE*, ensure format MM/DD/YYYY or Nd/Nw/Nm): {e}")
        date_filter_active = False
        start_date = None
        end_date = None

    try:
        if start_time_str and end_time_str:
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.strptime(end_time_str, "%H:%M").time()
            time_filter_active = True
            print(f"Time filtering active: {start_time.strftime('%H:%M')} to {end_time.strftime('%H:%M')}")
    except Exception as e:
        print(f"Disabling time filtering due to error (check TIME_RANGE*, ensure format HH:MM): {e}")
        time_filter_active = False
        start_time = None
        end_time = None

    return date_filter_active, start_date, end_date, time_filter_active, start_time, end_time


def get_filtered_locations(your_address, distance_range_str, location_file):
    try:
        if not (your_address and distance_range_str):
            print("YOUR_ADDRESS or DISTANCE_RANGE not set. Scraping all locations.")
            return None, False
        distance_range_miles = Decimal(distance_range_str)
        if distance_range_miles <= 0:
            raise ValueError("Distance range must be positive.")
        print(f"Distance filtering active: Address='{your_address}', Range={distance_range_miles} miles.")
    except Exception as e:
        print(f"Error setting up filtering (check YOUR_ADDRESS, DISTANCE_RANGE): {e}. Scraping all locations.")
        return None, False

    try:
        with open(location_file, 'r') as f:
            locations_data = json.load(f)
        print(f"Loaded location data from {location_file}")
    except Exception as e:
        print(f"Error loading location data from '{location_file}': {e}. Scraping all locations.")
        return None, False

    try:
        geolocator = Nominatim(user_agent="dmv_appointment_scraper")
        print(f"Geocoding your address: {your_address}...")
        user_location = geolocator.geocode(your_address, timeout=10)
        if not user_location:
            raise ValueError("Could not geocode YOUR_ADDRESS")
        user_coords = (user_location.latitude, user_location.longitude)
        print(f"Your coordinates: {user_coords}")
    except Exception as e:
        print(f"Error geocoding YOUR_ADDRESS '{your_address}': {e}. Scraping all locations.")
        return None, False

    allowed_locations = set()
    print("Calculating distances...")
    for item in locations_data:
        try:
            location_address = item["address"] 
            location_coords = item["coordinates"]
            if len(location_coords) != 2:
                raise ValueError("Invalid coordinates format")
            dist = geopy_distance(user_coords, tuple(location_coords)).miles
            if Decimal(dist) <= distance_range_miles:
                allowed_locations.add(location_address)
        except Exception as e:
            print(f"Warning: Error processing location entry '{item.get('address', 'N/A')}': {e}")
            continue 

    print(f"Found {len(allowed_locations)} locations within range.")
    return allowed_locations, True

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

def send_discord_notification(webhook_url, message_content):
    if not webhook_url or webhook_url == "YOUR_WEBHOOK_URL_HERE":
        print("Discord webhook URL not configured. Skipping notification.")
        return

    if message_content == None and PROOF_OF_LIFE == True:
        requests.post(webhook_url, json={"content":"No valid appointments found at this time"}, timeout=10)
        return
    elif message_content == None:
        return

    # intro_message = f"@everyone Appointments available at {NCDOT_APPOINTMENT_URL}:\n"
    full_message = INTRO_MESSAGE + message_content

    message_chunks = []
    remaining_message = full_message

    while len(remaining_message) > 0:
        if len(remaining_message) <= MAX_DISCORD_MESSAGE_LENGTH:
            message_chunks.append(remaining_message)
            remaining_message = ""
        else:
            split_index = remaining_message.rfind('\n', 0, MAX_DISCORD_MESSAGE_LENGTH)
            if split_index == -1:
                split_index = MAX_DISCORD_MESSAGE_LENGTH

            message_chunks.append(remaining_message[:split_index])
            remaining_message = remaining_message[split_index:].lstrip()

            if split_index == MAX_DISCORD_MESSAGE_LENGTH and len(remaining_message) > 0:
                 message_chunks[-1] += "\n... (split)" # forced split in middle of line


    print(f"Sending notification in {len(message_chunks)} chunk(s)...")
    success = True
    if "https://ntfy.sh/" in webhook_url:
        try:
            response = requests.post(webhook_url, data=full_message,timeout=10,headers={ "Markdown": "yes" })
            response.raise_for_status()
            print("ntfy notification sent successfully")
        except requests.exceptions.RequestException as e:
            print(f"Error sending ntfy notification: {e}")
            success = False
        except Exception as e:
            print(f"An unexpected error occurred during sending ntfy notification: {e}")
            success = False
    else:
        for i, chunk in enumerate(message_chunks):
            payload = {
                        "number": SIGNAL_NUMBER,
                        "message": chunk,
                        "recipients": [
                            SIGNAL_GROUP
                        ]
                    }
            try:
                response = requests.post(webhook_url, json=payload, timeout=15)
                response.raise_for_status()
                print(f"Signal notification chunk {i+1}/{len(message_chunks)} sent successfully.")
                if i < len(message_chunks) - 1:
                    time.sleep(1) # avoid ratelimit
            except requests.exceptions.RequestException as e:
                print(f"Error sending Signal notification chunk {i+1}: {e}")
                success = False
                break
            except Exception as e:
                print(f"An unexpected error occurred during Signal notification chunk {i+1}: {e}")
                success = False
                break

    if success:
        print("All Discord notification chunks sent.")
    else:
        print("Failed to send all Discord notification chunks.")


def format_results_for_discord(raw_results):
    """Formats the valid results into a string for Discord."""
    message_lines = []
    found_valid_times = False
    for location, result in raw_results.items():
        if isinstance(result, list) and result:
            message_lines.append(f"\n**Location: {location}**")
            for dt_str in result:
                message_lines.append(f"- {dt_str}")
            found_valid_times = True

    if not found_valid_times:
        return None

    return "\n".join(message_lines)

def parse_datetime_for_sort(datetime_str):
    try:
        return datetime.strptime(datetime_str, "%m/%d/%Y %I:%M:%S %p")
    except ValueError:
        return datetime.max

def wait_for_options_in_select(driver, locator, timeout=35):
    start_wait = time.time()
    while time.time() - start_wait < timeout:
        try:
            select_element = driver.find_element(*locator)
            options = select_element.find_elements(By.TAG_NAME, "option")
            if len(options) > 1:
                return select_element
        except Exception:
            pass
        time.sleep(0.3)
    return None

def initialize_webdriver(driver_path, binary_path, user_address=None):
    """Initialize and return a new Firefox webdriver instance."""
    try:
        print("Starting Firefox setup...")
        firefox_options = Options()
        firefox_options.add_argument("--headless")
        
        # Enable geolocation and set Charlotte, NC coordinates if address is provided
        if user_address:
            print(f"Setting browser location for address: {user_address}")
            # Get coordinates for the user's address
            try:
                from geopy.geocoders import Nominatim
                geolocator = Nominatim(user_agent="dmv_appointment_scraper")
                location = geolocator.geocode(user_address, timeout=10)
                if location:
                    lat, lon = location.latitude, location.longitude
                    print(f"Setting browser coordinates to: {lat}, {lon}")
                    
                    # Enable geolocation and set coordinates
                    firefox_options.set_preference("geo.enabled", True)
                    firefox_options.set_preference("geo.provider.use_corelocation", False)
                    firefox_options.set_preference("geo.prompt.testing", True)
                    firefox_options.set_preference("geo.prompt.testing.allow", True)
                    # Set the location coordinates
                    firefox_options.set_preference("geo.provider.network.url", f"data:application/json,{{\"location\": {{\"lat\": {lat}, \"lng\": {lon}}}, \"accuracy\": 27000.0}}")
                else:
                    print("Could not geocode address, disabling geolocation")
                    firefox_options.set_preference("geo.enabled", False)
            except Exception as e:
                print(f"Error setting up geolocation: {e}, disabling geolocation")
                firefox_options.set_preference("geo.enabled", False)
        else:
            firefox_options.set_preference("geo.enabled", False)
            
        if binary_path:
            firefox_options.binary_location = binary_path
        service = FirefoxService(executable_path=driver_path)

        driver = webdriver.Firefox(service=service, options=firefox_options)
        driver.implicitly_wait(2)
        driver.set_page_load_timeout(90)
        print("Firefox driver initialized.")
        return driver
    except Exception as e:
        error_msg = str(e).lower()
        if "unable to find binary" in error_msg or \
           ("message: process unexpectedly closed" in error_msg and binary_path):
             print("ERROR: Selenium couldn't find your Firefox installation.")
             print("Please ensure Firefox is installed or FIREFOX_BINARY_PATH is set.")
        else:
             print(f"ERROR: Failed to initialize Firefox driver: {e}")
        return None

def navigate_to_location_selection(driver, url):
    """Navigate to the location selection page. Returns True if successful, False otherwise."""
    try:
        print(f"Navigating to URL: {url}")
        driver.get(url)
        print("Page loaded.")

        try:
            make_appointment_button = WebDriverWait(driver, 90).until(
                EC.presence_of_element_located((By.ID, "cmdMakeAppt"))
            )
            print("Found 'Make an Appointment' button.")
            make_appointment_button.click()
            print("Clicked 'Make an Appointment' button.")
        except Exception as e:
            print(f"ERROR: Could not find or click 'Make an Appointment' button: {e}")
            return False

        try:
            first_layer_button_xpath = f"//div[contains(@class, 'QflowObjectItem') and .//div[contains(text(), '{APPOINTMENT_TYPE}')]]"
            time.sleep(2)
            first_layer_button = WebDriverWait(driver, 50).until(
                EC.element_to_be_clickable((By.XPATH, first_layer_button_xpath))
            )
            print(f"Found '{APPOINTMENT_TYPE}' button.")
            first_layer_button.click()
            print(f"Clicked '{APPOINTMENT_TYPE}' button.")
        except Exception as e:
            print(f"ERROR: Could not find or click '{APPOINTMENT_TYPE}' button: {e}")
            return False
        
        return True
    except Exception as e:
        print(f"ERROR: Failed to navigate to location selection: {e}")
        return False

def extract_times_for_all_locations_firefox(
    url, driver, driver_path, binary_path,
    allowed_locations_filter, filtering_active,
    date_filter_enabled, start_date, end_date,
    time_filter_enabled, start_time, end_time,
    user_address=None
):
    raw_location_results = {}
    start_run_time_str = time.strftime('%Y-%m-%d %H:%M:%S')

    try:
        print(f"[{start_run_time_str}] Refreshing page...")
        
        # If driver is None, initialize it
        if driver is None:
            print("Initializing new webdriver...")
            driver = initialize_webdriver(driver_path, binary_path, user_address)
            if driver is None:
                return {}, False, None

        # Check if driver is still healthy
        if not is_driver_healthy(driver):
            print("Driver appears unhealthy, returning for restart...")
            return {}, False, None

        print(f"Navigating to URL: {url}")
        driver.get(url)
        print("Page loaded.")

        try:
            make_appointment_button = WebDriverWait(driver, 90).until(
                EC.presence_of_element_located((By.ID, "cmdMakeAppt"))
            )
            print("Found 'Make an Appointment' button.")
            make_appointment_button.click()
            print("Clicked 'Make an Appointment' button.")
        except (WebDriverException, TimeoutException) as e:
            print(f"ERROR: Could not find or click 'Make an Appointment' button: {e}. Stopping.")
            if isinstance(e, WebDriverException):
                return {}, False, None  # Need driver restart
            return {}, False, driver

        try:
            first_layer_button_xpath = f"//div[contains(@class, 'QflowObjectItem') and .//div[contains(text(), '{APPOINTMENT_TYPE}')]]"
            time.sleep(2)
            first_layer_button = WebDriverWait(driver, 50).until(
                EC.element_to_be_clickable((By.XPATH, first_layer_button_xpath))
            )
            print(f"Found '{APPOINTMENT_TYPE}' button.")
            first_layer_button.click()
            print(f"Clicked '{APPOINTMENT_TYPE}' button.")
            
            # Wait for the location selection page to load
            print("Waiting for location selection page to load...")
            time.sleep(3)
            
        except (WebDriverException, TimeoutException) as e:
            print(f"ERROR: Could not find or click '{APPOINTMENT_TYPE}' button: {e}. Stopping.")
            if isinstance(e, WebDriverException):
                return {}, False, None  # Need driver restart
            return {}, False, driver

        location_button_wait = WebDriverWait(driver, 45)
        # Look for actual DMV office location buttons - these should have different structure
        second_layer_button_selector = "div.QflowObjectItem.form-control.ui-selectable"

        try:
            print("Waiting for location buttons...")
            location_button_wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, second_layer_button_selector)))
            print("Location buttons are present.")
        except (WebDriverException, TimeoutException) as e:
            print(f"ERROR: No location buttons found after clicking appointment type: {e}. Stopping.")
            if isinstance(e, WebDriverException):
                return {}, False, None  # Need driver restart
            return {}, False, driver

        initial_buttons = driver.find_elements(By.CSS_SELECTOR, second_layer_button_selector)
        num_initial_buttons = len(initial_buttons)
        print(f"Found {num_initial_buttons} total location buttons (including inactive ones).")
        
        # Quick sanity check - make sure we're on the location selection page
        if any("Driver License" in btn.text or "Motorcycle" in btn.text or "Teen Driver" in btn.text for btn in initial_buttons[:5]):
            print("WARNING: Still appears to be on appointment type selection page, not location selection!")
            print("This suggests the appointment type click didn't navigate to the location page.")
            return {}, False, driver

        # First, quickly identify all available buttons to avoid processing unavailable ones
        print("Quickly scanning for available locations...")
        available_button_indices = []
        WebDriverWait(driver, 15).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, second_layer_button_selector)))
        location_button_elements = driver.find_elements(By.CSS_SELECTOR, second_layer_button_selector)
        
        for index in range(min(num_initial_buttons, len(location_button_elements))):
            try:
                current_button = location_button_elements[index]
                button_class = current_button.get_attribute("class") or ""
                has_disabled_class = "disabled-unit" in button_class
                
                if not has_disabled_class and current_button.is_displayed() and current_button.is_enabled():
                    available_button_indices.append(index)
                    # Get location name for quick reference
                    try:
                        button_lines = current_button.text.splitlines()
                        location_name = button_lines[0].strip() if button_lines else f"Location {index}"
                        print(f"  Available: {location_name} (index {index})")
                    except:
                        print(f"  Available: Location {index}")
            except Exception as e:
                continue
        
        print(f"Found {len(available_button_indices)} available locations out of {num_initial_buttons} total.")
        if len(available_button_indices) == 0:
            print("No available locations found - all are currently disabled/unavailable.")
            return raw_location_results, True, driver
        
        # Now process only the available locations
        for index in available_button_indices:
            location_name = f"Unknown Location {index}"
            location_address_from_site = "Unknown Address"
            location_processed_successfully = False

            try:
                print(f"\n--- Processing available location index: {index} ---")
                WebDriverWait(driver, 15).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, second_layer_button_selector)))
                location_button_elements = driver.find_elements(By.CSS_SELECTOR, second_layer_button_selector)
                
                if index >= len(location_button_elements):
                    print(f"Index {index} out of bounds ({len(location_button_elements)} total buttons). Skipping.")
                    continue

                current_button = location_button_elements[index]
                
                # Double-check that button is still available (page might have changed)
                try:
                    button_class = current_button.get_attribute("class") or ""
                    has_disabled_class = "disabled-unit" in button_class
                    
                    if has_disabled_class or not current_button.is_displayed() or not current_button.is_enabled():
                        print(f"Location {index} became unavailable since scan. Skipping.")
                        continue
                except Exception as e:
                    print(f"Warning: Could not re-check button state for index {index}: {e}. Skipping.")
                    continue

                try:
                    button_text = current_button.text
                    print(f"Button {index} text: '{button_text}'")
                    
                    button_lines = current_button.text.splitlines()
                    if button_lines:
                        location_name = button_lines[0].strip()
                    else:
                        location_name = f"Unknown Location {index}"
                        
                    try:
                        address_element = current_button.find_element(By.CSS_SELECTOR, "div.form-control-child")
                        location_address_from_site = address_element.text.strip()
                    except NoSuchElementException:
                        print(f"Could not find address element with 'div.form-control-child' for button {index}")
                        # Try alternative selectors
                        try:
                            address_element = current_button.find_element(By.CSS_SELECTOR, "div[class*='form-control']")
                            location_address_from_site = address_element.text.strip()
                            print(f"Found address using alternative selector: '{location_address_from_site}'")
                        except NoSuchElementException:
                            location_address_from_site = f"Unknown Address {index}"
                            print(f"Could not find any address element for button {index}")
                    
                    print(f"Location: {location_name} ({location_address_from_site})")
                except Exception as e:
                    print(f"Warning: Could not get name/address for index {index}: {e}")
                    location_name = f"Unknown Location {index}"
                    location_address_from_site = f"Unknown Address {index}"

                if filtering_active and location_address_from_site not in allowed_locations_filter:
                    print(f"Skipping {location_name} (Address '{location_address_from_site}' not in allow list)")
                    # Since locations are sorted by distance, if this one is out of range, 
                    # all remaining locations will also be out of range
                    print("Breaking out of location loop - remaining locations will be out of range")
                    break

                print(f"Clicking button for: {location_name}")
                current_button.click()
                location_processed_successfully = True
                time.sleep(5)

                valid_appointment_datetimes_for_location = []
                location_status_message = ""
                process_dates = True

                datepicker_table_selector_css = "table.ui-datepicker-calendar"
                error_locator_id = "547650da-008d-4fd0-a164-31a44e94"
                overlay_selector_css = "div.blockUI.blockOverlay"

                try:
                    print("Waiting for datepicker...")
                    WebDriverWait(driver, 30).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, datepicker_table_selector_css))
                    )
                    print("Datepicker visible.")
                    try:
                        error_element = driver.find_element(By.ID, error_locator_id)
                        error_html = error_element.get_attribute('innerHTML')
                        if "does not currently have any appointments available" in error_html:
                            print("Message: No appointments available in next 90 days.")
                            location_status_message = "No appointments in next 90 days"
                            process_dates = False
                    except NoSuchElementException:
                        pass
                    except Exception as e:
                        print(f"Warning checking 90-day error msg: {e}")

                except Exception as e:
                    print(f"Did not find datepicker or error occurred: {e}")
                    location_status_message = "Datepicker Not Found"
                    process_dates = False

                if process_dates:
                    print("Processing available dates...")
                    clickable_dates_selector_css = "td[data-handler='selectDay']:not(.ui-datepicker-unselectable):not(.ui-state-disabled) a.ui-state-default"
                    time_select_locator = (By.ID, "6f1a7b21-2558-41bb-8e4d-2cba7a8b1608")

                    try:
                        WebDriverWait(driver,10).until(EC.presence_of_element_located((By.CSS_SELECTOR, datepicker_table_selector_css)))
                        date_elements = driver.find_elements(By.CSS_SELECTOR, clickable_dates_selector_css)
                        num_dates = len(date_elements)
                        print(f"Found {num_dates} clickable dates.")

                        if num_dates == 0 and not location_status_message:
                            location_status_message = "No clickable dates found"

                        for date_index in range(num_dates):
                            processed_date = False
                            try:
                                current_date_links = driver.find_elements(By.CSS_SELECTOR, clickable_dates_selector_css)
                                if date_index >= len(current_date_links):
                                    print(f"Date index {date_index} out of bounds on re-find. Skipping remaining.")
                                    break

                                date_link_element = current_date_links[date_index]
                                date_day_text = date_link_element.text
                                print(f"    Processing Date Index {date_index} (Day: '{date_day_text}')...", end="")

                                overlay_wait_start = time.time()
                                max_overlay_wait = 15
                                overlay_timed_out = False
                                while True:
                                    try:
                                        overlay = driver.find_element(By.CSS_SELECTOR, overlay_selector_css)
                                        if overlay.is_displayed():
                                            if time.time() - overlay_wait_start > max_overlay_wait:
                                                print(" Overlay still visible after timeout.", end="")
                                                overlay_timed_out = True
                                                break
                                            time.sleep(0.5)
                                        else:
                                            break
                                    except NoSuchElementException:
                                        break
                                    except Exception as e_overlay_check:
                                        print(f" Error checking overlay: {e_overlay_check}", end="")
                                        break

                                if overlay_timed_out:
                                    print(" Skipping date click due to persistent overlay.")
                                    continue

                                date_link_element.click()

                                time_select_element = wait_for_options_in_select(driver, time_select_locator, timeout=25)

                                if time_select_element:
                                    time_options = time_select_element.find_elements(By.TAG_NAME, "option")
                                    times_found_this_date = 0
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
                                                times_found_this_date += 1
                                                if times_found_this_date == 1 and len(raw_location_results.keys()) == 0:
                                                    send_discord_notification(YOUR_DISCORD_WEBHOOK_URL, "🚨🚨🚨 NEW APPOINTMENTS ARRIVING \n\n https://skiptheline.ncdot.gov")
                                        except Exception:
                                            pass
                                    if times_found_this_date > 0:
                                        print(f" Added {times_found_this_date} time(s).")
                                        processed_date = True
                                    else:
                                         print(" No matching times found.")
                                else:
                                     print(" Time options did not load.")

                            except Exception as e_date:
                                if not processed_date: 
                                     print(f" Error processing date index {date_index} (Day '{date_day_text}'): {e_date}")

                    except Exception as e_find_dates:
                        print(f"  Error finding or looping through date elements: {e_find_dates}")
                        if not location_status_message:
                            location_status_message = "Error processing dates"

                if valid_appointment_datetimes_for_location:
                    try:
                        valid_appointment_datetimes_for_location.sort(key=parse_datetime_for_sort)
                    except Exception as e_sort:
                         print(f"  Warning: Could not sort times for {location_name}: {e_sort}")
                    raw_location_results[location_name] = valid_appointment_datetimes_for_location
                elif location_status_message:
                    raw_location_results[location_name] = location_status_message
                else:
                    raw_location_results[location_name] = []

            except Exception as location_e:
                print(f"!! ERROR processing location index {index} ({location_name}): {location_e}")
                raw_location_results[location_name] = f"Error processing location: {type(location_e).__name__}"

            finally:
                if location_processed_successfully:
                    try:
                        print("Navigating back to location list...")
                        driver.back()
                        time.sleep(2.0)
                        print("Waiting for location buttons...")
                        WebDriverWait(driver, 25).until(
                             EC.presence_of_all_elements_located((By.CSS_SELECTOR, second_layer_button_selector))
                        )
                        print("Location buttons present for next iteration.")
                        time.sleep(0.5)
                    except Exception as back_wait_e:
                         print(f"WARNING: Issue navigating back or waiting for buttons after location index {index}: {back_wait_e}. Trying next location.")


        print("\nFinished processing locations loop.")

    except (WebDriverException, Exception) as e:
        print(f"\n--- !!! ---")
        print(f"An MAJOR unhandled error occurred outside the location loop: {type(e).__name__} - {e}")
        print(f"--- !!! ---\n")
        # For WebDriverExceptions, we should restart the driver
        if isinstance(e, WebDriverException):
            print("WebDriverException detected - driver restart needed")
            try:
                if driver:
                    driver.quit()
            except:
                pass
            return {}, False, None
        return {}, False, driver  # Return False to indicate need for driver restart

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Extraction process finished.")
    return raw_location_results, True, driver  # Return True to indicate successful run


allowed_locations, filtering_enabled = get_filtered_locations(YOUR_ADDRESS, DISTANCE_RANGE_MILES_STR, LOCATION_DATA_FILE)

date_filter, dt_start, dt_end, time_filter, tm_start, tm_end = parse_datetime_filters(
    DATE_RANGE_START_STR, DATE_RANGE_END_STR, DATE_RANGE_RELATIVE_STR, 
    TIME_RANGE_START_STR, TIME_RANGE_END_STR
)

if YOUR_DISCORD_WEBHOOK_URL == "YOUR_WEBHOOK_URL_HERE":
    print("!!! WARNING: DISCORD WEBHOOK URL IS NOT SET. Notifications will be skipped. !!!")
    print("!!! Edit the YOUR_DISCORD_WEBHOOK_URL variable in the script. !!!")

# Initialize webdriver once outside the main loop
driver = None
driver_restart_needed = True

while True:
    print(f"\n--- Starting run at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")

    try:
        # Initialize or restart driver if needed
        if driver_restart_needed or driver is None or not is_driver_healthy(driver):
            if driver:
                print("Restarting webdriver...")
                try:
                    driver.quit()
                except:
                    pass
                driver = None
            driver = initialize_webdriver(GECKODRIVER_PATH, FIREFOX_BINARY_PATH, YOUR_ADDRESS)
            if driver is None:
                print("Failed to initialize webdriver. Retrying in next run...")
                driver_restart_needed = True
                time.sleep(BASE_INTERVAL_SECONDS)
                continue
            driver_restart_needed = False
        
        results, success, driver = extract_times_for_all_locations_firefox(
            NCDOT_APPOINTMENT_URL, # URL
            driver,                # Persistent driver
            GECKODRIVER_PATH,      # Driver path
            FIREFOX_BINARY_PATH,   # Binary path
            allowed_locations,     # Distance filter
            filtering_enabled,     # Distance filter flag
            date_filter,           # Date filter flag
            dt_start,              # Date filter start
            dt_end,                # Date filter end
            time_filter,           # Time filter flag
            tm_start,              # Time filter start
            tm_end,                # Time filter end
            YOUR_ADDRESS           # User address for geolocation
        )
        
        if not success:
            print("!!! Error occurred during extraction. Will restart driver in next run. !!!")
            driver_restart_needed = True
            # If driver was returned as None, we need to restart
            if driver is None:
                driver_restart_needed = True
            continue

        print(results)

        discord_message_content = format_results_for_discord(results)
        if discord_message_content:
            print("Valid appointment times found. Sending notification...")
            send_discord_notification(YOUR_DISCORD_WEBHOOK_URL, discord_message_content)
        else:
            send_discord_notification(YOUR_DISCORD_WEBHOOK_URL, None)
            print("No valid appointment times found in this run.")

    except Exception as e:
        print(f"!!! Unexpected error in main loop: {e}. Will restart driver in next run. !!!")
        driver_restart_needed = True
        continue

    #base_sleep = BASE_INTERVAL_SECONDS
    random_delay = random.randint(MIN_RANDOM_DELAY_SECONDS, MAX_RANDOM_DELAY_SECONDS)
    total_sleep = random_delay

    print(f"--- Run finished. Sleeping for {total_sleep // 60} minutes and {total_sleep % 60} seconds ---")
    try:
        time.sleep(total_sleep)
    except KeyboardInterrupt:
        print("\nCtrl+C detected. Closing webdriver and exiting script.")
        if driver:
            try:
                driver.quit()
            except:
                pass
        break
