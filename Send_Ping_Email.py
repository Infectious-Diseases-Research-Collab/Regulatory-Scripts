import smtplib
from datetime import datetime
from email.message import EmailMessage
from cryptography.fernet import Fernet


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



to_list = ['glavoy@idrc-uganda.org', 'geofflavoy@gmail.com']
    
sender_mail = 'idrcreg@idrc-uganda.org'

subject = 'Automated ping from server'

body = "This is a test email from Python - testing if automated tasks are running."

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
    file_object.write('\nPing EMAIL SENT on ' + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ', To: '+ ';'.join(to_list))
    file_object.close()
except Exception as ex: 
    # Write to log file
    file_object = open('regulatory.log', 'a')
    file_object.write('\nEMAIL FAILED on ' + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    file_object.close()











