from PIL import Image, ImageEnhance, ImageOps
import pytesseract
from paddleocr import PaddleOCR
import re
import os
import cv2
import pandas as pd
from rapidfuzz import process, distance
import numpy as np
from prompt_toolkit import prompt

from datetime import datetime, timedelta, timezone
import os.path
import dotenv

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from utils import *

dotenv.load_dotenv()
cal_id = os.getenv('cal_id')

class Segment:
    def __init__(self, flight_number, dep_time, arr_time, dep_airport, arr_airport):
        self.flight_number = flight_number
        self.dep_time = dep_time
        self.arr_time = arr_time
        self.dep_airport, self.dep_airport_tz = airport_with_tz(dep_airport)
        self.arr_airport, self.arr_airport_tz = airport_with_tz(arr_airport)

    def __repr__(self):
        return f"UA-{self.flight_number:<4}: {self.dep_airport} --> {self.arr_airport} @ {self.dep_time} --> {self.arr_time}"

class Day:
    def __init__(self, date, segments, layover_time, layover_airport):
        self.date = date
        self.segments = segments
        self.layover_time = layover_time
        self.layover_airport = layover_airport

    def __repr__(self):
        if self.layover_time == "":
            return f"{self.date}:\n {'\n '.join([str(s) for s in self.segments])}\nNo Layover"
        else:
            return f"{self.date}:\n {'\n '.join([str(s) for s in self.segments])}\nLayover:\n {self.layover_time} Hours in {self.layover_airport}"

class ExitTryBlock(Exception):
    def __init__(self, seg, code):
        # Pass the message to the base Exception class
        super().__init__(f"Cannot Segment **{code}** on '{seg}'")
    pass

def extract_segment(seg):
    # Define patterns
    patterns = {
        "flight": r"\b\d{3,4}\b",  # 3 or 4 digit flight number
        "times": r"\b\d{2}:\d{2}\b",  # Times formatted as HH:MM
        "airports": r"\b[A-Z]{3}\b",  # 3-letter uppercase airport codes
        #"aircraft": r"\b\d{2}[A-Z]-\d{2}[A-Z]\b",  # e.g., 37X-37X
    }

    # Extract matches
    flight_number_list = re.findall(patterns['flight'], seg)
    times = re.findall(patterns["times"], seg)
    airports = re.findall(patterns["airports"], seg)
    try:
        if len(flight_number_list) > 1:
            flight_number = flight_number_list[0]
        else:
            flight_number = "???(?)"
        # Times
        if len(times) >= 2:
            dep_time = times[0]
            arr_time = times[1]
        elif len(times) == 1:
            dep_time = times[0]
            arr_time = "??:??"
        else:
            dep_time = "??:??"
            arr_time = "??:??"
        # Airports
        if len(airports) >= 2:
            dep_airport = airports[0]
            arr_airport = airports[1]
        elif len(airports) == 1:
            dep_airport = airports[0]
            arr_airport = "???"
        else:
            dep_airport = "???"
            arr_airport = "???"
            #raise ExitTryBlock(seg, "AIRPORTS")
        ##############################################
        # Fit into Segment class
        ll = prompt(" -- Segment: ", 
                    default=f"{flight_number:<4} {dep_time} {arr_time} {dep_airport} {arr_airport}")
        return(Segment(*ll.split()))

    except ExitTryBlock as error:
        print(error)
        return(None)

def create_trip(ocr_result):
    trip = []
    days = ' '.join(ocr_result[0]['rec_texts']).split('DP')[1:]

    for idx, day in enumerate(days):
        layover_time = ""
        layover_airport = ""
        # Split day into day_init + segments
        segs = day.split('UA')
        #print(segs[0])
        #print("*"*50)
        day_re_match = re.search(r'\d\d\/\d\d\/\d\d', segs[0].split()[1].strip())
        if day_re_match:
            day_date = day_re_match.group()
        else:
            print(f"Cannot find date. Enter manually.")
            day_date = prompt(f"Enter Date ('dd/mm/yy'): ", default=segs[0].strip())
            #raise ExitTryBlock
        # Iterate through true segments
        segments = []
        print(f"Date: {day_date} {"-"*35}")
        for seg in segs[1:]:
                # Send to segment
                #print(seg)
                #print("-"*40)
                segments.append(extract_segment(seg))
        # Look for layover, but only if we're not on the last day
        if idx != len(days) - 1:
            try:
                layover_substring = re.findall(r"[Ll]ayover\s\d{2}:\d{2}in[A-Za-z]{3}", seg)[0]
                layover_time = re.findall(r"\d{2}:\d{2}", layover_substring)[0]
                layover_airport = airport_with_tz(
                    re.findall(r"[A-Za-z]{3}", layover_substring.split('in')[1])[0]
                )[0]
                layover_time, layover_airport = prompt(" -- Layover: ", default=f"{layover_time} {layover_airport}").split()
            except IndexError:
                print(f'Cannot find layover on "{seg}"')
                print("Enter layover Manually:")
                layover_time, layover_airport = prompt(" -- Layover: ", default="??:?? ???").split()
        # Add day to trip
        trip.append(
            Day(day_date, segments, layover_time, layover_airport)
        )

    return(trip)

