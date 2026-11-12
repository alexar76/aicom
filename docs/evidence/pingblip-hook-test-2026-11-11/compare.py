"""Compare the PingBlip hook test from local aggregate snapshots."""

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def instant(value):
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("Timestamps need an explicit timezone")
    return timestamp.astimezone(timezone.utc)


def funnel_counts(episode, release, metrics, snapshot):
    at = instant(snapshot["generatedAt"])
    target = release + timedelta(hours=metrics["funnelReadAgeHours"])
    if abs(at - target) > timedelta(minutes=metrics["funnelReadToleranceMinutes"]):
        raise ValueError(f"{episode} funnel snapshot falls outside the matched-age window")
    if instant(snapshot["since"]) > release:
        raise ValueError(f"{episode} funnel snapshot excludes the release date")
    tags = dict(metrics["funnelAttribution"], content=episode.lower())
    matching = [row for row in snapshot["groups"] if all(row.get(k) == v for k, v in tags.items())]
    if len(matching) > 1:
        raise ValueError(f"{episode} has duplicate attribution groups")
    if not matching:
        return dict.fromkeys(metrics["funnelOutcomes"], 0)
    counts = {key: matching[0][key] for key in metrics["funnelOutcomes"]}
    if any(type(n) is not int or n < 0 for n in counts.values()):
        raise ValueError(f"{episode} has invalid funnel counts")
    return counts


def studio_metrics(episode, release, zone, row):
    first = release.astimezone(zone).date()
    last = first + timedelta(days=6)
    if (row["startDate"], row["endDate"]) != (str(first), str(last)):
        raise ValueError(f"{episode} Studio data must cover {first} through {last}")
    stayed = row["stayedToWatchPercent"]
    if stayed is not None and (type(stayed) not in (int, float) or not 0 <= stayed <= 100):
        raise ValueError(f"{episode} has invalid Stayed to watch percentage")
    for key in ("shownInFeed", "engagedViews"):
        value = row[key]
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"{episode} has invalid {key}")
    return {key: row[key] for key in ("videoId", "stayedToWatchPercent", "shownInFeed", "engagedViews")}


def compare(plan, snapshot_directory, studio):
    metrics = plan["metrics"]
    zone = ZoneInfo(metrics["studioTimezone"])
    planned = plan["episodes"]
    ids = {episode["id"] for episode in planned}
    if len(ids) != len(planned) or ids != set(studio):
        raise ValueError("Provide exactly one Studio entry for each planned episode")
    video_ids = [row["videoId"] for row in studio.values()]
    if len(set(video_ids)) != len(video_ids) or any(not re.fullmatch(r"[\w-]{11}", key) for key in video_ids):
        raise ValueError("Studio data must identify distinct YouTube video IDs")

    slots = Counter()
    days = {}
    episodes = []
    stayed_by_slot = {}
    queue_end = instant(plan["queueEvidence"]["lastScheduledAt"])
    release_times = set()
    for item in planned:
        episode, variant = item["id"], item["variant"]
        if not re.fullmatch(r"PB[0-9]{2,4}", episode):
            raise ValueError(f"Invalid PingBlip episode ID: {episode}")
        release = instant(item["publishAt"])
        slot = release.strftime("%H:%M")
        if slot not in plan["cadence"]["slots"] or release.second or release.microsecond:
            raise ValueError(f"{episode} must use a native UTC slot")
        if release in release_times or release <= queue_end:
            raise ValueError(f"{episode} must occupy its own slot after the existing queue")
        release_times.add(release)
        slots[variant, slot] += 1
        snapshot = read_json(snapshot_directory / f"{episode.lower()}.funnel.json")
        analytics = studio_metrics(episode, release, zone, studio[episode])
        funnel = funnel_counts(episode, release, metrics, snapshot)
        stayed = analytics["stayedToWatchPercent"]
        days.setdefault(str(release.date()), []).append((variant, stayed))
        stayed_by_slot.setdefault((variant, slot), []).append(stayed)
        episodes.append(dict(item, studio=analytics, funnel=funnel))

    variants = ("weather_reveal", "first_feed")
    expected_slots = {(variant, slot) for variant in variants for slot in plan["cadence"]["slots"]}
    if set(slots) != expected_slots or len(set(slots.values())) != 1:
        raise ValueError("Each variant must have equal representation at both UTC slots")
    daily = {}
    for day, pair in sorted(days.items()):
        if len(pair) != 2 or set(dict(pair)) != set(variants):
            raise ValueError(f"{day} must have a matched pair")
        weather, feed = (dict(pair)[variant] for variant in variants)
        daily[day] = None if weather is None or feed is None else round(weather - feed, 4)

    counts = {
        variant: {key: sum(row["funnel"][key] for row in episodes if row["variant"] == variant)
                  for key in metrics["funnelOutcomes"]}
        for variant in variants
    }
    complete = all(value is not None for value in daily.values())
    slot_differences = {}
    for slot in plan["cadence"]["slots"]:
        weather, feed = (stayed_by_slot[variant, slot] for variant in variants)
        slot_differences[slot] = (
            None if None in weather + feed else round(mean(weather) - mean(feed), 4)
        )
    return {
        "episodes": episodes,
        "dailyStayedToWatchDifferencePercentagePointsWeatherMinusFeed": daily,
        "slotStayedToWatchDifferencePercentagePointsWeatherMinusFeed": slot_differences,
        "meanDifferencePercentagePoints": round(mean(daily.values()), 4) if complete else None,
        "attributedFunnelByVariant": counts,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("snapshot_directory", type=Path)
    parser.add_argument("studio", type=Path)
    args = parser.parse_args()
    result = compare(read_json(args.plan), args.snapshot_directory, read_json(args.studio))
    print(json.dumps(result, indent=2))
