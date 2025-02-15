# -*- coding: utf-8 -*-

from app_modules.utils import run
from app_modules.utils import json

response.headers['Content-Type'] = 'application/json'


def index():
    response.headers['Content-Type'] = 'text/html'

    return menu([
        "pcis",
        "version",
        "issn",
        "all/issn",
    ])


def version():
    opt = "--decorate --decorate-refs='refs/tags/*'"
    fmt = "--pretty='%H/%D'"
    ver = run(f"git log {opt} {fmt} HEAD -1").strip().split('/')

    return json({
        "version": { "hash": ver[0], "tag": ver[1] }
    })


def pcis():
    host = pci_hosts()
    desc = read_confs("description", cleanup="s:Peer Community [iI]n ::")

    return json({
        host[i]: desc[i] for i,_ in enumerate(host)
    })


def issn():
    return json({
        "issn": db.config[1].issn
    })


def all():
    endpoint = request.args[0] if request.args else None

    if endpoint is None: return error("usage: api/all/<endpoint>")
    if endpoint == "all": return error("recursive call on all")

    return json({
        host: res for host, res in call_all(pci_hosts(), endpoint)
    })


# internals

def pci_hosts(conf_key="host"):
    return read_confs(conf_key, cleanup="s:[.].*::")


def read_confs(key, cleanup=""):
    return run(f"""sh -c "
        cd ..
        cat PCI*/private/appconfig.ini \\
        | egrep '^{key} = ' \\
        | sed  's:{key} = ::; {cleanup}'
        " """
        ).strip().split('\n')


def menu(items):
    return "<br>\n".join(map(str, [
        A(x, _href=URL(x)) for x in items
    ]))


def error(mesg, status=400):
    response.status = status
    return json({"error": mesg})

import requests

def api_call(host, endpoint):
    api_url = f"https://{host}.peercommunityin.org/api/" \
            if host != "localhost" else f"http://{host}:8000/pci/api/"

    try:
        return requests.get(
            api_url + endpoint
        ).json()

    except Exception as err:
        return { "error": f"{type(err).__name__}: {err}" }


from multiprocessing.pool import ThreadPool

def call_all(hosts, endpoint):
    return ThreadPool().map(
        lambda host: [host, api_call(host, endpoint)],
        hosts
    )
