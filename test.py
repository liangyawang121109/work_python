import hashlib

def genPasswd(name):
    """生成每个成员的密码 md5"""
    src = "%sYsx@1ppt"%(name)
    modify = hashlib.md5()
    modify.update(src.encode("utf-8"))
    print(modify.hexdigest())

genPasswd("fantengjiang")

