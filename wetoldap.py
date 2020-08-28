import os
import requests
import json
import hashlib
import datetime
import random
import pypinyin


#企业微信的后台管理和企业微信的secret
CORPID = "xxxxxxx"
SECRET = "xxxxxxx"

TOKEN_URL = 'https://qyapi.weixin.qq.com/cgi-bin/gettoken'
GROUP_URL = 'https://qyapi.weixin.qq.com/cgi-bin/department/list'
MEMBER_URL = 'https://qyapi.weixin.qq.com/cgi-bin/user/simplelist'
LDAP_USER = "cn=root,dc=example,dc=com"
LDAP_PASWD = "xxxxxxx"
DIR_PATH = os.path.split(os.path.realpath(__file__))[0]
#prod
#SERVER_HOST = "ldap://172.17.2.136"
#test
SERVER_HOST = "ldap://192.168.12.93"
GROUP_CONF = "%s/partment.ldif"%(DIR_PATH)
MEMBER_CONF = "%s/member.ldif"%(DIR_PATH)
MODIFY_CONF = "%s/modify.ldif"%(DIR_PATH)
MEMBER_CACHE = "%s/member.json"%(DIR_PATH)
GROUP_CACHE = "%s/group.json"%(DIR_PATH)

def dataGet(url,params):
    """获取数据小函数"""
    res = requests.get(url=url,params=params)
    return res

def cnToen(word):
    """汉字转换为拼音"""
    str = ''
    for i in pypinyin.pinyin(word, style=pypinyin.NORMAL):
        str += ''.join(i)
    return str

def uniqrandom():
    nowTime = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    ranDom = random.randint(0,100000)
    return str(nowTime)+str(ranDom)

def saveData(filedict):
    """保存新拉的数据到本地缓存文件 以便下次拉取进行对比"""
    for i in filedict:
        json.dump(filedict[i],open(i,'w'))

def genPasswd(name):
    """生成每个成员的密码 md5"""
    src = "%sYsx@1ppt"%(name)
    modify = hashlib.md5()
    modify.update(src.encode("utf-8"))
    return modify.hexdigest()

ACCESSTOKEN = dataGet(TOKEN_URL,{'corpid':CORPID,'corpsecret':SECRET}).json()['access_token']
GROUPLISTGET = dataGet(GROUP_URL,{'access_token':ACCESSTOKEN})

def wechatDataRet():
    groupDict = {}
    memberDict = {}
    for i in GROUPLISTGET.json()['department']:
        """
        循环取出wechat所有部门名称 以及对应的id 转换为拼音 并添加到group dict中
        循环通过每个部门的id取出部门里所有人员名称 以及对应的部门id 并添加到member dict中
        """
        memberListGet = dataGet(MEMBER_URL,{'access_token':ACCESSTOKEN,'department_id':i['id']})
        groupDict[i['id']] = cnToen(i['name'])
        """由于在json规则中userid的为人员名称的拼音 所以直接取userid即可"""
        for i in memberListGet.json()['userlist']:
            memberDict[(i["userid"]).lower()] = i['department']
    return groupDict,memberDict

def difNeOl(data,file):
    """
    针对新拉取的数据与旧缓存数据进行比对
    old - new 表示缓存存在 但是wechat不存在 即删除ldap账号
    new - old 表示wechat存在 但是缓存没有 即添加账号
    """
    old_Memb = json.load(open(MEMBER_CACHE))
    old_Grou = json.load(open(GROUP_CACHE))
    if file == GROUP_CACHE:
        old = set(old_Grou.values())
        new = set(data.values())
        return list(old - new),list(new - old)
    elif file == MEMBER_CACHE:
        old = set(old_Memb)
        new = set(data)
        return list(old - new), list(new - old)
    else:
        print("cache file Error")

def initLdap(choose,data,conf):
    """执行创建语句"""
    genraLdif(choose=choose, data=data)
    os.system('ldapadd -x -D %s -w %s -H %s -f %s' % (LDAP_USER, LDAP_PASWD, SERVER_HOST, conf))

def syncMembInfo(data,choose):
    """如果有已离开或者新入职的员工他是在哪个部门 获取部门"""
    old_Memb = json.load(open(MEMBER_CACHE))
    old_Grou = json.load(open(GROUP_CACHE))
    if data and choose == "dele":
        for i in data:
            old_memb = old_Memb[i]
            os.system('ldapdelete -x -D %s -w %s -H %s \
                        "cn=%s,ou=people,dc=yunshuxie,dc=com"'%(LDAP_USER,LDAP_PASWD,SERVER_HOST,i))
            confluenceUser("delete",i)
            for z in old_memb:
                groupEdit("delete",i,old_Grou[str(z)])
            print("%s -- %s"%(i,choose))
    elif data and choose == "add":
        for i in data:
            initLdap("member", i, MEMBER_CONF)
            confluenceUser(choose,i)
            for z in memberDic[i]:
                groupEdit(choose,i,groupDic[z])
            print("%s -- %s"%(i,choose))
    else:
        print('人员无%s'%(choose))

