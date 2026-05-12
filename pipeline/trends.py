"""
Advanced trend detection for horror/mystery content creators.
Scrapes REAL viral data from multiple sources — no generic garbage.

Sources:
- Reddit (multiple horror subreddits, sorted by virality score)
- YouTube Data API v3 (viral horror videos with view/like counts)
- Google Trends via pytrends (rising horror-related queries)
- Creepypasta.com (popular stories)
- 4chan /x/ (paranormal threads with high engagement)

All sources work without paid APIs (YouTube needs a free key).
"""
import httpx
import json
import re
import os
from datetime import datetime, timedelta

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")

# Horror subreddits ranked by content quality for video adaptation
HORROR_SUBREDDITS = [
    "nosleep",              # Long horror stories (best for 60-90s videos)
    "shortscarystories",    # Ultra-short stories (perfect for 30s videos)
    "creepypasta",          # Classic horror tales
    "LetsNotMeet",          # True scary encounters
    "TrueScaryStories",     # Real experiences
    "Thetruthishere",       # Paranormal experiences
    "scarystories",         # Scary stories community
]

# YouTube search queries for horror niche
YOUTUBE_HORROR_QUERIES = [
    "horror story narration",
    "true scary stories",
    "creepypasta animated",
    "scary story that actually happened",
    "mystery unsolved case",
    "paranormal caught on camera",
]


def _load_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# =============================================================
# REDDIT — Multiple horror subs, sorted by virality
# =============================================================

async def get_reddit_viral(subreddits: list = None, timeframe: str = "week",
                           limit: int = 50, min_score: int = 50) -> list:
    """
    Get top viral horror posts from multiple subreddits.
    Uses TOP sort (not hot) to get proven viral content.
    Calculates virality score = upvotes × upvote_ratio.
    """
    subs = subreddits or HORROR_SUBREDDITS
    combined = "+".join(subs[:8])  # Reddit supports multi-sub queries

    url = f"https://old.reddit.com/r/{combined}/top.json"
    params = {"limit": min(limit, 100), "t": timeframe}
    headers = {"User-Agent": "VideoFactory/2.0 (horror content research tool)"}

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code != 200:
                return []
            data = response.json()
    except Exception as e:
        return [{"error": str(e), "source": "reddit"}]

    results = []
    for post in data.get("data", {}).get("children", []):
        d = post.get("data", {})
        if d.get("stickied"):
            continue

        score = d.get("score", 0)
        if score < min_score:
            continue

        ratio = d.get("upvote_ratio", 0.5)
        virality = int(score * ratio)
        comments = d.get("num_comments", 0)

        # Estimate video potential: high score + high ratio + good comment engagement
        engagement_rate = comments / max(score, 1)
        video_potential = "high" if (virality > 500 and engagement_rate > 0.1) else \
                         "medium" if virality > 100 else "low"

        # Get story length hint from selftext
        selftext = d.get("selftext", "")
        word_count = len(selftext.split()) if selftext else 0
        duration_hint = "30s" if word_count < 200 else "60s" if word_count < 500 else "90s"

        created = datetime.utcfromtimestamp(d.get("created_utc", 0))
        age_hours = (datetime.utcnow() - created).total_seconds() / 3600

        results.append({
            "title": d.get("title", ""),
            "score": score,
            "comments": comments,
            "ratio": round(ratio, 2),
            "virality": virality,
            "video_potential": video_potential,
            "duration_hint": duration_hint,
            "subreddit": d.get("subreddit", ""),
            "url": f"https://reddit.com{d.get('permalink', '')}",
            "age_hours": round(age_hours, 1),
            "source": "reddit",
        })

    results.sort(key=lambda x: x["virality"], reverse=True)
    return results


# =============================================================
# YOUTUBE — Find viral horror videos with real view counts
# =============================================================

