## Flight Attendant Schedule Uploader

This application inputs screenshots from a Flight Attendant Schedule and uploads them into a google calendar via API. You will need to provide the calendar ID in an `.env` file.

Future Features to Add:
 - Log Upload Data and Move folders
 - Deadhead capability (including upload UAX data)
 - Add details to trip objects and flight segments
 - Add layover details with hotel info and time
 - Check if overlapping trip exists in calendar and replace it (i.e. trip gets replaced for various reasons)