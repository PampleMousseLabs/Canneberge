"""
export_issues.py
Usage: penguin: cd ~/PampleMousseLabs/ProjectCanneberge/4_application python export_issues.py PampleMousseLabs ProjectCanneberge
"""
import sys
import json
import urllib.request

def main():
    if len(sys.argv) < 3:
        print("Usage: python export_issues.py <owner> <repo> [github_token]")
        sys.exit(1)

    owner = sys.argv[1]
    repo = sys.argv[2]
    token = sys.argv[3] if len(sys.argv) > 3 else None

    url = f"https://api.github.com/repos/{owner}/{repo}/issues?state=open&per_page=100"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Python-Urllib")
    req.add_header("Accept", "application/vnd.github.v3+json")
    if token:
        req.add_header("Authorization", f"token {token}")

    try:
        with urllib.request.urlopen(req) as response:
            issues = json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching issues: {e}")
        sys.exit(1)

    out_path = "issues_audit.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Open Issues Audit: {owner}/{repo}\n\n")
        count = 0
        for issue in issues:
            # GitHub API returns pull requests under the 'issues' endpoint, skip them
            if "pull_request" in issue:
                continue
            count += 1
            f.write(f"## #{issue['number']}: {issue['title']}\n")
            f.write(f"- **State:** {issue['state']}\n")
            f.write(f"- **URL:** {issue['html_url']}\n\n")
            f.write("### Description\n")
            body = issue.get("body") or "*No description provided.*"
            f.write(f"{body}\n\n")
            f.write("---\n\n")
            
    print(f"Successfully exported {count} open issues to {out_path}")

if __name__ == "__main__":
    main()