def syncGroup(group,choose):
    """对部门进行增删同步"""
    if group and choose == "dele":
        for i in group:
            os.system('ldapdelete -x -D %s -w %s -H %s \
                    "ou=%s,ou=group,dc=yunshuxie,dc=com"'%(LDAP_USER,LDAP_PASWD,SERVER_HOST,i))
            print("%s部门已删除"%(i))
    elif group and choose == "add":
        for i in group:
            initLdap("partment",i,GROUP_CONF)
            print("%s部门已添加"%(i))
    else:
        print('人事架构无%s'%(choose))

def confluenceUser(choose,name):
    """关联所有成员到confluence-user组中"""
    confluenceUser="""
        dn: ou=confluence-users,ou=group,dc=yunshuxie,dc=com
        changetype: modify
        %s: uniqueMember
        uniqueMember: cn=%s,ou=people,dc=yunshuxie,dc=com
    """%(choose,name)
    with open(MODIFY_CONF,'w') as f:
        f.write(confluenceUser.replace(" ",""))
    os.system('ldapadd -x -D %s -w %s -H %s -f %s' % (LDAP_USER, LDAP_PASWD, SERVER_HOST, MODIFY_CONF))

def groupEdit(choose,name,partment):
    """对每个成员进行所在的组关联以及 删除时对成员的组进行同步删除"""
    modifyLdif="""
        dn: ou=%s,ou=group,dc=yunshuxie,dc=com
        changetype: modify
        %s: uniqueMember
        uniqueMember: cn=%s,ou=people,dc=yunshuxie,dc=com
    """%(partment,choose,name)


    with open(MODIFY_CONF, 'w') as f:
        f.write(modifyLdif.replace(" ", ""))
    os.system('ldapadd -x -D %s -w %s -H %s -f %s' % (LDAP_USER, LDAP_PASWD, SERVER_HOST, MODIFY_CONF))

def genraLdif(choose, data):
   partmentLdif = """
       dn: ou=%s,ou=group,dc=yunshuxie,dc=com
       objectClass: groupOfUniqueNames
       cn: %s
       uniqueMember: ou=manager,dc=yunshuxie,dc=com
       """ % (data, data)

   memberLdif = """
        dn: cn=%s,ou=people,dc=yunshuxie,dc=com
        objectClass: top
        objectClass: inetOrgPerson
        objectClass: posixAccount
        givenName: %s
        mail: %s@yunshuxie.com
        uid: %s
        displayName: %s
        userPassword: %s
        description: LDAP %s
        gidNumber: 1007
        uidNumber: %s
        homeDirectory: /home/%s
        sn: %s
        cn: %s
        """ % (data, data, data, data, data, genPasswd(data), data, uniqrandom(), data, data, data)
   if choose == "partment":
      with open(GROUP_CONF,'w') as f:
         f.write(partmentLdif.replace(" ",""))
   elif choose == "member":
      with open(MEMBER_CONF,"w") as f:
         f.write(memberLdif.replace(" ",""))
   else:
      print("argments Error")
      exit()



if os.path.exists("%s"%(MEMBER_CACHE)) and os.path.getsize("%s"%(MEMBER_CACHE)) \
   and os.path.exists("%s"%(GROUP_CACHE)) and os.path.getsize("%s"%(GROUP_CACHE)):
    """
    判断如果缓存文件都存在并且都不为空则视为人事框架及人员已存在 直接进行增量增删即可
    如果不符合要求 即视为ldap人事架构及人员为空 需重新初始化 并创建
    """
    groupDic, memberDic = wechatDataRet()
    old_G,new_G = difNeOl(groupDic,GROUP_CACHE)
    old_M, new_M = difNeOl(memberDic, MEMBER_CACHE)
    syncGroup(new_G,"add")
    syncMembInfo(new_M, "add")
    syncMembInfo(old_M,"dele")
    syncGroup(old_G, "dele")
    saveData({MEMBER_CACHE:memberDic,GROUP_CACHE:groupDic})
    print("%s  部门数：%s,人员数：%s" % (datetime.datetime.now(),len(groupDic), len(memberDic)))
else:
    groupDic, memberDic = wechatDataRet()
    for id,departments in groupDic.items():
        initLdap("partment",departments,GROUP_CONF)
    for member,id in memberDic.items():
        initLdap("member",member,MEMBER_CONF)
        confluenceUser("add", member)
        for i in memberDic[member]:
            groupEdit("add",member,groupDic[i])
    print("%s  部门数：%s,人员数：%s" % (datetime.datetime.now(),len(groupDic), len(memberDic)))
    saveData({MEMBER_CACHE:memberDic,GROUP_CACHE:groupDic})