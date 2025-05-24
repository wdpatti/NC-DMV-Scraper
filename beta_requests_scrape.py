import requests
from geopy.distance import distance as geopy_distance
from geopy.geocoders import Nominatim
from decimal import Decimal
import json
from datetime import datetime
import os
import time
from bs4 import BeautifulSoup
import random


# --- Configuration ---

# --- Notification Settings ---
YOUR_DISCORD_WEBHOOK_URL = os.getenv("YOUR_DISCORD_WEBHOOK_URL", "YOUR_WEBHOOK_URL_HERE")
PROOF_OF_LIFE = os.getenv("PROOF_OF_LIFE", "False").lower() == 'true'
INTRO_MESSAGE = os.getenv("INTRO_MESSAGE", "@everyone NCDMV Appointments Found at https://skiptheline.ncdot.gov/:\n")
MAX_DISCORD_MESSAGE_LENGTH = 1950

# --- Locations Data ---
# Path to your locations.json file
LOCATIONS_JSON_FILE = os.getenv("LOCATIONS_FILE_PATH", "locations.json")

# --- Scheduling ---
BASE_INTERVAL_MINUTES = os.getenv("BASE_INTERVAL_MINUTES", "1")
# For "10 minutes plus or minus 25 seconds":
RANDOM_OFFSET_SECONDS_MIN = os.getenv("RANDOM_OFFSET_SECONDS_MIN", "-25")
RANDOM_OFFSET_SECONDS_MAX = os.getenv("RANDOM_OFFSET_SECONDS_MAX", "25")

# --- Filtering Criteria from Environment ---
# For Distance
YOUR_ADDRESS = os.getenv("YOUR_ADDRESS")  # e.g., "123 Main St, Raleigh, NC"
DISTANCE_RANGE_MILES = os.getenv("DISTANCE_RANGE")  # e.g., "25"

# For Appointment Type
# User provides the string name, e.g., "Motorcycle Skills Test"
# APPOINTMENT_TYPE_NAME = os.getenv("APPOINTMENT_TYPE", "Driver License - First Time")
APPOINTMENT_TYPE_NAME = os.getenv("APPOINTMENT_TYPE", "Motorcycle Skills Test")

# For Date Range (Format: YYYY-MM-DD)
DATE_RANGE_START = os.getenv("DATE_RANGE_START")  # e.g., "2024-08-01"
DATE_RANGE_END = os.getenv("DATE_RANGE_END")      # e.g., "2024-08-31"

# For Time Range (Format: HH:MM in 24-hour)
TIME_RANGE_START = os.getenv("TIME_RANGE_START")  # e.g., "08:00"
TIME_RANGE_END = os.getenv("TIME_RANGE_END")      # e.g., "17:00"

# end of configuration.

TYPE_MAPPING = {
    1: "Driver License - First Time", 2: "Driver License Duplicate", 3: "Driver License Renewal",
    4: "Fees", 5: "ID Card", 6: "Knowledge/Computer Test", 7: "Legal Presence",
    8: "Motorcycle Skills Test", 9: "Permits", 10: "Teen Driver Level 1",
    11: "Teen Driver Level 2", 12: "Teen Driver Level 3", 13: "Non-CDL Road Test",
}

REVERSE_TYPE_MAPPING = {name: f"formJourney{num}" for num, name in TYPE_MAPPING.items()}

LOCATIONS_DATA_FILE = "locations.json"


