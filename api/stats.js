// Vercel Serverless Function — /api/stats
// Fetches live coding-profile stats from 5 platforms server-side.
// Returns JSON with per-platform data + fetchedAt timestamp.
// Each platform is fetched in parallel with a 6-second timeout;
// on failure, its "source" field is "fallback" and hardcoded data is returned.

const USERNAMES = {
  leetcode:   'sayyadsameerm3',
  codeforces: 'sayyad_sameer',
  codechef:   'sayyadsameer',
  gfg:        'sayyadsameer',
  hackerrank: 'sayyadsameerm3',
};

// ── Hardcoded fallback (last verified values — Nov 2026) ────────────
const FALLBACK = {
  leetcode: {
    platform: 'LeetCode',
    url: 'https://leetcode.com/u/sayyadsameerm3/',
    total: 246, easy: 187, medium: 55, hard: 4,
    ranking: 673937, streak: 15, totalActiveDays: 85,
    activeBadge: '50 Days Badge',
    source: 'fallback',
  },
  codeforces: {
    platform: 'Codeforces',
    url: 'https://codeforces.com/profile/sayyad_sameer',
    rating: 880, maxRating: 880, rank: 'newbie', maxRank: 'newbie',
    solved: 21, contribution: 0,
    source: 'fallback',
  },
  codechef: {
    platform: 'CodeChef',
    url: 'https://www.codechef.com/users/sayyadsameer',
    rating: 1417, maxRating: 1428, stars: 2, globalRank: 3429, solved: 659,
    source: 'fallback',
  },
  gfg: {
    platform: 'GeeksForGeeks',
    url: 'https://www.geeksforgeeks.org/user/sayyadsameer/',
    solved: 115, score: 219, basic: 32, easy: 65, medium: 17, hard: 1, streak: 0,
    source: 'fallback',
  },
  hackerrank: {
    platform: 'HackerRank',
    url: 'https://www.hackerrank.com/profile/sayyadsameerm3',
    totalBadges: 6, totalStars: 21,
    badges: [
      { name: 'Problem Solving', stars: 4, solved: 36, category: 'Core Problem Solving' },
      { name: 'SQL',             stars: 4, solved: 40, category: 'Database Skills' },
      { name: 'C',               stars: 4, solved: 15, category: 'Language Proficiency' },
      { name: 'Python',          stars: 3, solved: 16, category: 'Language Proficiency' },
      { name: 'Java',            stars: 3, solved: 10, category: 'Language Proficiency' },
      { name: 'C++',             stars: 3, solved: 8,  category: 'Language Proficiency' },
    ],
    source: 'fallback',
  },
};

// ── Helpers ─────────────────────────────────────────────────────────
async function timedFetch(url, opts = {}, ms = 6000) {
  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(), ms);
  try {
    const res = await fetch(url, { ...opts, signal: ctrl.signal });
    clearTimeout(id);
    return res;
  } catch (err) {
    clearTimeout(id);
    throw err;
  }
}

function parseInt10(v) { return parseInt(v, 10) || 0; }

// ── Platform fetchers ───────────────────────────────────────────────

async function fetchLeetCode() {
  // LeetCode GraphQL (server-side — no CORS issue)
  const query = `query userProfile($username: String!) {
    matchedUser(username: $username) {
      submitStatsGlobal { acSubmissionNum { difficulty count } }
      profile { ranking }
      userCalendar { streak totalActiveDays }
      badges { name }
    }
  }`;
  const res = await timedFetch('https://leetcode.com/graphql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, variables: { username: USERNAMES.leetcode } }),
  });
  const json = await res.json();
  const user = json.data.matchedUser;
  const sub  = user.submitStatsGlobal.acSubmissionNum;
  const easy   = sub.find(s => s.difficulty === 'Easy')?.count   || 0;
  const medium = sub.find(s => s.difficulty === 'Medium')?.count || 0;
  const hard   = sub.find(s => s.difficulty === 'Hard')?.count   || 0;
  const total  = sub.find(s => s.difficulty === 'All')?.count    || (easy + medium + hard);
  const cal    = user.userCalendar || {};
  const badges = user.badges || [];
  const activeBadge = badges.length > 0 ? badges[badges.length - 1].name : null;

  return {
    platform: 'LeetCode',
    url: `https://leetcode.com/u/${USERNAMES.leetcode}/`,
    total, easy, medium, hard,
    ranking: user.profile.ranking || 0,
    streak: cal.streak || 0,
    totalActiveDays: cal.totalActiveDays || 0,
    activeBadge,
    source: 'live',
  };
}

