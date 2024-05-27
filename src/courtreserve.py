from requests import Session
from time import sleep
from bs4 import BeautifulSoup
from urllib.parse import unquote
from .logger import Logger
from traceback import format_exc
from pytz import timezone
from datetime import datetime, timedelta, time
from enum import Enum
from .database import Reservation, db
from telebot import TeleBot


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
        return self.value

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

LOCATION_ID_TO_NAME_MAPPING = {v: k for k, v in LOCATION_NAME_TO_ID_MAPPING.items()}

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


class ReserveBot:
    def __init__(self):
        self.session  = Session()
        self.logger   = Logger('api_courtreserve')
        self.is_setup = False
        self.zone = timezone(TIME_ZONE)
        self.bot: TeleBot

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


    def setup(self):
        cookies = {
            'ASP.NET_SessionId': 'bcnynxy1syh0xkb1my2fkw1p',
            '_hjSessionUser_839874': 'eyJpZCI6ImM3ZjQ0MGY4LTQ4NWItNTI4OC04MTBjLWQ1YjRmYjZkNTlhNyIsImNyZWF0ZWQiOjE3MTYwMDg0NjY1NDMsImV4aXN0aW5nIjp0cnVlfQ==',
            '.AspNet.ApplicationCookie': 'WavzJicPGJ2y8Y-fqMOW0H41V1uvpll3Q3jQDUEBOpkQFW592_K4fDeG2g9NTXwnMOCOZ3QZIi3JQaOuzixeMpwZ0h_Apq4wDJuMhalYZOSFeTt6VFv-MmqMRlEdw1xgXs6lLPk4MZclWaGif3PscTtl1-63cL6-rTM59z1KfmKbV7fYsIjslmaem7vtAhtey_cz3Q4-9L6klnTd8ElOYp1SXG2ij9Npl8GVJyKnIRYXtVMeZ_G1U7gN4OcDjB9ydOi_9ulUL4cHwca0LRr44q7MF90Cf8EnVHr1ESnsTMHEDzGV7tDN0Lrp2gW5Oq4yYInQGj18dhmlC0aUXzraqjg5LNCuph0L_3nRJAhbz270SbcgFMZJlMoYws3ZutYWG-b7OKrpIo4krh8C-quN6ZAGOoocu4LreLoiKSOH7aLC-iaAdSEmoKtWaX7pHvyXbBYRfJUXXWngNSGIN0fLXhqO_g7ouAOT1W6SZ5eYjU8ad3f0-JJzUqGN6s4oDyCEBHwAWDR6f2t-_lUeFordpXfSD9gF8kaxhbKcHq_MQ-RviUIz',
            'InternalCalendarDate': '5%2F24%2F2024',
            'IsPayNowVisible': 'false',
        }

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
        self.session.cookies.update(cookies)

        res = self._get('https://app.courtreserve.com/Online/Reservations/Index/12207', headers=headers, cookies=cookies)

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
        with open('res.html', 'wb') as f:
            f.write(res.content)

        soup = BeautifulSoup(res.text, "html.parser")

        return {
            "__RequestVerificationToken": soup.find("input", {"name": "__RequestVerificationToken"}).get("value"),
            "RequestData": soup.find("input", {"name": "RequestData"}).get("value"),
        }


    def reserve_court(self, keys, date: str, court_type: str, start_time: str, is_today: bool, court_id: str):
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
        ('MemberId', '5663355'),
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
        ('SelectedMembers[0].OrgMemberId', '4442712'),
        ('SelectedMembers[0].MemberId', '5663355'),
        ('SelectedMembers[0].OrgMemberFamilyId', ''),
        ('SelectedMembers[0].FirstName', 'Zafar'),
        ('SelectedMembers[0].LastName', 'Bhayat'),
        ('SelectedMembers[0].Email', 'zbhayat0@gmail.com'),
        ('SelectedMembers[0].MembershipNumber', '1138'),
        ('SelectedMembers[0].PaidAmt', ''),
        ('SelectedNumberOfGuests', ''),
        ('X-Requested-With', 'XMLHttpRequest'),
        ]

        res = self._post('https://reservations.courtreserve.com//Online/ReservationsApi/CreateReservation/12207', params=params, data=data)
        return res.json() # check for isValid = True


    def reserve(self, date: datetime, court: Location):
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
        court_type = court.court_type
        court_id = str(court.id)
        
        if not self.is_setup:
            self.setup()
            self.is_setup = True
        
        url = self.create_reservation_url(start, end, court_label)
        keys = self.create_reservation(url)

        reservation = self.reserve_court(keys, _date, court_type, _date.split(" ")[1], is_today, court_id)
        self.logger.info(reservation)
        return reservation


    def worker(self):
        self.logger.info("reserver bot worker is running...")
        while True:
            # only run this at 11AM UTC -15 seconds to be safe
            now = datetime.now(tz=self.zone)

            if (remainder:=abs(now - datetime(now.year, now.month, now.day, 11, 0, 0, tzinfo=self.zone))) < timedelta(seconds=15):
                for reservation in db.all():
                    is_reserved = False

                    for court in [Location.PICKLEBALL_2A, Location.PICKLEBALL_1A]:
                        if is_reserved:
                            break

                        for offset in [timedelta(hours=0), timedelta(hours=1)]:
                            try:
                                resrv = self.reserve(reservation.date+offset, court=court)
                                if resrv and resrv["isValid"]:
                                    db.delete(reservation)
                                    is_reserved = True
                                    break
                            except Exception:
                                self.logger.error(format_exc())
                    
                    if not is_reserved:
                        self.logger.error(f"Failed to reserve {reservation.date}")
            
            self.logger.info(f"Sleeping for {remainder.total_seconds()} seconds")
            sleep(max(remainder.total_seconds()-5, 0.1))



if __name__ == "__main__":
    bot = ReserveBot()
    bot.worker()