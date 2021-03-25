# -*- coding: utf-8 -*-
import os
from datetime import datetime, timedelta
import time
from gluon.contrib.appconfig import AppConfig


myconf = AppConfig(reload=True)
MAIL_DELAY = float(myconf.get("config.mail_delay", default=1.5))  # in seconds; must be smaller than cron intervals
MAIL_MAX_SENDING_ATTEMPTS = int(myconf.get("config.mail_max_sending_attemps", default=3))

log = None
if (myconf.get("config.use_logger", default=True) is True):
	try:
		import logging
		from systemd.journal import JournalHandler
		logName = myconf.take("app.name")
		log = logging.getLogger(logName)
		hand = JournalHandler(SYSLOG_IDENTIFIER=logName)
		hand.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
		log.root.addHandler(hand)
		log.setLevel(logging.INFO)
		print("systemd logging used")
	except:
		print("systemd logging not available")
else:
	print("systemd logging not enabled in config")

# Reminders config
def get_reminders_from_config():
    reminders = []
    with open(os.path.join(os.path.dirname(__file__), "../private", "reminders_config")) as f:
        # Remove empty lines
        non_empty_lines = [lin for lin in f if lin.strip() != ""]

        # Parse lines
        for line in non_empty_lines:
            # Remove whitechar
            line = line.strip()
            line = line.replace(" ", "")
            element = line.split("=")

            # Get hashtag_template
            hashtag = element[0]

            # Get elapsed_days
            # Remove array notation
            elapsed_days_str = element[1].replace("[", "")
            elapsed_days_str = elapsed_days_str.replace("]", "")
            elapsed_days_str = elapsed_days_str.split(",")

            # Convert elapsed_days from str to int
            elapsed_days_int = []
            for i in elapsed_days_str:
                elapsed_days_int.append(int(i))

            # Append item
            reminders.append(dict(hashtag=hashtag, elapsed_days=elapsed_days_int))

    return reminders


REMINDERS = get_reminders_from_config()


def getMailsInQueue():
    return db((db.mail_queue.sending_status.belongs("in queue", "pending")) & (db.mail_queue.removed_from_queue == False) & (db.mail_queue.sending_date <= datetime.now())).select(
        orderby=db.mail_queue.sending_date
    )


def tryToSendMail(mail_item):
    try:
        mail.send(to=mail_item.dest_mail_address, cc=mail_item.cc_mail_addresses, subject=mail_item.mail_subject, message=mail_item.mail_content)
        isSent = True
    except Exception as err:
        if log:
            try:
                #journal.write(err)
                log.error(err)
            except:
                print(err)
        else:
            print(err)
        isSent = False

    if mail_item.sending_status == "pending":
        prepareNextReminder(mail_item)

    updateSendingStatus(mail_item, isSent)
    logSendingStatus(mail_item, isSent)



def prepareNextReminder(mail_item):
    reminder_count = mail_item["reminder_count"]

    reminder = list(filter(lambda item: item["hashtag"] == mail_item["mail_template_hashtag"], REMINDERS))

    if reminder[0] and len(reminder[0]["elapsed_days"]) >= reminder_count + 1:
        current_reminder_elapsed_days = reminder[0]["elapsed_days"][reminder_count]

    if reminder[0] and len(reminder[0]["elapsed_days"]) >= reminder_count + 2:
        next_reminder_elapsed_days = reminder[0]["elapsed_days"][reminder_count + 1]

        days_between_reminders = next_reminder_elapsed_days - current_reminder_elapsed_days
        sending_date = datetime.now() + timedelta(days=days_between_reminders)

        db.mail_queue.insert(
            sending_status="pending",
            reminder_count=reminder_count + 1,
            sending_date=sending_date,
            dest_mail_address=mail_item["dest_mail_address"],
            cc_mail_addresses=mail_item["cc_mail_addresses"],
            mail_subject=mail_item["mail_subject"],
            mail_content=mail_item["mail_content"],
            user_id=mail_item["user_id"],
            recommendation_id=mail_item["recommendation_id"],
            article_id=mail_item["article_id"],
            mail_template_hashtag=mail_item["mail_template_hashtag"],
        )


def updateSendingStatus(mail_item, isSent):
    attempts = mail_item.sending_attempts + 1

    if isSent:
        new_status = "sent"
    if not isSent and attempts >= MAIL_MAX_SENDING_ATTEMPTS:
        new_status = "failed"
    elif not isSent and attempts < MAIL_MAX_SENDING_ATTEMPTS:
        new_status = "in queue"

    mail_item.update_record(sending_status=new_status, sending_attempts=attempts)
    db.commit()


def logMailsInQueue(queue_length):
    if queue_length > 0:
        colored_queue_length = "\033[1m\033[93m%i\033[0m" % queue_length
    else:
        colored_queue_length = "\033[1m\033[90m%i\033[0m" % queue_length
    colored_date = "[\033[90m%s\033[0m]" % datetime.now().strftime("%m-%d-%Y %H:%M:%S")
    print("%s Mail(s) in queue : %s" % (colored_date, colored_queue_length))
    if log:
         msg = "Queue length = %(queue_length)s" % locals()
         log.info(msg)

def logSendingStatus(mail_item, isSent):
    if isSent:
        sending_status = "\033[92msent\033[0m"
        sending_log = "SENT"
    else:
        sending_status = "\033[91mnot sent\033[0m"
        sending_log = "NOT SENT"

    mail_dest = "\033[4m%s\033[0m" % mail_item.dest_mail_address
    hashtag_text = "\033[3m%s\033[0m" % mail_item.mail_template_hashtag
    print("\t- mail %s to : %s => %s" % (sending_status, mail_dest, hashtag_text))
    
    if log:
         to_log = mail_item.dest_mail_address
         hashtag_log = mail_item.mail_template_hashtag
         msg = "Email %(sending_log)s to %(to_log)s [%(hashtag_log)s]" % locals()
         if isSent:
             log.info(msg)
         else:
             log.warning(msg)


######################################################################################################################################################################
# Run Mailing Queue Once
######################################################################################################################################################################
#print("Entering sendQueuedMails")
mails_in_queue = getMailsInQueue()
logMailsInQueue(len(mails_in_queue))
# As the cron runs every minute, we break when the threshold of 50s is reached.
# Remaining emails will be sent on next cron.
start_ts = datetime.now().timestamp()
for mail_item in mails_in_queue:
    curr_ts = datetime.now().timestamp()
    if (curr_ts - start_ts) < 50.0:
        tryToSendMail(mail_item)
        # wait beetween email sendings
        time.sleep(MAIL_DELAY)