def scrapelocations(type):
    with open(LOCATIONS_DATA_FILE, 'r') as f:
        all_locations_data = json.load(f)
    formJourney = (all_locations_data["fjbase"])
    data = {
        # this has been minimized, all of these are necessary.
        'StepId': '09004482-03df-4378-bce7-b39db9dc7711',
        'formJourney': formJourney,
        'StepControls[0].FieldName': 'ApptTypeIdPreUnit',  # not needed, but got really slow suddenly when i commented out? might be fluke.
        'StepControls[0].TargetTypeName': 'OABSEngine.StepControl, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[0].Model.ModelTypeName': 'OABSEngine.Models.QFlowObjectModel, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[0].StepControlId': '7225b493-d89c-4c14-b670-3f9c5bb24645',
        'StepControls[0].Model.Value': type,
        'StepControls[1].TargetTypeName': 'OABSEngine.StepControl, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[1].Model.ModelTypeName': 'OABSEngine.Models.ListItemModel, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[1].StepControlId': 'ede2f6a3-ff89-4412-b382-8cd2e4ff10d3',
        'StepControls[1].Step.StepId': '418e99e5-dd8c-4dc0-b25b-6504ca5217f6',
        'StepControls[2].TargetTypeName': 'OABSEngine.StepControl, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[2].Model.ModelTypeName': 'OABSEngine.Models.CustomerLocationModel, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[2].StepControlId': '2e1c2c27-af0d-40d2-b350-eacdb995d6dd',
    }

    while True:
        errors = 0
        try:
            response = requests.post(
                'https://skiptheline.ncdot.gov/Webapp/Appointment/Index/a7ade79b-996d-4971-8766-97feb75254de',
                data=data,
                timeout=20
            )
            if "<title>500 Application Error</title>" in response.text:
                print("we ran into a 500 error, fuuuck bro")
                return -1
            if "UnitIdList" in response.text:
                break
            # sleep(.5)
        except Exception as e:
            if errors > 5:
                print("over 5 errors idiot stpuid fuck!!!!")
                print(e)
                return -1
            errors += 1
            time.sleep(.5)
    soup = BeautifulSoup(response.text, 'html.parser')
    active_location_names = []

    location_item_divs = soup.find_all('div', class_='QflowObjectItem')
    if not location_item_divs:
        return []

    for loc_div in location_item_divs:
        classes = loc_div.get('class', [])
        if 'Active-Unit' in classes and 'disabled-unit' not in classes:
            name_container = loc_div.find('div', recursive=False)
            if name_container:
                location_name_tag = name_container.find('div', recursive=False)
                if location_name_tag and location_name_tag.string:
                    location_name = location_name_tag.string.strip()
                    active_location_names.append(location_name)
    return active_location_names


def scrapeday(date, formJourney):
    params = {
        'stepControlTriggerId': '919c2e66-f9d4-44a3-9a11-c271d12d8f3c',
        'targetStepControlId': '39f2cb09-28e2-41bf-9f8e-8c8057cbdb93',
    }

    data = {
        # this has been minimized, all of these are necessary
        'StepId': '34cc0d43-4c99-42ea-abec-e639d2e1180b',
        'formJourney': formJourney,
        'StepControls[0].TargetTypeName': 'OABSEngine.StepControl, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',  # neeeded
        'StepControls[0].Model.ModelTypeName': 'OABSEngine.Models.ListItemModel, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[0].StepControlId': 'da1fb91a-c5cb-487f-b293-44c71ffeb1ec',
        'StepControls[1].TargetTypeName': 'OABSEngine.StepControl, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[1].Model.ModelTypeName': 'OABSEngine.Models.ListItemModel, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[1].StepControlId': '547650da-008d-4fd0-a164-31a489a44e94',
        'StepControls[2].TargetTypeName': 'OABSEngine.StepControl, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[2].Model.ModelTypeName': 'OABSEngine.Models.CalendarDateModel, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[2].StepControlId': '919c2e66-f9d4-44a3-9a11-c271d12d8f3c',
        'StepControls[2].Model.Value': date,
        'StepControls[3].TargetTypeName': 'OABSEngine.StepControl, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[3].Model.ModelTypeName': 'OABSEngine.Models.TimeSlotModel, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[3].StepControlId': '39f2cb09-28e2-41bf-9f8e-8c8057cbdb93',
        'StepControls[4].TargetTypeName': 'OABSEngine.StepControl, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[4].Model.ModelTypeName': 'OABSEngine.Models.ListItemModel, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[4].StepControlId': 'fc6c2f34-0580-4a8a-8c0b-dbb316e1a6d7',

    }

    while True:
        errors = 0
        try:
            response = requests.post('https://skiptheline.ncdot.gov/Webapp/Appointment/AmendStep', params=params, data=data, timeout=20)
            if "<title>500 Application Error</title>" in response.text:
                print("we ran into a 500 error, fuuuck bro")
                return -1
            if "data-datetime" in response.text:
                break
        except Exception as e:
            if errors > 5:
                print("over 5 errors idiot stpuid fuck!!!!")
                print(e)
                return -1
            errors += 1
            time.sleep(.5)

    soup = BeautifulSoup(response.text, 'html.parser')
    parsed_datetime_objects = []
    option_tags = soup.find_all('option', attrs={'data-datetime': True})
    if not option_tags:
        return -1

    found_valid_time = False
    for option in option_tags:
        datetime_str = option.get('data-datetime')
        if datetime_str and datetime_str.strip():
            try:
                dt_object = datetime.strptime(datetime_str, "%m/%d/%Y %I:%M:%S %p")
                parsed_datetime_objects.append(dt_object)
                found_valid_time = True
            except ValueError:
                pass
    if not found_valid_time:
        return -1
    if not parsed_datetime_objects:
        return -1

    parsed_datetime_objects.sort()

    final_time_strings = []
    seen_formatted_times = set()
    for dt_obj in parsed_datetime_objects:
        time_str = dt_obj.strftime("%I:%M %p")
        # print(time_str)
        if time_str.startswith("0"):
            time_str = time_str[1:]
        if time_str not in seen_formatted_times:
            final_time_strings.append(time_str)
            seen_formatted_times.add(time_str)
    return final_time_strings


