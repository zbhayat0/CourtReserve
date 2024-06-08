from datetime import datetime, time, timedelta
from pytz import timezone
from enum import Enum
import json

# UTC Timezone
TIME_ZONE = "UTC"
START_HOUR = 11 # 11 AM UTC

ORG_ID = 12207
OPEN, CLOSE = (7, 21) # (7 AM, 9 PM)
COURT_BOOKINGS_API_URL = 'https://memberschedulers.courtreserve.com/SchedulerApi/ReadExpandedApi'
COURT_RESERVATIONS_LANDING_PAGE_URL = 'https://app.courtreserve.com/Online/Reservations/Bookings'


class Location(Enum):
    HARD_TENNIS_1 = "Hard - Tennis Court #1"
    HARD_TENNIS_2 = "Hard - Tennis Court #2"
    PICKLEBALL_1A = "Pickleball - Pickleball 1A"
    PICKLEBALL_1B = "Pickleball - Pickleball 1B"
    PICKLEBALL_2A = "Pickleball - Pickleball 2A"
    PICKLEBALL_2B = "Pickleball - Pickleball 2B"

    @property
    def id(self) -> int:
        return LOCATION_NAME_TO_ID_MAPPING[self.value]

    @property
    def court_type(self) -> str:
        return self.value.split(" - ")[1].split(" ")[0] # Pickleball/Tennis

    @property
    def court_label(self) -> str:
        return self.value.split(" - ")[1]
    

LOCATION_NAME_TO_ID_MAPPING = {
    Location.HARD_TENNIS_1.value: 46164,
    Location.HARD_TENNIS_2.value: 46165,
    Location.PICKLEBALL_1A.value: 46166,
    Location.PICKLEBALL_1B.value: 46167,
    Location.PICKLEBALL_2A.value: 46168,
    Location.PICKLEBALL_2B.value: 46169
}

LOCATION_ID_TO_LOCATION_MAPPING = {v: Location(k) for k, v in LOCATION_NAME_TO_ID_MAPPING.items()}


zafar_details = {
    'member_id': '5663355',
    'org_member_id': '4442712',
    'first_name': 'Zafar',
    'last_name': 'Bhayat',
    'email': 'zbhayat0@gmail.com',
    'membership_number': '1138'

}

michael_details = {
    'member_id': '5663625',
    'org_member_id': '4443056',
    'first_name': 'Michael',
    'last_name': 'Buffolino',
    'email': 'michaelbuffolino1@gmail.com',
    'membership_number': '1159'
}





def get_available_hours():
    return [(time(hour, 0), time(hour+1, 0)) for hour in range(OPEN, CLOSE + 1)]

def get_available_days() -> list[datetime]:
    # days to reserve in advance
    # only two days in advance
    # new day starts from 11AM UTC

    days = []
    today = datetime.now(timezone(TIME_ZONE))
    if today.hour < START_HOUR:
        days.append(today + timedelta(days=2))
    days.append(today + timedelta(days=3))
    days.append(today + timedelta(days=4))

    return days

def planB_court(court: Location, date: datetime) -> list[tuple[datetime, Location]]:
    # return two lists
    # current court + another alternative court of the same type (PICKLEBALL_1A, PICKLEBALL_1B) or (PICKLEBALL_2A, PICKLEBALL_2B) or (HARD_TENNIS_1, HARD_TENNIS_2)
    # current date + current date + 1 hour

    from itertools import product
    dates = [date, date + timedelta(hours=1)]
    courts = [court]
    court_type = court.court_type
    
    while len(courts) < 2:
        for _court in Location:
            if _court.court_type == court_type and _court != court:
                courts.append(_court)
                break
    
    print(list(product(dates, courts)))
    return list(product(dates, courts))


def load_credentials(acc):
    with open(f"creds/{acc}.json") as f:
        return json.load(f)


class ExceededReservationTime(Exception):
    pass

