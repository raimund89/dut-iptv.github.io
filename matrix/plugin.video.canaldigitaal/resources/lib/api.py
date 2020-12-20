import datetime, os, time, uuid, xbmc

from resources.lib.base.l1.constants import ADDON_ID, ADDON_PROFILE
from resources.lib.base.l2 import settings
from resources.lib.base.l2.log import log
from resources.lib.base.l3.language import _
from resources.lib.base.l3.util import check_key, clean_filename, combine_playlist, find_highest_bandwidth, get_credentials, is_file_older_than_x_minutes, load_file, load_profile, load_tests, query_epg, query_settings, set_credentials, update_prefs, write_file
from resources.lib.base.l4 import gui
from resources.lib.base.l4.exceptions import Error
from resources.lib.base.l4.session import Session
from resources.lib.base.l5.api import api_download
from resources.lib.constants import CONST_BASE_HEADERS, CONST_BASE_URL, CONST_DEFAULT_API, CONST_LOGIN_HEADERS, CONST_LOGIN_URL

try:
    from urllib.parse import parse_qs, urlparse, quote
except ImportError:
    from urlparse import parse_qs, urlparse
    from urllib import quote

try:
    unicode
except NameError:
    unicode = str

try:
    from sqlite3 import dbapi2 as sqlite
except:
    from pysqlite2 import dbapi2 as sqlite

def api_add_to_watchlist():
    return None

def api_get_session(force=0):
    force = int(force)
    profile_settings = load_profile(profile_id=1)

    if not force ==1 and check_key(profile_settings, 'last_login_time') and profile_settings['last_login_time'] > int(time.time() - 3600) and profile_settings['last_login_success'] == 1:
        return True
    elif force == 1 and not profile_settings['last_login_success'] == 1:
        return False

    capi_url = '{base_url}/m7be2iphone/capi.aspx?z=pg&a=cds&lng=nl'.format(base_url=CONST_BASE_URL)

    download = api_download(url=capi_url, type='get', headers=None, data=None, json_data=False, return_json=False, allow_redirects=False)
    data = download['data']
    code = download['code']

    if not code or not code == 200:
        login_result = api_login()

        if not login_result['result']:
            return False

    try:
        query = "UPDATE `vars` SET `last_login_time`={last_login_time}, `last_login_success`=1 WHERE profile_id={profile_id}".format(last_login_time=int(time.time()),profile_id=1)
        query_settings(query=query, return_result=False, return_insert=False, commit=True)
    except:
        pass

    return True

def api_list_watchlist():
    return None

