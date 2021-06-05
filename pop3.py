import base64
import re
import socket
import ssl
from configparser import ConfigParser

parser = ConfigParser()
with open('config.cfg', 'r', encoding='utf-8') as f:
    parser.read_file(f)
FROM_MAIL = parser['Account_from']['Login']
PASSWORD = parser['Account_from']['Password']
POP3_SERVER = parser['Account_from']['Mail']
POP3_PORT = int(parser['Account_from']['Port'])

ENCODING = 'utf-8'
MAXLENGTH = 4096

CRLF = '\r\n'
B_CRLF = b'\r\n'


class POP3:
    welcome = None
    closed = False

    def __init__(self, address=None, port=None):
        if not address and not port:
            self.address = None
        else:
            self.address = (address, port)
        self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.receivers = []
        self.sender = ""
        self.subject = ""

        self.commands = {"AUTH": self.auth,
                         "USER": self.user,
                         "DELE": self.delete,
                         "PASS": self.password,
                         "STAT": self.stat,
                         "LIST": self.list,
                         "TOP": self.top,
                         "NOOP": self.noop,
                         "RSET": self.reset,
                         "RETR": self.retrieve,
                         "QUIT": self.quit,
                         "HELP": self.help,
                         }

    def help(self, command=None):
        """
        Prints list of available commands, if called without arguments.
        Prints command's docstring otherwise.
        :param command:
        :return:
        """
        if not command:
            header = "List of available commands:\n"
            body = ", ".join(cmd for cmd in self.commands.keys())
            return header + body
        return self.commands[command.upper()].__doc__.replace(":return:", "")

    def stat(self):
        """
        Learn, how many letters there are on the server and the total size
        :return:
        """
        rep = self.send("STAT" + CRLF)
        return rep

    def list(self, letter_number=None):
        """
        Gets info about every letter, if no arguments are given,
        or about one passed as an argument
        :param letter_number:
        :return:
        """
        if letter_number is None:
            letter_number = ""
        rep = self.send(f"LIST {letter_number}" + CRLF)
        return rep

    def user(self, username):
        """
        Sends username to server. The next command must be PASS.
        :param username:
        :return:
        """
        rep = self.send(f"USER {username}" + CRLF)
        return rep

    def password(self, password):
        """
        Sends password to server. The previous command must be USER.
        :param password:
        :return:
        """
        rep = self.send(f"PASS {password}" + CRLF)
        return rep

    def auth(self, username=FROM_MAIL, password=PASSWORD):
        """
        USER and PASS commands combined.
        :param username:
        :param password:
        :return:
        """
        print(self.user(username))
        return self.password(password)

    def delete(self, letter_number):
        """
        Mark letter as to be deleted.
        :param letter_number:
        :return:
        """
        rep = self.send(f"DELE {letter_number}" + CRLF)
        return rep

    def reset(self):
        """
        Cancel deletion marks.
        :return:
        """
        rep = self.send("RSET" + CRLF)
        return rep

    def top(self, mail_num, lines_shown=0):
        """
        Shows headers of <mail_num> letter, and <lines_shown> of the message itself.
        :param mail_num:
        :param lines_shown:
        :return:
        """
        mes = f"TOP {mail_num} {lines_shown}" + CRLF
        rep = self.send(mes)
        return rep

    def retrieve(self, letter_number):
        """
        Download letter from the server
        :param letter_number:
        :return:
        """
        rep = self.send("RETR " + letter_number + CRLF)
        result = []

        print(self.parse_sender(rep))
        print(self.parse_subject(rep))
        print(self.parse_date(rep))

        boundary = self.find_boundary(rep)
        if boundary:
            mime_objects = self.find_mime(boundary, rep)
            for obj in mime_objects:
                result.append(self.parse_mime(obj))
        else:
            result.append(self.find_text(rep))
        for element in result:
            if isinstance(element, tuple):
                print("Saving attachment " + element[0])
                with open(element[0], 'wb') as f:
                    f.write(element[1])
            else:
                print(element)

    def parse_sender(self, text):
        from_reg_base64 = re.compile("From: (=\?.*\?=).*?<(.*)>")
        from_reg_no_base64 = re.compile("From: (.*).*?<(.*)>")

        sender_match = re.search(from_reg_base64, text)
        if sender_match:
            name = self.parse_base64_string(sender_match.group(1))
            mail = sender_match.group(2)
            return "From: {0} ({1})".format(name, mail)
        sender_match = re.search(from_reg_no_base64, text)
        name = sender_match.group(1)
        mail = sender_match.group(2)
        return "From: {0} ({1})".format(name, mail)

    def parse_date(self, text):
        date_reg = re.compile("Date: .*")
        return re.search(date_reg, text).group(0)

    def parse_subject(self, text):
        subj_reg_base64 = re.compile("Subject: (=\?.*\?=)")
        subj_reg__no_base64 = re.compile("Subject: (.*)")

        subj_match = re.search(subj_reg_base64, text)
        if subj_match:
            topic = self.parse_base64_string(subj_match.group(1))
            return "Subject: {0}".format(topic)
        subj_match = re.search(subj_reg__no_base64, text)
        if subj_match:
            return "Subject: {0}".format(subj_match.group(1))
        return "Subject: (Без темы)"

    def find_text(self, text):
        text_reg = re.compile("\n\n(.*)\.", re.DOTALL)
        text_reg2 = re.compile("\r\n\r\n(.*)\.", re.DOTALL)
        plain_text = re.search(text_reg, text)
        if not plain_text:
            plain_text = re.search(text_reg2, text)
        return plain_text.group(1)

    def parse_mime(self, text):
        coded_reg = re.compile('\n\n(.+==)', re.DOTALL)
        coded_reg2 = re.compile('\r\n\r\n(.+?)--', re.DOTALL)
        plain_reg = re.compile('Content-Transfer-Encoding:.*?\r\n\r\n(.+?)--',
                               re.DOTALL)
        filename_reg = re.compile('filename="(.*)"')
        if "text" in text:
            if "base64" in text:
                coded = re.search(coded_reg, text).group(1)
                return base64.b64decode(coded)
            else:
                lines = re.search(plain_reg, text).group(1).split("\n")
                result = []
                for line in lines:
                    if not line:
                        continue
                    if line[0] == '.':
                        line = line[1:]
                    result.append(line)
                return "\n".join(result)
        elif "Content-Disposition: attachment" in text:
            coded = re.search(coded_reg, text)
            if not coded:
                coded = re.search(coded_reg2, text)
            filename = self.parse_base64_string(re.search(filename_reg,
                                                          text).group(1))
            coded_text = coded.group(1).strip('\n').strip('\r')
            return filename, base64.b64decode(coded_text)

    def parse_base64_string(self, name):
        encoding_regex = re.compile("=\?(.+)\?B\?(.+)\?=")
        match = re.search(encoding_regex, name)
        if match:
            encoding = match.group(1)
            filename = match.group(2)
            return base64.b64decode(filename).decode(encoding)
        return name

    def find_mime(self, boundary, text):
        regexp = re.compile(r'(?=(--{0}(.+?)--{0}))'.format(boundary),
                            re.DOTALL)
        matches = re.finditer(regexp, text)
        if matches:
            result = []
            for match in matches:
                result.append(match.group(1))
            return result

    def find_boundary(self, text):
        match = re.search('boundary="(.+?)"', text)
        if match:
            return match.group(1)

    def noop(self):
        """
        Empty keep-alive message.
        :return:
        """
        rep = self.send("NOOP" + CRLF)
        return rep

    def quit(self):
        """
        Ends the session. Server will now delete marked messages
        :return:
        """
        rep = self.send("QUIT" + CRLF)
        self.closed = True
        self.control_socket.shutdown(socket.SHUT_RDWR)
        self.control_socket.close()
        return rep

    def send(self, command, text=True):
        """
        Send a command to server
        :param text:
        :param command:
        :return:
        """
        if text:
            self.control_socket.sendall(command.encode(ENCODING))
        else:
            self.control_socket.sendall(command)
        return self.get_reply()

    def connect(self, address=None, port=None):
        """
        Connect to the server and print welcome message
        :return:
        """
        if not self.address:
            self.address = (address, port)
        elif not address and not port and not self.address:
            raise Exception("Address and port must be specified in "
                            "constructor or in connect()")
        self.control_socket = ssl.wrap_socket(
            self.control_socket, ssl_version=ssl.PROTOCOL_SSLv23)
        self.control_socket.connect(self.address)
        self.control_socket.settimeout(1)
        self.welcome = self.get_reply()
        return self.welcome

    def get_reply(self):
        """
        Get a reply from server
        :return:
        """
        reply = self.__get_full_reply()
        return reply

    def __get_full_reply(self):
        """
        Get a long reply
        :return:
        """
        reply = ''
        tmp = self.control_socket.recv(MAXLENGTH).decode(ENCODING)
        reply += tmp
        while tmp:
            try:
                tmp = self.control_socket.recv(MAXLENGTH).decode(ENCODING)
                reply += tmp
            except Exception:
                break
        return reply

    def run_batch(self):
        """
        Runs a POP3 client in console mode
        :return:
        """
        while not self.closed:
            print("Type a command:")
            inp = input().split(' ')
            command = inp[0].upper()
            arguments = inp[1:]
            if command in self.commands:
                if arguments:
                    if len(arguments) == 1:
                        print(
                            self.commands[command](arguments[0]))
                    if len(arguments) == 2:
                        print(self.commands[command](arguments[0], arguments[1]))
                else:
                    print(self.commands[command]())
            else:
                print("UNKNOWN COMMAND")
