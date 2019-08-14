from urllib3.contrib import pyopenssl as req
import idna
from datetime import datetime
import sys

"""
install module:
    idna,urllib3,pyopenssl

example: /usr/bin/python3 /usr/local/bin/ssl_mon.py www.xxx.com 443
"""

def ssl_mon(*args,**kwargs):
    x509 = req.OpenSSL.crypto.load_certificate(req.OpenSSL.crypto.FILETYPE_PEM,req.ssl.get_server_certificate((args)))
    x509.get_notAfter()
    notafter = datetime.strptime(x509.get_notAfter().decode()[0:-1],'%Y%m%d%H%M%S')
    remain = notafter - datetime.now()
    print(remain.days)

s1 = sys.argv[1]
s2 = sys.argv[2]

ssl_mon(s1,s2)