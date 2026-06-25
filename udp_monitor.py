#!/usr/bin/python3
# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import json
import smtplib
import socket

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate

CONFIG_FILE = "monit_udp_config.json"


def load_config():
    """Loads configuration from JSON file."""
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print("Failed to load config file '{}': {}".format(CONFIG_FILE, e))
        exit(1)


# Load configuration
CONFIG = load_config()

STATE_FILE = CONFIG.get("state_file", "udp_stats_state.json")
SMTP_SERVER = CONFIG.get("smtp_server")
EMAIL_FROM = CONFIG.get("email_from")
EMAIL_TO = CONFIG.get("email_to", [])
SUBJECT_PREFIX = CONFIG.get("subject_prefix", "UDP Alert")

# Dynamic hostname
HOSTNAME = socket.gethostname()


def get_udp_stats():
    """Parses /proc/net/snmp to get UDP InDatagrams and InErrors."""
    try:
        with open("/proc/net/snmp", "r") as f:
            lines = f.readlines()

            for i, line in enumerate(lines):
                if line.startswith("Udp:"):
                    headers = lines[i].split()
                    values = lines[i + 1].split()

                    stats = dict(zip(headers, values))

                    return {
                        "received": int(stats["InDatagrams"]),
                        "errors": int(stats["InErrors"])
                    }

    except Exception as e:
        print("Error reading /proc/net/snmp: {}".format(e))

    return None


def send_mail(send_from, send_to, subject, text, server):
    msg = MIMEMultipart()

    msg['From'] = send_from
    msg['To'] = COMMASPACE.join(send_to)
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = subject

    msg.attach(MIMEText(text))

    try:
        smtp = smtplib.SMTP(server)
        smtp.sendmail(send_from, send_to, msg.as_string())
        smtp.close()

    except Exception as e:
        print("Failed to send email: {}".format(e))


def main():
    current_stats = get_udp_stats()

    if not current_stats:
        return

    # Load previous state
    prev_stats = None

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                prev_stats = json.load(f)

        except Exception:
            pass

    # Save current state
    with open(STATE_FILE, "w") as f:
        json.dump(current_stats, f)

    # First execution
    if not prev_stats:
        print("First run: State initialized.")
        return

    # Counter reset protection
    if current_stats["received"] < prev_stats["received"]:
        print("Counter reset detected. Skipping calculation.")
        return

    delta_received = current_stats["received"] - prev_stats["received"]
    delta_errors = current_stats["errors"] - prev_stats["errors"]

    # Alert if new UDP errors occurred
    if delta_errors > 0:

        error_pct = (
            delta_errors * 100.0 / delta_received
            if delta_received > 0 else 0.0
        )

        body = (
            "UDP Error Alert for {}\n"
            "----------------------------------\n"
            "Interval: Last 60 seconds\n"
            "New Packets Received: {}\n"
            "New Packet Errors: {}\n"
            "Error Rate: {:.4f}%\n"
        ).format(
            HOSTNAME,
            delta_received,
            delta_errors,
            error_pct
        )

        subject = "{}: {} - {} New Errors".format(
            SUBJECT_PREFIX,
            HOSTNAME,
            delta_errors
        )

        send_mail(
            send_from=EMAIL_FROM,
            send_to=EMAIL_TO,
            subject=subject,
            text=body,
            server=SMTP_SERVER
        )

        print("Alert sent: {} errors found.".format(delta_errors))

    else:
        print("No new errors detected.")


if __name__ == "__main__":
    main()

