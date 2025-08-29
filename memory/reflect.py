import json
from datetime import datetime, timezone
from transformers import pipeline

MEM_FILE = "memory/memory.json"
SCORE_FILE = "memory/score.json"

summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-12-6")

def reflect_and_score():
    with open(MEM_FILE, "r") as f:
        mem = json.load(f)

    summary = summarizer(" ".join([m["command"] + ": " + m["output"] for m in mem[-10:]]), max_length=100, min_length=30, do_sample=False)[0]["summary_text"]

    score_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "score": {
            "success_rate": estimate_success(mem),
            "mutation_bias": suggest_mutation(summary)
        }
    }

    with open(SCORE_FILE, "a") as f:
        f.write(json.dumps(score_entry) + "\n")

    return score_entry

def estimate_success(mem):
    successes = [m for m in mem if "error" not in m["output"].lower()]
    return round(len(successes) / len(mem), 2) if mem else 0

def suggest_mutation(summary):
    if "failed" in summary or "error" in summary:
        return "explore alternative strategies"
    elif "successfully" in summary:
        return "reinforce current behavior"
    else:
        return "neutral"