def scrapeavailabledays(id, formJourney):
    data = {
        # this has been minimized, all of these are necessary
        'StepId': 'd7147c7b-b911-44a1-9ebd-809506b78cae',
        'formJourney': formJourney,
        'StepControls[0].TargetTypeName': 'OABSEngine.StepControl, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[0].Model.ModelTypeName': 'OABSEngine.Models.ListItemModel, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[0].StepControlId': 'ab66e42f-812f-4cdf-90fd-55456865e085',
        'StepControls[1].TargetTypeName': 'OABSEngine.StepControl, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[1].Model.ModelTypeName': 'OABSEngine.Models.StringModel, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[1].StepControlId': 'aa34462f-6355-4518-82b1-bdf84f068dfa',
        'StepControls[2].TargetTypeName': 'OABSEngine.StepControl, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[2].Model.ModelTypeName': 'OABSEngine.Models.ListItemModel, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[2].StepControlId': 'd9eb34df-9d86-4730-ae38-694b51ae2785',
        'StepControls[3].TargetTypeName': 'OABSEngine.StepControl, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[3].Model.ModelTypeName': 'OABSEngine.Models.QFlowObjectModel, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[3].StepControlId': 'f758c6da-46ae-4e42-bb78-84fecb432a90',
        'StepControls[3].Model.Value': id,
        'StepControls[4].TargetTypeName': 'OABSEngine.StepControl, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[4].Model.ModelTypeName': 'OABSEngine.Models.ListItemModel, OABSEngine, Version=2.29.47.104, Culture=neutral, PublicKeyToken=null',
        'StepControls[4].StepControlId': 'b556eac8-0619-42e9-89cc-5a003b646092',
    }

    errors = 0
    while True:
        try:
            response = requests.post(
                'https://skiptheline.ncdot.gov/Webapp/Appointment/Index/a7ade79b-996d-4971-8766-97feb75254de',
                data=data, timeout=20
            )
            if "var Dates" in response.text:
                break
            errors += 1
            if errors > 6:
                print("never found var dates... odd")
                print(response.text)
                return -1
        except Exception as e:
            if errors > 5:
                print(e)
                return -1
            time.sleep(.5)
            errors += 1
    idx_start_marker = response.text.find("var Dates = ")
    if idx_start_marker == -1:
        print("scrapeavailabledays: 'var Dates = ' marker not found.")
        return -1

    idx_array_content_start = idx_start_marker + len("var Dates = ")

    idx_semicolon = response.text.find("];", idx_array_content_start)
    if idx_semicolon == -1:
        print("scrapeavailabledays: Array end marker '];' not found.")
        return -1
    date_array_string_for_json = response.text[idx_array_content_start:idx_semicolon + 1]

    try:
        datearray = json.loads(date_array_string_for_json)
    except json.JSONDecodeError as e:
        print(f"scrapeavailabledays: Failed to parse date array with json.loads. String: '{date_array_string_for_json[:100]}...'. Error: {e}")
        return -1
    except Exception as e:
        print(f"scrapeavailabledays: Unexpected error during json.loads. Error: {e}")
        return -1
    return datearray


TYPE_MAPPING = {
    1: "Driver License - First Time",
    2: "Driver License Duplicate",
    3: "Driver License Renewal",
    4: "Fees",
    5: "ID Card",
    6: "Knowledge/Computer Test",
    7: "Legal Presence",
    8: "Motorcycle Skills Test",
    9: "Permits",
    10: "Teen Driver Level 1",
    11: "Teen Driver Level 2",
    12: "Teen Driver Level 3",
    13: "Non-CDL Road Test",
}


