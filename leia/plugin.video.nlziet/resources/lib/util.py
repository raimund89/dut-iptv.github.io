import _strptime
import datetime, time, xbmc

from resources.lib.base.l1 import uaparser
from resources.lib.base.l1.constants import DEFAULT_USER_AGENT
from resources.lib.base.l2 import settings
from resources.lib.base.l2.log import log 
from resources.lib.base.l3.language import _
from resources.lib.base.l3.util import check_key, convert_datetime_timezone, date_to_nl_dag, date_to_nl_maand, load_profile, query_epg, query_settings
from resources.lib.base.l4 import gui
from resources.lib.base.l4.session import Session
from resources.lib.base.l5 import inputstream
from resources.lib.constants import CONST_BASE_HEADERS, CONST_IMAGE_URL

try:
    unicode
except NameError:
    unicode = str

def plugin_ask_for_creds(creds):
    username = gui.input(message=_.ASK_USERNAME, default=creds['username']).strip()

    if not len(username) > 0:
        gui.ok(message=_.EMPTY_USER, heading=_.LOGIN_ERROR_TITLE)

        return {'result': False, 'username': '', 'password': ''}

    password = gui.input(message=_.ASK_PASSWORD, hide_input=True).strip()

    if not len(password) > 0:
        gui.ok(message=_.EMPTY_PASS, heading=_.LOGIN_ERROR_TITLE)

        return {'result': False, 'username': '', 'password': ''}

    return {'result': True, 'username': username, 'password': password}

def plugin_login_error(login_result):
    try:
        if (login_result['code'] == 403 and 'Teveel verschillende apparaten' in login_result['data']):
            gui.ok(message=_.TOO_MANY_DEVICES, heading=_.LOGIN_ERROR_TITLE)
        else:
            gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)
    except:
        gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)

def plugin_post_login():
    pass

def plugin_process_info(playdata):
    info = {
        'label1': '',
        'label2': '',
        'description': '',
        'image': '',
        'image_large': '',
        'duration': 0,
        'credits': [],
        'cast': [],
        'director': [],
        'writer': [],
        'genres': [],
        'year': '',
    }

    if check_key(playdata['info'], 'Start') and check_key(playdata['info'], 'End'):
        startT = datetime.datetime.fromtimestamp(time.mktime(time.strptime(playdata['info']['Start'], "%Y-%m-%dT%H:%M:%S")))
        startT = convert_datetime_timezone(startT, "UTC", "UTC")
        endT = datetime.datetime.fromtimestamp(time.mktime(time.strptime(playdata['info']['End'], "%Y-%m-%dT%H:%M:%S")))
        endT = convert_datetime_timezone(endT, "UTC", "UTC")

        if check_key(playdata['info'], 'DurationInSeconds'):
            info['duration'] = playdata['info']['DurationInSeconds']
        elif check_key(playdata['info'], 'Duur'):
            info['duration'] = playdata['info']['Duur']
        else:
            info['duration'] = int((endT - startT).total_seconds())

        if xbmc.getLanguage(xbmc.ISO_639_1) == 'nl':
            info['label1'] = '{weekday} {day} {month} {yearhourminute} '.format(weekday=date_to_nl_dag(startT), day=startT.strftime("%d"), month=date_to_nl_maand(startT), yearhourminute=startT.strftime("%Y %H:%M"))
        else:
            info['label1'] = startT.strftime("%A %d %B %Y %H:%M ").capitalize()

        info['label1'] += " - "
    elif check_key(playdata['info'], 'Duur'):
        info['duration'] = playdata['info']['Duur']

    if check_key(playdata['info'], 'Title'):
        info['label1'] += playdata['info']['Title']
        info['label2'] = playdata['info']['Title']
    elif check_key(playdata['info'], 'Serie') and check_key(playdata['info']['Serie'], 'Titel') and len(playdata['info']['Serie']['Titel']):
        info['label1'] += playdata['info']['Serie']['Titel']
        info['label2'] = playdata['info']['Serie']['Titel']

        if check_key(playdata['info'], 'Titel') and len(playdata['info']['Titel']) > 0 and playdata['info']['Titel'] != playdata['info']['Serie']['Titel']:
            info['label1'] += ": " + playdata['info']['Titel']
            info['label2'] += ": " + playdata['info']['Titel']
    elif check_key(playdata['info'], 'Titel'):
        info['label1'] += playdata['info']['Titel']
        info['label2'] = playdata['info']['Titel']

    if check_key(playdata['info'], 'LongDescription'):
        info['description'] = playdata['info']['LongDescription']
    elif check_key(playdata['info'], 'Omschrijving'):
        info['description'] = playdata['info']['Omschrijving']

    if check_key(playdata['info'], 'CoverUrl'):
        info['image'] = playdata['info']['CoverUrl']
        info['image_large'] = playdata['info']['CoverUrl']
    elif check_key(playdata['info'], 'AfbeeldingUrl'):
        info['image'] = playdata['info']['AfbeeldingUrl']
        info['image_large'] = playdata['info']['AfbeeldingUrl']

    if check_key(playdata['info'], 'ChannelTitle'):
        info['label2'] += " - "  + playdata['info']['ChannelTitle']
    elif check_key(playdata['info'], 'Zender'):
        info['label2'] += " - "  + playdata['info']['Zender']

    return info

def plugin_process_playdata(playdata):
    CDMHEADERS = {}

    if check_key(playdata, 'license') and check_key(playdata['license'], 'drmConfig') and check_key(playdata['license']['drmConfig'], 'widevine'):
        if 'nlznl.solocoo.tv' in playdata['license']['drmConfig']['widevine']['drmServerUrl']:
            if xbmc.Monitor().waitForAbort(1):
                return False

        if check_key(playdata['license']['drmConfig']['widevine'], 'customHeaders'):
            for row in playdata['license']['drmConfig']['widevine']['customHeaders']:
                CDMHEADERS[row] = playdata['license']['drmConfig']['widevine']['customHeaders'][row]

        item_inputstream = inputstream.Widevine(
            license_key = playdata['license']['drmConfig']['widevine']['drmServerUrl'],
        )
    else:
        item_inputstream = inputstream.MPD()

    return item_inputstream, CDMHEADERS

def plugin_renew_token(data):
    return None

def plugin_vod_subscription_filter():
    return None

def plugin_process_watchlist(data):
    items = []

    return items

def plugin_process_watchlist_listing(data, id=None):
    items = []

    return items

def proxy_get_match(path):
    if ".mpd" in path:
        return True

    return False

def proxy_get_session(proxy):
    return Session(cookies_key='cookies', save_cookies=False)

def proxy_get_url(proxy):
    return proxy._stream_url + str(proxy.path)

def proxy_xml_mod(xml):
    return xml

def service_timer(timer):
    if timer == 'daily':
        pass
    elif timer == 'hourly':
        pass
    elif timer == 'startup':
        pass

def update_settings():
    profile_settings = load_profile(profile_id=1)

    user_agent = profile_settings['user_agent']

    if len(user_agent) == 0:
        user_agent = DEFAULT_USER_AGENT

    query = "UPDATE `vars` SET `user_agent`='{user_agent}' WHERE profile_id={profile_id}".format(user_agent=user_agent, profile_id=1)
    query_settings(query=query, return_result=False, return_insert=False, commit=True)