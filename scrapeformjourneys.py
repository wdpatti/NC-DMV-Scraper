from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, ElementClickInterceptedException
import time
import json
import os
import re
from bs4 import BeautifulSoup
import traceback

# --- Configuration ---
GECKODRIVER_PATH = os.getenv('GECKODRIVER_PATH', 'YOUR_GECKODRIVER_PATH_HERE')
NCDOT_APPOINTMENT_URL = "https://skiptheline.ncdot.gov"
LOCATIONS_JSON_FILE = "locations.json"
FIREFOX_BINARY_PATH = os.getenv("FIREFOX_BINARY_PATH")
# --- End Configuration ---

if GECKODRIVER_PATH == 'YOUR_GECKODRIVER_PATH_HERE':
    print("Please set your geckodriver path.")
    exit()

# --- Helper Functions ---
def setup_driver(driver_path, binary_path=None):
    print("Setting up Firefox driver...")
    opts = Options()
    # opts.add_argument("--headless")
    opts.set_preference("geo.enabled", False)
    opts.set_preference("dom.storage.enabled", True)
    if binary_path: opts.binary_location = binary_path
    service = FirefoxService(executable_path=driver_path)
    try:
        d = webdriver.Firefox(service=service, options=opts)
        d.implicitly_wait(7)
        d.set_page_load_timeout(100)
        print("Firefox driver initialized.")
        return d
    except Exception as e_setup:
        print(f"ERROR: Failed to initialize Firefox driver: {e_setup}")
        return None

def load_locations_data(filepath):
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found. Creating an empty structure.")
        return {}
    try:
        with open(filepath, 'r') as f: data = json.load(f)
        print(f"Loaded data from {filepath}")
        return data
    except Exception as e_load:
        print(f"Error loading/decoding {filepath}: {e_load}. Returning empty structure.")
        return {}

def save_locations_data(filepath, data):
    try:
        with open(filepath, 'w') as f: json.dump(data, f, indent=2)
    except Exception as e_save: print(f"Error saving data to {filepath}: {e_save}")

def extract_form_journey_details(html_source):
    soup = BeautifulSoup(html_source, 'html.parser')
    fj_content, appt_id_str = None, None
    for script_tag in soup.find_all('script', type="text/javascript"):
        if script_tag.string and (match := re.search(r"sessionStorage\.setItem\s*\(\s*[\"']formJourney[\"']\s*,\s*[\"'](.*?)[\"']\s*\)", script_tag.string, re.DOTALL)):
            fj_content = match.group(1); break
    for select_el in soup.find_all('select'):
        for option_el in select_el.find_all('option', attrs={'data-appointmenttypeid': True}):
            if (appt_id := option_el.get('data-appointmenttypeid')) and appt_id.isdigit() and option_el.get_text(strip=True) != '-':
                appt_id_str = appt_id; break
        if appt_id_str: break
    if not fj_content: print("    DEBUG: formJourney content not found.")
    if not appt_id_str: print("    DEBUG: data-appointmenttypeid not found.")
    return fj_content, appt_id_str

def navigate_to_appt_type_page(driver, base_url, wait_for_xpath):
    print("Attempting to navigate/ensure on appointment type selection page...")
    try:
        WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.XPATH, f"({wait_for_xpath})[1]")))
        print("Already on appointment type selection page.")
        return True
    except TimeoutException: pass
    print(f"  Navigating to base URL: {base_url}")
    driver.get(base_url)
    print("  Clicking 'Make an Appointment' button on base page...")
    WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.ID, "cmdMakeAppt"))).click()
    time.sleep(3.5) # Increased sleep after click
    try:
        WebDriverWait(driver, 30).until(EC.visibility_of_element_located((By.XPATH, f"({wait_for_xpath})[1]")))
        print("Successfully navigated to appointment type selection page.")
        return True
    except TimeoutException:
        print("ERROR: Failed to navigate to appointment type selection page after multiple attempts.")
        return False

def get_location_name_from_button(location_button_element):
    """Helper to safely get name from a location button WebElement."""
    try:
        # A quick check to see if the element might be stale.
        # This doesn't guarantee it's not, but can catch some obvious cases.
        _ = location_button_element.is_displayed() 
        
        title_div = location_button_element.find_element(By.XPATH, "./div[@title]")
        name_div = title_div.find_element(By.XPATH, "./div[1]")
        return name_div.text.strip()
    except NoSuchElementException:
        # This can happen if the button structure is not as expected
        # print("    DEBUG: Could not find name structure in button during get_location_name_from_button.")
        return None
    except StaleElementReferenceException:
        # This means the element is no longer attached to the DOM
        # print("    DEBUG: Stale element when trying to get name from button during get_location_name_from_button.")
        return None 
    except Exception as e:
        # Catch any other unexpected errors
        # print(f"    DEBUG: Unexpected error in get_location_name_from_button: {e}")
        return None

