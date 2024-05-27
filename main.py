from datetime import datetime

from pytz import timezone
from telebot import TeleBot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.courtreserve import (TIME_ZONE, ReserveBot, get_available_days, Location, LOCATION_ID_TO_NAME_MAPPING,
                              get_available_hours)
from src.database import Reservation, db
from src.logger import Logger
import typing


bot = TeleBot("7021449655:AAGt6LG48rqtV6nCefane06878wJLYynCvk")
logger = Logger("bot")

class Menu:
    @staticmethod
    def admin():
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("➕ New Reservation", callback_data="new_reservation"))
        markup.add(InlineKeyboardButton("📅 Scheduled Reservations", callback_data="view_reservations"))
        return markup


    @staticmethod
    def new_reservation_menu():
        days = [day.date() for day in get_available_days()]
        markup = InlineKeyboardMarkup()
        for day in days:
            markup.add(InlineKeyboardButton(day.strftime("%B %d"), callback_data=f"day_{day.strftime('%Y/%m/%d')}"))
        
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="back.admin"))
        return markup

    @staticmethod
    def courts_menu():
        markup = InlineKeyboardMarkup()
        for location in Location:
            markup.add(InlineKeyboardButton(location.value, callback_data=f"court_{location.id}"))
        
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="back.days"))
        return markup

    @staticmethod
    def new_reservation_hours_menu():
        markup = InlineKeyboardMarkup(row_width=4)
        all_hours = get_available_hours()
        row = []
        for resrvation in all_hours:
            if len(row) == 4:
                markup.row(*row)
                row.clear()
            
            row.append(InlineKeyboardButton(" - ".join(f"{resrv.hour}:00" for resrv in resrvation), callback_data="hour_{}:{}".format(resrvation[0].hour, resrvation[1].hour)))
        
        if row:
            markup.row(*row)

        markup.add(InlineKeyboardButton("🔙 Back", callback_data="back.courts"))
        return markup

    @staticmethod
    def view_reservations_menu(reservations: list[Reservation]):
        markup = InlineKeyboardMarkup()
        for n, reservation in enumerate(reservations):
            court = LOCATION_ID_TO_NAME_MAPPING[int(reservation.court_id)].split("-")[1].strip()
            markup.add(InlineKeyboardButton(f"{n+1}. {court} On {reservation.date.strftime('%B %d %H:%M')}", callback_data=f"rsrv_{reservation.key}"))

        markup.add(InlineKeyboardButton("🔙 Back", callback_data="back.admin"))
        return markup

    @staticmethod
    def remove_reservation_menu(reservation_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("❌ Remove", callback_data=f"remove_{reservation_id}"))
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="back.admin"))
        return markup


queue: dict = {}


@bot.message_handler(commands=["reserve"])
def reserve(message):
    bot.send_message(message.chat.id, "Please select an option", reply_markup=Menu.admin())


@bot.callback_query_handler(func=lambda call: call.data.startswith("back."))
def back(call):
    page = call.data.split(".")[1] if "." in call.data else "admin"
    menu: typing.Callable

    if page == "days":
        menu = Menu.new_reservation_menu
    else:
        menu = Menu.admin

    try:
        bot.edit_message_text("Please select an option", call.message.chat.id, call.message.id, reply_markup=menu())
    except:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.id, reply_markup=menu())



@bot.callback_query_handler(func=lambda call: call.data == "new_reservation")
def new_reservation(call):
    bot.edit_message_text("Please select a day", call.message.chat.id, call.message.id, reply_markup=Menu.new_reservation_menu())


@bot.callback_query_handler(func=lambda call: call.data.startswith("day_"))
def new_reservation_day(call):
    date = datetime.strptime(call.data.split("_")[1], "%Y/%m/%d")
    queue.setdefault(call.message.chat.id, {}).update(date=date)
    
    bot.edit_message_text(f"Please select a court for {date.strftime('%B %d')}", call.message.chat.id, call.message.id, reply_markup=Menu.courts_menu())


@bot.callback_query_handler(func=lambda call: call.data.startswith("court_"))
def new_reservation_court(call):
    court = call.data.split("_")[1]
    date = queue.get(call.message.chat.id, {}).get("date")
    if not date:
        bot.answer_callback_query(call.id, "⚠️ Please select a day first or try again", show_alert=True)
        return

    queue[call.message.chat.id].update(court=court)
    bot.edit_message_text(f"Please select a time for {date.strftime('%B %d')} at {LOCATION_ID_TO_NAME_MAPPING[int(court)]}", call.message.chat.id, call.message.id, reply_markup=Menu.new_reservation_hours_menu())


@bot.callback_query_handler(func=lambda call: call.data.startswith("hour_"))
def book_reservation(call):
    hours = call.data.split("_")[1]
    start, end = map(int, hours.split(":"))
    
    date = queue.get(call.message.chat.id, {}).get("date")
    court = queue.get(call.message.chat.id, {}).get("court")

    reservation = Reservation(date=date.replace(hour=start, tzinfo=timezone(TIME_ZONE)), court_id=court)

    if not db.add(reservation):
        bot.answer_callback_query(call.id, "⚠️ Reservation already exists", show_alert=True)
        return

    msg = f"✅ Reservation for {LOCATION_ID_TO_NAME_MAPPING[int(court)]} created on {reservation.date.strftime('%B %d %H:%M')}" 
    bot.answer_callback_query(call.id, msg, show_alert=True)
    bot.send_message(call.message.chat.id, msg+"\nThe bot will book the court automatically once it becomes available")


@bot.callback_query_handler(func=lambda call: call.data == "view_reservations")
def view_reservations(call):
    reservations = db.all()
    if not reservations:
        bot.send_message(call.message.chat.id, "No reservations found")
        bot.answer_callback_query(call.id)
        return
    
    bot.edit_message_text("Please select a reservation", call.message.chat.id, call.message.id, reply_markup=Menu.view_reservations_menu(reservations))


@bot.callback_query_handler(func=lambda call: call.data.startswith("rsrv_"))
def reservation_details(call):
    reservation_id = call.data.split("_")[1]
    reservation = db.get(reservation_id)
    if not reservation:
        bot.answer_callback_query(call.id, "Reservation not found", show_alert=True)
        return
        
    bot.edit_message_text(f"Reservation on {reservation.date.strftime('%B %d %H:%M')}", call.message.chat.id, call.message.id, reply_markup=Menu.remove_reservation_menu(reservation.key))


@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_"))
def remove_reservation(call):
    reservation_id = call.data.split("_")[1]
    reservation = db.get(reservation_id)
    if not reservation:
        bot.answer_callback_query(call.id, "Reservation not found", show_alert=True)
        return
    
    db.delete(reservation)
    bot.answer_callback_query(call.id, "⚠️ Reservation removed", show_alert=True)
    bot.send_message(call.message.chat.id, f"Reservation on {reservation.date.strftime('%B %d %H:%M')} has been removed")
    back(call)


if __name__ == "__main__":
    logger.info("Starting the bot")
    bot.infinity_polling()

