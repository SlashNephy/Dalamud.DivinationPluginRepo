import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from zipfile import ZipFile

PROVIDER = os.getenv("PROVIDER", "dl.horoscope.dev")
USER_AGENT = os.getenv("USER_AGENT", "Dalamud.DivinationPluginRepo (+https://github.com/horoscope-dev/Dalamud.DivinationPluginRepo)")
SOURCE = os.getenv("SOURCE")

def extract_manifests(env):
    manifests = {}
    for dirpath, _, filenames in os.walk(f"dist/{env}"):
        if "latest.zip" not in filenames:
            continue

        with ZipFile(f"{dirpath}/latest.zip") as z:
            plugin_name = dirpath.split("/")[-1]
            manifest = json.loads(z.read(f"{plugin_name}.json").decode())
            manifests[manifest["InternalName"]] = manifest

    return manifests

def get_download_stats():
    try:
        request = urllib.request.Request(f"https://{PROVIDER}/statistics", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request) as response:
            return json.load(response)
    except urllib.error.HTTPError:
        return {}
    except urllib.error.URLError:
        return {}

def get_mtime_or_default(path):
    if not os.path.exists(path):
        return 0

    return int(os.path.getmtime(path))

def merge_manifests(stable, testing, downloads):
    manifest_keys = set(list(stable.keys()) + list(testing.keys()))
    query = f"?source={SOURCE}" if SOURCE else ""

    manifests = []
    for key in manifest_keys:
        stable_manifest = stable.get(key, {})
        stable_latest_zip = f"dist/stable/{key}/latest.zip"
        stable_link = f"https://{PROVIDER}/stable/{key}{query}"
        testing_manifest = testing.get(key, {})
        testing_latest_zip = f"dist/testing/{key}/latest.zip"
        testing_link = f"https://{PROVIDER}/testing/{key}{query}"

        manifest = testing_manifest.copy() if testing_manifest else stable_manifest.copy()

        manifest["IsHide"] = testing_manifest.get("IsHide", stable_manifest.get("IsHide", False))
        manifest["AssemblyVersion"] = stable_manifest["AssemblyVersion"] if stable_manifest else testing_manifest["AssemblyVersion"]
        manifest["TestingAssemblyVersion"] = testing_manifest["AssemblyVersion"] if testing_manifest else None
        manifest["IsTestingExclusive"] = not bool(stable_manifest) and bool(testing_manifest)
        manifest["DownloadCount"] = downloads.get(key, 0)
        manifest["LastUpdated"] = max(get_mtime_or_default(stable_latest_zip), get_mtime_or_default(testing_latest_zip))
        manifest["DownloadLinkInstall"] = stable_link if stable_manifest else testing_link
        manifest["DownloadLinkTesting"] = testing_link if testing_manifest else stable_link

        manifests.append(manifest)

    return manifests

def dump_master(manifests):
    manifests.sort(key=lambda x: x["InternalName"])

    with open("dist/pluginmaster.json", "w") as f:
        json.dump(manifests, f, indent=2, sort_keys=True)

def generate_markdown(manifests, downloads):
    lines = [
        "# Dalamud.Divination Plugins",
        "",
        "## Legend",
        "",
        "⚠️ = Testing/very experimental plugin. May cause game crashes and other inconveniences.",
        "",
        "## Plugin List",
        "",
        "| Name | Version | Author | Description | Downloads |",
        "|:-----|:-------:|:------:|:------------|----------:|"
    ]

    jst = timezone(timedelta(hours=9))

    for manifest in manifests:
        if manifest["IsHide"]:
            continue

        name = f"[{manifest['Name']}]({manifest['RepoUrl']})"

        stable_version = f"**[{manifest['AssemblyVersion']}]({manifest['DownloadLinkInstall']})**" if manifest["DownloadLinkInstall"] != manifest["DownloadLinkTesting"] else "-"
        testing_version = f"⚠️ [{manifest['TestingAssemblyVersion']}]({manifest['DownloadLinkTesting']})" if manifest["TestingAssemblyVersion"] else "-"
        last_updated = datetime.fromtimestamp(manifest["LastUpdated"], tz=jst).strftime("%Y-%m-%d")
        version = f"{stable_version} / {testing_version} ({last_updated})"

        author = manifest["Author"]

        tags = [fr"**\#{x}**" for x in manifest.get("CategoryTags", []) + manifest.get("Tags", [])]
        description = f"{manifest.get('Punchline', '-')}<br>{manifest.get('Description', '-')}<br>{' '.join(tags)}"

        total_downloads = downloads.get(manifest["InternalName"], "n/a")

        lines.append(f"| {name} | {version} | {author} | {description} | {total_downloads} |")

    with open("dist/README.md", "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    stable = extract_manifests("stable")
    testing = extract_manifests("testing")
    downloads = get_download_stats()

    manifests = merge_manifests(stable, testing, downloads)
    dump_master(manifests)

    generate_markdown(manifests, downloads)
