import smtplib
import urllib
import pyodbc
from datetime import datetime
from email.message import EmailMessage
import pandas as pd
import sqlalchemy as db
from cryptography.fernet import Fernet

server = 'PONTIAC'
database = 'Regulatory'

params = urllib.parse.quote_plus("DRIVER={SQL Server};"
                                 "SERVER="+server+";"
                                 "DATABASE="+database+";"
                                 "trusted_connection=yes")

engine = db.create_engine("mssql+pyodbc:///?odbc_connect={}".format(params))

conn = pyodbc.connect('Driver={SQL Server};'
                      "SERVER="+server+";"
                      "DATABASE="+database+";"
                      'Trusted_Connection=yes;')

cursor = conn.cursor()


# SQLAlCHEMY ORM QUERY TO FETCH ALL RECORDS
df = pd.read_sql_query(
    sql = """
    SELECT projectbodies.project, projectbodies.regbody, projectbodies.expirydate, projectemails.emailaddress
    FROM projectbodies INNER JOIN
                             projectemails ON projectbodies.project = projectemails.project
    WHERE datediff(d, getdate(), projectbodies.expirydate) <= 61
            AND projectbodies.needsattentionsent = 0 AND projectbodies.expirystatus = 'OK'
    ORDER BY projectbodies.expirydate, projectbodies.project, projectbodies.regbody
    """,
    con = engine
    )


study_df = df.drop(columns=['emailaddress'])
study_df = study_df.drop_duplicates()
study_df.reset_index(drop=True, inplace=True)

# Use CredFile.ini and key.key to retreive password
# CredFile.ini and key.key were created using writeCredentialsToFile.py
cred_filename = 'CredFile.ini'
key_file = 'key.key'
key = ''

with open('key.key','r') as key_in:
        key = key_in.read().encode()

f = Fernet(key)
with open(cred_filename,'r') as cred_in:
        lines = cred_in.readlines()
        config = {}
        for line in lines:
            tuples = line.rstrip('\n').split('=',1)
            if tuples[0] in ('Password'):
                config[tuples[0]] = tuples[1]
        password = f.decrypt(config['Password'].encode()).decode()


def sendmail(project, regbody, expirydate):
    emails = df[(df["project"]==project) & (df["regbody"]==regbody) & (df["expirydate"]==expirydate)]
    to_list = emails['emailaddress'].tolist()
    to_list.append("glavoy@idrc-uganda.org")
    
    # delete this later
    # to_list = ['glavoy@idrc-uganda.org', 'geofflavoy@gmail.com', 'idrcreg@idrc-uganda.org']
    
    sender_mail = 'idrcreg@idrc-uganda.org'

    subject = 'IRB Renewal Requires Your Attention'

    body = """Dear PIs and Study Coordinator:

This is a reminder from the IDRC Regulatory Core team that your study: '""" + project + """' is due for annual renewal submission at: """ +  regbody + """. The current approval for this study expires on: """ + expirydate + """.

Please send the annual report to the IDRC regulatory team as soon as possible to ensure that your study\'s approval will not lapse. If you require a copy of last year\'s submission, please contact Faith Kagoya at fkagoya@idrc-uganda.org.

We appreciate you urgent attention to this matter!

IDRC Reg Team - Bridget, Faith and Emma

**NOTE: This is an auto-generated email, please do not reply.
    """

    # create email
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender_mail
    msg['To'] = to_list
    msg.set_content(body)
    
    try:
        smtp_server = smtplib.SMTP_SSL("smtp.dreamhost.com", 465)
        smtp_server.login(sender_mail, password)
        smtp_server.send_message(msg)
        # update database
        cursor.execute("update projectbodies set expirystatus = 'Needs Attention', needsattentionsent = 1 where needsattentionsent = 0 and datediff(d, getdate(), expirydate) <= 61 and expirystatus = 'OK'")
        conn.commit()
        cursor.close()
        conn.close()
        # Write to log file
        file_object = open('regulatory.log', 'a')
        file_object.write('\nEMAIL SENT on ' + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ', To: '+ ';'.join(to_list) + ', project: ' + project + ', regbody: ' + regbody + ', expirydate: ' + expirydate)
        file_object.close()
    except Exception as ex: 
        # Write to log file
        file_object = open('regulatory.log', 'a')
        file_object.write('\nEMAIL FAILED on ' + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        file_object.close()




def sendPingMail():
    to_list = ['glavoy@proton.me']
        
    sender_mail = 'idrcreg@idrc-uganda.org'

    subject = 'No Needs Attention emails today!'

    body = "There are no 'Needs Attention' emails to send out today."

    # create email
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender_mail
    msg['To'] = to_list
    msg.set_content(body)

    try:
        smtp_server = smtplib.SMTP_SSL("smtp.dreamhost.com", 465)
        smtp_server.login(sender_mail, password)
        smtp_server.send_message(msg)
    
        # Write to log file
        file_object = open('regulatory.log', 'a')
        file_object.write('\nNO NEEDS ATTENTION emails today sent on ' + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ', To: '+ ';'.join(to_list))
        file_object.close()
    except Exception as ex: 
        # Write to log file
        file_object = open('regulatory.log', 'a')
        file_object.write('\nNO NEEDS ATTENTION EMAIL FAILED on ' + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        file_object.close()



# Send a 'ping' email, if nothing to send, otherwise, send the emails
if study_df.empty:
    sendPingMail()
else:
    for index, row in study_df.iterrows():
        sendmail(row['project'], row['regbody'], row['expirydate'])


