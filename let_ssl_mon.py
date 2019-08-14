import sys
import ssl
import socket
import time
from datetime import datetime

"""
get let's encrypt ssl info

example: /usr/bin/python3 /usr/local/bin/let_ssl_mon.py www.xxx.com 443

"""

def info(*args,**kwargs):
    name = args[0]
    port = int(args[1])

    context = ssl.create_default_context()
    conn = context.wrap_socket(socket.socket(socket.AF_INET),server_hostname=name,)
    conn.settimeout(3.0)
    conn.connect((name,port))
    ssl_info = conn.getpeercert()
    return ssl_info

s1 = sys.argv[1]
s2 = sys.argv[2]

format_time = datetime.strptime(info(s1,s2)['notAfter'],r'%b %d %H:%M:%S %Y %Z')
notbefore = datetime.strptime(info(s1,s2)['notBefore'],r'%b %d %H:%M:%S %Y %Z')

end_days = format_time - datetime.now()

print(end_days.days)
