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
    solved: 42, contribution: 0,
    source: 'fallback',
  },
  codechef: {
    platform: 'CodeChef',
    url: 'https://www.codechef.com/users/sayyadsameer',
    rating: 1409, maxRating: 1409, stars: 2, globalRank: 4127, solved: 659,
    source: 'fallback',
  },
  gfg: {
    platform: 'GeeksForGeeks',
    url: 'https://www.geeksforgeeks.org/user/sayyadsameer/',
    solved: 115, score: 115, basic: 32, easy: 65, medium: 17, hard: 1, streak: 5,
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
  // Official Codeforces API
  const [infoRes, statusRes] = await Promise.all([
    timedFetch(`https://codeforces.com/api/user.info?handles=${USERNAMES.codeforces}`),
    timedFetch(`https://codeforces.com/api/user.status?handle=${USERNAMES.codeforces}&from=1&count=10000`),
  ]);
  const info = await infoRes.json();
  const status = await statusRes.json();

  const u = info.result[0];
  // Count unique accepted problems
  const solved = new Set();
  if (status.status === 'OK') {
    for (const sub of status.result) {
      if (sub.verdict === 'OK') {
        solved.add(`${sub.problem.contestId}-${sub.problem.index}`);
      }
    }
  }

  return {
    platform: 'Codeforces',
    url: `https://codeforces.com/profile/${USERNAMES.codeforces}`,
    rating: u.rating ?? 0,
    maxRating: u.maxRating ?? 0,
    rank: u.rank || 'unrated',
    maxRank: u.maxRank || 'unrated',
    solved: solved.size || FALLBACK.codeforces.solved,
    contribution: u.contribution || 0,
    source: 'live',
  };
}

async function fetchCodeChef() {
  // Scrape CodeChef profile page for key metrics
  const res = await timedFetch(
    `https://www.codechef.com/users/${USERNAMES.codechef}`,
    { headers: { 'User-Agent': 'Mozilla/5.0 (compatible; PortfolioBot/1.0)' } },
  );
  const html = await res.text();

  const ratingMatch   = html.match(/class="rating-number"[^>]*>(\d+)/);
  const starsMatch    = html.match(/class="rating-star"[^>]*>\s*(★+)/);
  const solvedMatch   = html.match(/Total Problems Solved:\s*<[^>]*>(\d+)/i)
                     || html.match(/problems-solved[^>]*>[\s\S]*?<h3[^>]*>(\d+)/);
  const maxMatch      = html.match(/Highest Rating[^:]*:\s*<[^>]*>(\d+)/i);
  const rankMatch     = html.match(/Global Rank[^:]*:\s*<[^>]*>(\d+)/i);

  const rating   = ratingMatch ? parseInt(ratingMatch[1], 10) : null;
  const maxRating = maxMatch   ? parseInt(maxMatch[1], 10)    : rating;
  const starCount = starsMatch ? starsMatch[1].length         : null;
  const solved   = solvedMatch ? parseInt(solvedMatch[1], 10) : null;
  const globalRank = rankMatch ? parseInt(rankMatch[1], 10)   : null;

  // If scraping yielded nothing useful, throw so fallback kicks in
  if (rating == null && solved == null) throw new Error('CodeChef scrape empty');

  return {
    platform: 'CodeChef',
    url: `https://www.codechef.com/users/${USERNAMES.codechef}`,
    rating:    rating    ?? FALLBACK.codechef.rating,
    maxRating: maxRating ?? FALLBACK.codechef.maxRating,
    stars:     starCount ?? FALLBACK.codechef.stars,
    globalRank: globalRank ?? FALLBACK.codechef.globalRank,
    solved:    solved    ?? FALLBACK.codechef.solved,
    source: 'live',
  };
}

async function fetchGFG() {
  // GFG practice-api profile endpoint
  const res = await timedFetch(
    `https://www.geeksforgeeks.org/api/profilePage/?username=${USERNAMES.gfg}`,
    { headers: { 'User-Agent': 'Mozilla/5.0 (compatible; PortfolioBot/1.0)' } },
  );
  const json = await res.json();

  // Profile data lives at different nesting levels depending on GFG's API version
  const info = json.profile_data || json;
  const solveData = json.solvedStats || json.solved_stats || {};

  // Parse difficulty counts from the nested structure
  let basic = 0, easy = 0, medium = 0, hard = 0;
  if (solveData.SCHOOL)  basic  = solveData.SCHOOL.count  || 0;
  if (solveData.BASIC)   basic += solveData.BASIC.count   || 0;
  if (solveData.EASY)    easy   = solveData.EASY.count    || 0;
  if (solveData.MEDIUM)  medium = solveData.MEDIUM.count  || 0;
  if (solveData.HARD)    hard   = solveData.HARD.count    || 0;

  const solved = (info.total_problems_solved != null)
    ? parseInt(info.total_problems_solved, 10)
    : (basic + easy + medium + hard) || FALLBACK.gfg.solved;
  const score  = parseInt(info.coding_score || info.overall_coding_score || 0, 10) || solved;
  const streak = parseInt(info.current_streak || info.max_streak || 0, 10);

  return {
    platform: 'GeeksForGeeks',
    url: `https://www.geeksforgeeks.org/user/${USERNAMES.gfg}/`,
    solved, score, basic, easy, medium, hard, streak,
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

  const badges = models.map(b => ({
    name:     b.badge_name || b.badge_type || 'Unknown',
    stars:    b.stars || b.current_points || 0,
    solved:   b.solved || b.challenges_solved || 0,
    category: b.categories ? b.categories.join(', ') : (b.domain || ''),
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
