import json
from datetime import datetime, time, timedelta
from enum import Enum
from time import sleep
from traceback import format_exc
from urllib.parse import unquote

from bs4 import BeautifulSoup
from pytz import timezone
from requests import Session
from telebot import TeleBot

from .database import Reservation, db
from .logger import Logger

# UTC Timezone
TIME_ZONE = "UTC"
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
    if today.hour < 11:
        days.append(today + timedelta(days=2))
    days.append(today + timedelta(days=3))
    days.append(today + timedelta(days=4))

    return days

def planB_court(court: Location, date: datetime) -> list[tuple[datetime, Location]]:
    # return two lists
    # current court + another alternative court of the same type (PICKLEBALL_1A, PICKLEBALL_1B) or (PICKLEBALL_2A, PICKLEBALL_2B) or (HARD_TENNIS_1, HARD_TENNIS_2)
    # current date + current date + 1 hour

    dates = [date, date + timedelta(hours=1)]
    courts = [court]
    court_type = court.court_type
    
    while len(courts) < 2:
        for _court in Location:
            if _court.court_type == court_type and _court != court:
                courts.append(_court)
                break
    
    return list(zip(dates, courts))

def load_credentials(acc):
    with open(f"creds/{acc}.json") as f:
        return json.load(f)


class ExceededReservationTime(Exception):
    pass

