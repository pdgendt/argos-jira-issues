#!/usr/bin/env python3

from __future__ import print_function
import base64
import json
import os
import sys
import requests

import jira

SHELL = 'bash'

# files used
CONFIG_FILE = '.jira_config.json'
CACHE_FILE  = '.jira_cache.json'
STATE_FILE  = '.jira_state.json'

# some globals
_config = {}
_state  = {}
_cache  = {}
_jira_query = 'resolution = Unresolved and assignee = currentUser()' # start with a default query

os.chdir(os.path.dirname(os.path.realpath(__file__)))

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def as_base64(url):
    return base64.b64encode(requests.get(url).content).decode("utf-8")

def argos_fatal(message):
    print(':no_entry: ' + message)
    exit(1)

def argos_separator():
    print('---')

def argos_entry(text, options=None):
    options_str = ""
    if options:
        options_str += "|"

        # Override defaults
        if "bash" in options:
            if "refresh" not in options:
                options["refresh"] = "true"
            if "terminal" not in options:
                options["terminal"] = "false"

        for key, value in options.items():
            options_str += "%s=%s " % (key, value)
    print(text + options_str)

def argos_sub_entry(text, options=None):
    argos_entry("--" + text, options)

def argos_jira_issue(issue):
    global _state
    argos_entry('<b>%s</b>: %s' % (issue['key'], issue['fields']['summary']), {
        'image': _cache['types'][issue['fields']['issuetype']['id']]['icon']
    })
    argos_sub_entry('Open in jira', {
        'href': _config['server'] + '/browse/' + issue['key'],
        'image': 'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAMZJREFUOI2Vkj0OAUEAhb9IJOKn3PM5gEaCWqOROIIrKPWicAm9hEoidHyaXdaameUl00zevL8MpDEFZjWcKDL1ql6ALEZqJAT6QBvoAuO/7dWNbyRTxATOJQGB+T/vW+rDTwRTxDZ4BO66wKjOOQNWQE89+Y3aLeZ53yWwDggkt8jUS867A4uQQDVFeYNx3rO4bwKnyBZf/6LsXmAHTH5J8epewQHoqMe6LULuhQC/pAi5q25zgXQKda/eqgcYlCoOQxx1/wRTboLP64okfwAAAABJRU5ErkJggg=='
    })

def load_config():
    global _config, _jira_query
    try:
        with open(CONFIG_FILE, 'r') as config_file:
            _config = json.load(config_file)
    except:
        argos_fatal('Unable to load config file')

    if not 'username' in _config:
        argos_fatal('Missing required username in config')
    if not 'token' in _config:
        argos_fatal('Missing required token in config')
    if not 'server' in _config:
        argos_fatal('Missing required server in config')
    if 'query' in _config:
        _jira_query = _config['query']

def read_cache():
    global _cache
    try:
        with open(CACHE_FILE, 'r') as cache_file:
            _cache = json.load(cache_file)
    except:
        eprint('Error loading cache')
        _cache = {}
        
    if not 'issues' in _cache:
        _cache['issues'] = {}
    if not 'types' in _cache:
        _cache['types'] = {}

def write_cache():
    global _cache
    try:
        with open(CACHE_FILE, 'w') as cache_file:
            json.dump(_cache, cache_file)
    except:
        argos_fatal('Unable to write cache file')

def read_state():
    global _state
    try:
        with open(STATE_FILE, 'r') as state_file:
            _state = json.load(state_file)
    except:
        eprint('Error loading state')
        _state = {}

def update_cache():
    global _jira, _jira_query, _cache
    read_cache()

    # real inefficient, but why not
    cached_keys = set()
    for issue_key in _cache['issues'].keys():
        cached_keys.add(issue_key)

    # update all outdated issues in cache
    for issue in _jira.search_issues(_jira_query, fields='key,updated', maxResults=100, json_result=True)['issues']:
        key = issue['key']
        if key in cached_keys:
            cached_keys.remove(key)
        if (not key in _cache['issues'] 
                or issue['fields']['updated'] != _cache['issues'][key]['fields']['updated']):
            _cache['issues'][key] = _jira.issue(key, fields='summary,status,updated,issuetype').raw
            eprint('Updating issue', key)

    # remove obsolete issues from cache
    for issue_key in cached_keys:
        del(_cache['issues'][issue_key])
        eprint('Removing issue', issue_key)

    write_cache()

def main():
    global _cache
    update_cache()
    read_state()

    # list all issue statuses
    issue_status = set()
    for issue in _cache['issues'].values():
        issue_status.add(issue['fields']['status']['name'])
        if not issue['fields']['issuetype']['id'] in _cache['types']:
            _cache['types'][issue['fields']['issuetype']['id']] = {'icon': as_base64(issue['fields']['issuetype']['iconUrl'])}

    argos_entry('Main')
    for status in issue_status:
        argos_separator()
        argos_entry('<b>%s</b>' % status)
        for issue in _cache['issues'].values():
            if issue['fields']['status']['name'] == status:
                argos_jira_issue(issue)

# actual script
load_config()
_jira = jira.JIRA(_config['server'], basic_auth=(_config['username'], _config["token"]))

if len(sys.argv) == 1:
    main()

exit(0)