"""One real outbound integration: synthetic review tasks in this GitHub repository."""

import hashlib
import json
import re
import urllib.error
import urllib.request


class GitHubQueue:
    def __init__(self, repository, token):
        if (
            not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository or "")
            or not token
        ):
            raise ValueError("A repository and repository-scoped token are required.")
        self.repository = repository
        self.token = token

    def _request(self, method, path, payload=None):
        request = urllib.request.Request(
            "https://api.github.com/repos/" + self.repository + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "returnops",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read(1048577)
            if len(raw) > 1048576:
                raise ValueError("Oversized API response.")
            return json.loads(raw)
        except urllib.error.HTTPError as error:
            raise RuntimeError(
                "GitHub returned HTTP "
                + str(error.code)
                + ". Review task not confirmed."
            ) from None
        except (urllib.error.URLError, TimeoutError, ValueError):
            # Do not blindly retry POST: a timeout may occur after GitHub accepted it.
            raise RuntimeError(
                "GitHub outcome unknown. Rerun the serialized demo "
                "to search for an existing task first."
            ) from None

    def publish_review(self, result):
        if result["route"] != "human_review":
            return {
                "status": "not_required",
                "reason": "A response draft exists; no review task needed.",
            }
        ticket = result["ticket"]
        if not ticket["sender_email"].endswith("@example.com") or not re.fullmatch(
            r"DEMO-\d{3}", ticket["ticket_id"]
        ):
            raise ValueError(
                "GitHub publication accepts only the supplied fictional DEMO tickets."
            )
        digest = hashlib.sha256(json.dumps(ticket, sort_keys=True).encode()).hexdigest()
        marker = "<!-- returnops:" + result["mode"] + ":" + ticket["ticket_id"] + " -->"
        payload_marker = "<!-- payload-sha256:" + digest + " -->"
        for page in range(1, 11):
            issues = self._request(
                "GET", "/issues?state=all&per_page=100&page=" + str(page)
            )
            if not isinstance(issues, list):
                raise RuntimeError("Invalid GitHub response.")
            for issue in issues:
                if "pull_request" not in issue and marker in (issue.get("body") or ""):
                    if payload_marker not in (issue.get("body") or ""):
                        raise RuntimeError(
                            "Existing task has different ticket content. Inspect it manually."
                        )
                    return {
                        "status": "reused",
                        "url": issue["html_url"],
                        "number": issue["number"],
                    }
            if len(issues) < 100:
                break
        else:
            raise RuntimeError("Demo queue search limit reached; task not created.")
        checks = "\n".join(
            "- "
            + ("PASS" if c["passed"] else "REVIEW")
            + ": "
            + c["label"]
            + " — "
            + c["detail"]
            for c in result["checks"]
        )
        trace = "\n".join(
            str(i + 1) + ". " + row["step"] + ": " + row["detail"]
            for i, row in enumerate(result["trace"])
        )
        body = (
            marker + "\n" + payload_marker + "\n\n"
            "## Synthetic operations review\n\n"
            "This is a fictional test scenario, not a customer request.\n\n"
            "**Classifier:** " + result["classifier"] + "\n\n"
            "**Ticket:** " + ticket["ticket_id"] + "\n\n"
            "**Message:** " + ticket["message"] + "\n\n"
            "**Why a person is needed:** " + result["reason"] + "\n\n"
            "### Checks\n\n" + (checks or "No order-policy checks reached.") + "\n\n"
            "### Trace\n\n" + trace + "\n\n"
            "No email, refund or shipping label has been sent. A human decides the next step."
        )
        issue = self._request(
            "POST",
            "/issues",
            {
                "title": "ReturnOps review: "
                + ticket["ticket_id"]
                + " ("
                + result["mode"]
                + ")",
                "body": body,
            },
        )
        expected_prefix = "https://github.com/" + self.repository + "/issues/"
        if (
            not isinstance(issue, dict)
            or not isinstance(issue.get("number"), int)
            or not isinstance(issue.get("html_url"), str)
            or not issue["html_url"].startswith(expected_prefix)
        ):
            raise RuntimeError("GitHub task creation was not confirmed.")
        return {
            "status": "created",
            "url": issue["html_url"],
            "number": issue["number"],
        }
