"""A reply draft written by code from the draft input. Used by the offline provider and as the
fallback when the AI is unavailable, so a draft is always possible. It only restates facts."""

from app.ai.schemas import DraftOutput

QUESTION_TEXT = {
    "budget": "What budget do you have in mind?",
    "timeline": "When would you like this to be ready?",
    "phone": "What is the best phone number to reach you?",
    "company": "What is the name of your business?",
}
OPENERS = {
    "professional": "Thank you for contacting {org}.",
    "friendly": "Thanks so much for reaching out to {org}!",
    "concise": "Thanks for your message.",
    "sales": "Thanks for thinking of {org}. This is exactly the kind of project we love.",
}


def _money(minor: int | None, currency: str) -> str:
    return f"{currency} {minor / 100:,.0f}" if minor is not None else ""


def template_draft(data: dict) -> DraftOutput:
    org = data.get("business", {}).get("name", "our team")
    style = data.get("style", "professional")
    first = (data.get("customer", {}).get("first_name") or "").strip()
    services = data.get("services", [])
    facts = data.get("facts", {})
    lines = [f"Hi {first}," if first else "Hello,", ""]
    if data.get("kind") == "follow_up":
        topic = services[0]["name"].lower() if services else "your project"
        lines.append(f"I'm following up on your message about {topic}.")
        lines.append("If it would help, we're happy to answer any questions.")
        first_q = [
            QUESTION_TEXT.get(q, f"Could you share more about {q}?")
            for q in data.get("open_questions", [])
        ][:1]
        if first_q:
            lines += ["", first_q[0]]
        lines += [
            "",
            data.get("business", {}).get("response_time_line")
            or "We look forward to hearing from you.",
        ]
        return DraftOutput(
            subject=f"Following up: {services[0]['name']}" if services else "Following up",
            body="\n".join(lines),
            questions=first_q,
            services_mentioned=[services[0]["name"]] if services else [],
        )
    lines.append(OPENERS.get(style, OPENERS["professional"]).format(org=org))
    if services:
        s = services[0]
        rng = ""
        if s.get("price_min_minor") is not None and s.get("price_max_minor") is not None:
            cur = s.get("currency", "USD")
            rng = (
                f" Projects like this usually range from {_money(s['price_min_minor'], cur)}"
                f" to {_money(s['price_max_minor'], cur)}, depending on the details."
            )
        lines.append(f"We'd be glad to help with {s['name'].lower()}.{rng}")
    need = facts.get("requirements") or []
    if need and style != "concise":
        lines.append(f"You mentioned: {need[0]}. That is something we can plan for.")
    questions = [
        QUESTION_TEXT.get(q, f"Could you share more about {q}?")
        for q in data.get("open_questions", [])
    ][:3]
    if questions:
        lines += ["", "To prepare an accurate proposal, could you tell us:"]
        lines += [f"- {q}" for q in questions]
    lines += [
        "",
        data.get("business", {}).get("response_time_line")
        or "We look forward to hearing from you.",
    ]
    subject = (
        f"Re: {services[0]['name']} for your business"
        if services
        else f"Thanks for contacting {org}"
    )
    return DraftOutput(
        subject=subject[:80],
        body="\n".join(lines),
        questions=questions,
        services_mentioned=[services[0]["name"]] if services else [],
    )
