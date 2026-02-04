import smtplib
import urllib
import pyodbc
from datetime import datetime
from email.message import EmailMessage
import traceback
import pandas as pd
import sqlalchemy as db
from cryptography.fernet import Fernet

server = "PONTIAC"
database = "Regulatory"

sender_mail = "idrcreg@idrc-uganda.org"
admin_email = "glavoy@idrc-uganda.org"
ping_recipients = ["glavoy@proton.me"]

# Adjust this value anytime without changing the rest of the script.
DAYS_BEFORE_EXPIRY = 30

CERTIFICATIONS = [
    {
        "name": "APL",
        "expiry_column": "apl_expiry_date",
        "sent_column": "apl_60_day_sent",
    },
    {
        "name": "GCP",
        "expiry_column": "gcp_expiry_date",
        "sent_column": "gcp_60_day_sent",
    },
    {
        "name": "HSP",
        "expiry_column": "hsp_expiry_date",
        "sent_column": "hsp_60_day_sent",
    },
]


def write_log(message):
    print(message)
    with open("regulatory.log", "a") as file_object:
        file_object.write("\n" + message)


def get_mail_password():
    with open("key.key", "r") as key_in:
        key = key_in.read().encode()

    f = Fernet(key)
    with open("CredFile.ini", "r") as cred_in:
        lines = cred_in.readlines()

    config = {}
    for line in lines:
        tuples = line.rstrip("\n").split("=", 1)
        if tuples[0] == "Password":
            config[tuples[0]] = tuples[1]

    return f.decrypt(config["Password"].encode()).decode()


def send_cert_email(smtp_server, name, email_address, cert_name, expiry_date):
    to_list = [email_address, admin_email]
    subject = f"{cert_name} certificate expiry reminder"
    body = (
        f"Dear {name},\n\n"
        f"This is a reminder that your {cert_name} certificate is expiring on {expiry_date}.\n"
        "Please complete renewal before expiry and share updated documentation with the Regulatory team.\n\n"
        "**NOTE: This is an auto-generated email, please do not reply.\n"
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender_mail
    msg["To"] = ", ".join(to_list)
    msg.set_content(body)

    smtp_server.send_message(msg)
    write_log(
        "INVESTIGATOR REMINDER EMAIL SENT on "
        + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        + ", To: "
        + ";".join(to_list)
        + ", name: "
        + str(name)
        + ", cert: "
        + cert_name
        + ", expirydate: "
        + str(expiry_date)
    )


def send_ping_email(smtp_server):
    msg = EmailMessage()
    msg["Subject"] = "No investigator reminder emails today!"
    msg["From"] = sender_mail
    msg["To"] = ", ".join(ping_recipients)
    msg.set_content("There are no investigator reminder emails to send out today.")
    smtp_server.send_message(msg)

    write_log(
        "NO INVESTIGATOR REMINDER emails today sent on "
        + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        + ", To: "
        + ";".join(ping_recipients)
    )


params = urllib.parse.quote_plus(
    "DRIVER={SQL Server};"
    + "SERVER="
    + server
    + ";"
    + "DATABASE="
    + database
    + ";"
    + "trusted_connection=yes"
)

engine = db.create_engine("mssql+pyodbc:///?odbc_connect={}".format(params))
conn = None
cursor = None
smtp_server = None
emails_to_send = 0

try:
    write_log(
        "INVESTIGATOR REMINDER PROCESS STARTED on "
        + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        + f", days_before_expiry={DAYS_BEFORE_EXPIRY}"
    )

    conn = pyodbc.connect(
        "Driver={SQL Server};"
        + "SERVER="
        + server
        + ";"
        + "DATABASE="
        + database
        + ";"
        + "Trusted_Connection=yes;"
    )
    cursor = conn.cursor()
    write_log("Database connection established.")

    password = get_mail_password()
    smtp_server = smtplib.SMTP_SSL("smtp.dreamhost.com", 465)
    smtp_server.login(sender_mail, password)
    write_log("SMTP login successful.")

    for cert in CERTIFICATIONS:
        write_log(f"Checking {cert['name']} expiries...")
        df = pd.read_sql_query(
            sql=f"""
                SELECT investigator_id, name, email_address,
                       CONVERT(varchar(10), {cert["expiry_column"]}, 23) AS expiry_date
                FROM investigators
                WHERE {cert["expiry_column"]} IS NOT NULL
                  AND email_address IS NOT NULL
                  AND LTRIM(RTRIM(email_address)) <> ''
                  AND DATEDIFF(d, GETDATE(), {cert["expiry_column"]}) BETWEEN 0 AND {DAYS_BEFORE_EXPIRY}
                  AND ISNULL({cert["sent_column"]}, 0) = 0
                ORDER BY {cert["expiry_column"]}, investigator_id
            """,
            con=engine,
        )
        write_log(f"{cert['name']} rows to email: {len(df)}")

        for _, row in df.iterrows():
            try:
                write_log(
                    f"Sending {cert['name']} reminder to investigator_id={row['investigator_id']}, email={row['email_address']}"
                )
                send_cert_email(
                    smtp_server=smtp_server,
                    name=row["name"],
                    email_address=row["email_address"],
                    cert_name=cert["name"],
                    expiry_date=row["expiry_date"],
                )
                cursor.execute(
                    f"UPDATE investigators SET {cert['sent_column']} = 1 WHERE investigator_id = ?",
                    int(row["investigator_id"]),
                )
                conn.commit()
                write_log(
                    f"Updated investigator_id={row['investigator_id']} set {cert['sent_column']}=1"
                )
                emails_to_send += 1
            except Exception as ex:
                write_log(
                    "INVESTIGATOR REMINDER EMAIL FAILED on "
                    + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    + ", name: "
                    + str(row["name"])
                    + ", cert: "
                    + cert["name"]
                    + ", error: "
                    + str(ex)
                )
                write_log(traceback.format_exc())

    if emails_to_send == 0:
        write_log("No reminder emails found. Sending ping email.")
        send_ping_email(smtp_server)
except Exception as ex:
    write_log(
        "INVESTIGATOR REMINDER PROCESS FAILED on "
        + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        + ", error: "
        + str(ex)
    )
    write_log(traceback.format_exc())
finally:
    if smtp_server is not None:
        smtp_server.quit()
    if cursor is not None:
        cursor.close()
    if conn is not None:
        conn.close()
