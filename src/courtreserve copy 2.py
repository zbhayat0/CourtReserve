import json
from rich import print
import re
import traceback
from collections import defaultdict
from datetime import datetime, timedelta, time
from enum import Enum

import pandas as pd
import pytz
import requests
import streamlit as st
from streamlit.logger import get_logger

logger = get_logger(__name__)

PST_TIME_ZONE = 'America/New_York'
ORG_ID = 12207
CLUB_OPENING_HOURS = (7, 21)  # open, close hour
COURT_BOOKINGS_API_URL = 'https://memberschedulers.courtreserve.com/SchedulerApi/ReadExpandedApi'
COURT_RESERVATIONS_LANDING_PAGE_URL = 'https://app.courtreserve.com/Online/Reservations/Bookings'


class Location(Enum):
    HARD_TENNIS_1 = "Hard - Tennis Court #1"
    HARD_TENNIS_2 = "Hard - Tennis Court #2"
    PICKLEBALL_1A = "Pickleball - Pickleball 1A"
    PICKLEBALL_1B = "Pickleball - Pickleball 1B"
    PICKLEBALL_2A = "Pickleball - Pickleball 2A"
    PICKLEBALL_2B = "Pickleball - Pickleball 2B"


LOCATION_NAME_TO_ID_MAPPING = {
    Location.HARD_TENNIS_1.value: 46164,
    Location.HARD_TENNIS_2.value: 46165,
    Location.PICKLEBALL_1A.value: 46166,
    Location.PICKLEBALL_1B.value: 46167,
    Location.PICKLEBALL_2A.value: 46168,
    Location.PICKLEBALL_2B.value: 46169
}


def fetch_court_times_data(court_date: datetime):
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'origin': 'https://app.courtreserve.com',
        'priority': 'u=1, i',
        'referer': 'https://app.courtreserve.com/',
        'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
    utc_datetime = court_date.astimezone(pytz.utc)
    params = {
        'id': str(ORG_ID),
        'uiCulture': 'en-US',
        'sort': '',
        'group': '',
        'filter': '',
        'jsonData': json.dumps({
            'startDate': utc_datetime.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            'orgId': str(ORG_ID),
            'TimeZone': PST_TIME_ZONE,
            'Date': court_date.strftime('%a, %d %b %Y %H:%M:%S GMT'),
            'KendoDate': {'Year': court_date.year, 'Month': court_date.month, 'Day': court_date.day},
            'UiCulture': 'en-US',
            'CostTypeId': '88166',
            'CustomSchedulerId': '',  # Retrieves for all locations
            'ReservationMinInterval': '60',
            'SelectedCourtIds': '',  # Retrieves for all court numbers
            'SelectedInstructorIds': '',
            'MemberIds': '',
            'MemberFamilyId': '',
            'EmbedCodeId': '',
            'HideEmbedCodeReservationDetails': 'False'
        })
    }

    try:
        response = requests.get(COURT_BOOKINGS_API_URL, params=params, headers=headers)
        response.raise_for_status()  # Raise an exception for non-2xx status codes
        return response.json()['Data']
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching court times data: {e}")
        raise e



def get_available_court_times_by_location(court_date: datetime) -> dict:
    logger.info(f"Fetching reserved court times on {court_date}.")
    court_times = fetch_court_times_data(court_date)
    reserved_court_times_by_location = defaultdict(lambda: defaultdict(list))
    available_court_times_by_location = defaultdict(lambda: defaultdict(list))
    for item in court_times:
        court_location, court_number = get_court_location_and_name(item)

        if not item["EventOnlineSignUpOff"] and not item["CanSignUpToEvent"] and not item["RegistrationOpen"]:
            continue

        reserved_court_times_by_location[court_location][court_number].append(
            (get_reserved_court_start_end_times(item)))
        available_court_times_by_location[court_location][court_number] = []

    
    with open('data.json', 'w') as f:
        json.dump(reserved_court_times_by_location, f, indent=4, default=str)

    available_60min_intervals = generate_60min_intervals_end_time_inclusive(
        get_datetime_by_hour(court_date, CLUB_OPENING_HOURS[0], PST_TIME_ZONE),
        get_datetime_by_hour(court_date, CLUB_OPENING_HOURS[1], PST_TIME_ZONE))

    def is_overlapping(interval, reserved):
        start, end = interval, interval + timedelta(hours=1)
        res_start, res_end = reserved
        return max(start, res_start) < min(end, res_end)

    # Initialize all possible times as available
    for location, courts in reserved_court_times_by_location.items():
        for court in courts:
            available_court_times_by_location[location][court] = list(available_60min_intervals)

    # Remove reserved times
    for location, courts in reserved_court_times_by_location.items():
        for court, reserved_times in courts.items():
            available_court_times_by_location[location][court] = [
                [interval] for interval in available_court_times_by_location[location][court]
                if not any(is_overlapping(interval, reserved) for reserved in reserved_times)
            ]

    return available_court_times_by_location
    # for location, court_times_by_court_number in reserved_court_times_by_location.items():
    #     for court_number, reserved_court_times in court_times_by_court_number.items():
    #         available_court_times = []
    #         for i in range(len(available_60min_intervals) - 1):
    #             interval_start = available_60min_intervals[i]
    #             interval_end = available_60min_intervals[i + 1]

    #             is_available = True
    #             for reserved_start, reserved_end in reserved_court_times:
    #                 print(reserved_start, reserved_end, interval_start, interval_end)
    #                 if interval_end == reserved_end and interval_start == reserved_start:
    #                     is_available = False
    #                     print(location, court_number, 'broke')
    #                     break
                    
    #             if is_available:
    #                 available_court_times.append((interval_start, interval_end))
    #         available_court_times_by_location[location][court_number] = available_court_times
    # return available_court_times_by_location


