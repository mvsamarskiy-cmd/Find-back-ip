#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "ops" / "railway-production.json"
RAILWAY_GRAPHQL = "https://backboard.railway.com/graphql/v2"

WORKSPACE_AUDIT = """
query WorkspaceAudit($workspaceId: String!) {
  workspace(workspaceId: $workspaceId) {
    id
    name
    projects(first: 100) {
      edges { node {
        id
        name
        buckets(first: 20) { edges { node { id name parentServiceId } } }
        environments(first: 20) {
          edges { node {
            id
            name
            isEphemeral
            variables(first: 100) { edges { node { name serviceId isSealed } } }
            volumeInstances(first: 20) {
              edges { node { id serviceId mountPath currentSizeMB state } }
            }
            serviceInstances(first: 20) {
              edges { node {
                serviceId
                serviceName
                source { repo image }
                domains {
                  serviceDomains { domain }
                  customDomains { domain }
                }
                latestDeployment { id status createdAt deploymentStopped }
              } }
            }
          } }
        }
      } }
    }
  }
}
"""


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def edges(connection):
    return [edge["node"] for edge in (connection or {}).get("edges", [])]


def project_services(project):
    for environment in edges(project.get("environments")):
        for service in edges(environment.get("serviceInstances")):
            yield environment, service


def project_inventory(project):
    environments = edges(project.get("environments"))
    services = []
    variables = []
    volumes = []
    custom_domains = []
    railway_domains = []

    for environment in environments:
        variables.extend(node["name"] for node in edges(environment.get("variables")))
        volumes.extend(edges(environment.get("volumeInstances")))
        for service in edges(environment.get("serviceInstances")):
            source = service.get("source") or {}
            domains = service.get("domains") or {}
            services.append({
                "id": service.get("serviceId"),
                "name": service.get("serviceName"),
                "repo": source.get("repo"),
                "status": (service.get("latestDeployment") or {}).get("status"),
            })
            custom_domains.extend(
                item["domain"] for item in domains.get("customDomains", [])
            )
            railway_domains.extend(
                item["domain"] for item in domains.get("serviceDomains", [])
            )

    return {
        "projectId": project.get("id"),
        "projectName": project.get("name"),
        "services": services,
        "variableNames": sorted(set(variables)),
        "volumeCount": len(volumes),
        "bucketCount": len(edges(project.get("buckets"))),
        "customDomains": sorted(set(custom_domains)),
        "railwayDomains": sorted(set(railway_domains)),
    }


def analyze_workspace(payload, manifest):
    workspace = payload["workspace"]
    repository = manifest["repository"]
    canonical_id = manifest["project"]["id"]
    attached = []

    for project in edges(workspace.get("projects")):
        if any(
            (service.get("source") or {}).get("repo") == repository
            for _, service in project_services(project)
        ):
            attached.append(project_inventory(project))

    canonical = next(
        (item for item in attached if item["projectId"] == canonical_id), None
    )
    shadows = [item for item in attached if item["projectId"] != canonical_id]
    for item in shadows:
        item["deletionSafety"] = {
            "noVariables": not item["variableNames"],
            "noVolumes": item["volumeCount"] == 0,
            "noBuckets": item["bucketCount"] == 0,
            "noCustomDomains": not item["customDomains"],
            "onlyCanonicalRepo": all(
                service["repo"] == repository for service in item["services"]
            ),
        }

    return {
        "workspaceId": workspace.get("id"),
        "workspaceName": workspace.get("name"),
        "canonical": canonical,
        "shadows": shadows,
    }


def graphql_request(token, manifest):
    body = json.dumps({
        "query": WORKSPACE_AUDIT,
        "variables": {"workspaceId": manifest["workspace"]["id"]},
    }).encode("utf-8")
    request = urllib.request.Request(
        RAILWAY_GRAPHQL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "NameMachine-Railway-Guard/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        messages = "; ".join(item.get("message", "GraphQL error") for item in payload["errors"])
        raise RuntimeError(messages)
    return payload["data"]


def command_show(manifest):
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


def command_link(manifest):
    railway = shutil.which("railway")
    if not railway:
        raise SystemExit("Railway CLI is required: https://docs.railway.com/cli")
    command = [
        railway,
        "link",
        "--project", manifest["project"]["id"],
        "--environment", manifest["environment"]["id"],
        "--service", manifest["service"]["id"],
        "--json",
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    print("Linked Railway CLI to the canonical production target.")


def get_url(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "NameMachine-release-guard/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, response.headers.get_content_type(), response.read()


def command_smoke(manifest):
    base = manifest["productionUrl"].rstrip("/")
    root_status, root_type, root_body = get_url(f"{base}/")
    health_status, health_type, health_body = get_url(
        f"{base}{manifest['healthPath']}"
    )
    health = json.loads(health_body)
    if root_status != 200 or root_type != "text/html":
        raise SystemExit(f"Root smoke failed: HTTP {root_status}, {root_type}")
    if b"NameMachine" not in root_body:
        raise SystemExit("Root smoke failed: NameMachine marker missing")
    if health_status != 200 or health_type != "application/json":
        raise SystemExit(f"Health smoke failed: HTTP {health_status}, {health_type}")
    if health != {"status": "ok"}:
        raise SystemExit(f"Unexpected health response: {health!r}")
    print(json.dumps({
        "root": {"status": root_status, "contentType": root_type},
        "health": {"status": health_status, "body": health},
        "target": base,
    }, indent=2))


def command_audit(manifest):
    token = os.environ.get("RAILWAY_API_TOKEN")
    if not token:
        raise SystemExit("RAILWAY_API_TOKEN is required for the workspace audit")
    report = analyze_workspace(graphql_request(token, manifest), manifest)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["canonical"]:
        raise SystemExit("Canonical Railway project was not found")
    if report["shadows"]:
        raise SystemExit(f"Found {len(report['shadows'])} shadow Railway project(s)")
    print("No shadow Railway projects are attached to the repository.")


def main():
    parser = argparse.ArgumentParser(description="Guard NameMachine's Railway target")
    parser.add_argument("command", choices=("show", "link", "smoke", "audit"))
    args = parser.parse_args()
    manifest = load_manifest()
    commands = {
        "show": command_show,
        "link": command_link,
        "smoke": command_smoke,
        "audit": command_audit,
    }
    try:
        commands[args.command](manifest)
    except urllib.error.HTTPError as error:
        raise SystemExit(f"Railway/HTTP request failed: HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise SystemExit(f"Railway/HTTP request failed: {error.reason}") from error
    except (json.JSONDecodeError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
