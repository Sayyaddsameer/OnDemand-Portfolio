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

    # Count unique accepted problems — limit to last 5000 to avoid timeout
    solved = None
    try:
        status = json.loads(
            _get(f'https://codeforces.com/api/user.status?handle={u}&from=1&count=5000', timeout=12)
        )
        if status['status'] == 'OK':
            solved = len({
                f"{s['problem']['contestId']}-{s['problem']['index']}"
                for s in status['result']
                if s.get('verdict') == 'OK'
            })
    except Exception:
        pass   # solved stays None — rating/rank still returned

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
    u = PROFILES['codechef']['username']

    # CodeChef profile page is classic Drupal server-rendered HTML.
    # Data is embedded directly in the HTML — no JS execution needed.
    try:
        html = _get(f'https://www.codechef.com/users/{u}')

        def _ri(pat):
            m = re.search(pat, html)
            return int(m.group(1)) if m else None

        # Current rating: <a href='...ratings/all' class='rating'>1407 (<span...
        rating = _ri(r"class='rating'>\s*(\d+)\s*\(")

        # Stars: username badge shows >2&#9733;</span> or >2★<  (1-7 stars)
        # Try both HTML entity and literal Unicode star character
        stars = _ri(r'>([1-7])&#9733;<') or _ri(r'>([1-7])★<')

        # Global rank: <strong class='global-rank'>3220</strong>
        global_rank = _ri(r"class='global-rank'>(\d+)</strong>")

        # Total Problems Solved: <h3>Total Problems Solved: 632</h3>
        solved = _ri(r"Total Problems Solved:\s*(\d+)")

        # Highest rating is not directly shown; use a JS variable if present
        max_rating = _ri(r'"highestRating"\s*:\s*(\d+)')

        if rating or global_rank or solved:
            return {
                'platform':   'CodeChef',
                'url':        PROFILES['codechef']['url'],
                'rating':     rating,
                'maxRating':  max_rating,
                'stars':      stars if stars else None,   # never return 0
                'globalRank': global_rank,
                'solved':     solved,
            }
    except Exception:
        pass

    # ── Env var fallback ──────────────────────────────────────────────────────
    # If scraping fails, set these in AWS Lambda > Configuration > Environment variables:
    #   CC_RATING, CC_MAX_RATING, CC_STARS, CC_GLOBAL_RANK, CC_SOLVED
    def _ev(key):
        v = os.environ.get(key)
        return int(v) if v and v.isdigit() else None

    rating = _ev('CC_RATING')
    if rating is None:
        raise RuntimeError('CodeChef: scraping failed and no env var fallback set.')
    return {
        'platform':   'CodeChef',
        'url':        PROFILES['codechef']['url'],
        'rating':     rating,
        'maxRating':  _ev('CC_MAX_RATING'),
        'stars':      _ev('CC_STARS'),
        'globalRank': _ev('CC_GLOBAL_RANK'),
        'solved':     _ev('CC_SOLVED'),
        'fromEnv':    True,
    }


# ── GeeksForGeeks ─────────────────────────────────────────────────────────────
def _fetch_gfg():
    u = PROFILES['gfg']['username']

    # ── Primary: gfgstatscard.vercel.app (confirmed working ✅) ─────────────
    # Returns: {"userHandle","total_score","total_problems_solved",
    #           "pod_solved_current_streak","School","Basic","Easy","Medium","Hard",...}
    try:
        resp = json.loads(_get(
            f'https://gfgstatscard.vercel.app/{u}?raw=true',
            extra={'Accept': 'application/json'},
            timeout=12
        ))
        school = resp.get('School', 0) or 0
        basic  = resp.get('Basic',  0) or 0
        easy   = resp.get('Easy',   0) or 0
        medium = resp.get('Medium', 0) or 0
        hard   = resp.get('Hard',   0) or 0
        solved = resp.get('total_problems_solved') or (school + basic + easy + medium + hard) or None
        score  = resp.get('total_score') or None
        streak = resp.get('pod_solved_current_streak') or None

        if solved or score:
            return {
                'platform':      'GeeksForGeeks',
                'url':           PROFILES['gfg']['url'],
                'solved':        solved,
                'score':         score,
                'instituteRank': None,   # not in this API
                'streak':        streak,
                'school':        school if school else None,
                'basic':         basic  if basic  else None,
                'easy':          easy   if easy   else None,
                'medium':        medium if medium else None,
                'hard':          hard   if hard   else None,
            }
    except Exception:
        pass

    # ── Fallback: geeks-for-geeks-stats-api.vercel.app ──────────────────────
    for api in [
        f'https://geeks-for-geeks-stats-api.vercel.app/?userName={u}',
        f'https://geeks-for-geeks-api.vercel.app/api?userName={u}',
    ]:
        try:
            resp = json.loads(_get(api, extra={'Accept': 'application/json'}, timeout=10))
            if resp.get('error') or resp.get('message') == 'error':
                continue
            school = resp.get('School', 0) or 0
            basic  = resp.get('Basic',  0) or 0
            easy   = resp.get('Easy',   0) or 0
            medium = resp.get('Medium', 0) or 0
            hard   = resp.get('Hard',   0) or 0
            solved = (
                resp.get('totalProblemsSolved')
                or resp.get('total_problems_solved')
                or (school + basic + easy + medium + hard)
                or None
            )
            if solved:
                return {
                    'platform':      'GeeksForGeeks',
                    'url':           PROFILES['gfg']['url'],
                    'solved':        solved,
                    'score':         resp.get('total_score') or resp.get('codingScore'),
                    'instituteRank': resp.get('instituteRank'),
                    'streak':        resp.get('pod_solved_current_streak') or resp.get('streak'),
                    'school':        school if school else None,
                    'basic':         basic  if basic  else None,
                    'easy':          easy   if easy   else None,
                    'medium':        medium if medium else None,
                    'hard':          hard   if hard   else None,
                }
        except Exception:
            continue

    # ── Last resort: env var fallback ────────────────────────────────────────
    # Set in AWS Lambda > Configuration > Environment variables:
    #   GFG_SOLVED, GFG_SCORE, GFG_RANK, GFG_STREAK, GFG_BASIC, GFG_EASY, GFG_MEDIUM, GFG_HARD
    def _ev(key):
        v = os.environ.get(key)
        return int(v) if v and v.isdigit() else None

    solved = _ev('GFG_SOLVED')
    score  = _ev('GFG_SCORE')
    if solved is None and score is None:
        raise RuntimeError('GFG: all APIs failed. Set GFG_SOLVED env var in Lambda as fallback.')
    return {
        'platform':      'GeeksForGeeks',
        'url':           PROFILES['gfg']['url'],
        'solved':        solved,
        'score':         score,
        'instituteRank': _ev('GFG_RANK'),
        'streak':        _ev('GFG_STREAK'),
        'school':        _ev('GFG_SCHOOL'),
        'basic':         _ev('GFG_BASIC'),
        'easy':          _ev('GFG_EASY'),
        'medium':        _ev('GFG_MEDIUM'),
        'hard':          _ev('GFG_HARD'),
        'fromEnv':       True,
    }


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
