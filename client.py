import argparse
import os
import sys

from pop3 import POP3, POP3_PORT, POP3_SERVER

SENDER = "From"
RECEIVERS = "To"
TEXT = "Text"
SUBJECT = "Subject"
ATTACHMENTS = "Attachments"


def main():
    parser = argparse.ArgumentParser(
        usage='{} [OPTIONS]'.format(
            os.path.basename(
                sys.argv[0])),
        description='SMTP client')
    parser.add_argument('address', help='address to connect',
                        nargs='?', default=POP3_SERVER)
    parser.add_argument('port', help='port', nargs='?',
                        type=int, default=POP3_PORT)
    parser.add_argument('-c', '--console', action="store_true", help="Enable console mode")

    args = parser.parse_args()
    pop3_con = POP3(args.address, args.port)
    print(pop3_con.connect())
    if args.console:
        pop3_con.run_batch()


if __name__ == '__main__':
    sys.exit(main())
