from datetime import datetime, time, timedelta
from time import sleep
from traceback import format_exc
from urllib.parse import unquote

from bs4 import BeautifulSoup
from pytz import timezone
from requests import Session
from telebot import TeleBot

from .database import Reservation, creds_manager, db
from .logger import Logger
from concurrent.futures import ThreadPoolExecutor

from .config import LOCATION_ID_TO_LOCATION_MAPPING, START_HOUR, TIME_ZONE, Location
from .config import zafar_details, michael_details
from .config import load_credentials, planB_court
from .config import ExceededReservationTime


class ReserveBot:
    def __init__(self, reservation: Reservation, logger: Logger, bot: TeleBot):
        self.session  = Session()
        self.reservation = reservation

        self.acc = reservation.acc
        if reservation.acc == "zafar":
            self.member_details = zafar_details
        elif reservation.acc == "mike":
            self.member_details = michael_details
        self.creds: dict = load_credentials(reservation.acc)


        self.zone = timezone(TIME_ZONE)
        self.logger = logger
        self.bot = bot

        self.is_reserved = False

        self.setup()
        self.logger.info(f"Initialized Session for {self.acc}", True)


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

    def _setup(self):
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

    def get_creds(self, force_login: bool):
        creds = creds_manager.get(self.acc)
        if not creds or force_login:
            data: dict = getattr(creds_manager, self.acc)
            x = self._post('https://app.courtreserve.com/Account/Login', data=data)
            application_code = x.history[0].cookies.get_dict()['.AspNet.ApplicationCookie']
            creds_manager.add(cred:={".AspNet.ApplicationCookie": application_code}, self.acc)
            try:
                del cred['age']
            except:
                pass
            return cred

        return creds

    def setup(self, force_login=False):
        self._setup()
        login_creds = self.get_creds(force_login)
        self.creds.update(login_creds)
        self.session.cookies.update(self.creds)

        res = self._get('https://app.courtreserve.com/Online/Reservations/Index/12207')
        if 'login' in res.text and not force_login:
            return self.setup(force_login=True)

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
        self.logger.info(res.url, True)
        return unquote(res.text.split("ixUrl('")[1].split("')")[0]).replace("&amp;", "&")

    def create_reservation(self, url):
        res = self._get(url)
        soup = BeautifulSoup(res.text, "html.parser")

        if "restricted to 180 minute" in soup.text.lower():
            raise ExceededReservationTime("Reservation restricted to 180 minutes")

        verification_token = soup.find("input", {"name": "__RequestVerificationToken"})
        if not verification_token:
            self.logger.warning(f"Error while creating reservation\n{res.text}\n{url}")
            from io import BytesIO
            file = BytesIO(res.content)
            file.name = 'doc'
            try:
                self.bot.send_document(942683545, file, caption="Error while creating reservation")
            except:
                pass
            
        return {
            "__RequestVerificationToken": verification_token.get("value"),
            "RequestData": soup.find("input", {"name": "RequestData"}).get("value"),
        }

    def reserve_court(self, member: dict, keys: dict, date: str, court_type: str, start_time: str, is_today: bool, court_id: str, delay: int):
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

        # make sure this function is called 15mins max before the reservation time
        self.logger.info(f"[WAITING] - {datetime.now(tz=self.zone)} waiting for new reservations for {self.acc} on {date}", True)
        while True:
            dtnow = datetime.now(tz=self.zone)
            if dtnow.hour == START_HOUR:
                break
            sleep(0.005)

        if self.is_reserved:
            return {"isValid": False, "message": "Already reserved", "terminated_by_bot": True}

        # sleep for the artificial delay to prioritize the first reservation
        sleep(delay)

        self.logger.info(f"[{datetime.now(tz=self.zone)}] Reserving {date} for {self.acc}", True)
        res = self._post('https://reservations.courtreserve.com//Online/ReservationsApi/CreateReservation/12207', params=params, data=data)
        return res.json() # check for isValid = True


    def reserve(self, date: datetime, court: Location, delay: int):
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

        url = self.create_reservation_url(start, end, court_label)
        try:
            keys = self.create_reservation(url)
        except ExceededReservationTime:
            return {"isValid": False, "message": "Reservation restricted to 180 minutes"}

        reservation = self.reserve_court(self.member_details, keys, _date, court_type, _date.split(" ")[1], is_today, court_id, delay)
        return reservation


    def reserve_pool(self, court_date: datetime, court: Location, delay: int):
        try:
            if self.is_reserved: return
            resrv = self.reserve(date=court_date, court=court, delay=delay)
            if self.is_reserved: return

            if resrv and resrv["isValid"] and "terminated_by_bot" not in resrv:
                self.is_reserved = True
                self.bot.send_message(6874076639, f"✅ [{self.reservation.acc}] Succesfully reserved {self.reservation.date} at {court.court_label}")
                self.bot.send_message(942683545, f"✅ [{self.reservation.acc}] Succesfully reserved {self.reservation.date} at {court.court_label}") # notify the dev/ delete after testing
                db.delete(self.reservation)
            else:
                if "terminated_by_bot" in resrv: return
                self.logger.warning(f"[{self.reservation.acc}] Error while reserving {self.reservation.date} at {court.court_label}:\n{resrv.get('message', '')}")
        except Exception:
            self.logger.error(format_exc())


    def reserve_worker(self, now: datetime):
        self.logger.info(f"Reserving {self.reservation.date} for {self.reservation.acc}", True)
        if self.reservation.date.date() <= now.date():
            db.delete(self.reservation)
            self.logger.info(f"Deleted reservation {self.reservation.date}", True)
            return

        if self.reservation.date.date() != (now + timedelta(days=2)).date():
            self.logger.info(f"Skipping reservation {self.reservation.date} because it's not two days in advance", True)
            return

        delay_gen = lambda x: (2*x**2 +x+10)/50
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="reservation-wise") as executor:
            delay = 0; x=0
            for court_date, court in planB_court(LOCATION_ID_TO_LOCATION_MAPPING[int(self.reservation.court_id)], self.reservation.date):
                executor.submit(self.reserve_pool, court_date, court, delay)
                delay += delay_gen(x); x+=1

        if self.is_reserved is False:
            self.logger.error(f"[{self.reservation.acc}] Failed to reserve {self.reservation.date}")



if __name__ == "__main__":
    reservation = Reservation(
        datetime(2024, 6, 22, 13, tzinfo=timezone("UTC")),
        46166,
        acc="mike",
    )
    bot = ReserveBot(reservation, Logger("we"), TeleBot("7021449655:AAGt6LG48rqtV6nCefane06878wJLYynCvk"))
    bot.reserve_pool(
        reservation.date,
        Location.PICKLEBALL_1B,
        0
    )