def get_locations_within_distance(user_address_str, max_distance_miles_str, all_locations_data):
    if not user_address_str or not max_distance_miles_str:
        print("  Distance filtering skipped as address or range not provided.")
        return None, None

    try:
        max_distance_miles = Decimal(max_distance_miles_str)
        if max_distance_miles <= 0:
            print("  Distance range must be a positive number. Skipping distance filtering.")
            return None, None
    except ValueError:
        print("  Invalid distance range. Must be a number. Skipping distance filtering.")
        return None, None

    try:
        geolocator = Nominatim(user_agent="dmvscraper/1.0")
        print(f"  Geocoding your address: '{user_address_str}'...")
        user_location_geo = geolocator.geocode(user_address_str, timeout=10)
        if not user_location_geo:
            print(f"  Could not geocode your address '{user_address_str}'. Checking all locations. Please try some  other addresses near you.")
            return None, None
        user_coords = (user_location_geo.latitude, user_location_geo.longitude)
        user_coords_str = f"({user_coords[0]:.4f}, {user_coords[1]:.4f})"
        print(f"  Your geocoded coordinates: {user_coords_str}")
    except Exception as e:
        print(f"  Error geocoding your address '{user_address_str}': {e}. Checking all locations.")
        return None, None

    allowed_location_names = set()
    print("  Calculating distances to DMV locations...")
    for location_name, location_data in all_locations_data.items():
        try:
            if "coordinates" not in location_data or not isinstance(location_data["coordinates"], list) or len(location_data["coordinates"]) != 2:
                continue
            loc_coords = tuple(location_data["coordinates"])
            dist_miles = Decimal(geopy_distance(user_coords, loc_coords).miles)

            if dist_miles <= max_distance_miles:
                allowed_location_names.add(location_name)

        except Exception as e:
            print(f"    Warning: Error processing distance for {location_name}: {e}")
            continue
    if not allowed_location_names:
        print(f"  No locations found within {max_distance_miles} miles of your address.")
    else:
        print(f"  Found {len(allowed_location_names)} locations within {max_distance_miles} miles.")

    return allowed_location_names, user_coords_str


def send_discord_notification(webhook_url, message_content_to_send):
    if not webhook_url or webhook_url == "YOUR_WEBHOOK_URL_HERE":
        print("Webhook URL not configured. Skipping notification.")
        return

    if message_content_to_send is None:
        if PROOF_OF_LIFE:
            print("Sending proof-of-life notification (no appointments found).")
            payload = {"content": "No valid NCDMV appointments found at this time matching your criteria."}
            try:
                requests.post(webhook_url, json=payload, timeout=10)
            except requests.exceptions.RequestException as e:
                print(f"Error sending proof-of-life notification: {e}")
            return
        else:
            print("No appointments found and PROOF_OF_LIFE is False. No notification sent.")
            return

    full_message = INTRO_MESSAGE + message_content_to_send
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
                message_chunks[-1] += "\n... (message split)"

    print(f"Sending notification in {len(message_chunks)} chunk(s)...")
    success_all_chunks = True
    if "https://ntfy.sh/" in webhook_url:
        try:
            response = requests.post(webhook_url, data=full_message.encode('utf-8'), timeout=10, headers={"Markdown": "yes", "Title": "NCDMV Appointments"})
            response.raise_for_status()
            print("ntfy notification sent successfully.")
        except requests.exceptions.RequestException as e:
            print(f"Error sending ntfy notification: {e}")
            success_all_chunks = False
        except Exception as e:
            print(f"An unexpected error occurred during ntfy notification: {e}")
            success_all_chunks = False
    else:  # Discord webhook handling
        for i, chunk in enumerate(message_chunks):
            payload = {"content": chunk}
            try:
                response = requests.post(webhook_url, json=payload, timeout=15)
                response.raise_for_status()
                print(f"Discord notification chunk {i+1}/{len(message_chunks)} sent successfully.")
                if i < len(message_chunks) - 1:  # if not the last chunk, pause briefly
                    time.sleep(1)
            except requests.exceptions.RequestException as e:
                print(f"Error sending Discord notification chunk {i+1}: {e}")
                print(f"Response content: {response.text if 'response' in locals() else 'N/A'}")
                success_all_chunks = False
                break
            except Exception as e:
                print(f"An unexpected error occurred during Discord notification chunk {i+1}: {e}")
                success_all_chunks = False
                break
    if success_all_chunks:
        print("All notification chunks processed successfully.")
    else:
        print("Failed to send all/some notification chunks.")