async def get_youtube_viral_horror(days_back: int = 7, max_results: int = 20) -> list:
    """
    Search YouTube for viral horror content using Data API v3.
    Requires free API key (10,000 units/day free).
    Returns videos with actual view counts and engagement data.
    """
    settings = _load_settings()
    api_key = settings.get("youtube_api_key", "")

    if not api_key:
        # Fallback: scrape YouTube search results page (no API key)
        return await _youtube_search_fallback()

    published_after = (datetime.utcnow() - timedelta(days=days_back)).isoformat() + "Z"
    all_videos = []

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            for query in YOUTUBE_HORROR_QUERIES[:3]:  # Limit to save quota
                # Search for videos
                search_resp = await client.get(
                    "https://www.googleapis.com/youtube/v3/search",
                    params={
                        "q": query,
                        "type": "video",
                        "order": "viewCount",
                        "publishedAfter": published_after,
                        "videoDuration": "medium",
                        "maxResults": max_results,
                        "part": "snippet",
                        "relevanceLanguage": "en",
                        "key": api_key,
                    },
                )

                if search_resp.status_code != 200:
                    continue

                items = search_resp.json().get("items", [])
                video_ids = [item["id"]["videoId"] for item in items if "videoId" in item.get("id", {})]

                if not video_ids:
                    continue

                # Get statistics for these videos
                stats_resp = await client.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={
                        "part": "statistics",
                        "id": ",".join(video_ids),
                        "key": api_key,
                    },
                )

                stats_map = {}
                if stats_resp.status_code == 200:
                    for v in stats_resp.json().get("items", []):
                        stats_map[v["id"]] = v.get("statistics", {})

                for item in items:
                    vid = item.get("id", {}).get("videoId", "")
                    if not vid:
                        continue
                    s = stats_map.get(vid, {})
                    views = int(s.get("viewCount", 0))
                    likes = int(s.get("likeCount", 0))

                    if views < 1000:
                        continue

                    # Calculate engagement rate
                    engagement = (likes / max(views, 1)) * 100

                    all_videos.append({
                        "title": item["snippet"]["title"],
                        "channel": item["snippet"]["channelTitle"],
                        "views": views,
                        "likes": likes,
                        "comments": int(s.get("commentCount", 0)),
                        "engagement_pct": round(engagement, 2),
                        "video_url": f"https://youtube.com/watch?v={vid}",
                        "published": item["snippet"]["publishedAt"][:10],
                        "query": query,
                        "source": "youtube",
                    })

    except Exception as e:
        return [{"error": str(e), "source": "youtube"}]

    all_videos.sort(key=lambda x: x["views"], reverse=True)
    return all_videos[:30]


async def _youtube_search_fallback() -> list:
    """
    Fallback YouTube search without API key.
    Scrapes YouTube search results for horror content.
    Less data but works without any key.
    """
    queries = ["horror story narration", "true scary stories short"]
    results = []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for query in queries:
                resp = await client.get(
                    f"https://www.youtube.com/results",
                    params={"search_query": query, "sp": "CAMSAhAB"},  # Sort by view count, this week
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                             "Accept-Language": "en-US,en;q=0.9"},
                )

                if resp.status_code != 200:
                    continue

                # Extract video data from YouTube's initial data JSON
                matches = re.findall(r'"title":\{"runs":\[\{"text":"([^"]{10,100})"\}', resp.text)
                view_matches = re.findall(r'"viewCountText":\{"simpleText":"([^"]+)"\}', resp.text)
                vid_matches = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)

                seen = set()
                for i, title in enumerate(matches[:10]):
                    clean_title = title.replace("\\u0026", "&").replace("\\u0027", "'")
                    if clean_title in seen:
                        continue
                    seen.add(clean_title)

                    views_text = view_matches[i] if i < len(view_matches) else "N/A"
                    vid_id = vid_matches[i] if i < len(vid_matches) else ""

                    results.append({
                        "title": clean_title,
                        "views_text": views_text,
                        "video_url": f"https://youtube.com/watch?v={vid_id}" if vid_id else "",
                        "query": query,
                        "source": "youtube_search",
                    })

    except Exception as e:
        results.append({"error": str(e), "source": "youtube_search"})

    return results


# =============================================================
# GOOGLE TRENDS — Horror-specific rising queries
# =============================================================

async def get_horror_rising_trends() -> list:
    """
    Get rising horror-related search queries from Google Trends.
    Uses Google Trends autocomplete (free, no key needed).
    """
    seed_queries = [
        "creepypasta", "horror story", "scary story true",
        "paranormal activity real", "urban legend", "nosleep",
        "true crime mystery", "haunted house real",
    ]

    results = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for seed in seed_queries:
                # Google Trends autocomplete API (free, public)
                resp = await client.get(
                    "https://trends.google.com/trends/api/autocomplete/" + seed.replace(" ", "%20"),
                    headers={
                        "User-Agent": "Mozilla/5.0",
                    },
                )

                if resp.status_code != 200:
                    continue

                # Response has a ")]}'" prefix that needs to be stripped
                text = resp.text
                if text.startswith(")]}'"):
                    text = text[5:]

                try:
                    data = json.loads(text)
                    topics = data.get("default", {}).get("topics", [])
                    for topic in topics:
                        title = topic.get("title", "")
                        topic_type = topic.get("type", "")
                        if title and title.lower() != seed.lower():
                            results.append({
                                "title": title,
                                "type": topic_type,
                                "seed": seed,
                                "source": "google_trends",
                            })
                except json.JSONDecodeError:
                    continue

    except Exception as e:
        results.append({"error": str(e), "source": "google_trends"})

    # Deduplicate by title
    seen = set()
    unique = []
    for r in results:
        if r.get("title", "").lower() not in seen:
            seen.add(r.get("title", "").lower())
            unique.append(r)

    return unique


