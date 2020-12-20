import json, os, re, sys, time, xbmc

from resources.lib.base.l1.constants import ADDON_ID, ADDON_PROFILE
from resources.lib.base.l2 import settings
from resources.lib.base.l2.log import log
from resources.lib.base.l3.language import _
from resources.lib.base.l3.util import check_key, clean_filename, combine_playlist, download_files, find_highest_bandwidth, get_credentials, is_file_older_than_x_minutes, load_file, load_profile, load_tests, query_epg, query_settings, set_credentials, update_prefs, write_file
from resources.lib.base.l4 import gui
from resources.lib.base.l4.exceptions import Error
from resources.lib.base.l4.session import Session
from resources.lib.base.l5.api import api_download
from resources.lib.constants import CONST_VOD_CAPABILITY
from resources.lib.util import get_image, get_play_url, update_settings

try:
    from urllib.parse import urlparse, quote
except ImportError:
    from urllib import quote
    from urlparse import urlparse

try:
    unicode
except NameError:
    unicode = str

try:
    from sqlite3 import dbapi2 as sqlite
except:
    from pysqlite2 import dbapi2 as sqlite

def api_add_to_watchlist(id, type):
    if not api_get_session():
        return None

    profile_settings = load_profile(profile_id=1)

    if type == "item":
        mediaitems_url = '{listings_url}/{id}'.format(listings_url=profile_settings['listings_url'], id=id)
        download = api_download(url=mediaitems_url, type='get', headers=api_get_headers(), data=None, json_data=False, return_json=True)
        data = download['data']
        code = download['code']

        if not code or not code == 200 or not data or not check_key(data, 'mediaGroupId'):
            return False

        id = data['mediaGroupId']

    if profile_settings['base_v3'] == 1:
        watchlist_url = 'https://prod.spark.ziggogo.tv/nld/web/watchlist-service/v1/watchlists/{watchlist_id}/entries/{id}?sharedProfile=true'.format(watchlist_id=profile_settings['watchlist_id'], id=id)
    else:
        watchlist_url = '{watchlist_url}/entries'.format(watchlist_url=profile_settings['watchlist_url'])

    download = api_download(url=watchlist_url, type='post', headers=api_get_headers(), data={"mediaGroup": {'id': id}}, json_data=True, return_json=False)
    data = download['data']
    code = download['code']

    if not code or not code == 204 or not data:
        return False

    return True

def api_get_headers():
    creds = get_credentials()
    username = creds['username']

    profile_settings = load_profile(profile_id=1)

    HEADERS = {
        'User-Agent': profile_settings['user_agent'],
        'X-Client-Id': profile_settings['client_id'] + '||' + profile_settings['user_agent'],
        'X-OESP-Token': profile_settings['access_token'],
        'X-OESP-Username': username,
    }

    if profile_settings['base_v3'] == 1:
        HEADERS['X-OESP-Profile-Id'] = profile_settings['ziggo_profile_id']

    return HEADERS

def api_get_play_token(locator=None, path=None, force=0):
    if not api_get_session():
        return None

    force = int(force)

    profile_settings = load_profile(profile_id=1)

    if profile_settings['drm_token_age'] < int(time.time() - 50) and (profile_settings['tokenrun'] == 0 or profile_settings['tokenruntime'] < int(time.time() - 30)):
        force = 1

    if locator != profile_settings['drm_locator'] or profile_settings['drm_token_age'] < int(time.time() - 90) or force == 1:
        query = "UPDATE `vars` SET `tokenrun`=1, `tokenruntime`='{tokenruntime}' WHERE profile_id={profile_id}".format(tokenruntime=int(time.time()), profile_id=1)
        query_settings(query=query, return_result=False, return_insert=False, commit=True)

        if profile_settings['base_v3'] == 1 and 'sdash' in path:
            jsondata = {"contentLocator": locator, "drmScheme": "sdash:BR-AVC-DASH"}
        else:
            jsondata = {"contentLocator": locator}

        download = api_download(url=profile_settings['token_url'], type='post', headers=api_get_headers(), data=jsondata, json_data=True, return_json=True)
        data = download['data']
        code = download['code']

        if not code or not code == 200 or not data or not check_key(data, 'token'):
            query = "UPDATE `vars` SET `tokenrun`=0 WHERE profile_id={profile_id}".format(profile_id=1)
            query_settings(query=query, return_result=False, return_insert=False, commit=True)
            return None

        query = "UPDATE `vars` SET `tokenrun`=0, `drm_token`='{drm_token}', `drm_token_age`='{drm_token_age}', `drm_locator`='{drm_locator}' WHERE profile_id={profile_id}".format(drm_token=data['token'], drm_token_age=int(time.time()), drm_locator=locator, profile_id=1)
        query_settings(query=query, return_result=False, return_insert=False, commit=True)

        return data['token']
    else:
        return profile_settings['drm_token']

