import paramiko
import sys
import re
import os
import json
import shutil
from jinja2 import Template
from datetime import datetime
import pymysql

sys.stdout.flush()
serverInfo = {
    '172.17.2.65': {
        'user': 'root',
        'port': '1662',
        'disk': '',
        'load1': '',
        'load5': '',
        'memory': '',
    },
    '172.17.2.66': {
        'user': 'root',
        'port': '1662',
        'disk': '',
        'load1': '',
        'load5': '',
        'memory': '',
    }
}

PROXYSERVER = '172.17.2.66'
DIR_PATH = os.path.split(os.path.realpath(__file__))[0]
BUILD_CONF = '%s/build.conf' % DIR_PATH
NS_CONF = '%s/namespace.conf' % DIR_PATH
NG_TEMPLATE = '%s/template.ups' % DIR_PATH
NG_UP_path = '/usr/local/orange/conf/upstreams'
environment_tab = 'facilities_environment'
applicant_tab = 'facilities_applicant'
project_tab = 'facilities_project'
TIME = datetime.now()
MYSQL_SERVER = '172.17.0.203'
# 初始化数据链接
db = pymysql.connect(host=MYSQL_SERVER, user='ysx_dba', password='Dba@D83au4acn6', db='cmdb', charset='utf8',
                     autocommit=True)
# 执行sql以json格式返回数据
cur = db.cursor(pymysql.cursors.DictCursor)


def select_data(table, name, option):
    """通过传入不同的表以及字段值获取对应的id并返回 返回值为id号"""
    if option == 'container':
        field = 'container_name'
    else:
        field = 'name'
    try:
        sql = "select id from %s where %s = '%s'" % (table, field, name)
        cur.execute(sql)
        data = cur.fetchall()
        print(data)
        print('数据id获取成功')
        return data[0]['id']
    except Exception as e:
        print('数据id获取失败 %s\n' % name, e)
        exit()


def check_sql_data():
    """判断容器名是否已经存在 存在返回0 不存在返回1"""

    sql = "select * from %s where container_name = '%s'" % (environment_tab, container_name)
    cur.execute(sql)
    data = cur.fetchall()
    if data:
        return 0
    else:
        return 1


def relation_data():
    """关联数据库数据"""
    project_id = select_data(project_tab, project, 'name')
    applicant_id = select_data(applicant_tab, build_user, 'name')
    env_id = select_data(environment_tab, container_name, 'container')
    env_applicant_sql = "insert into facilities_environment_applicant " \
                        "(environment_id,applicant_id) values ('%s','%s')" % (env_id, applicant_id)

    env_project_sql = "insert into facilities_environment_project" \
                      "(environment_id,project_id) values ('%s','%s')" % (env_id, project_id)
    try:
        cur.execute(env_applicant_sql)
        cur.execute(env_project_sql)
        print('数据关联成功')
    except Exception as e:
        print('数据关联失败\n', e)
        exit()


def data_insert(port):
    """数据插入与更新  如果有相同数据 那么更新即可 如果没有即插入数据"""
    data_status = check_sql_data()
    update_sql = "update %s set container_port = %s where container_name = '%s'" % \
                 (environment_tab, port, container_name)
    environment_sql = "insert into %s " \
                      "(env_flag,env_tag,container_name,container_port,node_ip,create_time) " \
                      "values('%s','%s','%s%s%s',%s,'%s','%s')" % (environment_tab, env, tag, env, tag, project,
                                                                   port, return_ip(), datetime.now())
    if data_status == 0:
        print(data_status)
        print(update_sql)
        try:
            cur.execute(update_sql)
            print('更新数据库信息成功')
        except Exception as e:
            print('数据库信息更新失败\n%s' % e)
            exit()
    else:
        try:
            cur.execute(environment_sql)
            print('数据库插入完成')
            relation_data()  # 调用数据关联函数 关联对应表数据
        except Exception as e:
            print('数据库插入失败\n%s' % e)
            exit()


def get_port(host, port, user):
    """获取应用容器端口"""
    get_port_cmd = "docker ps | awk '$NF == \"%s%s%s\" {print $(NF-1)}' | awk -F \"->\" '{print $1}' | awk -F \":\" " \
                   "'{print $NF}'" % (env, tag, project)
    stout, err = connection_server(host, port, user, get_port_cmd)
    return stout.read().decode('utf-8')