def get_appointments(all_locations_master_data, configs):
    appointment_type_display_name = configs['appointment_type']
    current_form_journey = configs['form_journey']
    appointment_type_id_for_initial_scrape = configs['appointment_type_id_for_scrape']

    filter_start_date_obj = configs.get('filter_start_date')
    filter_end_date_obj = configs.get('filter_end_date')
    is_date_filter_active = configs.get('is_date_filter_active', False)
    filter_start_time_obj = configs.get('filter_start_time')
    filter_end_time_obj = configs.get('filter_end_time')
    is_time_filter_active = configs.get('is_time_filter_active', False)

    total_notification_string = ""

    print(f"Fetching current list of active locations for type ID: {appointment_type_id_for_initial_scrape}...")
    locations_active_on_site = []
    try:
        locations_from_scrapelocations = scrapelocations(appointment_type_id_for_initial_scrape)
        if locations_from_scrapelocations == -1:
            print("Warning: scrapelocations returned an error. Fallback initiated.")
            if configs.get('is_distance_filter_active', False):
                locations_active_on_site = list(configs.get('locations_allowed_by_distance', []) or [])
            else:
                locations_active_on_site = list(all_locations_master_data.keys())
                print("Warning: scrapelocations failed and no distance filter. Will check all locations from JSON.")
        elif not locations_from_scrapelocations:
            print("Info: scrapelocations found 0 initially active locations. No appointments for this run.")
            locations_active_on_site = []
        else:
            locations_active_on_site = locations_from_scrapelocations
            print(f"Found {len(locations_active_on_site)} initially active locations from site listing for this run.")
    except Exception as e:
        print(f"Critical Error during scrapelocations for this run: {e}. Skipping detailed checks.")
        return ""

    candidate_locations_after_prefilters = set(locations_active_on_site)
    if configs.get('is_distance_filter_active', False):
        distance_filtered_set = configs.get('locations_allowed_by_distance')
        if distance_filtered_set is not None:
            candidate_locations_after_prefilters.intersection_update(distance_filtered_set)
            print(f"After distance filter, {len(candidate_locations_after_prefilters)} candidate locations remain.")

    summary_parts = []
    if configs.get('is_distance_filter_active', False):
        summary_parts.append(f"dist ({configs.get('max_distance_for_display', 'N/A')}mi of '{configs.get('user_address_for_display', 'N/A')}')")
    if is_date_filter_active:
        start_date_display = filter_start_date_obj.strftime('%Y-%m-%d') if filter_start_date_obj else 'any'
        end_date_display = filter_end_date_obj.strftime('%Y-%m-%d') if filter_end_date_obj else 'any'
        summary_parts.append(f"date ({start_date_display} to {end_date_display})")
    if is_time_filter_active:
        start_time_display = filter_start_time_obj.strftime('%H:%M') if filter_start_time_obj else 'any'
        end_time_display = filter_end_time_obj.strftime('%H:%M') if filter_end_time_obj else 'any'
        summary_parts.append(f"time ({start_time_display} to {end_time_display})")

    filter_summary_text = ""
    if summary_parts:
        filter_summary_text = f" (filters: {'; '.join(summary_parts)})"

    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- Searching for '{appointment_type_display_name}' appointments{filter_summary_text} ---")

    sorted_locations_for_detailed_check = sorted(list(candidate_locations_after_prefilters))
    print(f"Will check {len(sorted_locations_for_detailed_check)} pre-filtered locations (sorted alphabetically) for details.")

    any_appointments_found_overall = False

    if not sorted_locations_for_detailed_check:
        print("No locations to check after applying pre-filters for this run.")

    for location_name_being_checked in sorted_locations_for_detailed_check:
        if location_name_being_checked not in all_locations_master_data:
            print(f"Warning: Location '{location_name_being_checked}' not found in main locations.json. Skipping.")
            continue

        current_location_details = all_locations_master_data[location_name_being_checked]
        current_location_id = current_location_details.get("id")
        location_form_journeys = current_location_details.get("formJourneys", {})

        if not current_location_id or current_form_journey not in location_form_journeys:
            continue

        journey_specific_content_map = location_form_journeys[current_form_journey]
        actual_journey_content_payload = journey_specific_content_map.get("journeyContent")

        if not actual_journey_content_payload or actual_journey_content_payload.startswith("Placeholder:"):
            continue

        print(f"\n--- Checking Location: {location_name_being_checked} ---")

        days_available_from_site = scrapeavailabledays(current_location_id, actual_journey_content_payload)
        all_valid_appointment_datetimes_for_this_location = []

        if days_available_from_site and days_available_from_site != -1:
            days_passing_date_range_filter = []
            for date_string_from_site in days_available_from_site:
                try:
                    date_object_for_comparison = datetime.strptime(date_string_from_site, "%Y-%m-%d").date()
                except ValueError:
                    continue

                passes_date_filter = True
                if is_date_filter_active:
                    if filter_start_date_obj and date_object_for_comparison < filter_start_date_obj:
                        passes_date_filter = False
                    if passes_date_filter and filter_end_date_obj and date_object_for_comparison > filter_end_date_obj:
                        passes_date_filter = False

                if passes_date_filter:
                    days_passing_date_range_filter.append(date_string_from_site)

            for date_to_get_times_for in days_passing_date_range_filter:
                time_strings_from_day_scrape = scrapeday(date_to_get_times_for, actual_journey_content_payload)
                if time_strings_from_day_scrape and time_strings_from_day_scrape != -1:
                    for time_string_candidate in time_strings_from_day_scrape:
                        passes_time_filter = True
                        try:
                            try:
                                temp_dt_for_filtering = datetime.strptime(f"{date_to_get_times_for} {time_string_candidate}", "%Y-%m-%d %I:%M:%S %p")
                            except ValueError:
                                temp_dt_for_filtering = datetime.strptime(f"{date_to_get_times_for} {time_string_candidate}", "%Y-%m-%d %I:%M %p")

                            time_object_for_comparison = temp_dt_for_filtering.time()

                            if is_time_filter_active:
                                if filter_start_time_obj and time_object_for_comparison < filter_start_time_obj:
                                    passes_time_filter = False
                                if passes_time_filter and filter_end_time_obj and time_object_for_comparison > filter_end_time_obj:
                                    passes_time_filter = False
                        except ValueError:
                            passes_time_filter = False

                        if passes_time_filter:
                            all_valid_appointment_datetimes_for_this_location.append(temp_dt_for_filtering)
        if all_valid_appointment_datetimes_for_this_location:
            any_appointments_found_overall = True
            all_valid_appointment_datetimes_for_this_location.sort()
            location_specific_output_string = f"**Location: {location_name_being_checked}**\n"
            for appointment_dt in all_valid_appointment_datetimes_for_this_location:
                # Format: M/D/YYYY H:MM:SS AM/PM, (e.g., 7/23/2025 2:45:00 PM,)
                time_str_maybe_padded_hour = appointment_dt.strftime('%I:%M:%S %p')

                final_time_str_part = ""
                if time_str_maybe_padded_hour.startswith('0'):
                    final_time_str_part = time_str_maybe_padded_hour[1:]
                else:
                    final_time_str_part = time_str_maybe_padded_hour

                appointment_line = f"*  {appointment_dt.month}/{appointment_dt.day}/{appointment_dt.year} {final_time_str_part},\n"
                location_specific_output_string += appointment_line

            print(location_specific_output_string.strip())

            if total_notification_string:
                total_notification_string += "\n"
            total_notification_string += location_specific_output_string
        else:
            print("    No appointments found matching all filters at this location.")

    if not any_appointments_found_overall:
        console_summary_message = f"\n--- No appointments found for '{appointment_type_display_name}'"
        if summary_parts:
            console_summary_message += " matching all specified filters"
        console_summary_message += " across checked locations for this run. ---"
        print(console_summary_message)
    else:
        print(f"\n--- Finished checking locations for '{appointment_type_display_name}' for this run. ---")

    return total_notification_string.strip()