def api_get_session(force=0):
    force = int(force)
    profile_settings = load_profile(profile_id=1)

    if not force ==1 and check_key(profile_settings, 'last_login_time') and profile_settings['last_login_time'] > int(time.time() - 3600) and profile_settings['last_login_success'] == 1:
        return True
    elif force == 1 and not profile_settings['last_login_success'] == 1:
        return False

    devices_url = profile_settings['devices_url']

    download = api_download(url=devices_url, type='get', headers=api_get_headers(), data=None, json_data=False, return_json=True)
    data = download['data']
    code = download['code']

    if not code or not code == 200 or not data or not check_key(data, 'isAccountEnabled'):
        login_result = api_login()

        if not login_result['result']:
            return False

    try:
        query = "UPDATE `vars` SET `last_login_time`={last_login_time}, `last_login_success`=1 WHERE profile_id={profile_id}".format(last_login_time=int(time.time()),profile_id=1)
        query_settings(query=query, return_result=False, return_insert=False, commit=True)
    except:
        pass

    return True

def api_get_watchlist_id():
    if not api_get_session():
        return None

    profile_settings = load_profile(profile_id=1)

    watchlist_url = 'https://prod.spark.ziggogo.tv/nld/web/watchlist-service/v1/watchlists/profile/{profile_id}?language=nl&maxResults=1&order=DESC&sharedProfile=true&sort=added'.format(profile_id=profile_settings['ziggo_profile_id'])

    download = api_download(url=watchlist_url, type='get', headers=api_get_headers(), data=None, json_data=False, return_json=True)
    data = download['data']
    code = download['code']

    if not code or not code == 200 or not data or not check_key(data, 'watchlistId'):
        return False

    query = "UPDATE `vars` SET `watchlist_id`='{watchlist_id}' WHERE profile_id={profile_id}".format(watchlist_id=data['watchlistId'], profile_id=1)
    query_settings(query=query, return_result=False, return_insert=False, commit=True)

    return True

def api_list_watchlist():
    if not api_get_session():
        return None

    profile_settings = load_profile(profile_id=1)

    if profile_settings['base_v3'] == 1:
        watchlist_url = 'https://prod.spark.ziggogo.tv/nld/web/watchlist-service/v1/watchlists/profile/{profile_id}?language=nl&order=DESC&sharedProfile=true&sort=added'.format(profile_id=profile_settings['ziggo_profile_id'])
    else:
        watchlist_url = profile_settings['watchlist_url']

    download = api_download(url=watchlist_url, type='get', headers=api_get_headers(), data=None, json_data=False, return_json=True)
    data = download['data']
    code = download['code']

    if not code or not code == 200 or not data or not check_key(data, 'entries'):
        return False

    return data