def build_configuration_file():
    server_port = serverInfo[return_ip()]['port']
    server_user = serverInfo[return_ip()]['user']
    """创建nginx配置文件"""
    with open(NG_TEMPLATE, 'r') as f:
        new_conf = '%s/%s%s/%s%s%s.ups' % (NG_UP_path, env, tag, env, tag, project)
        upstream_name = '%s%s%s' % (env, tag, project)
        container_port = ''
        if get_port(return_ip(), server_port, server_user):
            container_port = get_port(return_ip(), server_port, server_user)
        else:
            print("容器端口获取失败")
            exit()
        with open(new_conf, 'w') as f1:
            template_data = f.read()
            upstream_data = {'env': env, 'branch': branch, 'project': project, 'user': build_user,
                             'namespace': namespace, 'createtime': TIME, 'tag': tag,
                             'upstraemname': upstream_name, 'host': return_ip(), 'port': container_port}
            template = Template(template_data)
            new_data = template.render(upstream_data)
            f1.write(new_data)
        data_insert(container_port)  # 传入contqiner端口 并生成数据信息插入到数据库


def modify_filename(up_path):
    """批量修改公共upstream的配置文件名及upstream名称"""
    for filename in os.listdir(up_path):
        new_filename = filename.replace(filename[4:15], '%s' % tag)
        os.rename('%s/%s' % (up_path, filename), '%s/%s' % (up_path, new_filename))
        temp_file = '/tmp/temp.ups'
        old_file = '%s/%s' % (up_path, new_filename)
        with open(old_file, 'r') as f:
            with open(temp_file, 'w') as f1:
                for i in f.readlines():
                    if '%s-common' % env in i:
                        i = i.replace('%s-common' % env, tag)
                    f1.write(i)
                os.remove(old_file)
                os.rename(temp_file, old_file)
        with open(old_file, 'r') as f2:
            with open(temp_file, 'w') as f3:
                for i in f2.readlines():
                    if 'USER' in i:
                        i = i.replace(i, '#USER:    %s\n' % build_user)
                    f3.write(i)
                os.remove(old_file)
                os.rename(temp_file, old_file)


def judge_up_conf():
    """判断环境下的tag配置文件是否已存在 并生成不同环境下tag的配置文件及common配置rename"""
    if os.path.exists('%s/%s%s' % (NG_UP_path, env, tag)):
        build_configuration_file()
    else:
        new_path = '%s/%s%s' % (NG_UP_path, env, tag)
        if env == "beta":
            shutil.copytree('%s/betabeta-common' % NG_UP_path, new_path)
        elif env == "stage":
            shutil.copytree('%s/stagestage-common' % NG_UP_path, new_path)
        modify_filename(new_path)
        build_configuration_file()
    os.system('orange reload')
    print("代理配置文件已生成")


def create_ng_conf():
    """生成upstream配置文件"""
    if project != "wacc-core" and project != "wacc-query":
        if env == "beta" and tag != '':
            judge_up_conf()
        elif env == "stage" and tag != '':
            judge_up_conf()
    else:
        print("%s 无需代理配置" % project)
        exit()


def connection_server(host, port, user, cmd):
    client = paramiko.SSHClient()
    """登录服务器封装 执行命令 自动保存认证策略到本地know_hosts文件"""
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    private_key = paramiko.RSAKey.from_private_key_file('/root/.ssh/id_rsa')
    client.connect(hostname=host, port=port, username=user, pkey=private_key)
    stin, stout, sterr = client.exec_command(cmd)
    return stout, sterr


def load_check(host, port, user):
    """获取服务器1分钟5分钟负载情况"""
    cmd = 'uptime'
    stout, sterr = connection_server(host, port, user, cmd)
    if sterr.read().decode('utf-8'):
        print('painc: get load average error')
    else:
        load = stout.read().decode('utf-8').split(':')[-1].split(',')
        serverInfo[host]['load1'] = load[0]
        serverInfo[host]['load5'] = load[1]