def api_login():
    creds = get_credentials()
    username = creds['username']
    password = creds['password']

    query = "UPDATE `vars` SET `cookies`='', `session_token`='' WHERE profile_id={profile_id}".format(profile_id=1)
    query_settings(query=query, return_result=False, return_insert=False, commit=True)

    profile_settings = load_profile(profile_id=1)

    if len(profile_settings['devicekey']) == 0:
        devicekey = 'w{uuid}'.format(uuid=uuid.uuid4())
        query = "UPDATE `vars` SET `devicekey`='{devicekey}' WHERE profile_id={profile_id}".format(devicekey=devicekey, profile_id=1)
        query_settings(query=query, return_result=False, return_insert=False, commit=True)

    oauth = ''
    auth_url = '{login_url}/authenticate?redirect_uri=https%3A%2F%2Flivetv.canaldigitaal.nl%2Fauth.aspx&state={state}&response_type=code&scope=TVE&client_id=StreamGroup'.format(login_url=CONST_LOGIN_URL, state=int(time.time()))

    download = api_download(url=auth_url, type='get', headers=None, data=None, json_data=False, return_json=False, allow_redirects=False)
    data = download['data']
    code = download['code']

    if not code or not code == 200 or not data:
        return { 'code': code, 'data': data, 'result': False }

    headers = CONST_LOGIN_HEADERS
    headers.update({'Referer': auth_url})

    session_post_data = {
        "Password": password,
        "Username": username,
    }

    download = api_download(url=CONST_LOGIN_URL, type='post', headers=headers, data=session_post_data, json_data=False, return_json=False, allow_redirects=False)
    data = download['data']
    code = download['code']
    headers = download['headers']

    if not code or not code == 302:
        return { 'code': code, 'data': data, 'result': False }

    params = parse_qs(urlparse(headers['Location']).query)

    if check_key(params, 'code'):
        oauth = params['code'][0]

    if len(oauth) == 0:
        return { 'code': code, 'data': data, 'result': False }

    challenge_url = "{base_url}/m7be2iphone/challenge.aspx".format(base_url=CONST_BASE_URL)

    session_post_data = {
        "autotype": "nl",
        "app": "cds",
        "prettyname": profile_settings['browser_name'],
        "model": "web",
        "serial": profile_settings['devicekey'],
        "oauthcode": oauth
    }

    headers = {'Content-Type': 'application/json;charset=UTF-8'}

    download = api_download(url=challenge_url, type='post', headers=headers, data=session_post_data, json_data=True, return_json=True, allow_redirects=False)
    data = download['data']
    code = download['code']

    if not code or not code == 200 or not data or not check_key(data, 'id') or not check_key(data, 'secret'):
        return { 'code': code, 'data': data, 'result': False }

    login_url = "{base_url}/m7be2iphone/login.aspx".format(base_url=CONST_BASE_URL)

    headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}

    secret = '{id}\t{secr}'.format(id=data['id'], secr=data['secret'])

    session_post_data = {
        "secret": secret,
        "uid": profile_settings['devicekey'],
        "app": "cds",
    }

    download = api_download(url=login_url, type='post', headers=headers, data=session_post_data, json_data=False, return_json=False, allow_redirects=False)
    data = download['data']
    code = download['code']

    if not code or not code == 302:
        return { 'code': code, 'data': data, 'result': False }

    ssotoken_url = "{base_url}/m7be2iphone/capi.aspx?z=ssotoken".format(base_url=CONST_BASE_URL)

    download = api_download(url=ssotoken_url, type='get', headers=None, data=None, json_data=False, return_json=True, allow_redirects=False)
    data = download['data']
    code = download['code']

    if not code or not code == 200 or not data or not check_key(data, 'ssotoken'):
        return { 'code': code, 'data': data, 'result': False }

    session_url = "{api_url}/session".format(api_url=CONST_DEFAULT_API)

    session_post_data = {
        "sapiToken": data['ssotoken'],
        "deviceType": "PC",
        "deviceModel": profile_settings['browser_name'],
        "osVersion": '{name} {version}'.format(name=profile_settings['os_name'], version=profile_settings['os_version']),
        "deviceSerial": profile_settings['devicekey'],
        "appVersion": profile_settings['browser_version'],
        "brand": "cds"
    }

    headers = {'Content-Type': 'application/json;charset=UTF-8'}

    download = api_download(url=session_url, type='post', headers=headers, data=session_post_data, json_data=True, return_json=True, allow_redirects=False)
    data = download['data']
    code = download['code']

    if not code or not code == 200 or not data or not check_key(data, 'token'):
        return { 'code': code, 'data': data, 'result': False }

    query = "UPDATE `vars` SET `session_token`='{session_token}' WHERE profile_id={profile_id}".format(session_token=data['token'],profile_id=1)
    query_settings(query=query, return_result=False, return_insert=False, commit=True)

    return { 'code': code, 'data': data, 'result': True }

def api_play_url(type, channel=None, id=None, video_data=None, test=False, from_beginning=0, pvr=0):
    playdata = {'path': '', 'license': '', 'info': '', 'alt_path': '', 'alt_license': ''}

    if not api_get_session():
        return playdata

    alt_path = ''
    alt_license = ''

    from_beginning = int(from_beginning)
    pvr = int(pvr)
    profile_settings = load_profile(profile_id=1)

    info = []

    headers = {'Authorization': 'Bearer ' + profile_settings['session_token']}

    if not test:
        counter = 0

        while not xbmc.Monitor().abortRequested() and counter < 5:
            profile_settings = load_profile(profile_id=1)

            if profile_settings['test_running'] == 0:
                break

            counter += 1

            query = "UPDATE `vars` SET `last_playing`={last_playing} WHERE profile_id={profile_id}".format(last_playing=int(time.time()),profile_id=1)
            query_settings(query=query, return_result=False, return_insert=False, commit=True)

            if xbmc.Monitor().waitForAbort(1):
                break

        if xbmc.Monitor().abortRequested():
            return playdata

    if type == 'channel':
        info_url = '{api_url}/assets/{channel}'.format(api_url=CONST_DEFAULT_API, channel=channel)
    else:
        info_url = '{api_url}/assets/{id}'.format(api_url=CONST_DEFAULT_API, id=id)

    play_url = info_url + '/play'
    playfrombeginning = False

    if test:
        pass
    elif not pvr == 1 or settings.getBool(key='ask_start_from_beginning') or from_beginning == 1:
        download = api_download(url=info_url, type='get', headers=headers, data=None, json_data=False, return_json=True)
        data = download['data']
        code = download['code']

        if not code or not code == 200 or not data or not check_key(data, 'id'):
            return playdata

        info = data

        session_post_data = {
            "player": {
                "name":"Bitmovin",
                "version":"8.22.0",
                "capabilities": {
                    "mediaTypes": ["DASH","HLS","MSSS","Unspecified"],
                    "drmSystems": ["Widevine"],
                },
                "drmSystems": ["Widevine"],
            },
        }

        if type == 'channel' and check_key(data, 'params') and check_key(data['params'], 'now') and check_key(data['params']['now'], 'id'):
            play_url2 = '{api_url}/assets/{id}/play'.format(api_url=CONST_DEFAULT_API, id=data['params']['now']['id'])
            info = data['params']['now']

            download = api_download(url=play_url2, type='post', headers=headers, data=session_post_data, json_data=True, return_json=True)
            data = download['data']
            code = download['code']

            if code and code == 200 and data and check_key(data, 'url'):
                if check_key(data, 'drm') and check_key(data['drm'], 'licenseUrl'):
                    alt_license = data['drm']['licenseUrl']

                alt_path = data['url']

    if xbmc.Monitor().abortRequested():
        return playdata

    if not playfrombeginning:
        download = api_download(url=play_url, type='post', headers=headers, data=session_post_data, json_data=True, return_json=True)
        data = download['data']
        code = download['code']

    if not code or not code == 200 or not data or not check_key(data, 'url'):
        return playdata

    if check_key(data, 'drm') and check_key(data['drm'], 'licenseUrl'):
        license = data['drm']['licenseUrl']

    path = data['url']

    playdata = {'path': path, 'license': license, 'info': info, 'alt_path': alt_path, 'alt_license': alt_license}

    return playdata

