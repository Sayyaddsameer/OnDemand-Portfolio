"""
coding_stats_lambda.py — Live coding-stats proxy
Fetches all 5 platforms in parallel, caches to DynamoDB (TTL: 1 h).

Deploy as a new Lambda and add to API Gateway as:
  GET /coding-stats   →  this function (CORS enabled)

Required IAM permissions on this Lambda's execution role:
  dynamodb:GetItem  on  arn:aws:dynamodb:*:*:table/CodingStatsCache
  dynamodb:PutItem  on  arn:aws:dynamodb:*:*:table/CodingStatsCache

Environment variables (all optional — defaults shown):
  CACHE_TABLE    = CodingStatsCache
  CACHE_TTL      = 3600          (seconds)
  ALLOWED_ORIGIN = *
"""

import json
import os
import re
import time
import boto3
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Profile config ─────────────────────────────────────────────────────────────
PROFILES = {
    'leetcode': {
        'username': 'sayyadsameerm3',
        'url': 'https://leetcode.com/u/sayyadsameerm3/',
    },
    'codeforces': {
        'username': 'sayyad_sameer',
        'url': 'https://codeforces.com/profile/sayyad_sameer',
    },
    'codechef': {
        'username': 'sayyadsameer',
        'url': 'https://www.codechef.com/users/sayyadsameer',
    },
    'gfg': {
        'username': 'sayyadsameer',
        'url': 'https://www.geeksforgeeks.org/profile/sayyadsameer',
    },
    'hackerrank': {
        'username': 'sayyadsameerm3',
        'url': 'https://www.hackerrank.com/profile/sayyadsameerm3',
    },
}

CACHE_TABLE    = os.environ.get('CACHE_TABLE', 'CodingStatsCache')
CACHE_TTL      = int(os.environ.get('CACHE_TTL', '3600'))
ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN', '*')
CACHE_PK       = 'stats_v1'

_UA = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
)

# ── HTTP helpers ───────────────────────────────────────────────────────────────
def _get(url, extra=None, timeout=14):
    h = {
        'User-Agent': _UA,
        'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    if extra:
        h.update(extra)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='ignore')