async function fetchCodeforces() {
  // Official Codeforces API — fetch info only (rating, rank)
  // Solved count comes from user.status but can be unreliable for gym/virtual
  // contests, so we also try the simpler approach
  const infoRes = await timedFetch(
    `https://codeforces.com/api/user.info?handles=${USERNAMES.codeforces}`
  );
  const info = await infoRes.json();
  if (info.status !== 'OK') throw new Error('CF info failed');

  const u = info.result[0];

  // Fetch solved count from user.status (all submissions)
  let solvedCount = FALLBACK.codeforces.solved;
  try {
    const statusRes = await timedFetch(
      `https://codeforces.com/api/user.status?handle=${USERNAMES.codeforces}`
    );
    const status = await statusRes.json();
    if (status.status === 'OK') {
      const solved = new Set();
      for (const sub of status.result) {
        if (sub.verdict === 'OK' && sub.problem) {
          // Use problem name as key (more reliable than contestId which can be undefined for gym)
          const key = sub.problem.name;
          solved.add(key);
        }
      }
      if (solved.size > 0) solvedCount = solved.size;
    }
  } catch (_) { /* use fallback solved count */ }

  return {
    platform: 'Codeforces',
    url: `https://codeforces.com/profile/${USERNAMES.codeforces}`,
    rating: u.rating ?? 0,
    maxRating: u.maxRating ?? 0,
    rank: u.rank || 'unrated',
    maxRank: u.maxRank || 'unrated',
    solved: solvedCount,
    contribution: u.contribution || 0,
    source: 'live',
  };
}