def output_from_image(path):
    result = ocr.predict(path)
    return result

def output_schedule(data_path):
    trips = []
    for image_path in os.listdir(data_path):
        if '.png' in image_path or '.jpg' in image_path:
            print(f"Image: {image_path} ************************")
            image_result = output_from_image(os.path.join(data_path, image_path))
            trip = create_trip(image_result)
            trips.append(trip)
    # Sort Days
    #print(total_days)
    #total_days.sort(key=lambda day: datetime.strptime(day.date, "%m/%d/%y"))
    # Return List of Days
    return trips

# Calendar
def upload_schedule(trips, service, cal_id):
    api = service.events()
    current_day = 0
    for trip in trips:
        start_date = trip[0].date
        if all(not d.layover_airport.strip() for d in trip[:-1]):
            layovers = ''
        else:
            try:
                layovers = f"(Layover in {'/'.join([data.loc[data['iata'] == d.layover_airport, 'City'].values[0] for d in trip[:-1]])})"
            except IndexError:
                print(trip)
                print(trip[:-1])
                print([d.layover_airport for d in trip])
        for day in trip:
            print(f"Uploading Flights for {day.date}")
            for s in day.segments:
                # Adjust Date if landing after midnight
                if s.arr_time > s.dep_time:
                    end_time = f"{datetime.strptime(day.date, "%m/%d/%y").strftime("%Y-%m-%d")}T{s.arr_time}:00"
                else:
                    end_time = f"{(datetime.strptime(day.date, "%m/%d/%y") + timedelta(days=1)).strftime("%Y-%m-%d")}T{s.arr_time}:00"
                # Create Flight Segment
                flight_event = {
                    'summary': f'{s.dep_airport} --> {s.arr_airport} ({s.flight_number})',  # What shows up as the main calendar title
                    #'description': 'Flight Crew Duty Block\nReport Time: 05:15\nGate: M14',
                    'start': {
                        'dateTime': f"{datetime.strptime(day.date, "%m/%d/%y").strftime("%Y-%m-%d")}T{s.dep_time}:00",
                        'timeZone': s.dep_airport_tz,  # Standard IANA Time Zone string
                    },
                    'end': {
                        'dateTime': end_time,
                        'timeZone': s.arr_airport_tz,
                    },
                    #'colorId': '1'  # Optional: '1' is Lavender, '5' is Yellow, '11' is Tomato red
                }
                # Add segment to Calendar Events and Upload
                created_event = service.events().insert(
                    calendarId=cal_id,
                    body=flight_event
                ).execute()
                print(f" - Added {s}")
            end_date = trip[-1].date
        created_event = service.events().insert(
                calendarId=cal_id,
                body={
                    'summary': f"Tyler Trip {layovers}",
                    'start': {'date': datetime.strptime(start_date, "%m/%d/%y").strftime("%Y-%m-%d")},
                    'end': {'date': (datetime.strptime(end_date, "%m/%d/%y") + timedelta(days=1)).strftime("%Y-%m-%d")}
                }
            ).execute()
        

    return None

if __name__ == "__main__":
    # Initialize Engine
    print("Starting OCR Engine")
    ocr = PaddleOCR(use_angle_cls=True, lang='en')
    print("OCR Engine initialized")

    # Confirm Calendar
    SCOPES = ["https://www.googleapis.com/auth/calendar"]
    creds = None

    # 1. Safely check if token.json exists BEFORE trying to open it
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    # 2. If token.json doesn't exist, this block catches it and starts the login flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # This reads your credentials file and opens the browser window
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        # 3. This creates the token.json file so the error never happens again
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    print("Authentication successful!")

    service = build('calendar', 'v3', credentials=creds)

    # Create Days
    print("Beginning Scanning")
    trips = output_schedule("screenshots")

    continue_yn = input("\nUpload Days ?")
    if continue_yn.strip() == "":
        upload_schedule(trips, service, cal_id)