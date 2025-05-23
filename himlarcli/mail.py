from himlarcli.client import Client
import configparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.utils import formatdate,make_msgid
from email import encoders

class Mail(Client):

    def __init__(self, config_path, debug=False, log=None):
        super(Mail, self).__init__(config_path, debug, log)
        self.server = smtplib.SMTP(self.get_config('mail', 'smtp'), 25)
        if 'uio' in self.get_config('mail', 'smtp'):
            self.server.starttls()

    def enable_mail_debug(self, level=1):
        """ Turn on debug mode on smtplib """
        self.server.set_debuglevel(level)

    def send_mail(self, toaddr, mail, fromaddr=None, cc=None, bcc=None, msgid='default'):
        if fromaddr is None:
            fromaddr = self.get_config('mail', 'from_addr')
        if not 'From' in mail:
            mail['From'] = fromaddr
        if not 'To' in mail:
            mail['To'] = toaddr
        recipients = [toaddr]
        if cc:
            if not 'CC' in mail:
                mail['CC'] = cc
            recipients = recipients + [cc]
        if bcc:
            if not 'BCC' in mail:
                mail['BCC'] = bcc
            recipients = recipients + [bcc]
        mail['Date'] = formatdate(localtime=True)
        mail['Message-ID'] = make_msgid(idstring="nrec-" + msgid)
        if not self.dry_run:
            try:
                self.server.sendmail(fromaddr, recipients, mail.as_string())
            except smtplib.SMTPRecipientsRefused as e:
                self.log_error(e)
            except smtplib.SMTPServerDisconnected as e:
                self.log_error(e)
            except smtplib.SMTPDataError as e:
                self.log_error(e)
        self.debug_log('Sending mail to %s' % recipients)

    def close(self):
        self.debug_log('Closing mail server connection...')
        try:
            self.server.quit()
        except smtplib.SMTPServerDisconnected as e:
            self.log_error(e)

    @staticmethod
    def rt_mail(ticket, subject, msg):
        mail = MIMEMultipart('alternative')
        mail['References'] = 'RT-Ticket-%s@uio.no' % ticket
        mail['Subject'] = '[rt.uio.no #%s] %s' % (ticket, subject)
        mail['From'] = 'NREC support <support@nrec.no>'
        mail['Reply-To'] = 'support@nrec.no'
        mail['RT-Owner'] = 'Nobody'
        mail['X-RT-Queue'] = 'usit-nrec-support'
        mail['X-RT-Ticket'] = 'rt.uio.no #%s' % ticket
        mail.attach(MIMEText(msg, 'plain'))
        return mail

    def get_client(self):
        return self.server

    @staticmethod
    def get_mime_text(subject, body, fromaddr, cc=None):
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = fromaddr
        msg['Reply-To'] = fromaddr #'support@uh-iaas.no'
        if cc:
            msg['CC'] = cc
        return msg

    @staticmethod
    def create_mail_with_txt_attachment(subject, body, attachment_payload, attachment_name, fromaddr, cc=None, bcc=None):
        """
        Construct an email with attachment.

        :param subject: The mail subject
        :param body: The mail body
        :param attachment_payload: Contents of the attachment
        :param attachment_name: Name of the attachment
        :param fromaddr: Address used as From and Reply-To
        :param cc: Optional Cc address
        :param bcc: Optional Bcc address
        :return: returns the mail message
        """
        msg = MIMEMultipart('mixed')
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        attachment = MIMEText(attachment_payload, 'plain', 'utf-8')
        attachment.add_header('Content-Disposition', 'attachment', filename=attachment_name)
        msg.attach(attachment)

        msg['Subject'] = subject
        msg['From'] = fromaddr
        msg['Reply-To'] = fromaddr
        if cc:
            msg['Cc'] = cc
        return msg

    def mail_instance_owner(self, instances, body, subject, admin=False, options=['status']):
        if not self.ksclient:
            self.logger.error('=> notify aborted: unable to find keystone client')
            return
        users = dict()
        for i in instances:
            if not admin:
                user = self.ksclient.get_by_id('user', i.user_id)
                email = self.__get_user_email(user)
            if admin or not email:
                project = self.ksclient.get_by_id('project', i.tenant_id)
                email = self.__get_project_email(project)
            if not email:
                self.logger.debug('=> unable to find owner of %s (%s)', i.name, i.id)
                continue
            if email not in users:
                users[email] = dict()
            users[email][i.name] = {
                'status': i.status,
                'az': getattr(i, 'OS-EXT-AZ:availability_zone')
            }
            if admin:
                users[email][i.name]['project'] = project.name
        # Send mail
        for user, instances in users.iteritems():
            user_instances = (
                "You are receiving this e-mail because you (or a team you're part of)\n"
                "have the following instances running in NREC.\n\n"
            )
            for server, info in instances.iteritems():
                extra = list()
                for option in options:
                    extra.append(info[option])
                user_instances += '%s (' % server + ', '.join(extra) + ')\n'
            msg = MIMEText(user_instances + body, 'plain', 'utf-8')
            msg['Subject'] = subject
            log_msg = 'sending mail to %s' % user
            self.send_mail(user, msg)
        return users

    def set_keystone_client(self, ksclient):
        self.ksclient = ksclient

    def mail_user(self, body, subject, user, bcc=None):
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        log_msg = 'sending mail to %s' % user
        self.send_mail(toaddr=user, mail=msg, bcc=bcc)

    @staticmethod
    def __get_user_email(user):
        if not user:
            return None
        if hasattr(user, 'mail'):
            return user.email.lower()
        if hasattr(user, 'name') and "@" in user.name:
            return user.name.lower()
        return None

    @staticmethod
    def __get_project_email(project):
        if not project:
            return None
        if hasattr(project, 'contact'):
            return project.contact.lower()
        elif hasattr(project, 'admin'):
            return project.admin.lower()
        if hasattr(project, 'type') and project.type == 'personal':
            if hasattr(project, 'name') and "@" in project.name:
                return project.name.lower()
        return None