def get_open_to_reseve_court_times(court_date: datetime) -> dict:
    availble_court_times = get_available_court_times_by_location(court_date)



def get_court_location_and_name(item: dict):
    court_label = item["CourtLabel"]
    space_delimited_court_label = court_label.split(' ')
    if len(space_delimited_court_label) == 3 and "COACHING" not in court_label.upper():  # e.g. "Mukilteo Pickleball 12"
        court_location = f"{space_delimited_court_label[0]} {space_delimited_court_label[1]}"
        court_number = space_delimited_court_label[2]
    else:
        court_location = space_delimited_court_label[0]
        court_number = space_delimited_court_label[1]
    return court_location, f"Court {court_number}"


def get_reserved_court_start_end_times(item: dict):
    start_utc = item["Start"][:-1]
    end_utc = item["End"][:-1]

    start_dt_utc = pytz.utc.localize(datetime.fromisoformat(start_utc))
    end_dt_utc = pytz.utc.localize(datetime.fromisoformat(end_utc))

    pst = pytz.timezone(PST_TIME_ZONE)

    return start_dt_utc.astimezone(pst), end_dt_utc.astimezone(pst)

def reserve_button_column_name(location: str):
    return location + ' Reserve'


def get_court_link(location_name: str, court_start: datetime):
    try:
        return get_bbc_court_reservation_page(get_location_id_by_name_and_start_hour(location_name, court_start))
    except Exception as e:
        logger.error(f"Unable to get a link for {location_name} - {type(e).__name__}: {str(e)}")
        logger.error(traceback.format_exc())  # Print the full traceback


def get_location_id_by_name_and_start_hour(location_name: str, court_start: datetime):
    try:
        # Check if it's Early Access
        if ((court_start.weekday() < 5 and court_start.time() < time(9, 0) or  # Weekdays before 9AM
             court_start.weekday() >= 6 and court_start.time() < time(8, 0)) and  # Weekends before 8AM
                "Pickleball" not in location_name):
            location_lookup_name = EARLY_ACCESS_PREFIX + location_name
        else:
            location_lookup_name = location_name
        location_id = LOCATION_NAME_TO_ID_MAPPING[location_lookup_name]
        return location_id
    except KeyError as e:
        logger.error(
            f"Unable to get location id for {location_name}. We only have mappings for {LOCATION_NAME_TO_ID_MAPPING.keys()}.")
        raise e


def get_bbc_court_reservation_page(location_id: int):
    return f"{COURT_RESERVATIONS_LANDING_PAGE_URL}/{ORG_ID}?sId={location_id}"


def get_duration_options(max_hours=4, increments_in_hours=0.5):
    duration_options = []
    for hour in range(1, int(max_hours / increments_in_hours) + 1):
        duration = hour * increments_in_hours
        duration_options.append(int(duration) if duration.is_integer() else duration)
    return duration_options


