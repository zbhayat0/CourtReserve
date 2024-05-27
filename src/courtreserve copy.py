import json
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

PST_TIME_ZONE = 'America/Los_Angeles'
BELLEVUE_BADMINTON_CLUB_ORG_ID = 7031
CLUB_OPENING_HOURS = (6, 22)  # open, close hour
COURT_BOOKINGS_API_URL = 'https://memberschedulers.courtreserve.com/SchedulerApi/ReadExpandedApi'
COURT_RESERVATIONS_LANDING_PAGE_URL = 'https://app.courtreserve.com/Online/Reservations/Bookings'


class BBCLocation(Enum):
    BELLEVUE = "Bellevue"
    MUKILTEO = "Mukilteo"
    RENTON = "Renton"
    MUKILTEO_PICKLEBALL = "Mukilteo Pickleball"

    @classmethod
    def get_all_locations(cls):
        return [location.value for location in BBCLocation]

    @classmethod
    def get_default_locations(cls):
        return [location.value for location in BBCLocation if location != BBCLocation.MUKILTEO_PICKLEBALL]


EARLY_ACCESS_PREFIX = "Early Access: "

LOCATION_NAME_TO_ID_MAPPING = {
    BBCLocation.BELLEVUE.value: 1476,
    BBCLocation.MUKILTEO.value: 1478,
    BBCLocation.RENTON.value: 1479,
    EARLY_ACCESS_PREFIX + BBCLocation.BELLEVUE.value: 1503,
    EARLY_ACCESS_PREFIX + BBCLocation.MUKILTEO.value: 1504,
    EARLY_ACCESS_PREFIX + BBCLocation.RENTON.value: 1505,
    BBCLocation.MUKILTEO_PICKLEBALL.value: 15460
}