async function fetchCodeChef() {
  // Scrape CodeChef profile page — patterns confirmed Nov 2026
  const res = await timedFetch(
    `https://www.codechef.com/users/${USERNAMES.codechef}`,
    { headers: { 'User-Agent': 'Mozilla/5.0 (compatible; PortfolioBot/1.0)' } },
  );
  const html = await res.text();

  // Rating: <div class="rating-number">\n  1417  \n</div>
  const ratingMatch = html.match(/class="rating-number">\s*(\d+)/);
  // Highest: (Highest Rating 1428)
  const maxMatch = html.match(/Highest Rating (\d+)/);
  // Stars: class="rating-star"> <span ...>&#9733;</span> (count ★ entities)
  const starsBlock = html.match(/rating-star">([\s\S]*?)<\/div/);
  const starCount = starsBlock ? (starsBlock[1].match(/&#9733;|★/g) || []).length : null;
  // Total Problems Solved: 659</h3>
  const solvedMatch = html.match(/Total Problems Solved:\s*(\d+)/);
  // Global Rank: <strong class='global-rank'>3429</strong>
  const rankMatch = html.match(/class='global-rank'>(\d+)/);

  const rating = ratingMatch ? parseInt10(ratingMatch[1]) : null;
  const maxRating = maxMatch ? parseInt10(maxMatch[1]) : rating;
  const solved = solvedMatch ? parseInt10(solvedMatch[1]) : null;
  const globalRank = rankMatch ? parseInt10(rankMatch[1]) : null;

  // If we got at least the rating, consider it successful
  if (rating == null && solved == null) throw new Error('CodeChef scrape empty');

  return {
    platform: 'CodeChef',
    url: `https://www.codechef.com/users/${USERNAMES.codechef}`,
    rating:     rating     ?? FALLBACK.codechef.rating,
    maxRating:  maxRating  ?? FALLBACK.codechef.maxRating,
    stars:      starCount  ?? FALLBACK.codechef.stars,
    globalRank: globalRank ?? FALLBACK.codechef.globalRank,
    solved:     solved     ?? FALLBACK.codechef.solved,
    source: 'live',
  };
}

async function fetchGFG() {
  // GFG embeds profile data as triple-escaped JSON in the HTML page
  // Keys appear as: \\\"total_problems_solved\\\":115
  const res = await timedFetch(
    `https://www.geeksforgeeks.org/user/${USERNAMES.gfg}/`,
    { headers: { 'User-Agent': 'Mozilla/5.0 (compatible; PortfolioBot/1.0)' } },
  );
  const html = await res.text();

  // Match keys surrounded by escaped quotes: \\\"key\\\":value
  const grab = (key) => {
    // Try triple-escaped pattern first (most common in GFG's SSR)
    const re1 = new RegExp(`${key}[\\\\]*"?\\s*:\\s*(\\d+)`);
    const m = html.match(re1);
    return m ? parseInt10(m[1]) : null;
  };

  const solved = grab('total_problems_solved');
  const score  = grab('"?score');
  const streak = grab('pod_solved_current_streak');
  const rank   = grab('institute_rank');

  if (solved == null) throw new Error('GFG scrape empty');

  return {
    platform: 'GeeksForGeeks',
    url: `https://www.geeksforgeeks.org/user/${USERNAMES.gfg}/`,
    solved,
    score:  score  ?? FALLBACK.gfg.score,
    basic:  FALLBACK.gfg.basic,   // difficulty breakdown not in embedded JSON
    easy:   FALLBACK.gfg.easy,
    medium: FALLBACK.gfg.medium,
    hard:   FALLBACK.gfg.hard,
    streak: streak ?? FALLBACK.gfg.streak,
    source: 'live',
  };
}

async function fetchHackerRank() {
  // HackerRank REST API for badges (works server-side)
  const res = await timedFetch(
    `https://www.hackerrank.com/rest/hackers/${USERNAMES.hackerrank}/badges`,
    { headers: { 'User-Agent': 'Mozilla/5.0 (compatible; PortfolioBot/1.0)' } },
  );
  const json = await res.json();
  const models = json.models || [];

  // Filter to only skill badges (have stars > 0), skip challenge badges
  const skillBadges = models.filter(b => (b.stars || 0) > 0);

  const badges = skillBadges.map(b => ({
    name:     b.badge_name || b.badge_type || 'Unknown',
    stars:    b.stars || 0,
    solved:   b.solved || b.challenges_solved || 0,
    category: b.categories ? b.categories.join(', ') : (b.domain || 'Language Proficiency'),
  }));

  const totalStars = badges.reduce((s, b) => s + b.stars, 0);

  return {
    platform: 'HackerRank',
    url: `https://www.hackerrank.com/profile/${USERNAMES.hackerrank}`,
    totalBadges: badges.length,
    totalStars,
    badges,
    source: 'live',
  };
}

// ── Main handler ────────────────────────────────────────────────────
module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Cache-Control', 's-maxage=3600, stale-while-revalidate=1800');

  if (req.method === 'OPTIONS') return res.status(204).end();

  const FETCHERS = [
    ['leetcode',   fetchLeetCode],
    ['codeforces', fetchCodeforces],
    ['codechef',   fetchCodeChef],
    ['gfg',        fetchGFG],
    ['hackerrank', fetchHackerRank],
  ];

  const results = await Promise.allSettled(FETCHERS.map(([, fn]) => fn()));

  const stats = {};
  const meta  = {};

  FETCHERS.forEach(([key], i) => {
    const r = results[i];
    if (r.status === 'fulfilled') {
      stats[key] = r.value;
      meta[key]  = 'live';
    } else {
      stats[key] = FALLBACK[key];
      meta[key]  = `fallback (${r.reason?.message || 'error'})`;
    }
  });

  return res.status(200).json({
    stats,
    meta,
    fetchedAt: new Date().toISOString(),
  });
};