# --- Main Function ---
def main():
    driver = setup_driver(GECKODRIVER_PATH, FIREFOX_BINARY_PATH)
    if not driver: return

    all_locations_data = load_locations_data(LOCATIONS_JSON_FILE)

    appt_type_buttons_container_xpath = "//div[contains(@class, 'ApptTypeIdPreUnit') and contains(@class, 'QFlowObjectModel')]"
    appt_type_buttons_xpath = f"{appt_type_buttons_container_xpath}//div[@class='QflowObjectItem form-control ui-selectable valid']"

    if not navigate_to_appt_type_page(driver, NCDOT_APPOINTMENT_URL, appt_type_buttons_xpath):
        if driver: driver.quit(); return

    try:
        # Get initial count ONCE, but re-fetch list inside loop
        initial_num_appt_types = len(driver.find_elements(By.XPATH, appt_type_buttons_xpath))
        print(f"Found {initial_num_appt_types} appointment types initially.")

        for appt_type_idx in range(initial_num_appt_types): # Loop based on initial count
            print(f"\n--- Processing Appointment Type Index {appt_type_idx} (Button {appt_type_idx + 1}/{initial_num_appt_types}) ---")
            
            if not navigate_to_appt_type_page(driver, NCDOT_APPOINTMENT_URL, appt_type_buttons_xpath):
                print("Could not return to appointment type page. Ending current appt type processing.")
                continue 

            current_appt_type_buttons_list = driver.find_elements(By.XPATH, appt_type_buttons_xpath)
            if appt_type_idx >= len(current_appt_type_buttons_list):
                print(f"Error: Appt type index {appt_type_idx} out of sync with current buttons ({len(current_appt_type_buttons_list)}). Skipping."); continue
            
            appt_type_button = current_appt_type_buttons_list[appt_type_idx]
            appt_type_name = f"Unknown Appt Type {appt_type_idx+1}"
            current_appt_type_id_on_page = None
      
            try:
                # Wait for the specific button to be interactable before getting attributes/text
                WebDriverWait(driver,15).until(EC.element_to_be_clickable(appt_type_button))
                hover_div = appt_type_button.find_element(By.XPATH, ".//div[@class='hover-div']") # Re-find if needed
                appt_type_name = hover_div.text.splitlines()[0].strip() if hover_div.text else appt_type_name
                current_appt_type_id_on_page = appt_type_button.get_attribute('data-id') # .get_attribute() is fine on a WebElement
                if not current_appt_type_id_on_page: print(f"    Warning: No data-id for appt type '{appt_type_name}'.")
                print(f"Selected Appt Type: '{appt_type_name}' (ID on page: {current_appt_type_id_on_page})")

                locations_to_process_for_this_type = set()
                if current_appt_type_id_on_page and all_locations_data:
                    expected_fj_key = f"formJourney{current_appt_type_id_on_page}"
                    for loc_name_json, loc_data_json_entry in all_locations_data.items(): # Renamed loc_data_json to avoid confusion
                        
                        # Ensure the main entry for the location is a dictionary
                        if not isinstance(loc_data_json_entry, dict):
                            print(f"    INFO: Data for location '{loc_name_json}' in locations.json is not a dictionary ({type(loc_data_json_entry)}). Marking to process.")
                            locations_to_process_for_this_type.add(loc_name_json)
                            continue

                        form_journeys_in_json = loc_data_json_entry.get('formJourneys')
                        content_from_json = "" # Default to empty, meaning it needs processing

                        if form_journeys_in_json is None:
                            # No 'formJourneys' key for this location, so it needs processing.
                            pass # content_from_json remains "", will be added below
                        elif isinstance(form_journeys_in_json, dict):
                            # 'formJourneys' is a dictionary, proceed to get the specific journey.
                            specific_journey_data = form_journeys_in_json.get(expected_fj_key)

                            if specific_journey_data is None:
                                # No entry for this specific expected_fj_key. Needs processing.
                                pass # content_from_json remains "", will be added below
                            elif isinstance(specific_journey_data, str):
                                # THIS IS THE CASE: formjourneys themselves are strings.
                                # The value *is* the content string.
                                content_from_json = specific_journey_data
                            elif isinstance(specific_journey_data, dict):
                                # This is the structure your script saves: {"journeyContent": "..."}
                                content_from_json = specific_journey_data.get("journeyContent", "")
                            else:
                                # Unexpected data type for the specific journey.
                                print(f"    WARNING: Unexpected data type for '{expected_fj_key}' under 'formJourneys' for '{loc_name_json}': {type(specific_journey_data)}. Marking to process.")
                                # content_from_json remains "", will be added below
                        elif isinstance(form_journeys_in_json, str):
                            # The entire 'formJourneys' value is a single string.
                            # This structure is not expected for individual appointment type checking.
                            # This implies the location needs its formJourneys properly structured and populated.
                            print(f"    INFO: 'formJourneys' for '{loc_name_json}' is a single string, not a dict of journeys. Marking to process for {expected_fj_key}.")
                            # content_from_json remains "", will be added below
                        else:
                            # 'formJourneys' key exists but is neither None, dict, nor string.
                            print(f"    WARNING: 'formJourneys' for '{loc_name_json}' is an unexpected type: {type(form_journeys_in_json)}. Marking to process for {expected_fj_key}.")
                            # content_from_json remains "", will be added below

                        # Decide if this location needs to be processed for the current appointment type
                        if not content_from_json or content_from_json.startswith("Placeholder:"):
                            locations_to_process_for_this_type.add(loc_name_json)
                        
                    if not locations_to_process_for_this_type and all_locations_data:
                        print(f"    Skipping Appt Type '{appt_type_name}': All locations in JSON have valid data for {expected_fj_key}.")
                        # Before continuing, make sure to navigate back if necessary, or that the main loop handles it
                        # This 'continue' skips the appt_type_button.click() for this appt_type_idx
                        # Ensure you are back on the appt type selection page for the next iteration.
                        # The navigate_to_appt_type_page call at the start of the loop should handle this.
                        continue 
                    print(f"    Need to process {len(locations_to_process_for_this_type)} locations for {expected_fj_key} (or they are missing from JSON): {list(locations_to_process_for_this_type)[:5]}...")

                elif not all_locations_data: # If locations.json was empty or failed to load
                    print("    Warning: locations.json is empty or not loaded. Will attempt to process locations found on page.")
                    # In this case, locations_to_process_for_this_type remains empty,
                    # and the later while loop `(not all_locations_data and processed_any_location_in_while_loop)`
                    # will handle trying to scrape all locations.

                # Now, after determining locations_to_process_for_this_type, click the button
                appt_type_button.click() 
                time.sleep(4.5) # Consider replacing with WebDriverWait for a specific element on next page
            except Exception as e_appt_click:
                print(f"Error clicking/preparing appt type '{appt_type_name}': {e_appt_click}."); continue

    

            location_buttons_selector = "div.UnitIdList div.QflowObjectItem.form-control.ui-selectable:not(.disabled-unit)"
            
            processed_any_location_in_while_loop = True 
            while locations_to_process_for_this_type or (not all_locations_data and processed_any_location_in_while_loop):
                if not all_locations_data and not processed_any_location_in_while_loop: 
                    print("    First run: No more locations found on page or stuck. Ending for this type.")
                    break
                if all_locations_data and not locations_to_process_for_this_type: 
                    print("    All necessary locations for this type have been processed.")
                    break

                processed_any_location_in_while_loop = False 

                try:
                    print(f"    Scanning page for locations. Still need {len(locations_to_process_for_this_type)}: {list(locations_to_process_for_this_type)[:5]}...")
                    WebDriverWait(driver, 35).until(EC.visibility_of_element_located((By.CSS_SELECTOR, location_buttons_selector)))
                except TimeoutException:
                    print(f"    No location buttons visible on page for '{appt_type_name}' when trying to process remaining. Ending for this type.")
                    break 

                all_page_buttons_now = driver.find_elements(By.CSS_SELECTOR, location_buttons_selector)
                if not all_page_buttons_now:
                    print(f"    No location buttons retrieved for '{appt_type_name}'. Ending for this type."); break

                print(f"    Found {len(all_page_buttons_now)} buttons on current page view. Iterating to find a match...")
                
                visible_button_names_on_page_pass = [] 

                for web_button_element in all_page_buttons_now:
                    loc_name_html = get_location_name_from_button(web_button_element)
                    if not loc_name_html:
                        # If name can't be extracted, it might be a problematic element or truly stale.
                        # print("    Could not get name from a web button, skipping it for this pass.")
                        continue 
                    
                    visible_button_names_on_page_pass.append(loc_name_html)

                    should_process_this_one = False
                    if not all_locations_data: 
                        should_process_this_one = True
                    elif loc_name_html in locations_to_process_for_this_type:
                        should_process_this_one = True
                    
                    if not should_process_this_one:
                        # print(f"        Skipping visible button '{loc_name_html}' - not in 'to process' list.")
                        continue

                    print(f"    >>> Matched: '{loc_name_html}'. Attempting to process.")
                    try:
                        WebDriverWait(driver, 15).until(EC.element_to_be_clickable(web_button_element))
                        web_button_element.click()
                        
                        print(f"        Clicked. Waiting for AmendStep...")
                        WebDriverWait(driver, 50).until(
                            EC.presence_of_element_located((By.XPATH, "//select[.//option[@data-appointmenttypeid and string-length(@data-appointmenttypeid)>0 and text()!='-']]"))
                        )
                        time.sleep(2.5)
                        print(f"        Page updated. Extracting...")
                        fj_content, appt_id_select = extract_form_journey_details(driver.page_source)

                        if fj_content and appt_id_select:
                            fj_key_save = f"formJourney{appt_id_select}"
                            if current_appt_type_id_on_page and appt_id_select != current_appt_type_id_on_page:
                                print(f"        WARNING: Appt ID from select ({appt_id_select}) differs from page button ID ({current_appt_type_id_on_page}) for '{loc_name_html}'.")
                            
                            print(f"        Extracted: {fj_key_save} (len: {len(fj_content)})")
                            if loc_name_html not in all_locations_data: 
                                all_locations_data[loc_name_html] = {"id": "UNKNOWN_PAGE_ID", "address":"UNKNOWN", "formJourneys":{}} 
                                page_loc_id = web_button_element.get_attribute('data-id') # Get ID from current button
                                if page_loc_id: all_locations_data[loc_name_html]['id'] = page_loc_id
                            elif 'formJourneys' not in all_locations_data[loc_name_html]:
                                all_locations_data[loc_name_html]['formJourneys'] = {}
                            
                            all_locations_data[loc_name_html]['formJourneys'][fj_key_save] = {"journeyContent": fj_content}
                            save_locations_data(LOCATIONS_JSON_FILE, all_locations_data)
                            print(f"        Saved {fj_key_save} for '{loc_name_html}'.")
                            
                            if loc_name_html in locations_to_process_for_this_type: 
                                locations_to_process_for_this_type.remove(loc_name_html)
                            processed_any_location_in_while_loop = True
                        else:
                            print(f"        Failed to extract details for '{loc_name_html}'.")

                    except (TimeoutException, NoSuchElementException, ElementClickInterceptedException) as e_loc_interact:
                        print(f"        Interaction Error for '{loc_name_html}': {type(e_loc_interact).__name__}.")
                    except StaleElementReferenceException:
                        print(f"        StaleElement during processing of '{loc_name_html}'. Will re-scan page buttons.")
                    except Exception as e_loc_process:
                        print(f"        General Error processing '{loc_name_html}': {e_loc_process}")
                    
                    print(f"        Attempting to navigate back after trying to process '{loc_name_html}'...")
                    on_details_page = "ServiceAppointments" in driver.current_url or \
                                      driver.find_elements(By.CSS_SELECTOR, "table.ui-datepicker-calendar")
                    if on_details_page:
                        driver.back()
                        time.sleep(3.5)
                        try: 
                            WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.CSS_SELECTOR, location_buttons_selector)))
                            print("        Successfully back on location list page for re-scan.")
                        except TimeoutException:
                            print("        ERROR: Could not get back to location list page after processing. Breaking while loop for this appt type.")
                            locations_to_process_for_this_type.clear() 
                            break 
                    else:
                        print("        Not on details page, no back needed (or click/process failed early).")

                    if processed_any_location_in_while_loop: 
                        break 
                
                if not processed_any_location_in_while_loop and locations_to_process_for_this_type:
                    print(f"    Scanned all {len(all_page_buttons_now)} visible buttons but did not process any further needed locations.")
                    print(f"    Visible buttons were: {visible_button_names_on_page_pass[:10]}...") 
                    print(f"    Still need to process: {list(locations_to_process_for_this_type)[:10]}...")
                    print(f"    Ending processing for appt type '{appt_type_name}' as it seems stuck.")
                    break 
            
            print(f"Finished location processing for '{appt_type_name}'.")
            
        print("\n--- All appointment types processed ---")
        # time.sleep(1000000)

    except Exception as e_main:
        print(f"An critical unhandled error occurred in main: {e_main}")
        traceback.print_exc()
    finally:
        if driver: driver.quit(); print("Firefox driver quit.")

if __name__ == "__main__":
    main()