def mem_check(host, port, user):
    """获取内存余量"""
    cmd = "free -g | awk '/^Mem/ NR > 1 {print $NF}'"
    stout, sterr = connection_server(host, port, user, cmd)
    if sterr.read().decode('utf-8'):
        print('painc: get memoryinfo error')
    else:
        meminfo = stout.read().decode('utf-8').rstrip('\n')
        serverInfo[host]['memory'] = meminfo


def disk_check(host, port, user):
    """获取服务器磁盘可选总量 只获取home和含有data的数据盘剩余可用"""
    cmd = "df -h | awk 'NR > 1 {print $NF}'"
    stout, sterr = connection_server(host, port, user, cmd)
    if sterr.read().decode('utf-8'):
        print('painc: get diskinfo error')
    else:
        disk = stout.read().decode('utf-8').split('\n')
        datadisk = []
        for i in disk:
            if "home" in i or "data" in i:
                datadisk.append(i)
        for i in datadisk:
            getavail = "df -h %s | awk 'NR > 1 {print $4}' | sed -e 's/[a-zA-Z]//'" % i
            stout, sterr = connection_server(host, port, user, getavail)
            datadisk[datadisk.index(i)] = stout.read().decode('utf-8').rstrip('\n')
        total = 0
        for i in datadisk:
            total = total + int(i)
        serverInfo[host]['disk'] = total


def save_data(dic):
    """将获取到的服务器相关信息存放到字典中"""
    for i, v in dic.items():
        load_check(i, dic[i]['port'], dic[i]['user'])
        mem_check(i, dic[i]['port'], dic[i]['user'])


def check_tag(tag_check):
    """根据正则匹配检测输入的tag是否符合规则  字母不限制 结尾以4个数字结尾"""
    rule = re.compile('^[a-zA-z]+?[0-9]{4}$')
    if rule.match(tag_check) is not None:
        print("tag检测完毕 开始检测环境")
    else:
        print("tag输入格式不正确 请按照提示规则重新发布")
        exit()


def check_env(proxyserver, project_check):
    """发布前环境检查"""
    if project_check == "wacc-core" or project_check == "wacc-query":
        print("正在更新发布")
    else:
        cmd = "[ -f /usr/local/orange/conf/upstreams/%s%s/%s%s%s.ups ] && echo 0 || echo 1" % (
            env, tag, env, tag, project_check)
        stout, err = connection_server(proxyserver, 1662, 'root', cmd)
        status = stout.read().decode('utf-8').rstrip('\n')
        if int(status) == 1:
            print('准备创建新环境 ')
        else:
            cmd = "awk 'NR==4 {print $2}' /usr/local/orange/conf/upstreams/%s%s/%s%s%s.ups" % (
                env, tag, env, tag, project_check)
            user, sterr = connection_server(proxyserver, 1662, 'root', cmd)
            old_user = user.read().decode('utf-8')
            if old_user == '':
                print('painc: 获取信息失败 ')
                exit()
            else:
                if old_user.strip('\n') == build_user:
                    print("环境已存在 正在更新发布")
                else:
                    print("环境已存在")
                    exit()


def get_config(parent, subpro, file):
    """解析每个项目的发布配置"""

    data_dic = json.load(open(file))
    return data_dic[parent][subpro]


def get_ns_conf(user):
    """获取公共或者个人的ACM配置名称空间地址"""
    if namespace == "stage-common" or namespace == "beta-common":
        return get_config(namespace, 'namespace', NS_CONF)
    else:
        return get_config('%s-%s' % (env, user), 'namespace', NS_CONF)


def conf_check(file, strings):
    """检查文件中是否含有某字符串 当前用来检查dockerfile中是否含有某配置"""
    with open(file, 'r+') as f:
        if re.search(strings, f.read()) is not None:
            return True
        else:
            return False


def conf_add(file, new_str):
    """Dockerfile添加配置"""
    line = []
    new_file = '/data/tmp/add_temp'
    with open(file, 'r+') as f:
        with open(new_file, 'w') as f1:
            for i in f.readlines():
                line.append(i)
            line.insert(2, new_str)
            for i in line:
                f1.write(i)
            os.remove(file)
            os.rename(new_file, file)