def api_login():
    creds = get_credentials()
    username = creds['username']
    password = creds['password']

    query = "UPDATE `vars` SET `access_token`='', `household_id`='', `ziggo_profile_id`='' WHERE profile_id={profile_id}".format(profile_id=1)
    query_settings(query=query, return_result=False, return_insert=False, commit=True)

    profile_settings = load_profile(profile_id=1)

    user_agent = profile_settings['user_agent']

    HEADERS = {
        'User-Agent':  user_agent,
        'X-Client-Id': profile_settings['client_id'] + "||" + user_agent,
    }

    download = api_download(url=profile_settings['session_url'], type='post', headers=HEADERS, data={"username": username, "password": password}, json_data=True, return_json=True)
    data = download['data']
    code = download['code']

    if code and data and check_key(data, 'reason') and data['reason'] == 'wrong backoffice':
        if profile_settings['base_v3'] == 0:
            query = "UPDATE `vars` SET `base_v3`=1 WHERE profile_id={profile_id}".format(profile_id=1)
            query_settings(query=query, return_result=False, return_insert=False, commit=True)
        else:
            query = "UPDATE `vars` SET `base_v3`=0 WHERE profile_id={profile_id}".format(profile_id=1)
            query_settings(query=query, return_result=False, return_insert=False, commit=True)

        update_settings()
        download_files()
        profile_settings = load_profile(profile_id=1)

        download = api_download(url=profile_settings['session_url'], type='post', headers=HEADERS, data={"username": username, "password": password}, json_data=True, return_json=True)

    if not code or not data or not check_key(data, 'oespToken'):
        if not code:
            code = {}

        if not data:
            data = {}

        return { 'code': code, 'data': data, 'result': False }

    ziggo_profile_id = ''
    household_id = ''

    if profile_settings['base_v3'] == 1:
        ziggo_profile_id = data['customer']['sharedProfileId']
        household_id = data['customer']['householdId']

    query = "UPDATE `vars` SET `access_token`='{access_token}', `ziggo_profile_id`='{ziggo_profile_id}', `household_id`='{household_id}' WHERE profile_id={profile_id}".format(access_token=data['oespToken'], ziggo_profile_id=ziggo_profile_id, household_id=household_id, profile_id=1)
    query_settings(query=query, return_result=False, return_insert=False, commit=True)

    if profile_settings['base_v3'] == 1:
        if len(unicode(profile_settings['watchlist_id'])) == 0:
            api_get_watchlist_id()

    return { 'code': code, 'data': data, 'result': True }