def display_time_range_picker():
    opening_time = get_time_by_hour(CLUB_OPENING_HOURS[0])
    closing_time = get_time_by_hour(CLUB_OPENING_HOURS[1])
    opening_datetime = to_pst_datetime(get_time_by_hour(CLUB_OPENING_HOURS[0]))
    closing_datetime = to_pst_datetime(get_time_by_hour(CLUB_OPENING_HOURS[1]))

    col1, col2 = st.columns(2)

    start_datetime = opening_datetime
    end_datetime = closing_datetime

    with col2:
        end_time_or_duration = st.radio("End time or Duration", ["End Time", "Duration"],
                                        index=1,
                                        captions=["Find open courts from [Start Time] to [End Time]",
                                                  "Find open courts for [Duration] starting at [Start Time]"],
                                        horizontal=True)

    with col1:
        st.write("Start Time")
        start_hour_col, start_min_col, start_am_pm_col = st.columns(3)
        with start_hour_col:
            start_hour = st.number_input("Hour", min_value=1, max_value=12, value=opening_time.hour, key="start_hour")
        with start_min_col:
            start_minute = st.selectbox("Minute", [0, 60], index=0 if opening_time.minute == 0 else 1, key="start_min")
        with start_am_pm_col:
            start_am_pm = st.selectbox("AM/PM", ["AM", "PM"], index=0 if opening_time.hour < 12 else 1, key="start_ampm")
        start_datetime = to_pst_datetime(time(start_hour if start_am_pm == "AM" else start_hour + 12, start_minute))

        if end_time_or_duration == "End Time":
            st.write("End Time")
            end_hour_col, end_min_col, end_am_pm_col = st.columns(3)
            with end_hour_col:
                end_hour = st.number_input("Hour", min_value=1, max_value=12, value=closing_time.hour % 12, key="end_hour")
            with end_min_col:
                end_minute = st.selectbox("Minute", [0, 60], index=0 if closing_time.minute == 0 else 1, key="end_min")
            with end_am_pm_col:
                end_am_pm = st.selectbox("AM/PM", ["AM", "PM"], index=0 if closing_time.hour < 12 else 1, key="end_ampm")
            end_datetime = to_pst_datetime(time(end_hour if end_am_pm == "AM" else end_hour + 12, end_minute))
        else:
            duration = st.selectbox("Duration (in hours)", options=get_duration_options(), index=1)
            if duration:
                end_datetime = start_datetime + timedelta(hours=duration)

    if end_datetime < start_datetime:
        st.warning("End time cannot be before start time. Please select a valid end time.")
    elif start_datetime < opening_datetime or end_datetime > closing_datetime:
        st.warning(f"You're trying to look for courts from {get_formatted_time((start_datetime))} to {get_formatted_time(end_datetime)}. "
                   f"Please select times/duration that falls between Opening ({get_formatted_time(opening_time)}) and Closing ({get_formatted_time(closing_time)}).")
    else:
        st.session_state.time_range_filter = (start_datetime, end_datetime)


############################################################################################
# Util
############################################################################################
def get_default_date_range_filter() -> tuple[datetime, datetime]:
    start_time = get_datetime_by_hour(st.session_state.date_input_datetime, CLUB_OPENING_HOURS[0], PST_TIME_ZONE)
    end_time = get_datetime_by_hour(st.session_state.date_input_datetime, CLUB_OPENING_HOURS[1], PST_TIME_ZONE)
    return start_time, end_time


def get_datetime_by_hour(date: datetime, hour: int, timezone: str):
    return pytz.timezone(timezone).localize(datetime.combine(date, time(hour=hour)))


def get_last_court_start_time(end_time: datetime):
    return end_time - timedelta(minutes=60)


def generate_60min_intervals_end_time_inclusive(start_time: datetime, end_time: datetime):
    intervals = []
    current_time = start_time
    while current_time <= end_time:
        intervals.append(current_time)
        current_time += timedelta(minutes=60)
    return intervals


def get_default_datetime():
    current_datetime = datetime.now(pytz.timezone(PST_TIME_ZONE))
    if current_datetime.time() > time(21, 30):  # Latest court time is 9:30 PM
        return current_datetime + timedelta(days=1)
    return current_datetime


def to_pst_datetime(utc_time: time):
    return pytz.timezone(PST_TIME_ZONE).localize(datetime.combine(st.session_state.date_input_datetime, utc_time))


def get_formatted_time(time_to_format):
    return time_to_format.strftime('%I:%M %p')


def get_formatted_time_by_hour(hour: int):
    return get_formatted_time(get_time_by_hour(hour))


def get_time_by_hour(hour: int):
    return time(hour, 0)


def get_court_number(court_name: str):
    match = re.search(r'\d+', court_name)
    if match:
        return int(match.group())
    else:
        return float('inf')




if __name__ == "__main__":
    # main()
    print(get_available_court_times_by_location(datetime(2024, 5, 24)))

    