def api_remove_from_watchlist():
    return None

def api_search():
    return None

def api_test_channels(tested=False, channel=None):
    profile_settings = load_profile(profile_id=1)

    if channel:
        channel = unicode(channel)

    try:
        if not profile_settings['last_login_success'] == 1 or not settings.getBool(key='run_tests') or not api_get_session():
            return 5

        query = "UPDATE `vars` SET `test_running`={test_running} WHERE profile_id={profile_id}".format(test_running=1,profile_id=1)
        query_settings(query=query, return_result=False, return_insert=False, commit=True)

        query = "SELECT * FROM `channels`"
        channels = query_epg(query=query, return_result=True, return_insert=False, commit=False)
        results = load_tests(profile_id=1)

        count = 0
        first = True
        last_tested_found = False
        test_run = False
        user_agent = profile_settings['user_agent']

        if not results:
            results = {}

        for row in channels:
            if count == 5 or (count == 1 and tested):
                if test_run:
                    update_prefs()

                query = "UPDATE `vars` SET `test_running`={test_running} WHERE profile_id={profile_id}".format(test_running=0,profile_id=1)
                query_settings(query=query, return_result=False, return_insert=False, commit=True)
                return count

            id = unicode(row['id'])

            if len(id) > 0:
                if channel:
                    if not id == channel:
                        continue
                elif tested:
                    if unicode(profile_settings['last_tested']) == id:
                        last_tested_found = True
                        continue
                    elif last_tested_found:
                        pass
                    else:
                        continue

                if check_key(results, id) and not tested and not first:
                    continue

                livebandwidth = 0
                replaybandwidth = 0
                live = 0
                replay = 0
                epg = 0
                guide = 0

                profile_settings = load_profile(profile_id=1)

                if profile_settings['last_playing'] > int(time.time() - 300):
                    if test_run:
                        update_prefs()

                    query = "UPDATE `vars` SET `test_running`={test_running} WHERE profile_id={profile_id}".format(test_running=0,profile_id=1)
                    query_settings(query=query, return_result=False, return_insert=False, commit=True)
                    return 5

                playdata = api_play_url(type='channel', channel=id, id=id, test=True)

                if first and not profile_settings['last_login_success']:
                    if test_run:
                        update_prefs()

                    query = "UPDATE `vars` SET `test_running`={test_running} WHERE profile_id={profile_id}".format(test_running=0,profile_id=1)
                    query_settings(query=query, return_result=False, return_insert=False, commit=True)
                    return 5

                if len(playdata['path']) > 0:
                    CDMHEADERS = CONST_BASE_HEADERS
                    CDMHEADERS['User-Agent'] = user_agent
                    session = Session(headers=CDMHEADERS)
                    resp = session.get(playdata['path'])

                    if resp.status_code == 200:
                        livebandwidth = find_highest_bandwidth(xml=resp.text)
                        live = 1

                if check_key(results, id) and first and not tested:
                    first = False

                    if live == 1:
                        continue
                    else:
                        if test_run:
                            update_prefs()

                        query = "UPDATE `vars` SET `test_running`={test_running} WHERE profile_id={profile_id}".format(test_running=0,profile_id=1)
                        query_settings(query=query, return_result=False, return_insert=False, commit=True)
                        return 5

                first = False
                counter = 0

                while not xbmc.Monitor().abortRequested() and counter < 5:
                    if xbmc.Monitor().waitForAbort(1):
                        break

                    counter += 1

                    profile_settings = load_profile(profile_id=1)

                    if profile_settings['last_playing'] > int(time.time() - 300):
                        if test_run:
                            update_prefs()

                        query = "UPDATE `vars` SET `test_running`={test_running} WHERE profile_id={profile_id}".format(test_running=0,profile_id=1)
                        query_settings(query=query, return_result=False, return_insert=False, commit=True)
                        return 5

                if xbmc.Monitor().abortRequested():
                    return 5

                headers = {'Authorization': 'Bearer ' + profile_settings['session_token']}
                yesterday = datetime.datetime.now() - datetime.timedelta(1)
                fromtime = datetime.datetime.strftime(yesterday, '%Y-%m-%dT%H:%M:%S.000Z')
                tilltime = datetime.datetime.strftime(yesterday, '%Y-%m-%dT%H:%M:59.999Z')

                program_url = "{api_url}/schedule?channels={id}&from={fromtime}&until={tilltime}".format(api_url=CONST_DEFAULT_API, id=id, fromtime=fromtime, tilltime=tilltime);

                download = api_download(url=program_url, type='get', headers=headers, data=None, json_data=False, return_json=True)
                data = download['data']
                code = download['code']

                if code and code == 200 and data and check_key(data, 'epg') and check_key(data['epg'][0], 'id'):
                    profile_settings = load_profile(profile_id=1)

                    if profile_settings['last_playing'] > int(time.time() - 300):
                        if test_run:
                            update_prefs()

                        query = "UPDATE `vars` SET `test_running`={test_running} WHERE profile_id={profile_id}".format(test_running=0,profile_id=1)
                        query_settings(query=query, return_result=False, return_insert=False, commit=True)
                        return 5

                    playdata = api_play_url(type='program', channel=id, id=data['epg'][0]['id'], test=True)

                    if len(playdata['path']) > 0:
                        CDMHEADERS = CONST_BASE_HEADERS
                        CDMHEADERS['User-Agent'] = user_agent
                        session = Session(headers=CDMHEADERS)
                        resp = session.get(playdata['path'])

                        if resp.status_code == 200:
                            replaybandwidth = find_highest_bandwidth(xml=resp.text)
                            replay = 1

                query = "SELECT id FROM `epg` WHERE channel='{channel}' LIMIT 1".format(channel=id)
                data = query_epg(query=query, return_result=True, return_insert=False, commit=False)

                if len(data) > 0:
                    guide = 1

                    if live == 1:
                        epg = 1

                if not xbmc.Monitor().abortRequested():
                    query = "UPDATE `vars` SET `last_tested`='{last_tested}' WHERE profile_id={profile_id}".format(last_tested=id,profile_id=1)
                    query_settings(query=query, return_result=False, return_insert=False, commit=True)

                    query = "REPLACE INTO `tests_{profile_id}` VALUES ('{id}', '{live}', '{livebandwidth}', '{replay}', '{replaybandwidth}', '{epg}', '{guide}')".format(profile_id=1, id=id, live=live, livebandwidth=livebandwidth, replay=replay, replaybandwidth=replaybandwidth, epg=epg, guide=guide)
                    query_settings(query=query, return_result=False, return_insert=False, commit=True)

                test_run = True
                counter = 0

                while not xbmc.Monitor().abortRequested() and counter < 15:
                    if xbmc.Monitor().waitForAbort(1):
                        break

                    counter += 1

                    profile_settings = load_profile(profile_id=1)

                    if profile_settings['last_playing'] > int(time.time() - 300):
                        if test_run:
                            update_prefs()

                        query = "UPDATE `vars` SET `test_running`={test_running} WHERE profile_id={profile_id}".format(test_running=0,profile_id=1)
                        query_settings(query=query, return_result=False, return_insert=False, commit=True)
                        return 5

                if xbmc.Monitor().abortRequested():
                    return 5

                count += 1
    except:
        if test_run:
            update_prefs()

        count = 5

    query = "UPDATE `vars` SET `test_running`={test_running} WHERE profile_id={profile_id}".format(test_running=0,profile_id=1)
    query_settings(query=query, return_result=False, return_insert=False, commit=True)

    return count

def api_vod_download():
    return None

def api_vod_season(series, id):
    if not api_get_session():
        return None

    season = []
    episodes = []
    return season

def api_vod_seasons(id):
    if not api_get_session():
        return None

    seasons = []
    return {'type': 'seasons', 'seasons': seasons}

def api_vod_subscription():
    return None

def api_watchlist_listing():
    return None