def api_play_url(type, channel=None, id=None, video_data=None, test=False, from_beginning=0, pvr=0):
    playdata = {'path': '', 'license': '', 'token': '', 'locator': '', 'type': '', 'alt_path': '', 'alt_license': '', 'alt_locator': ''}

    if not api_get_session():
        return playdata

    from_beginning = int(from_beginning)
    pvr = int(pvr)
    profile_settings = load_profile(profile_id=1)

    if type == "channel":
        id = channel

    alt_path = ''
    alt_license = ''
    alt_locator = ''
    info = {}
    base_listing_url = profile_settings['listings_url']
    urldata = None
    urldata2 = None
    path = None
    locator = None

    if not type or not len(unicode(type)) > 0 or not id or not len(unicode(id)) > 0:
        return playdata

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
        query = "SELECT assetid FROM `channels` WHERE id='{channel}'".format(channel=id)
        data = query_epg(query=query, return_result=True, return_insert=False, commit=False)

        if data:
            for row in data:
                split = row['assetid'].rsplit('&%%&', 1)

                if len(split) == 2:
                    urldata = {'play_url': split[0], 'locator': split[1]}
                else:
                    return playdata

        listing_url = '{listings_url}?byEndTime={time}~&byStationId={channel}&range=1-1&sort=startTime'.format(listings_url=base_listing_url, time=int(time.time() * 1000), channel=id)
        download = api_download(url=listing_url, type='get', headers=api_get_headers(), data=None, json_data=False, return_json=True)
        data = download['data']
        code = download['code']

        if code and code == 200 and data and check_key(data, 'listings'):
            for row in data['listings']:
                if check_key(row, 'program'):
                    info = row['program']
    elif type == 'program':
        listings_url = "{listings_url}/{id}".format(listings_url=base_listing_url, id=id)
        download = api_download(url=listings_url, type='get', headers=api_get_headers(), data=None, json_data=False, return_json=True)
        data = download['data']
        code = download['code']

        if not code or not code == 200 or not data or not check_key(data, 'program'):
            return playdata

        info = data['program']
    elif type == 'vod':
        mediaitems_url = '{mediaitems_url}/{id}'.format(mediaitems_url=profile_settings['mediaitems_url'], id=id)
        download = api_download(url=mediaitems_url, type='get', headers=api_get_headers(), data=None, json_data=False, return_json=True)
        data = download['data']
        code = download['code']

        if not code or not code == 200 or not data:
            return playdata

        info = data

    if check_key(info, 'videoStreams'):
        urldata2 = get_play_url(content=info['videoStreams'])

    if not type == 'channel' and (not urldata2 or not check_key(urldata2, 'play_url') or not check_key(urldata2, 'locator') or urldata2['play_url'] == 'http://Playout/using/Session/Service') and profile_settings['base_v3'] == 1:
        urldata2 = {}

        if type == 'program':
            playout_str = 'replay'
        elif type == 'vod':
            playout_str = 'vod'
        else:
            return playdata

        playout_url = '{base_url}/playout/{playout_str}/{id}?abrType=BR-AVC-DASH'.format(base_url=profile_settings['base_url'], playout_str=playout_str, id=id)
        download = api_download(url=playout_url, type='get', headers=api_get_headers(), data=None, json_data=False, return_json=True)
        data = download['data']
        code = download['code']

        if not code or not code == 200 or not data or not check_key(data, 'url') or not check_key(data, 'contentLocator'):
            return playdata

        urldata2['play_url'] = data['url']
        urldata2['locator'] = data['contentLocator']

    if urldata and urldata2 and check_key(urldata, 'play_url') and check_key(urldata, 'locator') and check_key(urldata2, 'play_url') and check_key(urldata2, 'locator'):
        path = urldata['play_url']
        locator = urldata['locator']

        alt_path = urldata2['play_url']
        alt_locator = urldata2['locator']
    else:
        if urldata and check_key(urldata, 'play_url') and check_key(urldata, 'locator'):
            path = urldata['play_url']
            locator = urldata['locator']
        elif urldata2 and check_key(urldata2, 'play_url') and check_key(urldata2, 'locator'):
            path = urldata2['play_url']
            locator = urldata2['locator']
            
    if not locator or not len(unicode(locator)) > 0:
        return playdata

    license = profile_settings['widevine_url']
    alt_license = profile_settings['widevine_url']

    if xbmc.Monitor().abortRequested():
        return playdata

    token = api_get_play_token(locator=locator, path=path, force=1)

    if not token or not len(unicode(token)) > 0:
        if not test:
            gui.ok(message=_.NO_STREAM_AUTH, heading=_.PLAY_ERROR)

        return playdata

    if not test:
        token = 'WIDEVINETOKEN'

    token_regex = re.search(r"(?<=;vxttoken=)(.*?)(?=/)", path)

    if token_regex and token_regex.group(1) and len(token_regex.group(1)) > 0:
        path = path.replace(token_regex.group(1), token)
    else:
        if 'sdash/' in path:
            spliturl = path.split('sdash/', 1)

            if len(spliturl) == 2:
                if profile_settings['base_v3'] == 1:
                    path = '{urlpart1}sdash;vxttoken={token}/{urlpart2}'.format(urlpart1=spliturl[0], token=token, urlpart2=spliturl[1])
                else:
                    path = '{urlpart1}sdash;vxttoken={token}/{urlpart2}?device=Orion-Replay-DASH'.format(urlpart1=spliturl[0], token=token, urlpart2=spliturl[1])
        else:
            spliturl = path.rsplit('/', 1)

            if len(spliturl) == 2:
                path = '{urlpart1};vxttoken={token}/{urlpart2}'.format(urlpart1=spliturl[0], token=token, urlpart2=spliturl[1])

    playdata = {'path': path, 'license': license, 'token': token, 'locator': locator, 'info': info, 'type': type, 'alt_path': alt_path, 'alt_license': alt_license, 'alt_locator': alt_license}

    return playdata

