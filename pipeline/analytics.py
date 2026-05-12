"""
Analytics module.
Tracks video performance metrics and provides insights.
Identifies what's working and what's not to optimize production.
"""
import json
import os
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


async def calculate_video_stats(db) -> dict:
    """Calculate comprehensive production statistics."""
    total = await db.execute_fetchall("SELECT COUNT(*) as c FROM videos")
    done = await db.execute_fetchall("SELECT COUNT(*) as c FROM videos WHERE status = 'done'")
    errors = await db.execute_fetchall("SELECT COUNT(*) as c FROM videos WHERE status = 'error'")
    drafts = await db.execute_fetchall("SELECT COUNT(*) as c FROM videos WHERE status = 'draft'")

    total_cost = await db.execute_fetchall(
        "SELECT COALESCE(SUM(cost_usd), 0) as c FROM production_log"
    )

    # Videos per character
    chars = await db.execute_fetchall(
        """SELECT c.name, COUNT(v.id) as video_count
           FROM characters c LEFT JOIN videos v ON c.id = v.character_id
           GROUP BY c.id ORDER BY video_count DESC"""
    )

    # Videos per language
    langs = await db.execute_fetchall(
        """SELECT language, COUNT(*) as c FROM videos
           GROUP BY language ORDER BY c DESC"""
    )

    # Production time stats
    prod_times = await db.execute_fetchall(
        """SELECT v.id,
                  MIN(pl.started_at) as start_time,
                  MAX(pl.finished_at) as end_time
           FROM videos v
           JOIN production_log pl ON v.id = pl.video_id
           WHERE v.status = 'done'
           GROUP BY v.id"""
    )

    avg_production_secs = 0
    if prod_times:
        durations = []
        for pt in prod_times:
            if pt["start_time"] and pt["end_time"]:
                try:
                    start = datetime.fromisoformat(pt["start_time"])
                    end = datetime.fromisoformat(pt["end_time"])
                    durations.append((end - start).total_seconds())
                except (ValueError, TypeError):
                    pass
        if durations:
            avg_production_secs = sum(durations) / len(durations)

    # Recent videos with details
    recent = await db.execute_fetchall(
        """SELECT v.id, v.title, v.status, v.language, v.created_at,
                  v.output_path, c.name as character_name
           FROM videos v JOIN characters c ON v.character_id = c.id
           ORDER BY v.created_at DESC LIMIT 10"""
    )

    # Cost breakdown
    cost_by_step = await db.execute_fetchall(
        """SELECT step, SUM(cost_usd) as total_cost, COUNT(*) as count
           FROM production_log WHERE cost_usd > 0
           GROUP BY step ORDER BY total_cost DESC"""
    )

    # Success rate
    total_attempts = total[0]["c"]
    success_rate = (done[0]["c"] / max(total_attempts, 1)) * 100

    return {
        "overview": {
            "total_videos": total[0]["c"],
            "completed": done[0]["c"],
            "errors": errors[0]["c"],
            "drafts": drafts[0]["c"],
            "success_rate": round(success_rate, 1),
            "total_cost_usd": round(float(total_cost[0]["c"]), 2),
            "avg_production_seconds": round(avg_production_secs, 1),
        },
        "by_character": [dict(c) for c in chars],
        "by_language": [dict(l) for l in langs],
        "cost_breakdown": [dict(c) for c in cost_by_step],
        "recent_videos": [dict(r) for r in recent],
    }


