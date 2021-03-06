import json
import webbrowser
from datetime import datetime, timedelta
from functools import wraps
from pprint import pprint
from subprocess import run, PIPE
from urllib.parse import urlencode

import jmespath
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth

from config import document_path, get_section


def api_url(path, **kwargs):
    # preserve 405 http error
    host = 'https://' + get_section('JIRA', 'url')
    return host + path.format(**kwargs)


def load(file='jira_api.json'):
    with open(document_path(file)) as f:
        data = json.load(f)
    return data


def get(_id, *key):
    for d in load():
        for m in d['method']:
            if _id == m['_id']:
                return [m[k] for k in key]


def auth(func):
    jira_auth = load('jira_auth.json')

    @wraps(func)
    def wrapper(*args, **kwargs):
        name, path, req_param = func(*args, **kwargs)
        response = requests.request(
            name, path,
            **req_param,
            auth=HTTPBasicAuth(jira_auth['username'], jira_auth['token'])
        )
        try:
            return json.loads(response.content)
        except Exception:
            raise response.raise_for_status()

    return wrapper


@auth
def api_call(_id, method=None, fmt_param=None, url_param=None, req_param=None):
    if fmt_param is None:
        fmt_param = {}
    if url_param is None:
        url_param = {}
    if req_param is None:
        req_param = {}

    data = get(_id, 'name', 'path')
    if not data:
        name, path = method, _id
    else:
        name, path = data
    path = api_url(path, **fmt_param) + '?' + urlencode(url_param)

    return name, path, req_param


def api(name, path, *args):
    url_kwargs = {(argv := arg.split('&=', 1))[0]: argv[1] for arg in args if '&=' in arg}
    req_kwargs = {(argv := arg.split('@=', 1))[0]: argv[1] for arg in args if '@=' in arg}

    # preserve 415 error
    headers = {"Accept": "application/json"}
    if name.upper() == 'POST':
        headers["Content-Type"] = "application/json"
    req_kwargs.update({'headers': headers})

    args = [arg for arg in args if '=' not in arg]
    assert not args, f'Positional arguments "{args}" must not required.'
    return api_call(path, name, url_param=url_kwargs, req_param=req_kwargs)


def create_data_task(summary, reporter="Issue Templates for Jira", assignee="최종원 Jongwon Choi", duedate=None):
    if duedate is None:
        duedate = datetime.today().date() + timedelta(days=7)
        duedate = duedate.strftime('%Y-%m-%d')
    user_list = api_call('/rest/api/3/users/search', 'get', url_param={'maxResults': 500})
    user_list = jmespath.search('[].[displayName, accountId]', user_list)
    user_map = dict(user_list)
    data = {
        "fields": {
            "summary": summary,
            "issuetype": {"id": "10014"},
            "project": {"id": "10057"},
            "reporter": {"id": user_map[reporter]},
            "labels": ["templates"],
            "duedate": duedate,
            "assignee": {"id": user_map[assignee]}
        }
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    return api_call('/rest/api/3/issue', 'post', req_param={'json': data, 'headers': headers})


def create_meta(project_ids=None, project_keys=None, issue_type_ids=None,
                issue_type_names=None, expand=None):
    # TODO: keyword argument delegate
    return api_call('/rest/api/3/issue/createmeta', 'get',
                    url_param={
                        'projectIds': project_ids,
                        'projectKeys': project_keys,
                        'issuetypeIds': issue_type_ids,
                        'issuetypeNames': issue_type_names,
                        'expand': expand,
                    })


def get_issue(key):
    return api_call('api/2/issue-getIssue', fmt_param={'issueIdOrKey': key})


def search(jql, method):
    return api_call('/rest/api/3/search', method, url_param={'jql': jql})


def group(method, group_name):
    x = api_call('/rest/api/3/group/member', method, url_param={'groupname': group_name})
    pprint(x)


def help(product):
    links = {
        'confluence': 'https://developer.atlassian.com/cloud/confluence/rest/',
        'jira': 'https://developer.atlassian.com/cloud/jira/platform/rest/v3/',
    }
    webbrowser.open(links[product])


def teams():
    x = api_call('/rest/api/3/groupuserpicker', 'GET')
    pprint(x)


def archive(data):
    with open('test.json', 'w') as f:
        json.dump(data, f, indent=2)


jql_template = {
    'related_me': '(reporter was currentUser() OR watcher = currentUser() '
                  'OR assignee was currentUser() OR summary ~ currentUser() '
                  'OR description ~ currentUser() OR comment ~ currentUser())',
    'me': 'assignee = currentUser()',
    'unresolved': 'resolution = Unresolved',
    'weekly_resolved': '(resolved >= -1w OR status changed to closed AFTER -1w)'
}


def easy_jql(s):
    jql = s.format(**jql_template)
    pprint(jql)
    return jql


def pipe_search(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        return pipe_jq(json.dumps(result))

    return wrapper


@pipe_search
def search_me():
    jql = easy_jql('{me} AND {unresolved}')
    return search(jql, method='get')


@pipe_search
def today_closed():
    jql = easy_jql('{me} AND (status changed to resolved AFTER -1d OR status changed to closed AFTER -1d)')
    return search(jql, method='get')


@pipe_search
def search_related():
    jql = easy_jql('{unresolved} AND {related_me}')
    return search(jql, method='get')


@pipe_search
def last_resolved():
    jql = easy_jql('{me} and {weekly_resolved}')
    return search(jql, method='get')


def pipe_jq(data):
    p1 = run(['jq', '.issues[].key'], input=data.encode(), stdout=PIPE)
    res1 = p1.stdout.decode().split('\n')
    p2 = run(['jq', '.issues[].fields.status.name'], input=data.encode(),
             stdout=PIPE)
    res2 = p2.stdout.decode().split('\n')
    p3 = run(['jq', '.issues[].fields.summary'], input=data.encode(),
             stdout=PIPE)
    res3 = p3.stdout.decode().split('\n')
    p4 = run(['jq', '.issues[].fields.updated'], input=data.encode(),
             stdout=PIPE)
    res4 = p4.stdout.decode().split('\n')
    p5 = run(['jq', '.issues[].fields.resolution.name'], input=data.encode(),
             stdout=PIPE)
    res5 = p5.stdout.decode().split('\n')
    df = pd.DataFrame(
        list(zip(res1, res2, res4, res5, res3)),
        columns=['Key', 'Status', 'Updated', 'Resolution', 'Summary']
    ).applymap(lambda x: x.strip('"'))
    df['Updated'] = pd.to_datetime(df['Updated'])
    pprint(df.sort_values('Updated'))