def _post_json(url, payload, extra=None, timeout=14):
    h = {'User-Agent': _UA, 'Content-Type': 'application/json', 'Accept': 'application/json'}
    if extra:
        h.update(extra)
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=h, method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _next_data(html):
    """Extract the __NEXT_DATA__ JSON blob embedded by Next.js."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    return json.loads(m.group(1)) if m else None


# ── LeetCode (GraphQL API) ─────────────────────────────────────────────────────
def _fetch_leetcode():
    u = PROFILES['leetcode']['username']
    query = """
    query userProfile($username: String!) {
      matchedUser(username: $username) {
        submitStats: submitStatsGlobal {
          acSubmissionNum { difficulty count }
        }
        profile { ranking }
        badges { displayName }
        activeBadge { displayName }
        userCalendar { streak totalActiveDays }
      }
    }"""
    resp = _post_json(
        'https://leetcode.com/graphql',
        {'query': query, 'variables': {'username': u}},
        extra={'Referer': 'https://leetcode.com'},
    )
    mu   = resp['data']['matchedUser']
    cnts = {s['difficulty'].lower(): s['count'] for s in mu['submitStats']['acSubmissionNum']}
    cal  = mu.get('userCalendar') or {}
    return {
        'platform':        'LeetCode',
        'url':             PROFILES['leetcode']['url'],
        'total':           cnts.get('all', 0),
        'easy':            cnts.get('easy', 0),
        'medium':          cnts.get('medium', 0),
        'hard':            cnts.get('hard', 0),
        'ranking':         mu['profile']['ranking'],
        'streak':          cal.get('streak', 0),
        'totalActiveDays': cal.get('totalActiveDays', 0),
        'activeBadge':     (mu.get('activeBadge') or {}).get('displayName'),
        'badges':          [b['displayName'] for b in (mu.get('badges') or [])],
    }


# ── Codeforces (Official REST API) ────────────────────────────────────────────
def _fetch_codeforces():
    u    = PROFILES['codeforces']['username']
    info = json.loads(_get(f'https://codeforces.com/api/user.info?handles={u}'))
    if info['status'] != 'OK':
        raise RuntimeError('Codeforces API: non-OK status')
    cf = info['result'][0]

    # Count unique accepted problems
    solved = None
    try:
        status = json.loads(
            _get(f'https://codeforces.com/api/user.status?handle={u}&from=1&count=100000', timeout=20)
        )
        if status['status'] == 'OK':
            solved = len({
                f"{s['problem']['contestId']}-{s['problem']['index']}"
                for s in status['result']
                if s.get('verdict') == 'OK'
            })
    except Exception:
        pass

    return {
        'platform':     'Codeforces',
        'url':          PROFILES['codeforces']['url'],
        'rating':       cf.get('rating'),
        'maxRating':    cf.get('maxRating'),
        'rank':         cf.get('rank', 'Unrated'),
        'maxRank':      cf.get('maxRank', 'Unrated'),
        'solved':       solved,
        'contribution': cf.get('contribution', 0),
    }


# ── CodeChef (__NEXT_DATA__ scrape + regex fallback) ──────────────────────────
def _fetch_codechef():
    u    = PROFILES['codechef']['username']
    html = _get(f'https://www.codechef.com/users/{u}')
    nd   = _next_data(html)
    if nd:
        # Try multiple possible paths for userDetails
        ud = None
        for path in [
            ['props', 'pageProps', 'userDetails'],
            ['props', 'pageProps', 'data', 'userDetails'],
            ['props', 'pageProps', 'user'],
        ]:
            try:
                obj = nd
                for k in path:
                    obj = obj[k]
                if obj and isinstance(obj, dict):
                    ud = obj
                    break
            except (KeyError, TypeError):
                continue

        if ud:
            return {
                'platform':    'CodeChef',
                'url':         PROFILES['codechef']['url'],
                'rating':      ud.get('currentRating') or ud.get('rating'),
                'maxRating':   ud.get('highestRating') or ud.get('maxRating'),
                'stars':       ud.get('stars'),
                'globalRank':  ud.get('globalRank'),
                'countryRank': ud.get('countryRank'),
                'solved':      ud.get('totalProblems') or ud.get('solvedProblems'),
            }

    # Regex fallback — look directly in HTML
    def _ri(pat):
        m = re.search(pat, html)
        return int(m.group(1)) if m else None

    # Also try to extract star count from rendered HTML (★ characters)
    stars_val = None
    sm = re.search(r'(\d+)\s*(?:★|\*\s*Star)', html, re.IGNORECASE)
    if sm:
        stars_val = int(sm.group(1))
    else:
        sm2 = re.search(r'"stars"\s*:\s*"?(\d+)"?', html)
        if sm2:
            stars_val = int(sm2.group(1))

    return {
        'platform':   'CodeChef',
        'url':        PROFILES['codechef']['url'],
        'rating':     _ri(r'"currentRating"\s*:\s*(\d+)') or _ri(r'rating["\s]*:\s*(\d+)'),
        'maxRating':  _ri(r'"highestRating"\s*:\s*(\d+)'),
        'stars':      stars_val,
        'globalRank': _ri(r'"globalRank"\s*:\s*(\d+)'),
        'solved':     _ri(r'"totalProblems"\s*:\s*(\d+)') or _ri(r'"solvedProblems"\s*:\s*(\d+)'),
    }


# ── GeeksForGeeks (community API → __NEXT_DATA__ fallback) ────────────────────
def _fetch_gfg():
    u = PROFILES['gfg']['username']

    # Primary: try multiple community stat API mirrors
    for api in [
        f'https://geeks-for-geeks-api.vercel.app/api?userName={u}',
        f'https://geeks-for-geeks-api.vercel.app/?raw=y&userName={u}',
        f'https://gfgstatsapi.vercel.app/api/{u}',
        f'https://gfg-api.vercel.app/api/{u}',
        f'https://gfg-stats.vercel.app/api/user/{u}',
    ]:
        try:
            resp = json.loads(_get(api, extra={'Accept': 'application/json'}, timeout=10))
            info = resp.get('info', {})
            # Handle two common response shapes
            solved = (
                resp.get('totalProblemsSolved')
                or resp.get('problemsSolved')
                or info.get('totalProblemsSolved')
            )
            if solved is not None or info.get('codingScore') is not None:
                return {
                    'platform':      'GeeksForGeeks',
                    'url':           PROFILES['gfg']['url'],
                    'solved':        solved,
                    'score':         resp.get('codingScore') or info.get('codingScore'),
                    'instituteRank': resp.get('instituteRank') or info.get('instituteRank'),
                    'streak':        resp.get('streak') or resp.get('currentStreak'),
                    'school':        resp.get('School') or resp.get('school'),
                    'basic':         resp.get('Basic') or resp.get('basic'),
                    'easy':          resp.get('Easy') or resp.get('easy'),
                    'medium':        resp.get('Medium') or resp.get('medium'),
                    'hard':          resp.get('Hard') or resp.get('hard'),
                }
        except Exception:
            continue

    # Fallback: scrape __NEXT_DATA__ from multiple profile URL patterns
    for profile_url in [
        f'https://www.geeksforgeeks.org/user/{u}/',
        f'https://www.geeksforgeeks.org/profile/{u}',
        f'https://auth.geeksforgeeks.org/user/{u}/practice/',
    ]:
        try:
            html = _get(profile_url)
            nd   = _next_data(html)
            if nd:
                # Try multiple key paths
                for p_path in [
                    ['props', 'pageProps', 'userHandle'],
                    ['props', 'pageProps', 'data'],
                    ['props', 'pageProps'],
                ]:
                    try:
                        p = nd
                        for k in p_path:
                            p = p[k]
                        solved = (
                            p.get('totalProblemsSolved')
                            or p.get('problemsSolved')
                        )
                        if solved is not None or p.get('codingScore') is not None:
                            return {
                                'platform':      'GeeksForGeeks',
                                'url':           PROFILES['gfg']['url'],
                                'solved':        solved,
                                'score':         p.get('codingScore'),
                                'instituteRank': p.get('instituteRank'),
                                'streak':        p.get('currentStreak') or p.get('streak'),
                            }
                    except (KeyError, TypeError):
                        continue

            # Last resort: regex scan the raw HTML
            def _rp(pat):
                m = re.search(pat, html)
                return int(m.group(1)) if m else None

            solved  = _rp(r'"totalProblemsSolved"\s*:\s*(\d+)') or _rp(r'"problemsSolved"\s*:\s*(\d+)')
            score   = _rp(r'"codingScore"\s*:\s*(\d+)')
            rank    = _rp(r'"instituteRank"\s*:\s*(\d+)')
            if solved or score:
                return {
                    'platform':      'GeeksForGeeks',
                    'url':           PROFILES['gfg']['url'],
                    'solved':        solved,
                    'score':         score,
                    'instituteRank': rank,
                }
        except Exception:
            continue

    raise RuntimeError('GFG: all fetch strategies failed')


# ── HackerRank (REST badge endpoint → scrape fallback) ────────────────────────
def _fetch_hackerrank():
    u  = PROFILES['hackerrank']['username']
    hr = {'Accept': 'application/json', 'Referer': 'https://www.hackerrank.com'}

    # Primary: REST badge endpoint
    try:
        data   = json.loads(_get(f'https://www.hackerrank.com/rest/hackers/{u}/badges', extra=hr))
        badges = [
            {
                'name':     b.get('badge_name'),       # correct field
                'stars':    b.get('stars', 0),
                'type':     b.get('badge_type'),
                'solved':   b.get('solved', 0),
                'category': b.get('category_name'),
            }
            for b in (data.get('models') or [])
            if b.get('stars', 0) > 0                   # only earned badges
        ]
        return {
            'platform':    'HackerRank',
            'url':         PROFILES['hackerrank']['url'],
            'badges':      badges,
            'totalBadges': len(badges),
            'totalStars':  sum(b['stars'] for b in badges),
        }
    except Exception:
        pass

    # Fallback: scrape __NEXT_DATA__ from profile page
    try:
        nd = _next_data(_get(f'https://www.hackerrank.com/profile/{u}'))
        if nd:
            badges_raw = nd.get('props', {}).get('pageProps', {}).get('badges', [])
            badges = [
                {
                    'name':   b.get('badge_name') or b.get('name'),
                    'stars':  b.get('stars', 0),
                    'solved': b.get('solved', 0),
                }
                for b in badges_raw
                if b.get('stars', 0) > 0
            ]
            return {
                'platform':    'HackerRank',
                'url':         PROFILES['hackerrank']['url'],
                'badges':      badges,
                'totalBadges': len(badges),
                'totalStars':  sum(b['stars'] for b in badges),
            }
    except Exception:
        pass

    raise RuntimeError('HackerRank: all fetch strategies failed')


# ── DynamoDB cache ─────────────────────────────────────────────────────────────
def _cache_get():
    try:
        item = boto3.resource('dynamodb').Table(CACHE_TABLE).get_item(
            Key={'pk': CACHE_PK}
        ).get('Item')
        if item and int(item.get('expires_at', 0)) > int(time.time()):
            return json.loads(item['data'])
    except Exception:
        pass
    return None


def _cache_set(payload):
    try:
        boto3.resource('dynamodb').Table(CACHE_TABLE).put_item(Item={
            'pk':         CACHE_PK,
            'data':       json.dumps(payload),
            'expires_at': int(time.time()) + CACHE_TTL,
        })
    except Exception:
        pass


# ── Response helper ────────────────────────────────────────────────────────────
def _resp(status, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type':                'application/json',
            'Access-Control-Allow-Origin':  ALLOWED_ORIGIN,
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
        },
        'body': json.dumps(body),
    }


# ── Lambda handler ─────────────────────────────────────────────────────────────
_FETCHERS = {
    'leetcode':   _fetch_leetcode,
    'codeforces': _fetch_codeforces,
    'codechef':   _fetch_codechef,
    'gfg':        _fetch_gfg,
    'hackerrank': _fetch_hackerrank,
}


def lambda_handler(event, context):
    if (event.get('httpMethod') or '').upper() == 'OPTIONS':
        return _resp(200, {})

    cached = _cache_get()
    if cached:
        cached['cache_hit'] = True
        return _resp(200, cached)

    results = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fn): key for key, fn in _FETCHERS.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                results[key] = {
                    'platform': key.capitalize(),
                    'url':      PROFILES[key]['url'],
                    'error':    str(exc),
                }

    payload = {'stats': results, 'cache_hit': False, 'fetched_at': int(time.time())}
    _cache_set(payload)
    return _resp(200, payload)