def api_remove_from_watchlist(id):
    if not api_get_session():
        return None

    profile_settings = load_profile(profile_id=1)

    if profile_settings['base_v3'] == 1:
        remove_url = 'https://prod.spark.ziggogo.tv/nld/web/watchlist-service/v1/watchlists/{watchlist_id}/entries/{id}?sharedProfile=true'.format(watchlist_id=profile_settings['watchlist_id'], id=id)
    else:
        remove_url = '{watchlist_url}/entries/{id}'.format(watchlist_url=profile_settings['watchlist_url'], id=id)

    download = api_download(url=remove_url, type='delete', headers=api_get_headers(), data=None, json_data=False, return_json=False)
    code = download['code']

    if not code or not code == 204:
        return False

    return True

def api_search(query):
    if not api_get_session():
        return None

    profile_settings = load_profile(profile_id=1)

    if profile_settings['base_v3'] == 1:
        return False

    end = int(time.time() * 1000)
    start = end - (7 * 24 * 60 * 60 * 1000)
    enable_cache = settings.getBool(key='enable_cache')

    vodstr = ''

    file = "cache" + os.sep + "search_" + clean_filename(query) + ".json"

    search_url = '{search_url}?byBroadcastStartTimeRange={start}~{end}&numItems=25&byEntitled=true&personalised=true&q={query}'.format(search_url=profile_settings['search_url'], start=start, end=end, query=quote(query))

    if enable_cache and not is_file_older_than_x_minutes(file=ADDON_PROFILE + file, minutes=10):
        data = load_file(file=file, isJSON=True)
    else:
        download = api_download(url=search_url, type='get', headers=api_get_headers(), data=None, json_data=False, return_json=True)
        data = download['data']
        code = download['code']

        if code and code == 200 and data and (check_key(data, 'tvPrograms') or check_key(data, 'moviesAndSeries')) and enable_cache:
            write_file(file=file, data=data, isJSON=True)

    if not data or (not check_key(data, 'tvPrograms') and not check_key(data, 'moviesAndSeries')):
        return False

    items = []
    items_vod = []
    items_program = []
    vod_links = {}

    if not settings.getBool('showMoviesSeries'):
        try:
            data.pop('moviesAndSeries', None)
        except:
            pass
    else:
        for entry in CONST_VOD_CAPABILITY:
            sql_query = "SELECT * FROM `{table}`".format(table=entry['file'])
            sql_data = query_epg(query=sql_query, return_result=True, return_insert=False, commit=False)

            for row in sql_data:
                vod_links[row['id']] = {}
                vod_links[row['id']]['seasons'] = row['seasons']
                vod_links[row['id']]['duration'] = row['duration']
                vod_links[row['id']]['desc'] = row['description']
                vod_links[row['id']]['type'] = row['type']

    for currow in list(data):
        if currow == "moviesAndSeries":
            type = 'vod'
        else:
            type = 'program'

        for row in data[currow]['entries']:
            if not check_key(row, 'id') or not check_key(row, 'title'):
                continue

            item = {}

            id = row['id']
            label = row['title']
            description = ''
            duration = 0
            program_image = ''
            program_image_large = ''
            start = ''

            if check_key(row, 'images'):
                program_image = get_image("boxart", row['images'])
                program_image_large = get_image("HighResLandscape", row['images'])

                if program_image_large == '':
                    program_image_large = program_image
                else:
                    program_image_large += '?w=1920&mode=box'

            if type == 'vod':
                if check_key(vod_links, row['id']):
                    description = vod_links[row['id']]['desc']
                    item_type = vod_links[row['id']]['type']
                else:
                    item_type = 'Vod'

                label += " (Movies and Series)"
            else:
                item_type = 'Epg'
                label += " (ReplayTV)"

            if check_key(row, 'groupType') and row['groupType'] == 'show':
                if check_key(row, 'episodeMatch') and check_key(row['episodeMatch'], 'seriesEpisodeNumber') and check_key(row['episodeMatch'], 'secondaryTitle'):
                    if len(description) == 0:
                        description += label

                    season = ''

                    if check_key(row, 'seriesNumber'):
                        season = "S" + row['seriesNumber']

                    description += " Episode Match: {season}E{episode} - {secondary}".format(season=season, episode=row['episodeMatch']['seriesEpisodeNumber'], secondary=row['episodeMatch']['secondaryTitle'])
            else:
                if check_key(row, 'duration'):
                    duration = int(row['duration'])
                elif check_key(row, 'episodeMatch') and check_key(row['episodeMatch'], 'startTime') and check_key(row['episodeMatch'], 'endTime'):
                    duration = int(int(row['episodeMatch']['endTime']) - int(row['episodeMatch']['startTime'])) // 1000
                    id = row['episodeMatch']['id']
                elif check_key(vod_links, row['id']) and check_key(vod_links[row['id']], 'duration'):
                    duration = vod_links[row['id']]['duration']

            item['id'] = id
            item['title'] = label
            item['description'] = description
            item['duration'] = duration
            item['type'] = item_type
            item['icon'] = program_image_large
            item['start'] = start

            if type == "vod":
                items_vod.append(item)
            else:
                items_program.append(item)

    num = min(len(items_program), len(items_vod))
    items = [None]*(num*2)
    items[::2] = items_program[:num]
    items[1::2] = items_vod[:num]
    items.extend(items_program[num:])
    items.extend(items_vod[num:])

    return items

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
        listing_url = profile_settings['listings_url']

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

                playdata = api_play_url(type='channel', id=row['id'], test=True)

                if first and not profile_settings['last_login_success']:
                    if test_run:
                        update_prefs()

                    query = "UPDATE `vars` SET `test_running`={test_running} WHERE profile_id={profile_id}".format(test_running=0,profile_id=1)
                    query_settings(query=query, return_result=False, return_insert=False, commit=True)
                    return 5

                if len(playdata['path']) > 0:
                    CDMHEADERS = {
                        'User-Agent': user_agent,
                        'X-Client-Id': profile_settings['client_id'] + '||' + user_agent,
                        'X-OESP-Token': profile_settings['access_token'],
                        'X-OESP-Username': profile_settings['username'],
                        'X-OESP-License-Token': profile_settings['drm_token'],
                        'X-OESP-DRM-SchemeIdUri': 'urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed',
                        'X-OESP-Content-Locator': playdata['locator'],
                    }

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

                listing_url = '{listings_url}?byEndTime={time}~&byStationId={channel}&range=1-1&sort=startTime'.format(listings_url=listing_url, time=int(int(time.time() - 86400) * 1000), channel=id)
                download = api_download(url=listing_url, type='get', headers=api_get_headers(), data=None, json_data=False, return_json=True)
                data = download['data']
                code = download['code']

                program_id = None

                if code and code == 200 and data and check_key(data, 'listings'):
                    for row in data['listings']:
                        program_id = row['id']

                if program_id:
                    profile_settings = load_profile(profile_id=1)

                    if profile_settings['last_playing'] > int(time.time() - 300):
                        if test_run:
                            update_prefs()

                        query = "UPDATE `vars` SET `test_running`={test_running} WHERE profile_id={profile_id}".format(test_running=0,profile_id=1)
                        query_settings(query=query, return_result=False, return_insert=False, commit=True)
                        return 5

                    playdata = api_play_url(type='program', id=program_id, test=True)

                    if len(playdata['path']) > 0:
                        CDMHEADERS = {
                            'User-Agent': user_agent,
                            'X-Client-Id': profile_settings['client_id'] + '||' + user_agent,
                            'X-OESP-Token': profile_settings['access_token'],
                            'X-OESP-Username': profile_settings['username'],
                            'X-OESP-License-Token': profile_settings['drm_token'],
                            'X-OESP-DRM-SchemeIdUri': 'urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed',
                            'X-OESP-Content-Locator': playdata['locator'],
                        }

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

    profile_settings = load_profile(profile_id=1)

    season_url = '{mediaitems_url}?byMediaType=Episode%7CFeatureFilm&byParentId={id}&includeAdult=true&range=1-1000&sort=seriesEpisodeNumber|ASC'.format(mediaitems_url=profile_settings['mediaitems_url'], id=id)
    download = api_download(url=season_url, type='get', headers=None, data=None, json_data=False, return_json=True)
    data = download['data']
    code = download['code']

    if not data or not check_key(data, 'mediaItems'):
        return None

    if sys.version_info >= (3, 0):
        data['mediaItems'] = list(data['mediaItems'])

    for row in data['mediaItems']:
        desc = ''
        image = ''
        label = ''

        if not check_key(row, 'title') or not check_key(row, 'id'):
            continue

        if check_key(row, 'description'):
            desc = row['description']

        if check_key(row, 'duration'):
            duration = int(row['duration'])

        if check_key(row, 'images'):
            program_image = get_image("boxart", row['images'])
            image = get_image("HighResLandscape", row['images'])

            if image == '':
                image = program_image
            else:
                image += '?w=1920&mode=box'

        if check_key(row, 'earliestBroadcastStartTime'):
            startsplit = int(row['earliestBroadcastStartTime']) // 1000

            startT = datetime.datetime.fromtimestamp(startsplit)
            startT = convert_datetime_timezone(startT, "UTC", "UTC")

            if xbmc.getLanguage(xbmc.ISO_639_1) == 'nl':
                label = date_to_nl_dag(startT) + startT.strftime(" %d ") + date_to_nl_maand(startT) + startT.strftime(" %Y %H:%M ") + row['title']
            else:
                label = (startT.strftime("%A %d %B %Y %H:%M ") + row['title']).capitalize()
        else:
            label = row['title']

        season.append({'label': label, 'id': row['id'], 'start': '', 'duration': duration, 'title': row['title'], 'seasonNumber': '', 'episodeNumber': '', 'description': desc, 'image': image})

    return season