# =============================================================
# CREEPYPASTA.COM — Popular stories
# =============================================================

async def get_creepypasta_popular() -> list:
    """Scrape popular creepypasta stories (no API needed)."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://www.creepypasta.com/popular-creepypastas/",
                headers={"User-Agent": "Mozilla/5.0"},
            )

            if resp.status_code != 200:
                return []

            # Extract story titles and links from HTML
            links = re.findall(
                r'<a[^>]+href="(https://www\.creepypasta\.com/[^"]+)"[^>]*>([^<]+)</a>',
                resp.text,
            )

            seen = set()
            for url, title in links:
                clean = title.strip()
                if (clean and len(clean) > 5 and clean not in seen
                        and "creepypasta" not in clean.lower()
                        and "category" not in url and "tag" not in url
                        and "page" not in url):
                    seen.add(clean)
                    results.append({
                        "title": clean,
                        "url": url,
                        "source": "creepypasta",
                    })

    except Exception as e:
        results.append({"error": str(e), "source": "creepypasta"})

    return results[:20]


# =============================================================
# 4CHAN /x/ — Paranormal board (free public JSON API)
# =============================================================

async def get_4chan_paranormal(min_replies: int = 10) -> list:
    """
    Get high-engagement threads from 4chan's /x/ (paranormal) board.
    Free public API, no auth needed. Great for obscure horror ideas.
    """
    results = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://a.4cdn.org/x/catalog.json",
                headers={"User-Agent": "VideoFactory/2.0"},
            )

            if resp.status_code != 200:
                return []

            pages = resp.json()
            for page in pages:
                for thread in page.get("threads", []):
                    replies = thread.get("replies", 0)
                    if replies < min_replies:
                        continue

                    subject = thread.get("sub", "")
                    comment = thread.get("com", "")

                    # Clean HTML from comment
                    if not subject and comment:
                        subject = re.sub(r"<[^>]+>", "", comment)[:100]

                    if not subject:
                        continue

                    # Clean HTML entities
                    subject = subject.replace("&#039;", "'").replace("&amp;", "&").replace("&quot;", '"')

                    results.append({
                        "title": subject,
                        "replies": replies,
                        "images": thread.get("images", 0),
                        "thread_url": f"https://boards.4chan.org/x/thread/{thread.get('no', '')}",
                        "source": "4chan_x",
                    })

    except Exception as e:
        results.append({"error": str(e), "source": "4chan_x"})

    results.sort(key=lambda x: x.get("replies", 0), reverse=True)
    return results[:15]


# =============================================================
# AGGREGATOR — All sources combined with ranking
# =============================================================

async def get_all_trends(region: str = "US", niche: str = "horror") -> dict:
    """
    Aggregate trends from ALL sources.
    Returns categorized, ranked results ready for the UI.
    """
    reddit = await get_reddit_viral(
        subreddits=HORROR_SUBREDDITS,
        timeframe="week",
        min_score=50,
    )

    youtube = await get_youtube_viral_horror(days_back=7)
    google = await get_horror_rising_trends()
    creepypasta = await get_creepypasta_popular()
    chan = await get_4chan_paranormal(min_replies=10)

    # Filter out errors
    reddit = [r for r in reddit if "error" not in r]
    youtube = [r for r in youtube if "error" not in r]
    google = [r for r in google if "error" not in r]

    return {
        "reddit": reddit[:20],
        "youtube": youtube[:15],
        "google_trends": google[:15],
        "creepypasta": creepypasta[:10],
        "chan_x": chan[:10],
        "fetched_at": datetime.utcnow().isoformat(),
        "region": region,
        "niche": niche,
        "total_ideas": len(reddit) + len(youtube) + len(google) + len(creepypasta) + len(chan),
    }