class ReserveBot:
    def __init__(self):
        self.session  = Session()
        self.logger   = Logger('api_courtreserve')
        self.zone = timezone(TIME_ZONE)
        self.bot: TeleBot
        self.next_run = None

    def _get(self, url, *args, **kwargs):
        res = None
        try:
            res = self.session.get(url, *args, **kwargs)
            res.raise_for_status()
            return res
        except Exception:
            self.logger.error(format_exc())
    
    def _post(self, url, *args, **kwargs):
        res = None
        try:
            res = self.session.post(url, *args, **kwargs)
            res.raise_for_status()
            return res
        except Exception:
            self.logger.error(format_exc())


    def setup(self, creds: dict):
        self.session.cookies.clear()
        self.session.headers.clear()

        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9,ar;q=0.8',
            'cache-control': 'max-age=0',
            'dnt': '1',
            'priority': 'u=0, i',
            'sec-ch-ua': '"Microsoft Edge";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0',
        }

        self.session.headers.update(headers)
        self.session.cookies.update(creds)

        res = self._get('https://app.courtreserve.com/Online/Reservations/Index/12207', headers=headers)

        return unquote(res.text.split("OrganizationMemberFavoriteApi")[1].split("requestData=")[1].split("&")[0]).strip()


    def create_reservation_url(self, start: str, end: str, court_label: str):
        params = (
            ('start', start),
            ('end', end),
            ('courtLabel', court_label),
            ('customSchedulerId', ''),
            ('returnUrlStartPage', 'https://app.courtreserve.com//Online/Reservations/Index/12207'),
        )

        res = self._get('https://app.courtreserve.com/Online/Reservations/CreateReservationCourtsView/12207', params=params)
        return unquote(res.text.split("ixUrl('")[1].split("')")[0]).replace("&amp;", "&")


    def create_reservation(self, url):
        res = self._get(url)
        soup = BeautifulSoup(res.text, "html.parser")

        if "restricted to 180 minute" in soup.text.lower():
            raise ExceededReservationTime("Reservation restricted to 180 minutes")

        return {
            "__RequestVerificationToken": soup.find("input", {"name": "__RequestVerificationToken"}).get("value"),
            "RequestData": soup.find("input", {"name": "RequestData"}).get("value"),
        }


    def reserve_court(self, member: dict, keys: dict, date: str, court_type: str, start_time: str, is_today: bool, court_id: str):
        # date = '5/24/2024 12:00:00 AM'
        # court_type = 'Pickleball - Pickleball 2A'
        # start_time = '12:00:00'

        params = (
            ('uiCulture', 'en-US'),
        )

        data = [
        ('__RequestVerificationToken', keys["__RequestVerificationToken"]),
        ('Id', '12207'),
        ('OrgId', '12207'),
        ('MemberId', member["member_id"]),
        ('IsConsolidatedScheduler', 'False'),
        ('HoldTimeForReservation', '15'),
        ('RequirePaymentWhenBookingCourtsOnline', 'False'),
        ('AllowMemberToPickOtherMembersToPlayWith', 'False'),
        ('ReservableEntityName', 'Court'),
        ('IsAllowedToPickStartAndEndTime', 'False'),
        ('CustomSchedulerId', ''),
        ('CustomSchedulerId', ''),
        ('IsConsolidated', 'False'),
        ('IsToday', str(is_today)),
        ('IsFromDynamicSlots', 'False'),
        ('InstructorId', ''),
        ('InstructorName', ''),
        ('CanSelectCourt', 'False'),
        ('IsCourtRequired', 'False'),
        ('CostTypeAllowOpenMatches', 'False'),
        ('IsMultipleCourtRequired', 'False'),
        ('ReservationQueueId', ''),
        ('ReservationQueueSlotId', ''),
        ('RequestData', keys["RequestData"]),
        ('Date', date),
        ('SelectedCourtType', court_type),
        ('SelectedCourtTypeId', '0'),
        ('SelectedResourceId', ''),
        ('DisclosureText', ''),
        ('DisclosureName', ''),
        ('IsResourceReservation', 'False'),
        ('StartTime', start_time),
        ('CourtTypeEnum', '9'),
        ('MembershipId', '115054'),
        ('UseMinTimeByDefault', 'False'),
        ('IsEligibleForPreauthorization', 'False'),
        ('MatchMakerSelectedRatingIdsString', ''),
        ('DurationType', ''),
        ('MaxAllowedCourtsPerReservation', '1'),
        ('SelectedResourceName', ''),
        ('ReservationTypeId', '60221'),
        ('Duration', '60'),
        ('CourtId', court_id), # the court type id ig
        ('OwnersDropdown_input', ''),
        ('OwnersDropdown', ''),
        ('SelectedMembers[0].OrgMemberId', member["org_member_id"]),
        ('SelectedMembers[0].MemberId', member["member_id"]),
        ('SelectedMembers[0].OrgMemberFamilyId', ''),
        ('SelectedMembers[0].FirstName', member['first_name']),
        ('SelectedMembers[0].LastName', member['last_name']),
        ('SelectedMembers[0].Email', member['email']),
        ('SelectedMembers[0].MembershipNumber', member['membership_number']),
        ('SelectedMembers[0].PaidAmt', ''),
        ('SelectedNumberOfGuests', ''),
        ('X-Requested-With', 'XMLHttpRequest'),
        ]

        res = self._post('https://reservations.courtreserve.com//Online/ReservationsApi/CreateReservation/12207', params=params, data=data)
        return res.json() # check for isValid = True


    def reserve(self, date: datetime, court: Location, acc: str):
        # date = '5/24/2024 12:00:00 AM'

        # court_type = 'Pickleball - Pickleball 2A' or 'Hard - Tennis Court #2
        # start_time = '12:00:00'

        # create_reservation_url params:
        # start: 'Fri May 24 2024 12:00:00 GMT 0300 (GMT 03:00)'
        # end: 'Fri May 24 2024 13:00:00 GMT 0300 (GMT 03:00)'
        # court_label: 'Pickleball 2A'

        # `start` is basically the date and time of the reservation in the format above 
        # `court_label` is the second part of the court_type above
        # that's it

        _date = date.strftime("%m/%d/%Y %H:%M:%S %p")
        start = date.strftime("%a %b %d %Y %H:%M:%S GMT 0300 (GMT 03:00)")
        end = (date + timedelta(hours=1)).strftime("%a %b %d %Y %H:%M:%S GMT 0300 (GMT 03:00)")
        
        is_today = date.date() == datetime.now(tz=self.zone).date()

        court_label = court.court_label
        court_type = court.value
        court_id = str(court.id)
        
        if acc == "zafar":
            member = zafar_details
        elif acc == "mike":
            member = michael_details

        creds = load_credentials(acc)
        
        self.setup(creds=creds)
        
        url = self.create_reservation_url(start, end, court_label)
        try:
            keys = self.create_reservation(url)
        except ExceededReservationTime:
            return {"isValid": False, "message": "Reservation restricted to 180 minutes"}

        reservation = self.reserve_court(member, keys, _date, court_type, _date.split(" ")[1], is_today, court_id)
        try:
            self.logger.info(str(reservation)[:4000], True)
        except Exception:
            pass
        return reservation


    def worker(self):
        self.logger.info("reserver bot worker is running...", True)
        while True:
            # only run this at 11AM UTC -15 seconds to be safe
            now = datetime.now(tz=self.zone)

            if (remainder:=abs(now - datetime(now.year, now.month, now.day, 11, 0, 0, tzinfo=self.zone))) < timedelta(seconds=15):
                for reservation in db.all():
                    reservation: Reservation
                    court: Location
                    
                    if reservation.date.date() <= now.date():
                        db.delete(reservation)
                        self.logger.info(f"Deleted reservation {reservation.date}", True)
                        continue

                    if reservation.date.date() != (now + timedelta(days=2)).date():
                        continue

                    is_reserved = False

                    for court_date, court in planB_court(LOCATION_ID_TO_LOCATION_MAPPING[int(reservation.court_id)], reservation.date):
                        if is_reserved:
                            break
                        try:
                            resrv = self.reserve(date=court_date, court=court, acc=reservation.acc)
                            if resrv and resrv["isValid"]:
                                self.bot.send_message(6874076639, f"✅ Succesfully reserved {reservation.date} at {court.court_label}")
                                self.bot.send_message(942683545, f"✅ Succesfully reserved {reservation.date} at {court.court_label}") # notify the dev/ delete after testing
                                db.delete(reservation)
                                is_reserved = True
                                break
                            else:
                                self.bot.send_message(942683545, f"Error while reserving {reservation.date} at {court.court_label}:\n{resrv.get('message', '')}")
                        except Exception:
                            self.logger.error(format_exc())
                    
                    if not is_reserved:
                        self.logger.error(f"Failed to reserve {reservation.date}")
            
            self.logger.info(f"Sleeping for {remainder.total_seconds()} seconds", True)
            self.next_run = now + remainder
            sleep(max(remainder.total_seconds()-5, 0.1))



if __name__ == "__main__":
    bot = ReserveBot()
    bot.worker()