def api_vod_seasons(id):
    seasons = []

    for entry in CONST_VOD_CAPABILITY:
        sql_query = "SELECT * FROM `{table}` WHERE id='{id}'".format(table=entry['file'], id=id)
        sql_data = query_epg(query=sql_query, return_result=True, return_insert=False, commit=False)

        if len(sql_data) > 0:
            for row in sql_data:
                sql_seasons = json.loads(row['seasons'])

                for season in sql_seasons:
                    seasons.append({'id': season['id'], 'seriesNumber': season['seriesNumber'], 'description': row['description'], 'image': row['icon']})

            break

    return {'type': 'seasons', 'seasons': seasons, 'watchlist': id}

def api_vod_subscription():
    return None

def api_watchlist_listing(id):
    if not api_get_session():
        return None

    profile_settings = load_profile(profile_id=1)

    end = int(time.time() * 1000)
    start = end - (7 * 24 * 60 * 60 * 1000)

    mediaitems_url = '{media_items_url}?&byMediaGroupId={id}&byStartTime={start}~{end}&range=1-250&sort=startTime%7Cdesc'.format(media_items_url=profile_settings['listings_url'], id=id, start=start, end=end)
    download = api_download(url=mediaitems_url, type='get', headers=api_get_headers(), data=None, json_data=False, return_json=True)
    data = download['data']
    code = download['code']

    if not code or not code == 200 or not data or not check_key(data, 'listings'):
        return False

    return data