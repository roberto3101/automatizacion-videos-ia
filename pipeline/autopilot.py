"""
Autopilot module — Industrial automation loop.
Detect trends → Generate scripts → Produce videos → Schedule publishing → Measure results.
Runs as a background process that produces content automatically.
"""
import asyncio
import json
import os
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
AUTOPILOT_LOG = os.path.join(DATA_DIR, "autopilot_log.json")


class AutopilotState:
    """Track autopilot state."""

    def __init__(self):
        self.running = False
        self.current_step = ""
        self.log = []
        self.produced_count = 0
        self.errors = []

    def to_dict(self):
        return {
            "running": self.running,
            "current_step": self.current_step,
            "log": self.log[-20:],  # Last 20 entries
            "produced_count": self.produced_count,
            "errors": self.errors[-5:],
        }

    def add_log(self, message: str):
        entry = {"time": datetime.utcnow().isoformat(), "message": message}
        self.log.append(entry)
        self._save()

    def _save(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        try:
            with open(AUTOPILOT_LOG, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
        except Exception:
            pass


# Global state
autopilot = AutopilotState()


async def run_autopilot_cycle(db, settings: dict, character_id: int,
                               produce_func, trend_func) -> dict:
    """
    Run ONE cycle of the autopilot loop:
    1. Scan trends for best viral idea
    2. Generate script from top trend
    3. Produce video
    4. Prepare for publishing

    Returns the result of this cycle.
    """
    autopilot.running = True
    result = {"status": "started", "steps": []}

    try:
        # Step 1: Find best trend
        autopilot.current_step = "scanning_trends"
        autopilot.add_log("Scanning trends for viral ideas...")

        trends = await trend_func()
        reddit_trends = trends.get("reddit", [])

        if not reddit_trends:
            autopilot.add_log("No trends found. Skipping cycle.")
            result["status"] = "no_trends"
            return result

        # Pick top trending topic that hasn't been used recently
        used_topics = await _get_recent_topics(db)
        best_topic = None
        for trend in reddit_trends:
            title = trend.get("title", "")
            if title and title not in used_topics:
                best_topic = trend
                break

        if not best_topic:
            best_topic = reddit_trends[0]

        topic = best_topic["title"]
        autopilot.add_log(f"Selected topic: {topic} (score: {best_topic.get('score', 0)})")
        result["steps"].append({"step": "trend_selected", "topic": topic})

        # Step 2: The script should be generated via the produce_func
        autopilot.current_step = "producing"
        autopilot.add_log(f"Starting production for: {topic}")

        # Return the topic for the server to handle production
        result["topic"] = topic
        result["character_id"] = character_id
        result["trend_data"] = best_topic
        result["status"] = "topic_ready"

        autopilot.produced_count += 1
        autopilot.add_log(f"Cycle complete. Total produced: {autopilot.produced_count}")

    except Exception as e:
        autopilot.errors.append(str(e))
        autopilot.add_log(f"Error: {str(e)}")
        result["status"] = "error"
        result["error"] = str(e)

    finally:
        autopilot.running = False
        autopilot.current_step = ""

    return result


async def _get_recent_topics(db, limit: int = 50) -> set:
    """Get recently used topics to avoid repetition."""
    rows = await db.execute_fetchall(
        "SELECT topic FROM videos ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    return {r["topic"] for r in rows if r["topic"]}


def get_autopilot_status() -> dict:
    """Get current autopilot state."""
    return autopilot.to_dict()