async def get_production_insights(db) -> dict:
    """
    Surface concrete patterns the scriptwriter should learn from.

    Returns a dict suitable for injection into the script-generation prompt
    as a "what's working / what's failing" context section.

    Pulled from production data only (no view/retention data — that requires
    YouTube API). The signal here is what successfully produces vs. fails:
    which characters, topics, languages, durations, and scene counts.
    """
    insights = {
        "best_characters": [],
        "best_topics": [],
        "best_durations": [],
        "scene_count_sweet_spot": None,
        "common_failures": [],
        "narration_length_by_success": {},
    }

    # Which characters complete successfully most often?
    char_rows = await db.execute_fetchall(
        """SELECT c.name,
                  SUM(CASE WHEN v.status = 'done' THEN 1 ELSE 0 END) as done,
                  SUM(CASE WHEN v.status = 'error' THEN 1 ELSE 0 END) as errors,
                  COUNT(v.id) as total
           FROM characters c LEFT JOIN videos v ON c.id = v.character_id
           GROUP BY c.id HAVING total > 0
           ORDER BY done DESC LIMIT 5"""
    )
    for r in char_rows:
        d = dict(r)
        if d["total"]:
            d["success_rate"] = round(100 * d["done"] / d["total"], 1)
            insights["best_characters"].append(d)

    # Most successful topic substrings (rough — looks for first ~4 keywords)
    topic_rows = await db.execute_fetchall(
        """SELECT topic, status FROM videos
           WHERE topic IS NOT NULL AND topic != ''"""
    )
    topic_score = {}
    for r in topic_rows:
        topic = (r["topic"] or "").lower()
        # Extract a coarse keyword
        for word in topic.split():
            if len(word) < 5:
                continue
            score = topic_score.setdefault(word, {"done": 0, "total": 0})
            score["total"] += 1
            if r["status"] == "done":
                score["done"] += 1
    top_keywords = sorted(
        [(k, v) for k, v in topic_score.items() if v["total"] >= 2],
        key=lambda x: x[1]["done"], reverse=True
    )[:5]
    insights["best_topics"] = [
        {"keyword": k, "done": v["done"], "total": v["total"]}
        for k, v in top_keywords
    ]

    # Duration sweet spot — group successful videos by 15s buckets
    dur_rows = await db.execute_fetchall(
        """SELECT duration_target FROM videos WHERE status = 'done'
           AND duration_target IS NOT NULL"""
    )
    if dur_rows:
        buckets = {}
        for r in dur_rows:
            b = (r["duration_target"] // 15) * 15
            buckets[b] = buckets.get(b, 0) + 1
        best_bucket = max(buckets.items(), key=lambda x: x[1])
        insights["best_durations"] = [
            {"duration_seconds": k, "count": v}
            for k, v in sorted(buckets.items(), key=lambda x: x[1], reverse=True)
        ]
        insights["scene_count_sweet_spot"] = best_bucket[0] // 10

    # Common failure points — which step fails most?
    fail_rows = await db.execute_fetchall(
        """SELECT step, COUNT(*) as fails
           FROM production_log
           WHERE error IS NOT NULL AND error != ''
           GROUP BY step ORDER BY fails DESC LIMIT 3"""
    )
    insights["common_failures"] = [dict(r) for r in fail_rows]

    return insights


def format_insights_for_prompt(insights: dict) -> str:
    """Render insights as a natural-language block the LLM can use as context."""
    if not insights:
        return ""

    lines = []

    if insights.get("best_durations"):
        sweet = insights["best_durations"][0]
        lines.append(
            f"- Production data shows {sweet['duration_seconds']}-second videos "
            f"complete most reliably in this system ({sweet['count']} successes). "
            f"Stick close to this length."
        )

    if insights.get("best_characters"):
        top = insights["best_characters"][0]
        if top.get("success_rate", 0) >= 75 and top.get("total", 0) >= 3:
            lines.append(
                f"- Character '{top['name']}' has the highest completion rate "
                f"({top['success_rate']}%). Lean into their voice and tone."
            )

    if insights.get("best_topics"):
        keywords = [t["keyword"] for t in insights["best_topics"][:3]]
        if keywords:
            lines.append(
                f"- Topics involving these keywords have worked: {', '.join(keywords)}. "
                f"Audiences in this niche respond to these themes."
            )

    if insights.get("common_failures"):
        steps = [f"{f['step']} ({f['fails']}x)" for f in insights["common_failures"]]
        lines.append(
            f"- Recent failures clustered around: {', '.join(steps)}. "
            f"Keep scripts simple and well-structured to avoid these."
        )

    if not lines:
        return ""

    return "PRODUCTION INSIGHTS FROM YOUR PAST VIDEOS:\n" + "\n".join(lines) + "\n"


def get_content_recommendations(stats: dict) -> list:
    """Generate actionable recommendations based on production data."""
    recs = []

    overview = stats.get("overview", {})

    if overview.get("total_videos", 0) == 0:
        recs.append({
            "type": "action",
            "priority": "high",
            "message": "Produce your first video! Go to Trends to find viral ideas, then produce with Old Emilio.",
        })
        return recs

    if overview.get("success_rate", 0) < 80:
        recs.append({
            "type": "warning",
            "priority": "high",
            "message": f"Success rate is {overview['success_rate']}%. Check error logs for failing videos.",
        })

    if overview.get("completed", 0) < 3:
        recs.append({
            "type": "action",
            "priority": "high",
            "message": "Produce at least 3-5 videos before judging results. Algorithms need content to learn your audience.",
        })

    if overview.get("total_cost_usd", 0) > 50:
        recs.append({
            "type": "info",
            "priority": "medium",
            "message": f"You've spent ${overview['total_cost_usd']:.2f}. Consider using Ollama for free script generation to reduce costs.",
        })

    # Check character diversity
    by_char = stats.get("by_character", [])
    if len(by_char) == 1:
        recs.append({
            "type": "action",
            "priority": "medium",
            "message": "Try creating a second character to diversify content and test which persona gets more engagement.",
        })

    return recs