def replace_conf(file, old_str, new_str):
    """更改Dockerfile配置"""
    new_file = '/data/tmp/replace_temp'
    with open(file, 'r+') as f:
        with open(new_file, 'w') as f1:
            for i in f.readlines():
                if old_str in i:
                    i = i.replace(i, new_str)
                f1.write(i)
            os.remove(file)
            os.rename(new_file, file)


def container_run_check():
    """检查是否已经有相同的容器在运行 如果有 那么返回机器所在的ip地址"""
    for i in serverInfo.keys():
        container_check = 'docker ps -a | grep %s%s%s' % (env, tag, project)
        stout, err = connection_server(i, serverInfo[i]['port'], serverInfo[i]['user'],
                                       container_check)
        if stout.read().decode('utf-8') != '':
            return i


def return_ip():
    """返回符合一分钟以内负载小于16 内存大于4G的服务器ip"""
    server_ip = ''
    if container_run_check() is not None:
        server_ip = container_run_check()
    else:
        for i in serverInfo.keys():
            if float(serverInfo[i]['load1'].strip()) < 16.0 and int(serverInfo[i]['memory'].strip()) >= 4:
                server_ip = i
                break
    return server_ip


def java_docker_cmd(host, port, user, run_project):
    """docker启动命令"""
    common_log_path = get_config(run_project, 'commonLogsPath', BUILD_CONF)
    app_port = get_config(run_project, 'port', BUILD_CONF)
    image_url = get_config(run_project, 'imageUrl', BUILD_CONF)
    zk_domain = "z01.betadubbo.zk.inf.bandubanxie.com"
    zk_ip = "172.17.1.88"
    sk_path = "/home/service/skywalking/agent/skywalking-agent.jar"
    docker_run = ''
    catalina_args = "\"$CATALINA_OPTS -Xms1024m -Xmx1024m -XX:MaxPermSize=512m -javaagent:%s " \
                    "-Ddubbo.provider.tag=%s.%s\"" % (sk_path, env, tag)
    option = get_config(run_project, 'option', BUILD_CONF)
    docker_del = 'docker ps -a | grep %s%s%s && docker stop %s%s%s && docker rm %s%s%s' % (
        env, tag, run_project, env, tag, run_project, env, tag, run_project)
    stout, err = connection_server(host, port, user, docker_del)
    if err.read().decode('utf-8'):
        print('painc: already exists container delete error %s')
        exit()
    if option == "jar":
        docker_run = 'docker pull %s/%s:v%s && ' \
                     'docker run -dit --name %s%s%s ' \
                     '--add-host %s:%s -p :%s ' \
                     '--restart=always ' \
                     '-m 1G' \
                     ' -e YSX_PROJECT_DOMAIN=\"%s\"' \
                     ' -e SW_AGENT_INSTANCE_NAME=\"%s.%s\"' \
                     ' -e SW_LOGGING_DIR=\"/data/logs/tomcat_logs/%s\"' \
                     ' -e SK_AGENT=\"%s\"' \
                     ' -e YSX_SW_AGENT_COLLECTOR_BACKEND_SERVICES=\"192.168.12.51:11800\"' \
                     ' -e YSX_SW_AGENT_AUTHENTICATION=\"yunshuxie-test\"' \
                     ' -v %s/%s/%s/%s/:/data/logs %s/%s:v%s' % (
                         image_url, run_project, build_number, env, tag, run_project,
                         zk_domain, zk_ip, app_port, run_project, env, tag, run_project,
                         sk_path, common_log_path, env, tag, run_project, image_url,
                         run_project, build_number,)
    elif option == "war":
        docker_run = 'docker pull %s/%s:v%s && ' \
                     'docker run -dit --name %s%s%s ' \
                     '--add-host %s:%s -p :%s ' \
                     '--restart=always ' \
                     '-m 1G' \
                     ' -e YSX_PROJECT_DOMAIN=\"%s\"' \
                     ' -e SW_AGENT_INSTANCE_NAME=\"%s.%s\"' \
                     ' -e SW_LOGGING_DIR=\"/data/logs/tomcat_logs/%s\"' \
                     ' -e SK_AGENT=\"%s\"' \
                     ' -e YSX_SW_AGENT_COLLECTOR_BACKEND_SERVICES=\"192.168.12.51:11800\"' \
                     ' -e YSX_SW_AGENT_AUTHENTICATION=\"yunshuxie-test\"' \
                     ' -e CATALINA_OPTS=%s' \
                     ' -v %s/%s/%s/%s/:/data/logs %s/%s:v%s' % (
                         image_url, run_project, build_number, env, tag, run_project,
                         zk_domain, zk_ip, app_port, run_project, env, tag, run_project,
                         sk_path, catalina_args, common_log_path, env, tag, run_project,
                         image_url, run_project, build_number)
    print(docker_run)
    stout, err = connection_server(host, port, user, docker_run)
    if err.read().decode('utf-8'):
        print('painc: container run error %s')
        exit()
    create_ng_conf()