def parse_and_validate_configs(all_location_details):
    print("--- Parsing User-Defined Configurations ---")
    configs = {}
    appointment_type_numeric_id = None

    configs['appointment_type'] = APPOINTMENT_TYPE_NAME
    if APPOINTMENT_TYPE_NAME in REVERSE_TYPE_MAPPING:
        configs['form_journey'] = REVERSE_TYPE_MAPPING[APPOINTMENT_TYPE_NAME]
        for num_id, name_val in TYPE_MAPPING.items():
            if name_val == APPOINTMENT_TYPE_NAME:
                appointment_type_numeric_id = num_id
                break
        configs['appointment_type_id_for_scrape'] = appointment_type_numeric_id
        print(f"Appointment Type: '{configs['appointment_type']}' (Journey: {configs['form_journey']}, ID: {appointment_type_numeric_id})")
    else:
        print(f"ERROR: Invalid APPOINTMENT_TYPE_NAME '{APPOINTMENT_TYPE_NAME}'. Not found in TYPE_MAPPING.")
        exit(1)
    if configs['appointment_type_id_for_scrape'] is None:
        print(f"ERROR: Could not derive numeric ID for type '{APPOINTMENT_TYPE_NAME}'.")
        exit(1)

    allowed_locations_by_dist, geocoded_user_address = get_locations_within_distance(
        YOUR_ADDRESS, DISTANCE_RANGE_MILES, all_location_details
    )
    configs['locations_allowed_by_distance'] = allowed_locations_by_dist
    configs['is_distance_filter_active'] = allowed_locations_by_dist is not None
    configs['user_address_for_display'] = YOUR_ADDRESS if configs['is_distance_filter_active'] else ""
    configs['max_distance_for_display'] = DISTANCE_RANGE_MILES if configs['is_distance_filter_active'] else ""
    configs['geocoded_address_for_display'] = geocoded_user_address if configs['is_distance_filter_active'] else ""

    if configs['is_distance_filter_active']:
        print(f"Distance Filter: Active, for address '{YOUR_ADDRESS}', range '{DISTANCE_RANGE_MILES}' miles.")
        if allowed_locations_by_dist is not None and not allowed_locations_by_dist:
            print("  Note: Distance filter active, but 0 locations found within range from your locations.json.")
    else:
        print("Distance Filter: Inactive (YOUR_ADDRESS or DISTANCE_RANGE_MILES not set or invalid).")

    configs['is_date_filter_active'] = False
    configs['filter_start_date'] = None
    configs['filter_end_date'] = None

    date_format_expected = "%Y-%m-%d"
    if DATE_RANGE_START:
        try:
            configs['filter_start_date'] = datetime.strptime(DATE_RANGE_START, date_format_expected).date()
            configs['is_date_filter_active'] = True
        except ValueError:
            print(f"Warning: Invalid DATE_RANGE_START format ('{DATE_RANGE_START}'). Expected YYYY-MM-DD.")
    if DATE_RANGE_END:
        try:
            configs['filter_end_date'] = datetime.strptime(DATE_RANGE_END, date_format_expected).date()
            configs['is_date_filter_active'] = True
        except ValueError:
            print(f"Warning: Invalid DATE_RANGE_END format ('{DATE_RANGE_END}'). Expected YYYY-MM-DD.")
    if configs['filter_start_date'] and configs['filter_end_date'] and \
       configs['filter_end_date'] < configs['filter_start_date']:
        print("Warning: DATE_RANGE_END is before DATE_RANGE_START.")
    if configs['is_date_filter_active']:
        print(f"Date Filter: Active. Start: {configs['filter_start_date'] or 'Any'}, End: {configs['filter_end_date'] or 'Any'}")
    else:
        print("Date Filter: Inactive.")

    configs['is_time_filter_active'] = False
    configs['filter_start_time'] = None
    configs['filter_end_time'] = None
    time_format_expected = "%H:%M"
    if TIME_RANGE_START:
        try:
            configs['filter_start_time'] = datetime.strptime(TIME_RANGE_START, time_format_expected).time()
            configs['is_time_filter_active'] = True
        except ValueError:
            print(f"Warning: Invalid TIME_RANGE_START format ('{TIME_RANGE_START}'). Expected HH:MM.")
    if TIME_RANGE_END:
        try:
            configs['filter_end_time'] = datetime.strptime(TIME_RANGE_END, time_format_expected).time()
            configs['is_time_filter_active'] = True
        except ValueError:
            print(f"Warning: Invalid TIME_RANGE_END format ('{TIME_RANGE_END}'). Expected HH:MM.")

    if configs['filter_start_time'] and configs['filter_end_time'] and \
       configs['filter_end_time'] <= configs['filter_start_time']:
        print("Warning: TIME_RANGE_END is not after TIME_RANGE_START.")
    if configs['is_time_filter_active']:
        print(f"Time Filter: Active. Start: {configs['filter_start_time'] or 'Any'}, End: {configs['filter_end_time'] or 'Any'}")
    else:
        print("Time Filter: Inactive.")
    print("--- User-Defined Configuration Parsing Complete ---")
    return configs