############################################################################################
# Fetch data
############################################################################################
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
        'id': str(BELLEVUE_BADMINTON_CLUB_ORG_ID),
        'uiCulture': 'en-US',
        'sort': '',
        'group': '',
        'filter': '',
        'jsonData': json.dumps({
            'startDate': utc_datetime.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            'orgId': str(BELLEVUE_BADMINTON_CLUB_ORG_ID),
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
            'HideEmbedCodeReservationDetails': 'True'
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
        # Noticed there are these entries usually for Bellevue 10 and 11 that block 10 hours but don't actually
        # show up on CourtReserve. These are the fields that seem to differentiate them from other entries (when all
        # three fields are 'False').
        # Revisit this if we notice that this is causing reserved slots to get dropped.
        if not item["EventOnlineSignUpOff"] and not item["CanSignUpToEvent"] and not item["RegistrationOpen"]:
            continue

        court_location, court_number = get_court_location_and_name(item)
        reserved_court_times_by_location[court_location][court_number].append(
            (get_reserved_court_start_end_times(item)))
        available_court_times_by_location[court_location][court_number] = []

    available_30min_intervals = generate_30min_intervals_end_time_inclusive(
        get_datetime_by_hour(court_date, CLUB_OPENING_HOURS[0], PST_TIME_ZONE),
        get_datetime_by_hour(court_date, CLUB_OPENING_HOURS[1], PST_TIME_ZONE))

    for location, court_times_by_court_number in reserved_court_times_by_location.items():
        for court_number, reserved_court_times in court_times_by_court_number.items():
            available_court_times = []
            for i in range(len(available_30min_intervals) - 1):
                interval_start = available_30min_intervals[i]
                interval_end = available_30min_intervals[i + 1]
                is_available = True
                for reserved_start, reserved_end in reserved_court_times:
                    # Check if the interval is reserved
                    if interval_end <= reserved_start or interval_start >= reserved_end:
                        continue
                    else:
                        is_available = False
                        break
                if is_available:
                    available_court_times.append((interval_start, interval_end))
            available_court_times_by_location[location][court_number] = available_court_times
    return available_court_times_by_location


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


############################################################################################
# UI Data Refreshes
############################################################################################
def update_compact_view_available_court_times():
    if not st.session_state.df_by_location:
        return

    start_time = st.session_state.time_range_filter[0]
    end_time = st.session_state.time_range_filter[1]

    logger.info(f"Creating a compact view for {st.session_state.locations_filter}, from {start_time} to {end_time}.")
    intervals = pd.date_range(start=start_time, end=get_last_court_start_time(end_time), freq='30min')
    columns = sorted(
        st.session_state.locations_filter + [reserve_button_column_name(location) for location in st.session_state.locations_filter])

    compact_view_df = pd.DataFrame(index=intervals, columns=columns)
    for location in st.session_state.locations_filter:
        single_location_df = st.session_state.df_by_location[location]
        for index in compact_view_df.index:
            available_courts = []
            for court_number in single_location_df.columns:
                if not pd.isnull(single_location_df.loc[index.strftime('%I:%M %p'), court_number]):
                    available_courts.append(court_number)
            if available_courts:
                link = get_court_link(location, index)
                compact_view_df.at[index, reserve_button_column_name(location)] = link
            compact_view_df.at[index, location] = available_courts

    compact_view_df.index = compact_view_df.index.strftime('%I:%M %p')
    st.session_state.compact_view_df = compact_view_df


def update_available_courts_for_date():
    court_date = st.session_state.date_input_datetime
    available_court_times_by_location = get_available_court_times_by_location(court_date)
    for location, court_times_by_court_number in available_court_times_by_location.items():
        start_time, end_time = get_default_date_range_filter()
        intervals = pd.date_range(start=start_time, end=get_last_court_start_time(end_time), freq='30min')
        df = pd.DataFrame(index=intervals, columns=sorted(court_times_by_court_number.keys(), key=get_court_number))
        for court, times in court_times_by_court_number.items():
            for start, end in times:
                link = get_court_link(location, start)
                text = f"✓ {start.strftime('%I:%M %p')}"
                df.loc[(df.index >= start) & (df.index < end), court] = f"{link}&{text}"
        df.index = df.index.strftime('%I:%M %p')
        st.session_state.df_by_location[location] = df


############################################################################################
# UI Utils
############################################################################################
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
    return f"{COURT_RESERVATIONS_LANDING_PAGE_URL}/{BELLEVUE_BADMINTON_CLUB_ORG_ID}?sId={location_id}"


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
            start_minute = st.selectbox("Minute", [0, 30], index=0 if opening_time.minute == 0 else 1, key="start_min")
        with start_am_pm_col:
            start_am_pm = st.selectbox("AM/PM", ["AM", "PM"], index=0 if opening_time.hour < 12 else 1, key="start_ampm")
        start_datetime = to_pst_datetime(time(start_hour if start_am_pm == "AM" else start_hour + 12, start_minute))

        if end_time_or_duration == "End Time":
            st.write("End Time")
            end_hour_col, end_min_col, end_am_pm_col = st.columns(3)
            with end_hour_col:
                end_hour = st.number_input("Hour", min_value=1, max_value=12, value=closing_time.hour % 12, key="end_hour")
            with end_min_col:
                end_minute = st.selectbox("Minute", [0, 30], index=0 if closing_time.minute == 0 else 1, key="end_min")
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
    return end_time - timedelta(minutes=30)


def generate_30min_intervals_end_time_inclusive(start_time: datetime, end_time: datetime):
    intervals = []
    current_time = start_time
    while current_time <= end_time:
        intervals.append(current_time)
        current_time += timedelta(minutes=30)
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


############################################################################################
# Main App
############################################################################################
def main():
    try:
        st.set_page_config(page_title="BBC Court Finder", page_icon=":badminton_racquet_and_shuttlecock:", layout='wide')

        hide_menu_style = """
            <style>
                #MainMenu {visibility: hidden;}
                footer {visibility: hidden;}
            </style>
            """
        st.markdown(hide_menu_style, unsafe_allow_html=True)

        st.title("Find Available Courts @ BBC")

        # Initialize session states
        # (Streamlit reloads page on every input)
        if 'locations_filter' not in st.session_state:
            st.session_state.locations_filter = []
        if 'time_range_filter' not in st.session_state:
            st.session_state.time_range_filter = ()
        if 'date_input_datetime' not in st.session_state:
            st.session_state.date_input_datetime = None
        if 'df_by_location' not in st.session_state:
            st.session_state.df_by_location = {}
        if 'compact_view_df' not in st.session_state:
            st.session_state.compact_view_df = None

        current_datetime = get_default_datetime()
        date_input = st.date_input("Date", current_datetime,
                                   max_value=current_datetime + timedelta(days=30))

        st.session_state.date_input_datetime = pytz.timezone(PST_TIME_ZONE).localize(datetime.combine(date_input, datetime.min.time()))

        display_time_range_picker()

        update_available_courts_for_date()

        st.session_state.locations_filter = st.multiselect("Locations",
                                                           placeholder="Choose a location",
                                                           options=BBCLocation.get_all_locations(),
                                                           default=BBCLocation.get_default_locations())
        st.divider()

        update_compact_view_available_court_times()

        st.info("'✓ / Reserve' only links to the Reservations page on CourtReserve for each location. You'll need to manually set the date and find the available slot to reserve.")

        if st.session_state.compact_view_df is not None:
            st.write(f"### Available courts from {get_formatted_time(st.session_state.time_range_filter[0])} to "
                     f"{get_formatted_time(st.session_state.time_range_filter[1])} for {', '.join(st.session_state.locations_filter)}")
            with st.expander("How do I read/use this?"):
                st.write("- This is a filtered/compact view of the tables in the next section showing court-availability across locations.")
                st.write("- Each column is a BBC location.")
                st.write("- Each row lists the courts that should be open for reservation on CourtReserve at that starting time.")
                st.write("- 'Reserve' only links to the Reservations page on CourtReserve for each location. You'll need to manually set the date and find the available slot to reserve.")

            st.dataframe(st.session_state.compact_view_df,
                         column_config={reserve_button_column_name(location):
                                            st.column_config.LinkColumn(label=f"{location}",
                                                                        display_text="Reserve",
                                                                        help=f"This just links to the {location} Reservations page on CourtReserve. "
                                                                             f"You have to set the date in the calendar yourself and find the relevant slot to reserve.")
                                        for location in st.session_state.locations_filter})
            st.divider()

        if st.session_state.df_by_location:
            st.write(f"### Available courts from Opening ({get_formatted_time_by_hour(CLUB_OPENING_HOURS[0])}) to "
                     f"Close ({get_formatted_time_by_hour(CLUB_OPENING_HOURS[1])})")
            with st.expander("How do I read/use this?"):
                st.write("- These are the non-filtered court-availability views that should resemble the CourtReserve page when you click into specific locations under 'Reservations'.")
                st.write("- ✓ 07:00 AM - means a court should be open for reservation on CourtReserve with starting time at 07:00 AM. It only links to the Reservations page on CourtReserve for each location. You'll need to manually set the date and find the available slot to reserve.")
                st.write("- None - means the court is not available to be reserved at that time slot.")
            for location, df in st.session_state.df_by_location.items():
                st.write(f"#### :green[{location}]")

                # HACK!! to display a clickable <a href='{link}' target='_blank'>{text}</a>
                # The right way to have clickable links in dataframe is through: df.style.format(make_clickable).
                # Unfortunately st.dataframe() does not support this and does not render <a> tags properly: https://github.com/streamlit/streamlit/issues/4830
                # and displaying it in html is not as nice: st.markdown(df_styled.to_html(escape=False, render_links=True), unsafe_allow_html=True)
                #
                # Each cell in the dataframe contains f"{link}&{text}".
                # LinkColumn requires the cell values to be clickable link strings and limits the display_text to be a regex for extracting texts
                # in order to have cell-dependent texts.
                # So here we're extracting everything after '&', which should be the label.
                st.dataframe(df, column_config={column: st.column_config.LinkColumn(column,
                                                                                    display_text="&(.*)",
                                                                                    help=f"This just links to the {column} Reservations page on CourtReserve. "
                                                                                         f"You have to set the date in the calendar yourself and find the relevant slot to reserve.")
                                                for column in df.columns})
    except Exception as e:
        logger.error(f"{type(e).__name__}: {str(e)}")
        logger.error(traceback.format_exc())  # Print the full traceback
        st.error("Oops, something went wrong.")


if __name__ == "__main__":
    main()