def image_build_cmd(project_img, image_url):
    """docker容器gou"""
    status = os.system('cd %s && docker build -t %s/%s:v%s . && docker push %s/%s:v%s' %
                       (get_config(project_img, 'deployPath', BUILD_CONF),
                        image_url, project_img, build_number, image_url, project_img, build_number))
    if status == 0:
        print("镜像构建完毕 容器正在启动")


def image_build(project_img):
    """构建docker镜像 并运行调用docker命令启动容器"""
    deploy_path = get_config(project_img, 'deployPath', BUILD_CONF)
    option = get_config(project_img, 'option', BUILD_CONF)
    domain = get_config(project_img, 'domain', BUILD_CONF)
    jar_file = get_config(project_img, 'jarFile', BUILD_CONF)
    image_url = get_config(project_img, 'imageUrl', BUILD_CONF)
    server_port = serverInfo[return_ip()]['port']
    server_user = serverInfo[return_ip()]['user']
    server_ip = ''

    if return_ip():
        print('retuIp == %s' % return_ip())
        server_ip = return_ip()
    else:
        print("memory or load not available error")
        exit()
    if option == "jar":
        SK_AGENT = "/home/service/skywalking/agent/skywalking-agent.jar"
        start_cmd = '#!/bin/bash\njava -server -javaagent:%s ' \
                    '-Xms1024m -Xmx1024m -XX:MaxPermSize=512m -jar' \
                    ' -Ddubbo.provider.tag=%s.%s' \
                    ' /home/work/%s/%s --spring.profiles.active=%s' % \
                    (SK_AGENT, env, tag, domain, jar_file, env)
        with open('%s/server.sh' % deploy_path, 'w') as f:
            f.write(start_cmd)
        image_build_cmd(project_img, image_url)
        java_docker_cmd(server_ip, server_port, server_user, project_img)
    else:
        image_build_cmd(project_img, image_url)
        java_docker_cmd(server_ip, server_port, server_user, project_img)


def java_project_deploy(project_dep, commonpath):
    """特殊项目构建发布 例如mall-api或者mall-admin"""
    if project_dep == "mall-api" or project_dep == "mall-admin":
        os.chdir('%s/ysx-mall' % commonpath)
    else:
        os.chdir('%s/%s' % (commonpath, project_dep))
    status = os.system('git pull && git checkout %s && mvn clean package -U '
                       '-Dmaven.test.skip=true -P%s -Dconfig_namespace=%s && [ -f %s ]' % (
                           branch, env, get_ns_conf(build_user),
                           get_config(project_dep, 'resPath', BUILD_CONF)))
    if status == 0:
        print("代码更新完成 编译结束 开始构建镜像。。。")
        shutil.copyfile(get_config(project_dep, 'resPath', BUILD_CONF), '%s/%s' % (
            get_config(project_dep, 'deployPath', BUILD_CONF),
            get_config(project_dep, 'jarFile', BUILD_CONF)))
        """调用构建镜像"""
        image_build(project_dep)
    else:
        print("代码更新失败或编译失败 已退出。。。")
        exit(status)


def node_container_run(contain_check, server, container_name, app_port, rsync_path, work_path, common_log_path):
    """nodejs项目容器运行指令"""
    print(contain_check)
    chk_out, chk_err = connection_server(server, serverInfo[server]['port'], serverInfo[server]['user'],
                                         contain_check)
    if chk_err.read().decode('utf-8'):
        print('painc:nodejs_container run_check error ')
        exit()
    container_run = "docker run -dit --name %s -p :%s --restart=always -v %s:%s -v %s/%s/%s/%s:/data/logs " \
                    "172.17.2.66:5000/node:v1" % (container_name, app_port, rsync_path, work_path,
                                                  common_log_path, env, tag, project)
    print(container_run)
    run_out, run_err = connection_server(server, serverInfo[server]['port'], serverInfo[server]['user'],
                                         container_run)
    if run_err.read().decode('utf-8'):
        print(run_err.read().decode('utf-8'))
        print('painc:nodejs_container run error ')
        exit()


