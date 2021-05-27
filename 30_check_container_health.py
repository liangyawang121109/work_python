#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json

import docker
import time

import requests

client = docker.from_env()
coniainer_list = client.containers.list(all)
ts = int(time.time())


def container_status_check():
    return_dict = {}
    for i in coniainer_list:
        container_id = str(i).split()[1].rstrip(">")
        container = client.containers.get(container_id)
        if container.status == "exited":
            return_dict[container.name] = 1
        else:
            return_dict[container.name] = 0
    return return_dict


def generate_post_data(tags, value):

    endpoint = 'bj-docker-tmcenv-04'

    ret = {
           'endpoint': endpoint,
           'metric': 'container_healthy',
           'timestamp': ts,
           'step': 30,
           'value': value,
           'counterType': 'GAUGE',
           'tags': 'container_name=%s,container_status=%s' % (tags, 1),
          }

    return ret


if __name__ == '__main__':
    alarm_title = 'FATAL: container down'

    payload = []
    res = container_status_check()

    for name, stats in res.items():
        containers_name = name
        container_status = stats
        payload.append(generate_post_data(containers_name, container_status))

    requests.post("http://127.0.0.1:1988/v1/push", data=json.dumps(payload))