if __name__ == "__main__":
    try:
        base_interval_seconds = int(BASE_INTERVAL_MINUTES) * 60
        random_offset_min_s = int(RANDOM_OFFSET_SECONDS_MIN)
        random_offset_max_s = int(RANDOM_OFFSET_SECONDS_MAX)
        if random_offset_min_s > random_offset_max_s:
            print("Warning: RANDOM_OFFSET_SECONDS_MIN is greater than MAX. Using MIN value for both.")
            random_offset_max_s = random_offset_min_s
    except ValueError:
        print("Error: Invalid format for interval/offset ENV variables. Using defaults (10min +/- 25s).")
        base_interval_seconds = 10 * 60
        random_offset_min_s = -25
        random_offset_max_s = 25

    if not os.path.exists(LOCATIONS_JSON_FILE):
        print(f"ERROR: {LOCATIONS_JSON_FILE} not found. Make you are running scrape.py from the same directory that locations.json is in.")
        exit()
    try:
        with open(LOCATIONS_JSON_FILE, 'r') as f:
            all_locations_data_main = json.load(f)
        print(f"Loaded location data from '{LOCATIONS_JSON_FILE}'. ({len(all_locations_data_main)} locations)")
    except Exception as e:
        print(f"Error loading or parsing '{LOCATIONS_JSON_FILE}': {e}")
        exit(1)

    if YOUR_DISCORD_WEBHOOK_URL == "YOUR_WEBHOOK_URL_HERE":
        print("!!! WARNING: Discord webhook URL is not set. Notifications will be skipped. !!!")

    config = parse_and_validate_configs(all_locations_data_main)
    run_count = 0
    total_run_duration_seconds = 0.0 

    try:
        while True:
            run_count += 1
            print(f"\n==================== Starting Run #{run_count} ====================")
            run_start_time = time.monotonic()

            notification_payload_data = get_appointments(
                all_locations_data_main,
                config
            )
            run_end_time = time.monotonic()
            current_run_duration_seconds = run_end_time - run_start_time
            total_run_duration_seconds += current_run_duration_seconds
            average_run_duration_seconds = total_run_duration_seconds / run_count

            if notification_payload_data:
                send_discord_notification(YOUR_DISCORD_WEBHOOK_URL, notification_payload_data)
            else:
                send_discord_notification(YOUR_DISCORD_WEBHOOK_URL, None)
            random_offset = random.uniform(random_offset_min_s, random_offset_max_s)
            total_sleep_seconds = base_interval_seconds + random_offset
            if total_sleep_seconds < 1:
                total_sleep_seconds = 1
            print(f"\n--- Run #{run_count} finished. ---")
            print(f"Time taken for this run: {current_run_duration_seconds:.2f} seconds.")
            print(f"Average run time over {run_count} run(s): {average_run_duration_seconds:.2f} seconds.")
            sleep_minutes = int(total_sleep_seconds // 60)
            sleep_seconds_rem = int(total_sleep_seconds % 60)
            print(f"Next check in approximately {sleep_minutes} minutes and {sleep_seconds_rem} seconds.")
            print(f"(Base: {base_interval_seconds//60}min, Offset range: [{random_offset_min_s}s, {random_offset_max_s}s], Actual offset: {random_offset:.2f}s)")
            print("==========================================================")
            time.sleep(total_sleep_seconds)

    except KeyboardInterrupt:
        print("\nCtrl+C detected. Exiting scraper.")
    except Exception as e:
        print(f"\nAn unexpected error occurred in the main loop: {type(e).__name__} - {e}")
        import traceback
        traceback.print_exc()
        print("Exiting.")
    finally:
        print("Scraper shut down.")
        if run_count > 0:
            final_average = total_run_duration_seconds / run_count
            print(f"Final average run time over {run_count} run(s): {final_average:.2f} seconds.")