def nodejs_project_deploy(node_project_dep, node_commonpath):
    """nodejs项目编译 容器化部署"""
    deploy_path = get_config(node_project_dep, 'deployPath', BUILD_CONF)
    os.chdir('%s/%s' % (node_commonpath, node_project_dep))
    status = os.system('git pull && git checkout %s && npm install --unsafe-perm=true --allow-root && npm run build ' %
                       branch)
    if status == 0:
        print("node代码更新完成 编译结束 开始同步数据。。。")
        server = return_ip()
        rsync_path = '%s/%s/%s/%s/%s/%s' % (deploy_path, env, namespace, build_user, branch, tag)
        rsync_path_check = '[ -d %s ] || mkdir -p %s' % (rsync_path, rsync_path)
        stout, err = connection_server(server, serverInfo[server]['port'], serverInfo[server]['user'],
                                       rsync_path_check)
        if err.read().decode('utf-8'):
            print('painc: rsync_path_check error %s')
            exit()
        rsyn_sta = os.system('rsync -e "ssh -p 1662 -o StrictHostKeyChecking=no" -avz --delete %s/%s %s:%s' %
                             (node_commonpath, node_project_dep, server, rsync_path))
        if rsyn_sta == 0:
            print("数据同步完成 正在启动容器。。。")
            app_port = get_config(node_project_dep, 'port', BUILD_CONF)
            work_path = '/home/work/project'
            common_log_path = get_config(node_project_dep, 'commonLogsPath', BUILD_CONF)
            contain_check = 'docker ps -a | grep %s && docker stop %s && docker rm %s' % (
                container_name, container_name, container_name)
            node_container_run(contain_check, server, container_name, app_port, rsync_path, work_path, common_log_path)
            create_ng_conf()


def java_deploy_check(project_check):
    """发布前 环境检查 例如 所需的数据目录以及日志路径等 """
    common_path = get_config(project_check, 'commonPath', BUILD_CONF)
    git_Url = get_config(project_check, 'gitUrl', BUILD_CONF)
    if project_check == "mall-api" or project_check == "mall-admin":
        if not os.path.exists('%s/ysx-mall' % common_path):
            os.chdir(common_path)
            os.system('git clone %s' % git_Url)
            """调用部署"""
        java_project_deploy(project_check, common_path)
    else:
        if not os.path.exists('%s/%s' % (common_path, project_check)):
            os.chdir(common_path)
            os.system('git clone %s' % git_Url)
            """调用部署"""
        java_project_deploy(project_check, common_path)


def nodejs_deploy_check(project_check):
    """发布前 环境检查 例如 所需的数据目录以及日志路径等 关于nodejs所有函数都是与java分离的"""
    common_path = get_config(project_check, 'commonPath', BUILD_CONF)
    git_Url = get_config(project_check, 'gitUrl', BUILD_CONF)
    if not os.path.exists('%s/%s' % (common_path, project_check)):
        os.chdir(common_path)
        os.system('git clone %s' % git_Url)
        """调用部署"""
    nodejs_project_deploy(project_check, common_path)


if __name__ == '__main__':
    operation = sys.argv[1]
    language = sys.argv[2]
    project = sys.argv[3]
    branch = sys.argv[4]
    build_number = sys.argv[5]
    namespace = sys.argv[6]
    env = sys.argv[7]
    build_user = sys.argv[8]
    tag = sys.argv[9]
    container_name = '%s%s%s' % (env, tag, project)
    save_data(serverInfo)
    check_tag(tag)
    check_env(PROXYSERVER, project)
    if operation == 'push' and language == 'java':
        java_deploy_check(project)
    elif operation == 'push' and language == 'nodejs':
        nodejs_deploy_check(project)
    else:
        print("flag Error exit")
        exit()
